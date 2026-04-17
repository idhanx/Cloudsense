#!/usr/bin/env python3
"""
CloudSense — ML Model Evaluation Pipeline (Improved)

Computes: Accuracy, Precision, Recall, F1, IoU, Dice, PR curve, Confusion Matrix
Ground truth: DBSCAN on physics-based BT threshold (consistent with training)
Parameter extraction: skimage.measure.regionprops (PS requirement)
"""

import os
import sys
import numpy as np
import h5py
import torch
import cv2
import json
import logging
from datetime import datetime
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, precision_recall_curve, average_precision_score,
)
from sklearn.cluster import DBSCAN
from scipy import ndimage
from skimage.measure import regionprops, label as sk_label
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import segmentation_models_pytorch as smp

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Constants (must match training) ──
IMG_SIZE           = 512
BT_COLD_THRESHOLD  = 218.0
MIN_BT             = 180.0
MAX_BT             = 320.0
MIN_AREA_KM2       = 20000.0
PIXEL_RESOLUTION_KM = 4.0
DBSCAN_EPS_PIXELS  = 8
DBSCAN_MIN_SAMPLES = 5
MIN_AREA_PX        = int(MIN_AREA_KM2 / (PIXEL_RESOLUTION_KM ** 2))


# ══════════════════════════════════════════════════
# MODEL
# ══════════════════════════════════════════════════

def get_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(model_path: str, device: str) -> smp.Unet:
    model = smp.Unet(
        encoder_name="mobilenet_v2",
        encoder_weights=None,
        in_channels=1,
        classes=1,
        decoder_attention_type="scse",
    )
    state = torch.load(model_path, map_location=device, weights_only=True)
    # Support models saved without scse (backward compat — ignore missing keys)
    model.load_state_dict(state, strict=False)
    model.to(device)
    model.eval()
    return model


# ══════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════

def load_h5_data(h5_path: str) -> np.ndarray:
    """Load IRBT from H5 with LUT conversion."""
    with h5py.File(h5_path, "r") as f:
        ir_keys = ["IMG_TIR1", "TIR1", "IR", "IR1"]
        lut_keys = ["IMG_TIR1_TEMP", "TIR1_TEMP", "LUT"]

        ir_ds = next((f[k] for k in ir_keys if k in f), None)
        if ir_ds is None:
            ir_ds = next(
                (f[k] for k in f if isinstance(f[k], h5py.Dataset) and len(f[k].shape) >= 2),
                None
            )
        if ir_ds is None:
            raise ValueError(f"No IR data in {h5_path}")

        raw = ir_ds[0] if len(ir_ds.shape) == 3 else ir_ds[:]

        lut_ds = next((f[k] for k in lut_keys if k in f), None)
        if lut_ds is not None:
            lut  = lut_ds[:]
            raw  = np.clip(raw, 0, len(lut) - 1)
            irbt = lut[raw].astype(np.float32)
        else:
            irbt = raw.astype(np.float32)

        irbt = np.where(irbt < 100, np.nan, irbt)
        fill = np.nanmean(irbt) if not np.all(np.isnan(irbt)) else 250.0
        irbt = np.nan_to_num(irbt, nan=fill)

    return irbt


# ══════════════════════════════════════════════════
# GROUND TRUTH GENERATION
# ══════════════════════════════════════════════════

