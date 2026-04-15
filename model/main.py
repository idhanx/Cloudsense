#!/usr/bin/env python3
"""
Main Orchestration Script - Tropical Cloud Cluster Detection System

Orchestrates the complete workflow:
1. Data Download (via MOSDAC API)
2. Label Generation
3. Model Training
4. Inference & Output Generation

Usage:
    python main.py --mode download    # Download data from MOSDAC
    python main.py --mode train       # Train model
    python main.py --mode infer       # Run inference on new data
    python main.py --mode full        # Complete pipeline
"""

import argparse
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

def load_config(config_path: str = "config.json") -> dict:
    """Load and validate configuration file."""
    
    if not os.path.exists(config_path):
        logger.error(f"Config file not found: {config_path}")
        logger.info("Run: cp config.template.json config.json")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Validate required sections
    required_keys = ["user_credentials", "search_parameters", "model_settings", "output_settings"]
    for key in required_keys:
        if key not in config:
            logger.error(f"Missing config section: {key}")
            sys.exit(1)
    
    logger.info(f"✓ Configuration loaded from {config_path}")
    return config


# ============================================================================
# WORKFLOW STAGES
# ============================================================================

def stage_download(config: dict):
    """Stage 1: Download INSAT-3D data from MOSDAC."""
    
    logger.info("\n" + "="*80)
    logger.info("STAGE 1: DATA DOWNLOAD")
    logger.info("="*80)
    
    try:
        # Import MOSDAC module
        sys.path.insert(0, "./backend/mosdac_engine")
        from mdapi import main as mosdac_main
        
        download_path = config["download_settings"]["download_path"]
        os.makedirs(download_path, exist_ok=True)
        
        logger.info(f"Downloading INSAT-3D data to: {download_path}")
        logger.info("⚠ Note: MOSDAC download requires valid credentials in config.json")
        
        # Run MOSDAC download
        # Note: mdapi.main() is designed to run standalone with config.json in cwd
        # For integration, we'd need to refactor mdapi to accept config as parameter
        
        logger.info("Running MOSDAC Data Download API...")
        # mosdac_main()  # Ensure config.json is in working directory
        
        logger.warning("TODO: Implement MOSDAC integration")
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        raise


def stage_label_generation(config: dict):
    """Stage 2: Generate labels from raw H5 data."""
    
    logger.info("\n" + "="*80)
    logger.info("STAGE 2: LABEL GENERATION")
    logger.info("="*80)
    
    try:
        sys.path.insert(0, "./model")
        
        dataset_root = config.get("search_parameters", {}).get("dataset_root", "./data/downloads")
        
        logger.info(f"Scanning dataset: {dataset_root}")
        logger.info("Generating training labels (masks)...")
        
        # This would call generate_labels.py logic
        logger.warning("TODO: Implement label generation pipeline")
        
    except Exception as e:
        logger.error(f"Label generation failed: {e}")
        raise


def stage_training(config: dict):
    """Stage 3: Train U-Net model."""
    
    logger.info("\n" + "="*80)
    logger.info("STAGE 3: MODEL TRAINING")
    logger.info("="*80)
    
    try:
        sys.path.insert(0, "./model")
        from train_model_clean import train_model
        
        dataset_index = config.get("training_data_path", "./dataset/dataset_index_labeled.json")
        output_dir = config.get("model_settings", {}).get("model_path", "./model/weights")
        output_dir = os.path.dirname(output_dir)
        
        if not os.path.exists(dataset_index):
            logger.error(f"Dataset index not found: {dataset_index}")
            raise FileNotFoundError(dataset_index)
        
        logger.info(f"Training dataset: {dataset_index}")
        logger.info(f"Model output: {output_dir}")
        
        train_model(dataset_index, output_dir)
        
    except Exception as e:
        logger.error(f"Training failed: {e}")
        raise


def stage_inference(config: dict, h5_file: str = None):
    """Stage 4: Run inference on H5 data."""
    
    logger.info("\n" + "="*80)
    logger.info("STAGE 4: INFERENCE & OUTPUT GENERATION")
    logger.info("="*80)
    
    try:
        sys.path.insert(0, "./model")
        from inference_pipeline import infer_single_file
        
        model_path = config.get("model_settings", {}).get("model_path", "./model/weights/best_model.pth")
        output_dir = config.get("output_settings", {}).get("output_dir", "./output")
        
        if not os.path.exists(model_path):
            logger.error(f"Model not found: {model_path}")
            raise FileNotFoundError(model_path)
        
        if h5_file is None:
            logger.error("No H5 file specified for inference")
            raise ValueError("Specify --h5 <file>")
        
        if not os.path.exists(h5_file):
            logger.error(f"H5 file not found: {h5_file}")
            raise FileNotFoundError(h5_file)
        
        logger.info(f"Model: {model_path}")
        logger.info(f"Input: {h5_file}")
        logger.info(f"Output: {output_dir}")
        
        result = infer_single_file(h5_file, model_path, output_dir)
        
        logger.info(f"\n✓ Inference results:")
        logger.info(f"  Timestamp: {result['timestamp']}")
        logger.info(f"  TCC Pixels: {result['tcc_pixels']}")
        logger.info(f"  TCC Coverage: {result['tcc_percentage']:.2f}%")
        
        return result
        
    except Exception as e:
        logger.error(f"Inference failed: {e}")
        raise


def stage_full_pipeline(config: dict):
    """Full end-to-end pipeline (placeholder)."""
    
    logger.info("\n" + "="*80)
    logger.info("FULL PIPELINE: Download → Train → Infer")
    logger.info("="*80)
    
    try:
        stage_download(config)
        stage_label_generation(config)
        stage_training(config)
        
        logger.info("\n✓ Full pipeline complete!")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Tropical Cloud Cluster Detection - Main Orchestration Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --mode train                                    # Train model
  python main.py --mode infer --h5 data/satellite.h5            # Infer on file
  python main.py --mode full                                     # Full pipeline
        """
    )
    
    parser.add_argument(
        "--mode",
        choices=["download", "train", "infer", "full"],
        default="train",
        help="Execution mode"
    )
    
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config file (default: config.json)"
    )
    
    parser.add_argument(
        "--h5",
        help="Path to H5 file for inference"
    )
    
    parser.add_argument(
        "--output",
        help="Output directory (overrides config)"
    )
    
    args = parser.parse_args()
    
    # Load config
    config = load_config(args.config)
    
    # Override output if specified
    if args.output:
        config["output_settings"]["output_dir"] = args.output
    
    # Execute selected stage
    try:
        if args.mode == "download":
            stage_download(config)
        
        elif args.mode == "train":
            stage_training(config)
        
        elif args.mode == "infer":
            stage_inference(config, args.h5)
        
        elif args.mode == "full":
            stage_full_pipeline(config)
        
        logger.info("\n✓ All operations completed successfully!")
        sys.exit(0)
        
    except KeyboardInterrupt:
        logger.warning("\n⚠ Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"\n✗ Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    os.chdir(Path(__file__).parent)  # Set working dir to script location
    main()
