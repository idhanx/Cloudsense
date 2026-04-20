"""
CloudSense Inference Engine (FIXED)
Robust inference: H5/Image → Model → Correct Post-Processing → TCC Detection

FIXES APPLIED:
1. Resize mask back to original resolution before area calculation
2. Apply physics-based BT threshold (<218K) in ensemble
3. Connected component labeling with scipy.ndimage
4. Area filtering using native pixel resolution (16 km²/pixel)
5. Morphological cleanup for noise removal
"""

import os
import numpy as np
import h5py
import torch
import cv2
import xarray as xr
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import segmentation_models_pytorch as smp
import albumentations as A
from albumentations.pytorch import ToTensorV2
from datetime import datetime
from scipy import ndimage
from skimage.measure import regionprops, label as sk_label
from typing import List, Dict, Tuple, Optional
import logging

from core.temporal_tracker import TemporalTracker, Track

logger = logging.getLogger(__name__)


class InferencePipeline:
    """
    Corrected TCC inference pipeline with proper post-processing.
    
    Key improvements over original:
    - Resizes predictions back to native resolution
    - Applies physics-based BT threshold in ensemble
    - Runs connected component analysis
    - Filters by minimum TCC area (34,800 km²)
    """
    
    # Model configuration
    IMG_SIZE = 512
    PROB_THRESHOLD = 0.5        # Balanced threshold to reduce false positives
    
    # Physics-based thresholds
    BT_COLD_THRESHOLD = 221.0   # Kelvin - TCC cloud tops (IMD/WMO specification)
    MIN_BT = 180.0              # Normalization min
    MAX_BT = 320.0              # Normalization max
    
    # Geophysical constraints
    MIN_AREA_KM2 = 34800.0      # Problem statement: 90% of area of 1° radius circle
    PIXEL_RESOLUTION_KM = 4.0   # INSAT-3D native resolution (km/pixel)
    MIN_SEPARATION_KM = 1200.0  # Minimum separation between TCC centroids
    
    # Geographic bounding boxes (lat_min, lat_max, lon_min, lon_max)
    NORTH_INDIAN_OCEAN = (0.0, 30.0, 30.0, 100.0)   # 0°–30°N, 30°–100°E
    SOUTH_INDIAN_OCEAN = (-30.0, 0.0, 30.0, 110.0)  # 0°–30°S, 30°–110°E

    # Cloud-top height formula — standard atmosphere lapse rate 6.5 K/km
    # Reference surface temperature: 288K (ISA standard, 15°C at sea level)
    SURFACE_TEMP_K = 288.0
    LAPSE_RATE_K_PER_KM = 6.5
    
    # Dynamic dataset discovery keys
    IR_CANDIDATES = ['IMG_TIR1', 'TIR1', 'IR', 'IR1', 'IR_BT', 'Band4', 'IMG_TIR']
    LUT_CANDIDATES = ['IMG_TIR1_TEMP', 'TIR1_TEMP', 'LUT', 'TEMP_LUT']
    LAT_CANDIDATES = ['Latitude', 'Lat_Grid', 'lat', 'Geolocation/Latitude']
    LON_CANDIDATES = ['Longitude', 'Lon_Grid', 'lon', 'Geolocation/Longitude']
    
    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2):
        """Haversine distance between two lat/lon points in km."""
        import math
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    def _is_in_valid_region(self, lat: float, lon: float) -> bool:
        """
        Check if centroid falls within North or South Indian Ocean regions.
        
        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
        
        Returns:
            True if in valid region, False otherwise
        """
        # Handle NaN coordinates
        if np.isnan(lat) or np.isnan(lon):
            logger.warning(f"Invalid centroid coordinates: lat={lat}, lon={lon}")
            return False
        
        # Check North Indian Ocean (0°–30°N, 30°–100°E)
        lat_min_n, lat_max_n, lon_min_n, lon_max_n = self.NORTH_INDIAN_OCEAN
        if lat_min_n <= lat <= lat_max_n and lon_min_n <= lon <= lon_max_n:
            return True
        
        # Check South Indian Ocean (0°–30°S, 30°–110°E)
        lat_min_s, lat_max_s, lon_min_s, lon_max_s = self.SOUTH_INDIAN_OCEAN
        if lat_min_s <= lat <= lat_max_s and lon_min_s <= lon <= lon_max_s:
            return True
        
        return False
    
    def _enforce_separation_constraint(self, detections: List[Dict]) -> List[Dict]:
        """
        Enforce minimum 1200 km separation between cluster centroids.
        
        When clusters are closer than MIN_SEPARATION_KM, retain only the
        largest by area and discard others.
        
        Args:
            detections: List of detection dicts with centroid_lat, centroid_lon, area_km2
        
        Returns:
            Filtered list with separation constraint enforced
        """
        if len(detections) <= 1:
            return detections
        
        # Sort by area (largest first)
        sorted_detections = sorted(detections, key=lambda d: d['area_km2'], reverse=True)
        
        retained = []
        
        for detection in sorted_detections:
            lat = detection['centroid_lat']
            lon = detection['centroid_lon']
            
            # Check distance to all retained detections
            too_close = False
            merge_target_id = None
            
            for retained_det in retained:
                distance = self._haversine_km(
                    lat, lon,
                    retained_det['centroid_lat'], retained_det['centroid_lon']
                )
                
                if distance < self.MIN_SEPARATION_KM:
                    too_close = True
                    merge_target_id = retained_det['cluster_id']
                    break
            
            if too_close:
                logger.info(
                    f"  Separation constraint: Discarding cluster {detection['cluster_id']} "
                    f"at ({lat:.1f}°, {lon:.1f}°), area={detection['area_km2']:.0f}km² "
                    f"(merged into cluster {merge_target_id}, distance < {self.MIN_SEPARATION_KM}km)"
                )
            else:
                retained.append(detection)
        
        return retained
    
    def __init__(self, model_path: str = None):
        """Initialize with trained model."""
        if model_path is None:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            model_path = os.path.join(project_root, "model", "best_model.pth")
        
        self.model_path = model_path
        self.device = self._get_device()
        self.model = None
        self.tracker = TemporalTracker(proximity_threshold_km=500.0)
        
        logger.info(f"InferencePipeline initialized (device: {self.device})")
    
    def _get_device(self):
        """Detect available device."""
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps"
        return "cpu"
    
    def _load_model(self):
        """Lazy load model."""
        if self.model is not None:
            return self.model
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        
        self.model = smp.Unet(
            encoder_name="mobilenet_v2",
            encoder_weights=None,
            in_channels=1,
            classes=1,
            decoder_attention_type="scse",
        )
        self.model.load_state_dict(
            torch.load(self.model_path, map_location=self.device, weights_only=True),
            strict=False,  # backward compat with models saved without scse
        )
        self.model.to(self.device)
        self.model.eval()
        
        logger.info(f"Model loaded from {self.model_path}")
        return self.model
    
    def _find_dataset(self, f, candidates: list):
        """Find first matching dataset from list of candidates."""
        for name in candidates:
            if '/' in name:
                parts = name.split('/')
                try:
                    current = f
                    for part in parts:
                        current = current[part]
                    return current
                except KeyError:
                    continue
            elif name in f:
                return f[name]
        return None
    
    def _load_h5(self, h5_path: str) -> Tuple[np.ndarray, Optional[np.ndarray], Optional[np.ndarray]]:
        """Load INSAT-3D H5 file with dynamic discovery."""
        with h5py.File(h5_path, 'r') as f:
            logger.info(f"H5 keys: {list(f.keys())}")
            
            # 1. Find IR dataset
            ir_dataset = self._find_dataset(f, self.IR_CANDIDATES)
            if ir_dataset is None:
                for key in f.keys():
                    if isinstance(f[key], h5py.Dataset) and len(f[key].shape) >= 2:
                        ir_dataset = f[key]
                        logger.warning(f"Using fallback IR dataset: {key}")
                        break
            
            if ir_dataset is None:
                raise ValueError(f"No IR data found in H5 file. Available keys: {list(f.keys())}")
            
            raw_counts = ir_dataset[0] if len(ir_dataset.shape) == 3 else ir_dataset[:]
            
            # 2. Apply LUT if available
            lut_dataset = self._find_dataset(f, self.LUT_CANDIDATES)
            if lut_dataset is not None:
                lut = lut_dataset[:]
                raw_counts = np.clip(raw_counts, 0, len(lut) - 1)
                irbt = lut[raw_counts].astype(np.float32)
                logger.info("Applied LUT for brightness temperature conversion")
            else:
                irbt = raw_counts.astype(np.float32)
                logger.warning("No LUT found, using raw values as IRBT")
            
            # 3. Handle NaN/fill values
            irbt = np.where(irbt < 100, np.nan, irbt)
            irbt = np.nan_to_num(irbt, nan=np.nanmean(irbt) if not np.all(np.isnan(irbt)) else 250.0)
            
            # 4. Lat/Lon — try named arrays first, then derive from Mercator projection
            lat, lon = None, None
            
            lat_dataset = self._find_dataset(f, self.LAT_CANDIDATES)
            if lat_dataset is not None:
                lat = lat_dataset[:].astype(np.float32)
            
            lon_dataset = self._find_dataset(f, self.LON_CANDIDATES)
            if lon_dataset is not None:
                lon = lon_dataset[:].astype(np.float32)
            
            # Try deriving from Mercator projection (INSAT-3D ASIA_MER product)
            if (lat is None or lon is None) and 'X' in f and 'Y' in f and 'Projection_Information' in f:
                try:
                    lat, lon = self._derive_latlon_from_mercator(f)
                    logger.info("Derived lat/lon from Mercator projection parameters")
                except Exception as e:
                    logger.warning(f"Mercator lat/lon derivation failed: {e}")
                    lat, lon = None, None
            
            if lat is None or lon is None:
                logger.warning("Lat/Lon not found - using synthetic coordinates")
                lat, lon = self._create_synthetic_coords(irbt.shape)
        
        return irbt, lat, lon
    
    def _derive_latlon_from_mercator(self, f) -> Tuple[np.ndarray, np.ndarray]:
        """
        Derive lat/lon grids from INSAT-3D Mercator projection parameters.
        
        INSAT-3D ASIA_MER products store X/Y in metres (Mercator) and
        Projection_Information attributes with the projection origin and
        corner coordinates.
        """
        import math
        
        proj = f['Projection_Information']
        lon0 = float(proj.attrs['longitude_of_projection_origin'][0])  # central meridian
        R_major = float(proj.attrs['semi_major_axis'][0])
        R_minor = float(proj.attrs['semi_minor_axis'][0])
        
        x_m = f['X'][:].astype(np.float64)   # shape (W,)
        y_m = f['Y'][:].astype(np.float64)   # shape (H,)
        
        # Mercator inverse projection
        # lon = lon0 + x / R_major  (in radians → degrees)
        # lat = 2*atan(exp(y / R_major)) - pi/2  (in radians → degrees)
        lon_1d = np.degrees(x_m / R_major) + lon0
        lat_1d = np.degrees(2.0 * np.arctan(np.exp(y_m / R_major)) - math.pi / 2.0)
        
        # Build 2-D grids: rows = Y (lat), cols = X (lon)
        lon_grid, lat_grid = np.meshgrid(lon_1d, lat_1d)
        
        logger.info(f"Mercator lat/lon: lat [{lat_grid.min():.1f}, {lat_grid.max():.1f}], "
                    f"lon [{lon_grid.min():.1f}, {lon_grid.max():.1f}]")
        
        return lat_grid.astype(np.float32), lon_grid.astype(np.float32)
    
    def _create_synthetic_coords(self, shape: Tuple[int, int]) -> Tuple[np.ndarray, np.ndarray]:
        """Create synthetic lat/lon grids for data without geolocation."""
        h, w = shape
        lat_1d = np.linspace(30.0, 0.0, h)  # North to South
        lon_1d = np.linspace(60.0, 100.0, w)  # West to East
        lon_grid, lat_grid = np.meshgrid(lon_1d, lat_1d)
        return lat_grid.astype(np.float32), lon_grid.astype(np.float32)
    
    def _crop_satellite_region(self, img: np.ndarray) -> np.ndarray:
        """
        Auto-crop satellite data region from MOSDAC-style images.
        Removes header text, footer/colorbar, ISRO logo, and side annotations.
        
        Strategy:
        1. Detect rows/cols that are mostly uniform (text/border regions)
        2. Find the largest contiguous data block
        3. Fallback: center crop at 80% if auto-detection fails
        """
        h, w = img.shape[:2]
        
        # Convert to grayscale if needed
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()
        
        # Strategy: Use variance per row/col to find data vs annotation regions
        # Satellite data rows have HIGH variance (clouds + surface)
        # Text/border rows have LOW variance (uniform background)
        
        row_variance = np.var(gray.astype(np.float32), axis=1)
        col_variance = np.var(gray.astype(np.float32), axis=0)
        
        # Threshold: rows/cols with variance above median are likely data
        row_thresh = np.median(row_variance) * 0.3
        col_thresh = np.median(col_variance) * 0.3
        
        data_rows = np.where(row_variance > row_thresh)[0]
        data_cols = np.where(col_variance > col_thresh)[0]
        
        if len(data_rows) > 10 and len(data_cols) > 10:
            # Find contiguous block (largest gap-free region)
            top = data_rows[0]
            bottom = data_rows[-1]
            left = data_cols[0]
            right = data_cols[-1]
            
            # Add small margin (2% inward) to remove edge artifacts
            margin_y = max(5, int((bottom - top) * 0.02))
            margin_x = max(5, int((right - left) * 0.02))
            top = min(top + margin_y, h - 1)
            bottom = max(bottom - margin_y, 0)
            left = min(left + margin_x, w - 1)
            right = max(right - margin_x, 0)
            
            if bottom > top and right > left:
                cropped = gray[top:bottom+1, left:right+1]
                logger.info(f"Auto-cropped satellite region: ({top},{left}) to ({bottom},{right}) from {h}x{w}")
                return cropped
        
        # Fallback: center crop at 80%
        margin_y = int(h * 0.1)
        margin_x = int(w * 0.1)
        cropped = gray[margin_y:h-margin_y, margin_x:w-margin_x]
        logger.info(f"Fallback center crop: {cropped.shape} from {h}x{w}")
        return cropped
    
    def _load_image(self, image_path: str) -> np.ndarray:
        """
        Load image file (PNG/JPG) for inference.
        
        FIXED: 
        1. Auto-crops annotations/borders from MOSDAC screenshots
        2. Inverts BT mapping: in IR satellite images, bright = cold cloud tops
           So bright pixels → low BT (180K), dark pixels → high BT (320K)
        """
        img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Failed to load image: {image_path}")
        
        # Crop out annotations, borders, colorbar, etc.
        cropped = self._crop_satellite_region(img)
        
        # INVERTED mapping: In IR satellite imagery, bright = cold (cloud tops)
        # bright pixel (255) → MIN_BT (180K, cold cloud top)
        # dark pixel (0) → MAX_BT (320K, warm surface)
        irbt = self.MAX_BT - (cropped.astype(np.float32) / 255.0) * (self.MAX_BT - self.MIN_BT)
        
        logger.info(f"Image loaded: {img.shape} → cropped: {cropped.shape}, BT range: {irbt.min():.1f}K - {irbt.max():.1f}K")
        return irbt
    
    def _normalize_bt(self, irbt: np.ndarray) -> np.ndarray:
        """Normalize BT to [0, 1] using physics-based bounds."""
        normalized = (irbt - self.MIN_BT) / (self.MAX_BT - self.MIN_BT)
        return np.clip(normalized, 0, 1).astype(np.float32)
    
    def _prepare_tensor(self, normalized: np.ndarray) -> torch.Tensor:
        """Resize and convert to model input tensor."""
        resized = cv2.resize(normalized, (self.IMG_SIZE, self.IMG_SIZE), interpolation=cv2.INTER_LINEAR)
        tensor = torch.from_numpy(resized).unsqueeze(0).unsqueeze(0).float()
        return tensor.to(self.device)
    
    def _run_model_inference(self, tensor: torch.Tensor) -> np.ndarray:
        """Run model inference, return 512x512 probability map."""
        model = self._load_model()
        
        with torch.no_grad():
            output = model(tensor)
            prob = torch.sigmoid(output).squeeze().cpu().numpy()
        
        return prob
    
    def _apply_post_processing(self, 
                                prob_512: np.ndarray, 
                                irbt: np.ndarray,
                                lat: np.ndarray,
                                lon: np.ndarray,
                                input_type: str = 'h5') -> Dict:
        """
        CORRECTED post-processing pipeline.
        
        KEY FIX: Training masks were generated from DBSCAN clusters, NOT from
        BT threshold intersection. The model learned cluster shapes implicitly.
        We must NOT apply BT threshold intersection here - it kills valid predictions.
        
        For image inputs, uses stricter thresholds to reduce false positives
        since image data is inherently noisier than H5.
        
        Pipeline:
        1. Resize probability to native resolution
        2. Threshold (0.2 for H5, 0.4 for images)
        3. Morphological cleanup (stronger for images)
        4. Connected component analysis
        5. Area filtering (>= 5000 km² for H5, >= 10000 km² for images)
        """
        original_shape = irbt.shape
        h, w = original_shape
        
        # 1. RESIZE probability map to native resolution
        prob_native = cv2.resize(
            prob_512, 
            (w, h),  # (width, height) for cv2
            interpolation=cv2.INTER_LINEAR
        )
        
        # 2. THRESHOLD - Adaptive based on input type
        # Image inputs are noisier, need higher threshold to filter false positives
        if input_type == 'image':
            prob_threshold = 0.6   # Stricter for images (noisier data)
            min_area = 25000.0     # Larger minimum area to filter noise
        else:
            prob_threshold = self.PROB_THRESHOLD  # 0.5 for H5 (calibrated data)
            min_area = self.MIN_AREA_KM2          # 34,800 km² — IMD TCC definition
        
        binary_mask = (prob_native > prob_threshold).astype(np.uint8)
        
        # 3. MORPHOLOGICAL CLEANUP (stronger for images to remove text/annotation artifacts)
        if input_type == 'image':
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
            cleaned = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel, iterations=3)
            cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=3)
        else:
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
            cleaned = cv2.morphologyEx(binary_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel, iterations=2)
        
        # 4. CONNECTED COMPONENT ANALYSIS
        labeled, num_features = ndimage.label(cleaned)
        
        # 5. AREA FILTERING with correct pixel area
        pixel_area_km2 = self.PIXEL_RESOLUTION_KM ** 2  # 16 km²
        pixel_res_deg = self.PIXEL_RESOLUTION_KM / 111.0  # approx degrees per pixel
        
        valid_mask = np.zeros_like(cleaned)
        detections = []
        
        for label_id in range(1, num_features + 1):
            region_mask = (labeled == label_id)
            pixel_count = int(np.sum(region_mask))
            area_km2 = pixel_count * pixel_area_km2
            
            # Skip clusters that are too small (problem statement: 34,800 km²)
            if area_km2 < min_area:
                continue
            
            # BT filter: skip warm cloud clusters (not convective)
            region_bt = irbt[region_mask]
            region_min_bt = float(np.min(region_bt))
            if region_min_bt > 250.0:
                continue  # Warm clouds — not TCC candidates
            
            # ── PIXEL COORDINATES via regionprops ──
            rp = regionprops(region_mask.astype(np.uint8), intensity_image=irbt)
            if not rp:
                continue
            prop = rp[0]

            centroid_y = float(prop.centroid[0])
            centroid_x = float(prop.centroid[1])

            # ── GEOMETRIC CENTROID (lat/lon) ──
            y_coords, x_coords = np.where(region_mask)
            centroid_lat = float(np.mean(lat[y_coords, x_coords]))
            centroid_lon = float(np.mean(lon[y_coords, x_coords]))

            # ── GEOGRAPHIC FILTER: Check if centroid is in valid region ──
            if not self._is_in_valid_region(centroid_lat, centroid_lon):
                logger.info(f"  Excluding cluster at ({centroid_lat:.1f}°, {centroid_lon:.1f}°): outside Indian Ocean regions")
                continue
            
            valid_mask[region_mask] = 1
            
            # ── CONVECTIVE CENTER (coldest pixel) — Problem Statement Requirement ──
            coldest_idx = np.argmin(region_bt)
            conv_y = int(y_coords[coldest_idx])
            conv_x = int(x_coords[coldest_idx])
            conv_lat = float(lat[conv_y, conv_x])
            conv_lon = float(lon[conv_y, conv_x])
            
            # ── FULL BT STATISTICS — Problem Statement Requirements ──
            mean_bt = float(np.mean(region_bt))
            min_bt = float(np.min(region_bt))
            median_bt = float(np.median(region_bt))
            std_bt = float(np.std(region_bt))
            
            # ── RADII (max, min, mean) from center to edge — Problem Statement ──
            # Find edge pixels of the cluster
            eroded = cv2.erode(region_mask.astype(np.uint8), np.ones((3, 3), np.uint8))
            edge_mask = region_mask.astype(np.uint8) - eroded
            edge_y, edge_x = np.where(edge_mask > 0)
            
            if len(edge_y) > 0:
                # Distance from geometric center to each edge pixel (in km)
                dy_km = (edge_y - centroid_y) * self.PIXEL_RESOLUTION_KM
                dx_km = (edge_x - centroid_x) * self.PIXEL_RESOLUTION_KM
                edge_distances = np.sqrt(dy_km**2 + dx_km**2)
                radius_max_km = float(np.max(edge_distances))
                radius_min_km = float(np.min(edge_distances)) if np.min(edge_distances) > 0 else float(np.sort(edge_distances)[min(1, len(edge_distances)-1)])
                radius_mean_km = float(np.mean(edge_distances))
            else:
                radius_mean_km = float(np.sqrt(area_km2 / np.pi))
                radius_max_km = radius_mean_km
                radius_min_km = radius_mean_km
            
            # ── CLOUD-TOP HEIGHT — Problem Statement Requirement ──
            # Standard atmosphere: lapse rate 6.5 K/km, surface ref 288K (ISA)
            bt_for_height = region_bt[region_bt < 280]  # Only consider cloud pixels
            if len(bt_for_height) > 0:
                max_cloud_top_height_km = float(max(0, (self.SURFACE_TEMP_K - np.min(bt_for_height)) / self.LAPSE_RATE_K_PER_KM))
                mean_cloud_top_height_km = float(max(0, (self.SURFACE_TEMP_K - np.mean(bt_for_height)) / self.LAPSE_RATE_K_PER_KM))
            else:
                max_cloud_top_height_km = float(max(0, (self.SURFACE_TEMP_K - min_bt) / self.LAPSE_RATE_K_PER_KM))
                mean_cloud_top_height_km = float(max(0, (self.SURFACE_TEMP_K - mean_bt) / self.LAPSE_RATE_K_PER_KM))
            
            # ── COLD CORE RATIO ──
            cold_pixels = int(np.sum(region_bt < 235.0))
            cold_core_ratio = float(cold_pixels / pixel_count) if pixel_count > 0 else 0.0
            
            # ── TCC CLASSIFICATION (IMD/WMO Criteria) ──
            # Stricter thresholds to produce realistic distribution of classifications
            tcc_score = 0
            reasons = []

            # BT score (max 40 pts) — require very cold tops for high score
            if min_bt < 200.0:
                tcc_score += 40
                reasons.append(f"Extremely cold cloud top ({min_bt:.0f}K)")
            elif min_bt < 210.0:
                tcc_score += 30
                reasons.append(f"Very cold cloud top ({min_bt:.0f}K)")
            elif min_bt < 220.0:
                tcc_score += 20
                reasons.append(f"Cold cloud top ({min_bt:.0f}K)")
            elif min_bt < 235.0:
                tcc_score += 10
                reasons.append(f"Moderately cold top ({min_bt:.0f}K)")
            elif min_bt < 245.0:
                tcc_score += 5
                reasons.append(f"Cool cloud top ({min_bt:.0f}K)")
            else:
                reasons.append(f"Warm cloud top ({min_bt:.0f}K)")

            # Area score (max 25 pts)
            if area_km2 >= 200000:
                tcc_score += 25
                reasons.append(f"Very large extent ({area_km2/1000:.0f}k km²)")
            elif area_km2 >= 100000:
                tcc_score += 20
                reasons.append(f"Large extent ({area_km2/1000:.0f}k km²)")
            elif area_km2 >= 50000:
                tcc_score += 15
                reasons.append(f"Moderate extent ({area_km2/1000:.0f}k km²)")
            elif area_km2 >= 34800:
                tcc_score += 8
                reasons.append(f"TCC-scale extent ({area_km2/1000:.0f}k km²)")
            elif area_km2 >= 20000:
                tcc_score += 3
                reasons.append(f"Sub-TCC extent ({area_km2/1000:.0f}k km²)")

            # Cold core ratio score (max 25 pts)
            if cold_core_ratio > 0.60:
                tcc_score += 25
                reasons.append(f"Dominant cold core ({cold_core_ratio*100:.0f}%)")
            elif cold_core_ratio > 0.40:
                tcc_score += 18
                reasons.append(f"Strong cold core ({cold_core_ratio*100:.0f}%)")
            elif cold_core_ratio > 0.25:
                tcc_score += 12
                reasons.append(f"Moderate cold core ({cold_core_ratio*100:.0f}%)")
            elif cold_core_ratio > 0.10:
                tcc_score += 6
                reasons.append(f"Weak cold core ({cold_core_ratio*100:.0f}%)")

            # Mean BT bonus (max 10 pts)
            if mean_bt < 210.0:
                tcc_score += 10
            elif mean_bt < 220.0:
                tcc_score += 7
            elif mean_bt < 230.0:
                tcc_score += 4
            elif mean_bt < 240.0:
                tcc_score += 2

            tcc_score = min(tcc_score, 100)

            # Stricter classification bands — require BOTH high score AND minimum physical size
            # A "Confirmed TCC" must have: score >= 80 AND area >= 34,800 km² AND min_bt < 221K (IMD/WMO spec)
            if tcc_score >= 80 and area_km2 >= 34800 and min_bt < 221.0:
                classification = 'Confirmed TCC'
                is_tcc = True
            elif tcc_score >= 60 and area_km2 >= 20000 and min_bt < 235.0:
                classification = 'Probable TCC'
                is_tcc = True
            elif tcc_score >= 35 and area_km2 >= 10000:
                classification = 'Possible TCC'
                is_tcc = False
            else:
                classification = 'Cloud Cluster'
                is_tcc = False
            
            detections.append({
                'cluster_id': len(detections) + 1,
                # Geometry
                'area_km2': float(area_km2),
                'pixel_count': pixel_count,
                'centroid_lat': centroid_lat,
                'centroid_lon': centroid_lon,
                'centroid_y': centroid_y,
                'centroid_x': centroid_x,
                # Convective center (coldest pixel) — Problem Statement
                'conv_lat': conv_lat,
                'conv_lon': conv_lon,
                # BT statistics — Problem Statement
                'mean_bt': mean_bt,
                'min_bt': min_bt,
                'median_bt': median_bt,
                'std_bt': std_bt,
                # Radii — Problem Statement
                'radius_max_km': radius_max_km,
                'radius_min_km': radius_min_km,
                'radius_mean_km': radius_mean_km,
                'radius_km': radius_mean_km,  # backward compat
                # Cloud-top height — Problem Statement
                'max_cloud_top_height_km': max_cloud_top_height_km,
                'mean_cloud_top_height_km': mean_cloud_top_height_km,
                # Classification
                'cold_core_ratio': cold_core_ratio,
                'tcc_score': tcc_score,
                'is_tcc': is_tcc,
                'classification': classification,
                'classification_reasons': reasons
            })
            
            logger.info(f"  TCC-{len(detections)}: area={area_km2:.0f}km², Tb={min_bt:.0f}/{mean_bt:.0f}/{median_bt:.0f}K, "
                        f"radii={radius_min_km:.0f}/{radius_mean_km:.0f}/{radius_max_km:.0f}km, "
                        f"height={max_cloud_top_height_km:.1f}km, score={tcc_score}")
        
        # ── ENFORCE SEPARATION CONSTRAINT (≥ 1200 km between centroids) ──
        detections = self._enforce_separation_constraint(detections)
        
        # ── RE-NUMBER detections by area (largest first) ──
        if len(detections) > 1:
            detections.sort(key=lambda d: d['area_km2'], reverse=True)
            for i, d in enumerate(detections):
                d['cluster_id'] = i + 1
        
        logger.info(f"Post-processing ({input_type}): {num_features} components → {len(detections)} independent TCCs")
        
        return {
            'probability_native': prob_native,
            'binary_mask': binary_mask,
            'final_mask': valid_mask,
            'detections': detections,
            'total_tcc_area_km2': sum(d['area_km2'] for d in detections)
        }
    
    def _extract_timestamp(self, file_path: str) -> datetime:
        """Extract timestamp from filename or use current time."""
        basename = os.path.basename(file_path)
        try:
            parts = basename.split('_')
            date_str = parts[1]
            time_str = parts[2]
            return datetime.strptime(f"{date_str}_{time_str}", "%d%b%Y_%H%M")
        except:
            return datetime.now()
    
    def _save_mask_npy(self, mask: np.ndarray, output_path: str):
        """Save binary mask as .npy."""
        np.save(output_path, mask)
        logger.info(f"Saved: {output_path}")
    
    def _save_mask_png(self, mask: np.ndarray, output_path: str):
        """Save visual mask as .png."""
        plt.figure(figsize=(8, 8))
        plt.imshow(mask, cmap='gray')
        plt.axis('off')
        plt.tight_layout(pad=0)
        plt.savefig(output_path, bbox_inches='tight', pad_inches=0, dpi=150)
        plt.close()
        logger.info(f"Saved: {output_path}")
    
    def _save_satellite_image(self, irbt: np.ndarray, output_path: str):
        """Save original satellite IRBT image as .png."""
        plt.figure(figsize=(10, 10))
        plt.imshow(irbt, cmap='gray_r', vmin=180, vmax=320)
        plt.colorbar(label='Brightness Temperature (K)', shrink=0.8)
        plt.title('IR Brightness Temperature')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(output_path, bbox_inches='tight', dpi=150)
        plt.close()
        logger.info(f"Saved: {output_path}")
    
    def _save_overlay_visualization(self, irbt: np.ndarray, mask: np.ndarray, 
                                     detections: List[Dict], output_path: str,
                                     timestamp_str: str = None):
        """
        Save high-quality visualization with TCC detections annotated.
        Left: IR Brightness Temperature with detection contours
        Right: TCC Mask with cluster labels
        """
        fig, ax = plt.subplots(1, 2, figsize=(16, 7), facecolor='#0a0a1a')
        
        for a in ax:
            a.set_facecolor('#0a0a1a')
        
        # LEFT: IR Brightness Temperature with detection contours
        im1 = ax[0].imshow(irbt, cmap='jet_r', vmin=180, vmax=320)
        title_left = f'IR Brightness Temp ({timestamp_str})' if timestamp_str else 'IR Brightness Temp'
        ax[0].set_title(title_left, color='white', fontsize=12, fontweight='bold')
        ax[0].axis('off')
        cbar1 = plt.colorbar(im1, ax=ax[0], fraction=0.046, pad=0.04)
        cbar1.set_label('Temperature (K)', color='white', fontsize=9)
        cbar1.ax.yaxis.set_tick_params(color='white')
        plt.setp(cbar1.ax.yaxis.get_ticklabels(), color='white', fontsize=8)
        
        # Draw contours of detected TCCs on IR image
        if mask.sum() > 0:
            ax[0].contour(mask, levels=[0.5], colors=['red'], linewidths=1.5)
        
        # RIGHT: TCC Mask with cluster labels
        # Use a custom colormap: dark background, bright cyan for TCC
        from matplotlib.colors import ListedColormap
        tcc_cmap = ListedColormap(['#0a0a1a', '#00e5ff'])
        ax[1].imshow(mask, cmap=tcc_cmap, vmin=0, vmax=1)
        ax[1].set_title('TCC Detection Mask', color='white', fontsize=12, fontweight='bold')
        ax[1].axis('off')
        
        # Annotate each detection using stored pixel centroids
        for d in detections:
            cy = d.get('centroid_y')
            cx = d.get('centroid_x')
            if cy is None or cx is None:
                continue
            
            # Validate: only label if the pixel is actually in the mask
            iy, ix = int(round(cy)), int(round(cx))
            if iy < 0 or iy >= mask.shape[0] or ix < 0 or ix >= mask.shape[1]:
                continue
            if mask[iy, ix] == 0:
                # Centroid might be slightly off — check nearby
                found = False
                for dy in range(-3, 4):
                    for dx in range(-3, 4):
                        ny, nx = iy + dy, ix + dx
                        if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] > 0:
                            found = True
                            break
                    if found:
                        break
                if not found:
                    continue  # Skip — no mask at this location
            
            classification = d.get('classification', 'TCC')
            short_class = '✓' if 'Confirmed' in classification else '~' if 'Probable' in classification else '?'
            label_text = f"TCC-{d['cluster_id']} {short_class}"
            ax[1].annotate(label_text, (cx, cy), 
                          color='white', fontsize=7, fontweight='bold',
                          ha='center', va='center',
                          bbox=dict(boxstyle='round,pad=0.2', facecolor='#00000088', edgecolor='#00e5ff'))
        
        # Summary text
        total_area = sum(d.get('area_km2', 0) for d in detections)
        confirmed = sum(1 for d in detections if d.get('is_tcc', False))
        summary = f"Detections: {len(detections)} | Confirmed TCC: {confirmed} | Total Area: {total_area:,.0f} km²"
        fig.text(0.5, 0.02, summary, ha='center', va='bottom', 
                color='#00e5ff', fontsize=10, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.5', facecolor='#0a0a1a', edgecolor='#00e5ff44'))
        
        plt.tight_layout(rect=[0, 0.05, 1, 1])
        plt.savefig(output_path, dpi=200, facecolor='#0a0a1a', bbox_inches='tight')
        plt.close()
        logger.info(f"Saved comparison: {output_path}")
    
    def _save_netcdf(self, irbt: np.ndarray, prob: np.ndarray, mask: np.ndarray,
                     lat: np.ndarray, lon: np.ndarray, timestamp: datetime, 
                     detections: List[Dict], output_path: str):
        """Save CF-compliant NetCDF with full gridded data AND per-cluster variables."""
        h, w = irbt.shape
        
        # ── Build spatial coordinates ──
        if lat is not None and lon is not None:
            coords = {
                "time": [timestamp],
                "latitude": (["lat", "lon"], lat, {
                    "long_name": "Latitude",
                    "units": "degrees_north"
                }),
                "longitude": (["lat", "lon"], lon, {
                    "long_name": "Longitude",
                    "units": "degrees_east"
                }),
            }
        else:
            y_coords = np.arange(h)
            x_coords = np.arange(w)
            coords = {
                "time": [timestamp],
                "y": (["lat"], y_coords, {"long_name": "Y Pixel Index", "units": "1"}),
                "x": (["lon"], x_coords, {"long_name": "X Pixel Index", "units": "1"}),
            }
        
        # ── Gridded data variables ──
        data_vars = {
            "irbt": (["time", "lat", "lon"], irbt[np.newaxis, :, :], {
                "long_name": "IR Brightness Temperature",
                "units": "K",
                "standard_name": "brightness_temperature"
            }),
            "tcc_probability": (["time", "lat", "lon"], prob[np.newaxis, :, :], {
                "long_name": "TCC Detection Probability",
                "units": "1",
                "valid_range": [0.0, 1.0]
            }),
            "tcc_mask": (["time", "lat", "lon"], mask[np.newaxis, :, :], {
                "long_name": "TCC Binary Mask (Area Filtered)",
                "units": "1",
                "flag_values": [0, 1],
                "flag_meanings": "background TCC"
            }),
        }
        
        # ── Per-cluster data variables (Problem Statement Outputs) ──
        if len(detections) > 0:
            n = len(detections)
            coords["cluster"] = np.arange(1, n + 1)
            
            data_vars["cluster_latitude"] = (["cluster"], 
                np.array([d.get("centroid_lat", 0) for d in detections], dtype=np.float32),
                {"long_name": "Cluster Centroid Latitude", "units": "degrees_north"})
            data_vars["cluster_longitude"] = (["cluster"],
                np.array([d.get("centroid_lon", 0) for d in detections], dtype=np.float32),
                {"long_name": "Cluster Centroid Longitude", "units": "degrees_east"})
            data_vars["cluster_conv_latitude"] = (["cluster"],
                np.array([d.get("conv_lat", d.get("centroid_lat", 0)) for d in detections], dtype=np.float32),
                {"long_name": "Convective Center Latitude (coldest pixel)", "units": "degrees_north"})
            data_vars["cluster_conv_longitude"] = (["cluster"],
                np.array([d.get("conv_lon", d.get("centroid_lon", 0)) for d in detections], dtype=np.float32),
                {"long_name": "Convective Center Longitude (coldest pixel)", "units": "degrees_east"})
            data_vars["cluster_pixel_count"] = (["cluster"],
                np.array([d.get("pixel_count", 0) for d in detections], dtype=np.int32),
                {"long_name": "Number of TCC Pixels", "units": "1"})
            data_vars["cluster_mean_tb"] = (["cluster"],
                np.array([d.get("mean_bt", 0) for d in detections], dtype=np.float32),
                {"long_name": "Mean Brightness Temperature", "units": "K"})
            data_vars["cluster_min_tb"] = (["cluster"],
                np.array([d.get("min_bt", 0) for d in detections], dtype=np.float32),
                {"long_name": "Minimum Brightness Temperature", "units": "K"})
            data_vars["cluster_median_tb"] = (["cluster"],
                np.array([d.get("median_bt", 0) for d in detections], dtype=np.float32),
                {"long_name": "Median Brightness Temperature", "units": "K"})
            data_vars["cluster_std_tb"] = (["cluster"],
                np.array([d.get("std_bt", 0) for d in detections], dtype=np.float32),
                {"long_name": "Standard Deviation of Brightness Temperature", "units": "K"})
            data_vars["cluster_radius_max"] = (["cluster"],
                np.array([d.get("radius_max_km", 0) for d in detections], dtype=np.float32),
                {"long_name": "Maximum Radius (center to edge)", "units": "km"})
            data_vars["cluster_radius_min"] = (["cluster"],
                np.array([d.get("radius_min_km", 0) for d in detections], dtype=np.float32),
                {"long_name": "Minimum Radius (center to edge)", "units": "km"})
            data_vars["cluster_radius_mean"] = (["cluster"],
                np.array([d.get("radius_mean_km", 0) for d in detections], dtype=np.float32),
                {"long_name": "Mean Radius (center to edge)", "units": "km"})
            data_vars["cluster_max_cloud_top_height"] = (["cluster"],
                np.array([d.get("max_cloud_top_height_km", 0) for d in detections], dtype=np.float32),
                {"long_name": "Maximum Cloud-Top Height", "units": "km"})
            data_vars["cluster_mean_cloud_top_height"] = (["cluster"],
                np.array([d.get("mean_cloud_top_height_km", 0) for d in detections], dtype=np.float32),
                {"long_name": "Mean Cloud-Top Height", "units": "km"})
            data_vars["cluster_area_km2"] = (["cluster"],
                np.array([d.get("area_km2", 0) for d in detections], dtype=np.float32),
                {"long_name": "Cluster Area", "units": "km2"})
            data_vars["cluster_tcc_score"] = (["cluster"],
                np.array([d.get("tcc_score", 0) for d in detections], dtype=np.int32),
                {"long_name": "TCC Confidence Score", "units": "1", "valid_range": [0, 100]})
            data_vars["cluster_cold_core_ratio"] = (["cluster"],
                np.array([d.get("cold_core_ratio", 0) for d in detections], dtype=np.float32),
                {"long_name": "Cold Core Ratio (fraction of pixels with Tb < 235K)", "units": "1"})
            
            # ── Track ID (Temporal Tracking) ──
            track_ids = [d.get("track_id", "") for d in detections]
            # Convert to fixed-length string array for NetCDF compatibility
            max_len = max(len(tid) for tid in track_ids) if track_ids else 32
            track_id_array = np.array(track_ids, dtype=f'S{max_len}')
            data_vars["cluster_track_id"] = (["cluster"], track_id_array,
                {"long_name": "Temporal Track Identifier", "units": "1"})
        
        ds = xr.Dataset(
            data_vars=data_vars,
            coords=coords,
            attrs={
                "Conventions": "CF-1.8",
                "title": "CloudSense TCC Detection Output",
                "source": "INSAT-3D IRBT + U-Net Segmentation",
                "institution": "CloudSense",
                "history": f"Created {datetime.now().isoformat()}",
                "geolocation_available": "true" if lat is not None else "false",
                "tcc_count": len(detections),
                "total_tcc_area_km2": sum(d['area_km2'] for d in detections),
                "min_area_threshold_km2": self.MIN_AREA_KM2,
                "bt_threshold_K": self.BT_COLD_THRESHOLD
            }
        )
        
        ds.to_netcdf(output_path, engine="netcdf4")
        logger.info(f"Saved NetCDF: {output_path} ({len(detections)} clusters)")
    
    def process_file(self, h5_path: str, output_dir: str, analysis_id: str = None) -> dict:
        """
        Process single H5 file with CORRECTED post-processing.
        
        Returns:
            dict with success status, output paths, detections, and input_type
        """
        try:
            if analysis_id is None:
                timestamp = self._extract_timestamp(h5_path)
                analysis_id = timestamp.strftime("%Y%m%d_%H%M")
            
            file_output_dir = os.path.join(output_dir, analysis_id)
            os.makedirs(file_output_dir, exist_ok=True)
            
            logger.info(f"Processing H5: {os.path.basename(h5_path)}")
            
            # 1. Load data at native resolution
            irbt, lat, lon = self._load_h5(h5_path)
            timestamp = self._extract_timestamp(h5_path)
            
            logger.info(f"Input shape: {irbt.shape}, BT range: {irbt.min():.1f}K - {irbt.max():.1f}K")
            
            # 2. Normalize and prepare tensor
            normalized = self._normalize_bt(irbt)
            tensor = self._prepare_tensor(normalized)
            
            # 3. Run model inference (512x512)
            prob_512 = self._run_model_inference(tensor)
            
            # 4. CORRECTED post-processing
            results = self._apply_post_processing(prob_512, irbt, lat, lon)
            
            final_mask = results['final_mask']
            prob_native = results['probability_native']
            detections = results['detections']
            
            # 5. TEMPORAL TRACKING: Assign track IDs
            detections = self.tracker.update(detections, timestamp)
            
            tcc_pixels = int(np.sum(final_mask))
            
            logger.info(f"TCC detections: {len(detections)}, Total area: {results['total_tcc_area_km2']:,.0f} km²")
            
            # 6. Save outputs
            satellite_png_path = os.path.join(file_output_dir, "satellite.png")
            mask_npy_path = os.path.join(file_output_dir, "mask.npy")
            mask_png_path = os.path.join(file_output_dir, "mask.png")
            overlay_path = os.path.join(file_output_dir, "overlay.png")
            netcdf_path = os.path.join(file_output_dir, "output.nc")
            
            self._save_satellite_image(irbt, satellite_png_path)
            self._save_mask_npy(final_mask, mask_npy_path)
            self._save_mask_png(final_mask, mask_png_path)
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M")
            self._save_overlay_visualization(irbt, final_mask, detections, overlay_path, timestamp_str)
            self._save_netcdf(irbt, prob_native, final_mask, lat, lon, timestamp, detections, netcdf_path)
            
            return {
                "success": True,
                "analysis_id": analysis_id,
                "input_type": "h5",
                "tcc_pixels": tcc_pixels,
                "tcc_count": len(detections),
                "total_area_km2": results['total_tcc_area_km2'],
                "detections": detections,
                "outputs": {
                    "satellite_png": satellite_png_path,
                    "mask_npy": mask_npy_path,
                    "mask_png": mask_png_path,
                    "overlay_png": overlay_path,
                    "netcdf": netcdf_path
                }
            }
            
        except Exception as e:
            logger.error(f"H5 processing error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    def process_image(self, image_path: str, output_dir: str, analysis_id: str = None) -> dict:
        """
        Process image file (PNG/JPG) with CORRECTED post-processing.
        Note: No geolocation available for images, uses synthetic coordinates.
        """
        try:
            if analysis_id is None:
                analysis_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            file_output_dir = os.path.join(output_dir, analysis_id)
            os.makedirs(file_output_dir, exist_ok=True)
            
            logger.info(f"Processing image: {os.path.basename(image_path)}")
            
            # 1. Load image
            irbt = self._load_image(image_path)
            lat, lon = self._create_synthetic_coords(irbt.shape)
            
            logger.info(f"Input shape: {irbt.shape}")
            
            # 2. Normalize and prepare tensor
            normalized = self._normalize_bt(irbt)
            tensor = self._prepare_tensor(normalized)
            
            # 3. Run model inference (512x512)
            prob_512 = self._run_model_inference(tensor)
            
            # 4. CORRECTED post-processing
            results = self._apply_post_processing(prob_512, irbt, lat, lon, input_type='image')
            
            final_mask = results['final_mask']
            detections = results['detections']
            
            # 5. TEMPORAL TRACKING: Assign track IDs
            timestamp = datetime.now()
            detections = self.tracker.update(detections, timestamp)
            
            tcc_pixels = int(np.sum(final_mask))
            
            logger.info(f"TCC detections: {len(detections)}, Total area: {results['total_tcc_area_km2']:,.0f} km²")
            
            # 6. Save outputs
            satellite_png_path = os.path.join(file_output_dir, "satellite.png")
            mask_npy_path = os.path.join(file_output_dir, "mask.npy")
            mask_png_path = os.path.join(file_output_dir, "mask.png")
            overlay_path = os.path.join(file_output_dir, "overlay.png")
            
            # Copy input image as satellite view
            import shutil
            shutil.copy(image_path, satellite_png_path)
            
            self._save_mask_npy(final_mask, mask_npy_path)
            self._save_mask_png(final_mask, mask_png_path)
            # For images, use filename as timestamp
            basename = os.path.basename(image_path)
            ts_str = os.path.splitext(basename)[0]
            self._save_overlay_visualization(irbt, final_mask, detections, overlay_path, ts_str)
            
            # Generate NetCDF for image inputs too
            netcdf_path = os.path.join(file_output_dir, "output.nc")
            self._save_netcdf(irbt, results['probability_native'], final_mask, lat, lon, timestamp, detections, netcdf_path)
            
            return {
                "success": True,
                "analysis_id": analysis_id,
                "input_type": "image",
                "tcc_pixels": tcc_pixels,
                "tcc_count": len(detections),
                "total_area_km2": results['total_tcc_area_km2'],
                "detections": detections,
                "outputs": {
                    "satellite_png": satellite_png_path,
                    "mask_npy": mask_npy_path,
                    "mask_png": mask_png_path,
                    "overlay_png": overlay_path,
                    "netcdf": netcdf_path
                }
            }
            
        except Exception as e:
            logger.error(f"Image processing error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