def generate_ground_truth_mask(irbt: np.ndarray) -> np.ndarray:
    """
    Physics-based BT threshold → morphological clean → DBSCAN.
    Identical pipeline to model/train.py for fair evaluation.
    """
    cold = (irbt < BT_COLD_THRESHOLD).astype(np.uint8)

    # Morphological clean
    k     = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cold  = cv2.morphologyEx(cold, cv2.MORPH_CLOSE, k, iterations=2)
    cold  = cv2.morphologyEx(cold, cv2.MORPH_OPEN,  k, iterations=1)

    cold_pixels = np.argwhere(cold > 0)
    if len(cold_pixels) == 0:
        return np.zeros(irbt.shape, dtype=np.uint8)

    labels = DBSCAN(
        eps=DBSCAN_EPS_PIXELS,
        min_samples=DBSCAN_MIN_SAMPLES,
        algorithm="ball_tree",
        n_jobs=-1,
    ).fit_predict(cold_pixels)

    gt = np.zeros(irbt.shape, dtype=np.uint8)
    px_area = PIXEL_RESOLUTION_KM ** 2

    for lbl in set(labels):
        if lbl == -1:
            continue
        idx = cold_pixels[labels == lbl]
        if len(idx) * px_area >= MIN_AREA_KM2:
            gt[idx[:, 0], idx[:, 1]] = 1

    return gt


# ══════════════════════════════════════════════════
# INFERENCE
# ══════════════════════════════════════════════════

def predict_mask_and_prob(model, irbt: np.ndarray, device: str):
    """
    Run U-Net inference.
    Returns (binary_mask uint8, prob_map float32) both at native resolution.
    """
    h, w = irbt.shape

    norm    = np.clip((irbt - MIN_BT) / (MAX_BT - MIN_BT), 0, 1).astype(np.float32)
    resized = cv2.resize(norm, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)
    tensor  = torch.from_numpy(resized).unsqueeze(0).unsqueeze(0).float().to(device)

    with torch.no_grad():
        prob_512 = torch.sigmoid(model(tensor)).squeeze().cpu().numpy()

    prob_native = cv2.resize(prob_512, (w, h), interpolation=cv2.INTER_LINEAR)
    binary      = (prob_native > 0.5).astype(np.uint8)

    # Morphological cleanup
    k       = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN,  k, iterations=2)

    # Area filter
    labeled = sk_label(cleaned)
    final   = np.zeros_like(cleaned)
    for prop in regionprops(labeled):
        if prop.area * (PIXEL_RESOLUTION_KM ** 2) >= MIN_AREA_KM2:
            final[labeled == prop.label] = 1

    return final, prob_native


# ══════════════════════════════════════════════════
# PARAMETER EXTRACTION (regionprops — PS requirement)
# ══════════════════════════════════════════════════

