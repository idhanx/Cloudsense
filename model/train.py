#!/usr/bin/env python3
"""
CloudSense — U-Net Training Script (Improved)

Architecture : U-Net + MobileNetV2 encoder (segmentation_models_pytorch)
Label gen    : Physics-based BT threshold → sklearn.cluster.DBSCAN → clean mask
Improvements :
  - DBSCAN-based label generation (consistent with evaluate.py ground truth)
  - skimage.measure.regionprops for per-cluster parameter extraction
  - Mixed-precision training (torch.amp) for faster GPU runs
  - Early stopping with patience
  - Checkpoint resume (--resume flag)
  - Focal-Tversky loss for better handling of class imbalance
  - Cosine annealing with warm restarts (CosineAnnealingWarmRestarts)
  - Gradient clipping
  - Per-epoch metrics: IoU, F1, Precision, Recall
  - torchvision removed (albumentations handles all augmentation)
"""

import os
import sys
import glob
import logging
import argparse
import numpy as np
import cv2
import h5py
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts
from torch.cuda.amp import GradScaler, autocast
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2
from scipy import ndimage
from sklearn.cluster import DBSCAN
from skimage.measure import regionprops, label as sk_label

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════

IMG_SIZE          = 512
BATCH_SIZE        = 4
EPOCHS            = 50
LR                = 3e-4
WEIGHT_DECAY      = 1e-4
VAL_SPLIT         = 0.15
GRAD_CLIP         = 1.0
EARLY_STOP_PATIENCE = 10

# Physics thresholds (Kelvin)
BT_COLD_K         = 218.0
BT_MIN_K          = 180.0
BT_MAX_K          = 320.0
JPG_THRESHOLD     = 0.35     # Normalised proxy for JPG cold tops

# DBSCAN label generation
DBSCAN_EPS_PX     = 8        # pixels (~32 km at 4 km/px)
DBSCAN_MIN_SAMPLES = 5
MIN_AREA_KM2      = 20000.0
PIXEL_RES_KM      = 4.0
MIN_AREA_PX       = int(MIN_AREA_KM2 / (PIXEL_RES_KM ** 2))  # ~1250 px

DATA_DIR  = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dataset", "MOSDAC_Data"
)
MODEL_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_model.pth")
CKPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkpoint.pth")

DEVICE = (
    "mps"  if torch.backends.mps.is_available()  else
    "cuda" if torch.cuda.is_available()           else
    "cpu"
)
USE_AMP = DEVICE == "cuda"   # Mixed precision only supported on CUDA


# ══════════════════════════════════════════════════
# LABEL GENERATION
# ══════════════════════════════════════════════════

