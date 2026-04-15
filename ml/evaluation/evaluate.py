#!/usr/bin/env python3
"""
CloudSense — ML Model Evaluation Pipeline
Computes: Accuracy, Precision, Recall, F1, IoU, Confusion Matrix
Uses DBSCAN-generated ground truth masks from H5 files.
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
    confusion_matrix, classification_report
)
from scipy import ndimage
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import segmentation_models_pytorch as smp

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ──
IMG_SIZE = 512
BT_COLD_THRESHOLD = 218.0
MIN_BT = 180.0
MAX_BT = 320.0
MIN_AREA_KM2 = 20000.0
PIXEL_RESOLUTION_KM = 4.0
DBSCAN_EPS_PIXELS = 8
DBSCAN_MIN_SAMPLES = 5


def load_model(model_path: str, device: str):
    """Load trained U-Net model."""
    model = smp.Unet(encoder_name="mobilenet_v2", encoder_weights=None, in_channels=1, classes=1)
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model.to(device)
    model.eval()
    return model


def get_device():
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_h5_data(h5_path: str):
    """Load IRBT data from H5 file."""
    with h5py.File(h5_path, "r") as f:
        ir_candidates = ["IMG_TIR1", "TIR1", "IR", "IR1"]
        lut_candidates = ["IMG_TIR1_TEMP", "TIR1_TEMP", "LUT"]

        ir_dataset = None
        for name in ir_candidates:
            if name in f:
                ir_dataset = f[name]
                break
        if ir_dataset is None:
            for key in f.keys():
                if isinstance(f[key], h5py.Dataset) and len(f[key].shape) >= 2:
                    ir_dataset = f[key]
                    break
        if ir_dataset is None:
            raise ValueError(f"No IR data in {h5_path}")

        raw = ir_dataset[0] if len(ir_dataset.shape) == 3 else ir_dataset[:]

        lut_dataset = None
        for name in lut_candidates:
            if name in f:
                lut_dataset = f[name]
                break

        if lut_dataset is not None:
            lut = lut_dataset[:]
            raw = np.clip(raw, 0, len(lut) - 1)
            irbt = lut[raw].astype(np.float32)
        else:
            irbt = raw.astype(np.float32)

        irbt = np.where(irbt < 100, np.nan, irbt)
        irbt = np.nan_to_num(irbt, nan=np.nanmean(irbt) if not np.all(np.isnan(irbt)) else 250.0)

    return irbt


def generate_ground_truth_mask(irbt: np.ndarray) -> np.ndarray:
    """
    Generate ground truth mask using physics-based DBSCAN clustering.
    This is the same method used for training label generation.
    """
    from sklearn.cluster import DBSCAN

    # Apply BT threshold
    cold_mask = (irbt < BT_COLD_THRESHOLD).astype(np.uint8)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    cold_mask = cv2.morphologyEx(cold_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    cold_mask = cv2.morphologyEx(cold_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    # Get cold pixel coordinates
    cold_pixels = np.argwhere(cold_mask > 0)

    if len(cold_pixels) == 0:
        return np.zeros(irbt.shape, dtype=np.uint8)

    # Run DBSCAN on pixel coordinates
    clustering = DBSCAN(eps=DBSCAN_EPS_PIXELS, min_samples=DBSCAN_MIN_SAMPLES).fit(cold_pixels)

    gt_mask = np.zeros(irbt.shape, dtype=np.uint8)
    pixel_area = PIXEL_RESOLUTION_KM ** 2

    for label_id in set(clustering.labels_):
        if label_id == -1:
            continue  # Skip noise
        cluster_indices = cold_pixels[clustering.labels_ == label_id]
        area_km2 = len(cluster_indices) * pixel_area

        if area_km2 >= MIN_AREA_KM2:
            for y, x in cluster_indices:
                gt_mask[y, x] = 1

    return gt_mask


def predict_mask(model, irbt: np.ndarray, device: str) -> np.ndarray:
    """Run U-Net inference and return predicted binary mask at native resolution."""
    h, w = irbt.shape

    # Normalize
    normalized = (irbt - MIN_BT) / (MAX_BT - MIN_BT)
    normalized = np.clip(normalized, 0, 1).astype(np.float32)

    # Resize to model input
    resized = cv2.resize(normalized, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)
    tensor = torch.from_numpy(resized).unsqueeze(0).unsqueeze(0).float().to(device)

    # Inference
    with torch.no_grad():
        output = model(tensor)
        prob = torch.sigmoid(output).squeeze().cpu().numpy()

    # Resize back to native resolution
    prob_native = cv2.resize(prob, (w, h), interpolation=cv2.INTER_LINEAR)

    # Threshold
    binary = (prob_native > 0.5).astype(np.uint8)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=2)

    # Area filtering
    labeled, num_features = ndimage.label(cleaned)
    pixel_area = PIXEL_RESOLUTION_KM ** 2
    final = np.zeros_like(cleaned)
    for lid in range(1, num_features + 1):
        region = (labeled == lid)
        if np.sum(region) * pixel_area >= MIN_AREA_KM2:
            final[region] = 1

    return final


def compute_iou(pred: np.ndarray, gt: np.ndarray) -> float:
    """Intersection over Union."""
    intersection = np.sum((pred == 1) & (gt == 1))
    union = np.sum((pred == 1) | (gt == 1))
    if union == 0:
        return 1.0 if intersection == 0 else 0.0
    return float(intersection / union)


def compute_dice(pred: np.ndarray, gt: np.ndarray) -> float:
    """Dice coefficient (F1 for segmentation)."""
    intersection = np.sum((pred == 1) & (gt == 1))
    total = np.sum(pred == 1) + np.sum(gt == 1)
    if total == 0:
        return 1.0
    return float(2 * intersection / total)


def evaluate_on_dataset(model, h5_files: list, device: str, output_dir: str):
    """Evaluate model on a list of H5 files."""
    os.makedirs(output_dir, exist_ok=True)

    all_metrics = []
    all_pred_flat = []
    all_gt_flat = []

    for i, h5_path in enumerate(h5_files):
        fname = os.path.basename(h5_path)
        logger.info(f"[{i+1}/{len(h5_files)}] Evaluating: {fname}")

        try:
            irbt = load_h5_data(h5_path)
            gt_mask = generate_ground_truth_mask(irbt)
            pred_mask = predict_mask(model, irbt, device)

            # Flatten for sklearn metrics
            gt_flat = gt_mask.flatten()
            pred_flat = pred_mask.flatten()
            all_gt_flat.extend(gt_flat)
            all_pred_flat.extend(pred_flat)

            # Per-file metrics
            iou = compute_iou(pred_mask, gt_mask)
            dice = compute_dice(pred_mask, gt_mask)
            acc = accuracy_score(gt_flat, pred_flat)
            prec = precision_score(gt_flat, pred_flat, zero_division=0)
            rec = recall_score(gt_flat, pred_flat, zero_division=0)
            f1 = f1_score(gt_flat, pred_flat, zero_division=0)

            metrics = {
                "file": fname,
                "accuracy": round(acc, 4),
                "precision": round(prec, 4),
                "recall": round(rec, 4),
                "f1": round(f1, 4),
                "iou": round(iou, 4),
                "dice": round(dice, 4),
                "gt_positive_pixels": int(np.sum(gt_mask)),
                "pred_positive_pixels": int(np.sum(pred_mask)),
            }
            all_metrics.append(metrics)
            logger.info(f"  IoU={iou:.4f} | F1={f1:.4f} | Prec={prec:.4f} | Rec={rec:.4f}")

        except Exception as e:
            logger.error(f"  Error: {e}")
            all_metrics.append({"file": fname, "error": str(e)})

    # ── Aggregate Metrics ──
    all_gt_flat = np.array(all_gt_flat)
    all_pred_flat = np.array(all_pred_flat)

    agg = {
        "accuracy": round(accuracy_score(all_gt_flat, all_pred_flat), 4),
        "precision": round(precision_score(all_gt_flat, all_pred_flat, zero_division=0), 4),
        "recall": round(recall_score(all_gt_flat, all_pred_flat, zero_division=0), 4),
        "f1": round(f1_score(all_gt_flat, all_pred_flat, zero_division=0), 4),
        "iou": round(compute_iou(all_pred_flat, all_gt_flat), 4),
    }

    # ── Confusion Matrix ──
    cm = confusion_matrix(all_gt_flat, all_pred_flat)
    logger.info(f"\n{'='*60}")
    logger.info(f"AGGREGATE METRICS ({len(h5_files)} files)")
    logger.info(f"{'='*60}")
    logger.info(f"Accuracy:  {agg['accuracy']}")
    logger.info(f"Precision: {agg['precision']}")
    logger.info(f"Recall:    {agg['recall']}")
    logger.info(f"F1 Score:  {agg['f1']}")
    logger.info(f"IoU:       {agg['iou']}")
    logger.info(f"\nConfusion Matrix:")
    logger.info(f"  TN={cm[0][0]:,}  FP={cm[0][1]:,}")
    logger.info(f"  FN={cm[1][0]:,}  TP={cm[1][1]:,}")

    # ── Save Confusion Matrix Plot ──
    fig, ax = plt.subplots(1, 1, figsize=(6, 5))
    ax.imshow(cm, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i][j]:,}", ha="center", va="center", fontsize=14,
                    color="white" if cm[i][j] > cm.max()/2 else "black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Ground Truth")
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(["Background", "TCC"])
    ax.set_yticklabels(["Background", "TCC"])
    ax.set_title("Confusion Matrix")
    plt.tight_layout()
    cm_path = os.path.join(output_dir, "confusion_matrix.png")
    plt.savefig(cm_path, dpi=150)
    plt.close()
    logger.info(f"Saved: {cm_path}")

    # ── Save Results JSON ──
    results = {
        "timestamp": datetime.now().isoformat(),
        "model_info": {"architecture": "U-Net", "encoder": "MobileNetV2", "input_size": IMG_SIZE},
        "dataset_size": len(h5_files),
        "aggregate_metrics": agg,
        "confusion_matrix": {"TN": int(cm[0][0]), "FP": int(cm[0][1]), "FN": int(cm[1][0]), "TP": int(cm[1][1])},
        "per_file_metrics": all_metrics,
    }

    results_path = os.path.join(output_dir, "evaluation_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Saved: {results_path}")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="CloudSense Model Evaluation")
    parser.add_argument("--model", default=None, help="Path to model .pth file")
    parser.add_argument("--data", default=None, help="Directory containing H5 files")
    parser.add_argument("--output", default="./evaluation_output", help="Output directory")
    parser.add_argument("--max-files", type=int, default=None, help="Max files to evaluate")
    args = parser.parse_args()

    # Find model
    model_path = args.model
    if model_path is None:
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "best_model.pth"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model", "best_model.pth"),
        ]
        for c in candidates:
            if os.path.exists(c):
                model_path = c
                break
    if model_path is None or not os.path.exists(model_path):
        logger.error("Model not found. Use --model <path>")
        sys.exit(1)

    # Find data
    data_dir = args.data
    if data_dir is None:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset", "MOSDAC_Data")
    if not os.path.exists(data_dir):
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)

    h5_files = sorted([
        os.path.join(data_dir, f) for f in os.listdir(data_dir)
        if f.endswith(".h5")
    ])

    if args.max_files:
        h5_files = h5_files[:args.max_files]

    if not h5_files:
        logger.error("No H5 files found")
        sys.exit(1)

    logger.info(f"Model: {model_path}")
    logger.info(f"Dataset: {data_dir} ({len(h5_files)} files)")
    logger.info(f"Device: {get_device()}")

    device = get_device()
    model = load_model(model_path, device)
    evaluate_on_dataset(model, h5_files, device, args.output)


if __name__ == "__main__":
    main()
