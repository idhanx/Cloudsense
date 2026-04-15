#!/usr/bin/env python3
"""
CloudSense — U-Net Training Script
Architecture : U-Net + MobileNetV2 encoder (segmentation_models_pytorch)
Primary data : INSAT-3DR H5 files  → IMG_TIR1 + IMG_TIR1_TEMP LUT → real BT (K)
Fallback data: IR1 JPG images       → grayscale proxy
Labels       : Auto-generated via physics-based BT thresholding (no manual annotation)
"""

import os, sys, glob, logging
import numpy as np
import cv2
import h5py
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import segmentation_models_pytorch as smp
from torch.optim import Adam
from torch.optim.lr_scheduler import CosineAnnealingLR
import albumentations as A
from albumentations.pytorch import ToTensorV2
from scipy import ndimage

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Config ──
IMG_SIZE        = 512
BATCH_SIZE      = 4
EPOCHS          = 30
LR              = 1e-4
VAL_SPLIT       = 0.15
# Physics thresholds (Kelvin)
BT_COLD_K       = 218.0     # TCC cloud-top threshold
BT_MIN_K        = 180.0     # Normalisation min
BT_MAX_K        = 320.0     # Normalisation max
# JPG proxy threshold (normalised 0-1; cold = dark in IR1)
JPG_THRESHOLD   = 0.35
MIN_AREA_PX     = 500       # Minimum cluster pixels after morphology

DATA_DIR  = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "dataset", "MOSDAC_Data")
MODEL_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_model.pth")
DEVICE    = ("mps"  if torch.backends.mps.is_available()  else
             "cuda" if torch.cuda.is_available()           else "cpu")


# ════════════════════════════════════════════════════════════
# Label generation
# ════════════════════════════════════════════════════════════