def extract_cluster_params(mask: np.ndarray, irbt: np.ndarray) -> list:
    """
    Extract per-cluster parameters using skimage.measure.regionprops.
    Returns list of dicts matching the PS output specification.
    """
    labeled = sk_label(mask)
    clusters = []

    for prop in regionprops(labeled, intensity_image=irbt):
        y0, x0, y1, x1 = prop.bbox
        cy, cx = prop.centroid

        # BT statistics from the cluster region
        region_bt  = irbt[labeled == prop.label]
        min_bt     = float(np.min(region_bt))
        mean_bt    = float(np.mean(region_bt))
        median_bt  = float(np.median(region_bt))
        std_bt     = float(np.std(region_bt))

        # Coldest pixel (convective centre)
        coldest_idx = np.argmin(region_bt)
        ys, xs      = np.where(labeled == prop.label)
        conv_y      = int(ys[coldest_idx])
        conv_x      = int(xs[coldest_idx])

        # Radii from centroid to edge pixels (km)
        eroded      = cv2.erode((labeled == prop.label).astype(np.uint8), np.ones((3, 3), np.uint8))
        edge_mask   = (labeled == prop.label).astype(np.uint8) - eroded
        ey, ex      = np.where(edge_mask > 0)
        if len(ey) > 0:
            dy_km       = (ey - cy) * PIXEL_RESOLUTION_KM
            dx_km       = (ex - cx) * PIXEL_RESOLUTION_KM
            dists       = np.sqrt(dy_km ** 2 + dx_km ** 2)
            r_max       = float(np.max(dists))
            r_min       = float(np.min(dists[dists > 0])) if np.any(dists > 0) else float(np.min(dists))
            r_mean      = float(np.mean(dists))
        else:
            r_mean = r_max = r_min = float(np.sqrt(prop.area * (PIXEL_RESOLUTION_KM ** 2) / np.pi))

        # Cloud-top height (ISA: 288K surface, 6.5 K/km lapse rate)
        cloud_bt    = region_bt[region_bt < 280]
        if len(cloud_bt):
            cth_max  = float(max(0, (288.0 - np.min(cloud_bt))  / 6.5))
            cth_mean = float(max(0, (288.0 - np.mean(cloud_bt)) / 6.5))
        else:
            cth_max  = float(max(0, (288.0 - min_bt)  / 6.5))
            cth_mean = float(max(0, (288.0 - mean_bt) / 6.5))

        # Cold core ratio
        cold_px      = int(np.sum(region_bt < 235.0))
        cold_ratio   = cold_px / prop.area if prop.area > 0 else 0.0

        # regionprops geometric features
        area_km2     = prop.area * (PIXEL_RESOLUTION_KM ** 2)
        eccentricity = float(prop.eccentricity)
        orientation  = float(prop.orientation)  # radians
        solidity     = float(prop.solidity)

        clusters.append({
            "label":          int(prop.label),
            "area_km2":       float(area_km2),
            "pixel_count":    int(prop.area),
            "centroid_y":     float(cy),
            "centroid_x":     float(cx),
            "conv_y":         conv_y,
            "conv_x":         conv_x,
            "min_bt":         min_bt,
            "mean_bt":        mean_bt,
            "median_bt":      median_bt,
            "std_bt":         std_bt,
            "radius_max_km":  r_max,
            "radius_min_km":  r_min,
            "radius_mean_km": r_mean,
            "cth_max_km":     cth_max,
            "cth_mean_km":    cth_mean,
            "cold_core_ratio": float(cold_ratio),
            "eccentricity":   eccentricity,
            "orientation_rad": orientation,
            "solidity":       solidity,
        })

    return clusters


# ══════════════════════════════════════════════════
# METRICS
# ══════════════════════════════════════════════════

def compute_iou(pred: np.ndarray, gt: np.ndarray) -> float:
    inter = np.sum((pred == 1) & (gt == 1))
    union = np.sum((pred == 1) | (gt == 1))
    if union == 0:
        return 1.0 if inter == 0 else 0.0
    return float(inter / union)


def compute_dice(pred: np.ndarray, gt: np.ndarray) -> float:
    inter = np.sum((pred == 1) & (gt == 1))
    total = np.sum(pred == 1) + np.sum(gt == 1)
    if total == 0:
        return 1.0
    return float(2 * inter / total)


# ══════════════════════════════════════════════════
# PLOTS
# ══════════════════════════════════════════════════

def _plot_confusion_matrix(cm: np.ndarray, out_dir: str):
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.imshow(cm, cmap="Blues")
    labels = ["Background", "TCC"]
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i][j]:,}", ha="center", va="center",
                    fontsize=14, color="white" if cm[i][j] > cm.max() / 2 else "black")
    ax.set_xticks([0, 1]); ax.set_xticklabels(labels)
    ax.set_yticks([0, 1]); ax.set_yticklabels(labels)
    ax.set_xlabel("Predicted"); ax.set_ylabel("Ground Truth")
    ax.set_title("Confusion Matrix")
    plt.tight_layout()
    path = os.path.join(out_dir, "confusion_matrix.png")
    plt.savefig(path, dpi=150); plt.close()
    logger.info(f"Saved: {path}")


def _plot_pr_curve(prec_curve, rec_curve, ap: float, out_dir: str):
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(rec_curve, prec_curve, lw=2, color="steelblue", label=f"AP={ap:.3f}")
    ax.set_xlabel("Recall"); ax.set_ylabel("Precision")
    ax.set_title("Precision-Recall Curve")
    ax.legend(); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path = os.path.join(out_dir, "pr_curve.png")
    plt.savefig(path, dpi=150); plt.close()
    logger.info(f"Saved: {path}")