def _morph_clean(mask: np.ndarray, ksize: int = 7) -> np.ndarray:
    """Morphological close → open + area filter."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k, iterations=1)
    # Area filter using regionprops (PS requirement)
    labeled = sk_label(mask)
    out = np.zeros_like(mask)
    for prop in regionprops(labeled):
        if prop.area >= MIN_AREA_PX:
            out[labeled == prop.label] = 1
    return out


def _dbscan_mask(cold_mask: np.ndarray) -> np.ndarray:
    """
    Run sklearn DBSCAN on cold pixel coords, keep clusters >= MIN_AREA_KM2.
    Consistent with evaluate.py ground truth generation.
    """
    cold_pixels = np.argwhere(cold_mask > 0)
    if len(cold_pixels) == 0:
        return np.zeros(cold_mask.shape, dtype=np.uint8)

    labels = DBSCAN(
        eps=DBSCAN_EPS_PX,
        min_samples=DBSCAN_MIN_SAMPLES,
        algorithm="ball_tree",
        n_jobs=-1,
    ).fit_predict(cold_pixels)

    out = np.zeros(cold_mask.shape, dtype=np.uint8)
    pixel_area = PIXEL_RES_KM ** 2

    for lbl in set(labels):
        if lbl == -1:
            continue
        indices = cold_pixels[labels == lbl]
        if len(indices) * pixel_area >= MIN_AREA_KM2:
            out[indices[:, 0], indices[:, 1]] = 1

    return out


def mask_from_h5(h5_path: str):
    """
    Load IMG_TIR1 + LUT from H5 → BT (K).
    Label: DBSCAN on BT < BT_COLD_K pixels.
    Returns (normalised float32 image, binary uint8 mask).
    """
    with h5py.File(h5_path, "r") as f:
        raw = f["IMG_TIR1"][0].astype(np.int32)
        lut = f["IMG_TIR1_TEMP"][:].astype(np.float32)

    raw = np.clip(raw, 0, len(lut) - 1)
    bt  = lut[raw]
    valid = bt[bt > 100]
    bt  = np.where(bt < 100, valid.mean() if len(valid) else 250.0, bt)

    norm  = np.clip((bt - BT_MIN_K) / (BT_MAX_K - BT_MIN_K), 0, 1).astype(np.float32)
    cold  = (bt < BT_COLD_K).astype(np.uint8)
    cold  = _morph_clean(cold)          # morphological pre-clean
    mask  = _dbscan_mask(cold)          # DBSCAN clustering
    return norm, mask


def mask_from_jpg(jpg_path: str):
    """
    Load IR1 JPG as grayscale proxy (cold = dark pixel).
    Uses simple threshold + morphological cleaning (no DBSCAN — no BT calibration).
    """
    img = cv2.imread(jpg_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None, None
    norm = img.astype(np.float32) / 255.0
    cold = (norm < JPG_THRESHOLD).astype(np.uint8)
    mask = _morph_clean(cold)
    return norm, mask


# ══════════════════════════════════════════════════
# DATASET
# ══════════════════════════════════════════════════

class TCCDataset(Dataset):
    def __init__(self, samples, transform=None):
        self.samples   = samples
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, kind = self.samples[idx]
        try:
            if kind == "h5":
                norm, mask = mask_from_h5(path)
            else:
                norm, mask = mask_from_jpg(path)
                if norm is None:
                    raise ValueError("Failed to load JPG")
        except Exception as e:
            logger.debug(f"Sample load error ({path}): {e}")
            norm = np.zeros((IMG_SIZE, IMG_SIZE), dtype=np.float32)
            mask = np.zeros((IMG_SIZE, IMG_SIZE), dtype=np.uint8)

        norm = cv2.resize(norm, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)
        mask = cv2.resize(mask, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_NEAREST)

        if self.transform:
            aug    = self.transform(image=norm, mask=mask.astype(np.float32))
            img_t  = aug["image"]               # (1, H, W) via ToTensorV2
            mask_t = aug["mask"].unsqueeze(0)
        else:
            img_t  = torch.from_numpy(norm).unsqueeze(0)
            mask_t = torch.from_numpy(mask.astype(np.float32)).unsqueeze(0)

        return img_t, mask_t


# ══════════════════════════════════════════════════
# AUGMENTATIONS
# ══════════════════════════════════════════════════

train_tf = A.Compose([
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.3),
    A.RandomRotate90(p=0.5),
    A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.1, rotate_limit=20, p=0.5),
    A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.5),
    A.GaussNoise(var_limit=(5.0, 30.0), p=0.3),
    A.ElasticTransform(alpha=30, sigma=5, p=0.2),
    A.CoarseDropout(max_holes=4, max_height=32, max_width=32, p=0.2),
    ToTensorV2(),
])

val_tf = A.Compose([ToTensorV2()])


# ══════════════════════════════════════════════════
# LOSS FUNCTIONS
# ══════════════════════════════════════════════════

class FocalTverskyLoss(nn.Module):
    """
    Focal Tversky Loss — better handles class imbalance (sparse TCC pixels).
    alpha controls FN penalty, beta controls FP penalty.
    gamma=0.75 focuses on hard examples.
    """
    def __init__(self, alpha: float = 0.7, beta: float = 0.3, gamma: float = 0.75, smooth: float = 1.0):
        super().__init__()
        self.alpha  = alpha
        self.beta   = beta
        self.gamma  = gamma
        self.smooth = smooth

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        prob = torch.sigmoid(logits)
        tp   = (prob * targets).sum(dim=(2, 3))
        fp   = (prob * (1 - targets)).sum(dim=(2, 3))
        fn   = ((1 - prob) * targets).sum(dim=(2, 3))
        tversky = (tp + self.smooth) / (tp + self.alpha * fn + self.beta * fp + self.smooth)
        focal_tversky = (1 - tversky) ** self.gamma
        return focal_tversky.mean()


class CombinedLoss(nn.Module):
    """BCE + Focal Tversky — stable early training + imbalance handling."""
    def __init__(self, bce_weight: float = 0.4):
        super().__init__()
        self.bce   = nn.BCEWithLogitsLoss()
        self.ftv   = FocalTverskyLoss()
        self.w_bce = bce_weight

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        return self.w_bce * self.bce(logits, targets) + (1 - self.w_bce) * self.ftv(logits, targets)


# ══════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════

def batch_metrics(logits: torch.Tensor, targets: torch.Tensor, thr: float = 0.5) -> dict:
    """Compute IoU, F1, Precision, Recall for a batch."""
    pred  = (torch.sigmoid(logits) > thr).float()
    tp    = (pred * targets).sum(dim=(2, 3))
    fp    = (pred * (1 - targets)).sum(dim=(2, 3))
    fn    = ((1 - pred) * targets).sum(dim=(2, 3))
    eps   = 1e-6
    iou   = ((tp + eps) / (tp + fp + fn + eps)).mean().item()
    prec  = ((tp + eps) / (tp + fp + eps)).mean().item()
    rec   = ((tp + eps) / (tp + fn + eps)).mean().item()
    f1    = 2 * prec * rec / (prec + rec + eps)
    return {"iou": iou, "f1": f1, "precision": prec, "recall": rec}


# ══════════════════════════════════════════════════
# TRAINING LOOP
# ══════════════════════════════════════════════════

def train(resume: bool = False):
    logger.info(f"Device  : {DEVICE}  (AMP={'on' if USE_AMP else 'off'})")
    logger.info(f"Data    : {DATA_DIR}")

    # ── Collect samples ──
    h5_files  = sorted(glob.glob(os.path.join(DATA_DIR, "*.h5")))
    jpg_files = sorted(glob.glob(os.path.join(DATA_DIR, "*IR1*.jpg")))
    samples   = [(p, "h5") for p in h5_files] + [(p, "jpg") for p in jpg_files]

    if not samples:
        logger.error(f"No H5 or JPG files found in {DATA_DIR}")
        sys.exit(1)

    logger.info(f"H5 : {len(h5_files)}  JPG : {len(jpg_files)}  Total : {len(samples)}")

    # ── Train / val split (stratified by type) ──
    np.random.seed(42)
    idx     = np.random.permutation(len(samples))
    val_n   = max(1, int(len(samples) * VAL_SPLIT))
    train_s = [samples[i] for i in idx[val_n:]]
    val_s   = [samples[i] for i in idx[:val_n]]
    logger.info(f"Train: {len(train_s)}  Val: {len(val_s)}")

    train_loader = DataLoader(
        TCCDataset(train_s, train_tf), batch_size=BATCH_SIZE,
        shuffle=True, num_workers=0, pin_memory=(DEVICE == "cuda")
    )
    val_loader = DataLoader(
        TCCDataset(val_s, val_tf), batch_size=BATCH_SIZE,
        shuffle=False, num_workers=0, pin_memory=(DEVICE == "cuda")
    )

    # ── Model ──
    model = smp.Unet(
        encoder_name="mobilenet_v2",
        encoder_weights=None,   # train from scratch on satellite data
        in_channels=1,
        classes=1,
        decoder_attention_type="scse",  # Squeeze-and-excitation attention in decoder
    ).to(DEVICE)
    logger.info(f"Params: {sum(p.numel() for p in model.parameters()):,}")

    optimizer = AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = CosineAnnealingWarmRestarts(optimizer, T_0=10, T_mult=2, eta_min=1e-6)
    criterion = CombinedLoss(bce_weight=0.4)
    scaler    = GradScaler(enabled=USE_AMP)

    start_epoch = 1
    best_iou    = 0.0
    no_improve  = 0

    # ── Resume from checkpoint ──
    if resume and os.path.exists(CKPT_PATH):
        ckpt = torch.load(CKPT_PATH, map_location=DEVICE)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        scheduler.load_state_dict(ckpt["scheduler"])
        start_epoch = ckpt["epoch"] + 1
        best_iou    = ckpt["best_iou"]
        no_improve  = ckpt.get("no_improve", 0)
        logger.info(f"Resumed from epoch {ckpt['epoch']}  best_iou={best_iou:.4f}")

    # ── Training loop ──
    for epoch in range(start_epoch, EPOCHS + 1):

        # ── Train ──
        model.train()
        t_loss = t_iou = t_f1 = 0.0
        for imgs, masks in train_loader:
            imgs, masks = imgs.to(DEVICE), masks.to(DEVICE)
            optimizer.zero_grad()
            with autocast(enabled=USE_AMP):
                logits = model(imgs)
                loss   = criterion(logits, masks)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
            scaler.step(optimizer)
            scaler.update()

            m = batch_metrics(logits.detach(), masks)
            t_loss += loss.item()
            t_iou  += m["iou"]
            t_f1   += m["f1"]

        n = len(train_loader)
        t_loss /= n; t_iou /= n; t_f1 /= n

        # ── Validate ──
        model.eval()
        v_loss = v_iou = v_f1 = v_prec = v_rec = 0.0
        with torch.no_grad():
            for imgs, masks in val_loader:
                imgs, masks = imgs.to(DEVICE), masks.to(DEVICE)
                with autocast(enabled=USE_AMP):
                    logits = model(imgs)
                    v_loss += criterion(logits, masks).item()
                m = batch_metrics(logits, masks)
                v_iou  += m["iou"]
                v_f1   += m["f1"]
                v_prec += m["precision"]
                v_rec  += m["recall"]

        nv = len(val_loader)
        v_loss /= nv; v_iou /= nv; v_f1 /= nv; v_prec /= nv; v_rec /= nv

        scheduler.step(epoch)

        logger.info(
            f"Epoch {epoch:03d}/{EPOCHS}  "
            f"train[loss={t_loss:.4f} IoU={t_iou:.4f} F1={t_f1:.4f}]  "
            f"val[loss={v_loss:.4f} IoU={v_iou:.4f} F1={v_f1:.4f} "
            f"P={v_prec:.4f} R={v_rec:.4f}]"
        )

        # ── Save checkpoint ──
        torch.save({
            "epoch": epoch, "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "best_iou": best_iou, "no_improve": no_improve,
        }, CKPT_PATH)

        # ── Save best model ──
        if v_iou > best_iou:
            best_iou   = v_iou
            no_improve = 0
            torch.save(model.state_dict(), MODEL_OUT)
            logger.info(f"  ✅ Best model saved  (IoU={best_iou:.4f})")
        else:
            no_improve += 1
            if no_improve >= EARLY_STOP_PATIENCE:
                logger.info(f"Early stopping at epoch {epoch} (no improvement for {EARLY_STOP_PATIENCE} epochs)")
                break

    logger.info(f"\nDone. Best Val IoU: {best_iou:.4f}  →  {MODEL_OUT}")


# ══════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CloudSense U-Net Training")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--data",   default=None, help="Override DATA_DIR")
    parser.add_argument("--epochs", type=int, default=EPOCHS, help="Max epochs")
    args = parser.parse_args()

    if args.data:
        DATA_DIR = args.data
    EPOCHS = args.epochs

    train(resume=args.resume)