def _clean_mask(mask: np.ndarray) -> np.ndarray:
    """Morphological cleanup + area filter."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  k, iterations=1)
    labeled, n = ndimage.label(mask)
    out = np.zeros_like(mask)
    for lid in range(1, n + 1):
        region = (labeled == lid)
        if region.sum() >= MIN_AREA_PX:
            out[region] = 1
    return out


def mask_from_h5(h5_path: str):
    """
    Load IMG_TIR1 + LUT from H5, convert to BT (K),
    return (normalised_image float32, binary_mask uint8).
    """
    with h5py.File(h5_path, "r") as f:
        raw = f["IMG_TIR1"][0].astype(np.int32)          # (H, W)
        lut = f["IMG_TIR1_TEMP"][:].astype(np.float32)   # (1024,)

    raw  = np.clip(raw, 0, len(lut) - 1)
    bt   = lut[raw]                                        # BT in Kelvin
    bt   = np.where(bt < 100, np.nanmean(bt[bt > 100]) if (bt > 100).any() else 250.0, bt)

    # Normalise to [0, 1]
    norm = (bt - BT_MIN_K) / (BT_MAX_K - BT_MIN_K)
    norm = np.clip(norm, 0, 1).astype(np.float32)

    # Mask: cold pixels below threshold
    cold = (bt < BT_COLD_K).astype(np.uint8)
    mask = _clean_mask(cold)

    return norm, mask


def mask_from_jpg(jpg_path: str):
    """
    Load IR1 JPG as grayscale proxy.
    Cold cloud tops appear DARK → threshold low values.
    """
    img = cv2.imread(jpg_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None, None
    norm = img.astype(np.float32) / 255.0
    cold = (norm < JPG_THRESHOLD).astype(np.uint8)
    mask = _clean_mask(cold)
    return norm, mask


# ════════════════════════════════════════════════════════════
# Dataset
# ════════════════════════════════════════════════════════════

class TCCDataset(Dataset):
    def __init__(self, samples, transform=None):
        """
        samples: list of (path, 'h5'|'jpg')
        """
        self.samples   = samples
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, kind = self.samples[idx]

        if kind == "h5":
            try:
                norm, mask = mask_from_h5(path)
            except Exception:
                norm = np.zeros((IMG_SIZE, IMG_SIZE), dtype=np.float32)
                mask = np.zeros((IMG_SIZE, IMG_SIZE), dtype=np.uint8)
        else:
            norm, mask = mask_from_jpg(path)
            if norm is None:
                norm = np.zeros((IMG_SIZE, IMG_SIZE), dtype=np.float32)
                mask = np.zeros((IMG_SIZE, IMG_SIZE), dtype=np.uint8)

        # Resize to model input size
        norm = cv2.resize(norm, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)
        mask = cv2.resize(mask, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_NEAREST)

        if self.transform:
            aug  = self.transform(image=norm, mask=mask.astype(np.float32))
            img_t  = aug["image"]          # (1, H, W) from ToTensorV2
            mask_t = aug["mask"].unsqueeze(0)
        else:
            img_t  = torch.from_numpy(norm).unsqueeze(0)
            mask_t = torch.from_numpy(mask.astype(np.float32)).unsqueeze(0)

        return img_t, mask_t


# ════════════════════════════════════════════════════════════
# Augmentations
# ════════════════════════════════════════════════════════════

train_tf = A.Compose([
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.3),
    A.RandomRotate90(p=0.5),
    A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.1, rotate_limit=15, p=0.4),
    A.RandomBrightnessContrast(brightness_limit=0.15, contrast_limit=0.15, p=0.4),
    A.GaussNoise(p=0.2),
    ToTensorV2(),
])

val_tf = A.Compose([ToTensorV2()])


# ════════════════════════════════════════════════════════════
# Loss & metric
# ════════════════════════════════════════════════════════════

class BCEDiceLoss(nn.Module):
    def __init__(self, w=0.5):
        super().__init__()
        self.bce = nn.BCEWithLogitsLoss()
        self.w   = w

    def forward(self, logits, targets):
        bce  = self.bce(logits, targets)
        prob = torch.sigmoid(logits)
        smooth = 1.0
        inter  = (prob * targets).sum(dim=(2, 3))
        dice   = 1 - (2 * inter + smooth) / (prob.sum(dim=(2, 3)) + targets.sum(dim=(2, 3)) + smooth)
        return self.w * bce + (1 - self.w) * dice.mean()


def iou_score(logits, targets, thr=0.5):
    pred  = (torch.sigmoid(logits) > thr).float()
    inter = (pred * targets).sum(dim=(2, 3))
    union = (pred + targets).clamp(0, 1).sum(dim=(2, 3))
    return ((inter + 1e-6) / (union + 1e-6)).mean().item()


# ════════════════════════════════════════════════════════════
# Main training
# ════════════════════════════════════════════════════════════

def train():
    logger.info(f"Device : {DEVICE}")
    logger.info(f"Data   : {DATA_DIR}")

    # Collect samples — H5 files preferred, IR1 JPGs as supplement
    h5_files  = sorted(glob.glob(os.path.join(DATA_DIR, "*.h5")))
    jpg_files = sorted(glob.glob(os.path.join(DATA_DIR, "*IR1*.jpg")))

    samples = [(p, "h5")  for p in h5_files] + \
              [(p, "jpg") for p in jpg_files]

    if not samples:
        logger.error(f"No H5 or JPG files found in {DATA_DIR}")
        sys.exit(1)

    logger.info(f"H5 files : {len(h5_files)}")
    logger.info(f"JPG files: {len(jpg_files)}")
    logger.info(f"Total    : {len(samples)} samples")

    # Train / val split
    np.random.seed(42)
    idx      = np.random.permutation(len(samples))
    val_n    = max(1, int(len(samples) * VAL_SPLIT))
    val_idx  = idx[:val_n]
    train_idx= idx[val_n:]

    train_samples = [samples[i] for i in train_idx]
    val_samples   = [samples[i] for i in val_idx]
    logger.info(f"Train: {len(train_samples)} | Val: {len(val_samples)}")

    train_ds = TCCDataset(train_samples, transform=train_tf)
    val_ds   = TCCDataset(val_samples,   transform=val_tf)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,  num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    # U-Net + MobileNetV2 (no pretrained download — train from scratch on satellite data)
    logger.info("Building U-Net with MobileNetV2 encoder...")
    model = smp.Unet(
        encoder_name   = "mobilenet_v2",
        encoder_weights= None,
        in_channels    = 1,
        classes        = 1,
    ).to(DEVICE)
    logger.info(f"Model ready. Params: {sum(p.numel() for p in model.parameters()):,}")

    optimizer = Adam(model.parameters(), lr=LR, weight_decay=1e-5)
    scheduler = CosineAnnealingLR(optimizer, T_max=EPOCHS, eta_min=1e-6)
    criterion = BCEDiceLoss(w=0.5)

    best_iou = 0.0

    for epoch in range(1, EPOCHS + 1):
        # Train
        model.train()
        t_loss = 0.0
        for batch_idx, (imgs, masks) in enumerate(train_loader):
            imgs, masks = imgs.to(DEVICE), masks.to(DEVICE)
            optimizer.zero_grad()
            loss = criterion(model(imgs), masks)
            loss.backward()
            optimizer.step()
            t_loss += loss.item()
            if (batch_idx + 1) % 20 == 0 or (batch_idx + 1) == len(train_loader):
                logger.info(f"  Epoch {epoch:02d} batch {batch_idx+1}/{len(train_loader)}  loss={loss.item():.4f}")
        t_loss /= len(train_loader)

        # Validate
        model.eval()
        v_loss = v_iou = 0.0
        with torch.no_grad():
            for imgs, masks in val_loader:
                imgs, masks = imgs.to(DEVICE), masks.to(DEVICE)
                logits = model(imgs)
                v_loss += criterion(logits, masks).item()
                v_iou  += iou_score(logits, masks)
        v_loss /= len(val_loader)
        v_iou  /= len(val_loader)

        scheduler.step()
        logger.info(f"Epoch {epoch:02d}/{EPOCHS}  "
                    f"train_loss={t_loss:.4f}  val_loss={v_loss:.4f}  val_iou={v_iou:.4f}")

        if v_iou > best_iou:
            best_iou = v_iou
            torch.save(model.state_dict(), MODEL_OUT)
            logger.info(f"  ✅ Best model saved  (IoU={best_iou:.4f})")

    logger.info(f"\nDone. Best Val IoU: {best_iou:.4f}")
    logger.info(f"Model: {MODEL_OUT}")


if __name__ == "__main__":
    train()