def _plot_metric_history(per_file: list, out_dir: str):
    """Bar chart of IoU per file."""
    names = [m["file"][:20] for m in per_file if "iou" in m]
    ious  = [m["iou"]       for m in per_file if "iou" in m]
    if not names:
        return
    fig, ax = plt.subplots(figsize=(max(8, len(names) * 0.6), 4))
    ax.bar(range(len(names)), ious, color="steelblue")
    ax.set_xticks(range(len(names))); ax.set_xticklabels(names, rotation=45, ha="right", fontsize=7)
    ax.set_ylabel("IoU"); ax.set_title("Per-File IoU")
    ax.axhline(np.mean(ious), color="red", lw=1.5, linestyle="--", label=f"mean={np.mean(ious):.3f}")
    ax.legend(); plt.tight_layout()
    path = os.path.join(out_dir, "per_file_iou.png")
    plt.savefig(path, dpi=150); plt.close()
    logger.info(f"Saved: {path}")


# ══════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════

def evaluate_on_dataset(model, h5_files: list, device: str, output_dir: str) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    all_metrics   = []
    all_pred_flat = []
    all_gt_flat   = []
    all_prob_flat = []   # for PR curve

    for i, h5_path in enumerate(h5_files):
        fname = os.path.basename(h5_path)
        logger.info(f"[{i+1}/{len(h5_files)}] {fname}")

        try:
            irbt     = load_h5_data(h5_path)
            gt_mask  = generate_ground_truth_mask(irbt)
            pred_mask, prob_map = predict_mask_and_prob(model, irbt, device)

            # Extract per-cluster params with regionprops
            pred_clusters = extract_cluster_params(pred_mask, irbt)
            gt_clusters   = extract_cluster_params(gt_mask,   irbt)

            gt_flat   = gt_mask.flatten().astype(np.uint8)
            pred_flat = pred_mask.flatten().astype(np.uint8)
            prob_flat = prob_map.flatten()

            all_gt_flat.extend(gt_flat)
            all_pred_flat.extend(pred_flat)
            all_prob_flat.extend(prob_flat)

            iou  = compute_iou(pred_mask, gt_mask)
            dice = compute_dice(pred_mask, gt_mask)
            acc  = accuracy_score(gt_flat, pred_flat)
            prec = precision_score(gt_flat, pred_flat, zero_division=0)
            rec  = recall_score(gt_flat, pred_flat, zero_division=0)
            f1   = f1_score(gt_flat, pred_flat, zero_division=0)

            file_metrics = {
                "file":                  fname,
                "accuracy":              round(acc,  4),
                "precision":             round(prec, 4),
                "recall":                round(rec,  4),
                "f1":                    round(f1,   4),
                "iou":                   round(iou,  4),
                "dice":                  round(dice, 4),
                "gt_clusters":           len(gt_clusters),
                "pred_clusters":         len(pred_clusters),
                "gt_positive_pixels":    int(np.sum(gt_mask)),
                "pred_positive_pixels":  int(np.sum(pred_mask)),
                "pred_cluster_params":   pred_clusters,
            }
            all_metrics.append(file_metrics)
            logger.info(f"  IoU={iou:.4f} F1={f1:.4f} P={prec:.4f} R={rec:.4f}  "
                        f"GT clusters={len(gt_clusters)} Pred clusters={len(pred_clusters)}")

        except Exception as e:
            logger.error(f"  Error: {e}")
            all_metrics.append({"file": fname, "error": str(e)})

    # ── Aggregate metrics ──
    all_gt   = np.array(all_gt_flat,   dtype=np.uint8)
    all_pred = np.array(all_pred_flat, dtype=np.uint8)
    all_prob = np.array(all_prob_flat, dtype=np.float32)

    agg = {
        "accuracy":  round(accuracy_score(all_gt, all_pred), 4),
        "precision": round(precision_score(all_gt, all_pred, zero_division=0), 4),
        "recall":    round(recall_score(all_gt, all_pred, zero_division=0), 4),
        "f1":        round(f1_score(all_gt, all_pred, zero_division=0), 4),
        "iou":       round(compute_iou(all_pred, all_gt), 4),
        "dice":      round(compute_dice(all_pred, all_gt), 4),
    }

    # Average Precision (area under PR curve)
    prec_curve, rec_curve, _ = precision_recall_curve(all_gt, all_prob)
    ap = float(average_precision_score(all_gt, all_prob))
    agg["average_precision"] = round(ap, 4)

    cm = confusion_matrix(all_gt, all_pred)

    logger.info(f"\n{'='*60}")
    logger.info(f"AGGREGATE ({len(h5_files)} files)")
    logger.info(f"{'='*60}")
    for k, v in agg.items():
        logger.info(f"  {k:22s}: {v}")
    logger.info(f"\n  Confusion Matrix:")
    logger.info(f"    TN={cm[0][0]:,}  FP={cm[0][1]:,}")
    logger.info(f"    FN={cm[1][0]:,}  TP={cm[1][1]:,}")

    # ── Plots ──
    _plot_confusion_matrix(cm, output_dir)
    _plot_pr_curve(prec_curve, rec_curve, ap, output_dir)
    _plot_metric_history(all_metrics, output_dir)

    # ── Save JSON ──
    results = {
        "timestamp":         datetime.now().isoformat(),
        "model_info":        {"architecture": "U-Net+scse", "encoder": "MobileNetV2",
                              "input_size": IMG_SIZE, "label_method": "DBSCAN"},
        "dataset_size":      len(h5_files),
        "aggregate_metrics": agg,
        "confusion_matrix":  {
            "TN": int(cm[0][0]), "FP": int(cm[0][1]),
            "FN": int(cm[1][0]), "TP": int(cm[1][1]),
        },
        "per_file_metrics":  all_metrics,
    }

    out_path = os.path.join(output_dir, "evaluation_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    logger.info(f"Saved: {out_path}")

    return results


# ══════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="CloudSense Model Evaluation")
    parser.add_argument("--model",     default=None, help="Path to .pth file")
    parser.add_argument("--data",      default=None, help="Directory with H5 files")
    parser.add_argument("--output",    default="./evaluation_output")
    parser.add_argument("--max-files", type=int, default=None)
    args = parser.parse_args()

    # Find model
    model_path = args.model
    if not model_path:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [
            os.path.join(here, "best_model.pth"),
            os.path.join(here, "..", "model", "best_model.pth"),
            os.path.join(here, "..", "..", "model", "best_model.pth"),
        ]
        model_path = next((c for c in candidates if os.path.exists(c)), None)
    if not model_path or not os.path.exists(model_path):
        logger.error("Model not found. Use --model <path>")
        sys.exit(1)

    # Find data
    data_dir = args.data or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "dataset", "MOSDAC_Data"
    )
    if not os.path.exists(data_dir):
        logger.error(f"Data dir not found: {data_dir}")
        sys.exit(1)

    h5_files = sorted(f for f in [
        os.path.join(data_dir, fn) for fn in os.listdir(data_dir) if fn.endswith(".h5")
    ])
    if args.max_files:
        h5_files = h5_files[:args.max_files]
    if not h5_files:
        logger.error("No H5 files found")
        sys.exit(1)

    device = get_device()
    logger.info(f"Model : {model_path}")
    logger.info(f"Data  : {data_dir}  ({len(h5_files)} files)")
    logger.info(f"Device: {device}")

    model = load_model(model_path, device)
    evaluate_on_dataset(model, h5_files, device, args.output)


import argparse
if __name__ == "__main__":
    main()
