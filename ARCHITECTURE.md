# CloudSense — Architecture

## System Overview

CloudSense is a satellite imagery analysis system that detects Tropical Cloud Clusters (TCCs) from INSAT-3D/3DR infrared data. It combines a deep learning segmentation model with meteorological classification rules to identify and categorize deep convective systems.

## How It Works

### 1. Data Ingestion

Two input paths:

**MOSDAC Live Fetch:**
```
User enters MOSDAC credentials
    → mosdac_manager.py generates config.json
    → mdapi.py authenticates with MOSDAC API
    → Searches for 3RIMG_L1C_ASIA_MER files in time range
    → Downloads H5 files to backend/mosdac_engine/downloads/
    → Each file is automatically passed to inference
```

**Manual Upload:**
```
User uploads H5/image via /api/upload
    → File saved to backend/uploads/{uuid}.h5
    → Passed directly to inference engine
```

### 2. Inference Pipeline (`inference_engine.py`)

The core ML pipeline processes each file in 7 steps:

```
Step 1: Load HDF5
   └─ Open H5 file, find IMG_TIR1 dataset (10.8μm IR channel)
   └─ Apply Look-Up Table (LUT) → brightness temperature in Kelvin
   └─ Extract lat/lon grids (or generate synthetic coordinates)

Step 2: Preprocessing
   └─ Normalize BT to [0,1] range: (BT - 180) / (320 - 180)
   └─ Resize to 256×256 patches (tiled for large images)
   └─ Convert to PyTorch tensor

Step 3: U-Net Forward Pass
   └─ MobileNetV2 encoder → 5 skip connections → decoder
   └─ Output: probability map [0,1] per pixel
   └─ Device: CUDA > MPS > CPU (auto-detected)

Step 4: Binary Thresholding
   └─ probability > 0.3 → TCC candidate pixel
   └─ Resize mask back to original resolution

Step 5: Connected Components
   └─ SciPy ndimage.label → find contiguous regions
   └─ Filter: area ≥ 5,000 km² (removes noise)

Step 6: TCC Classification
   └─ For each surviving cluster:
      ├─ Compute centroid (lat, lon)
      ├─ Compute area (km²), radius (km)
      ├─ Extract mean BT and min BT
      └─ Classify:
          ├─ min BT < 220K → "Confirmed TCC" (deep convection)
          ├─ min BT < 235K → "Likely TCC"
          └─ min BT ≥ 235K → "Cloud Cluster"

Step 7: Output Generation
   └─ mask.npy     — raw binary mask array
   └─ mask.png     — mask as image
   └─ overlay.png  — IR + mask side-by-side (annotated, 200 DPI)
   └─ output.nc    — CF-compliant NetCDF with:
       ├─ brightness_temperature[lat,lon]
       ├─ tcc_probability[lat,lon]
       ├─ tcc_mask[lat,lon]
       └─ detection attributes (lat, lon, area, BT, class)
```

### 3. Data Storage

All results are persisted to SQLite:

```sql
analyses table:
   id          TEXT PRIMARY KEY    -- UUID
   filename    TEXT                -- original filename
   source      TEXT                -- 'manual_upload' or 'mosdac'
   status      TEXT                -- 'pending' → 'complete' / 'failed'
   results     TEXT (JSON)         -- {detections, tcc_pixels, tcc_count, ...}
   upload_timestamp TIMESTAMP
```

### 4. Frontend Display

The React frontend fetches from 4 API endpoints:

```
Dashboard ← /api/dashboard/stats     (KPI: active TCCs, min BT, height, radius)
          ← /api/analysis/clusters   (all clusters for map + table)
          ← /api/analyses/recent     (recent analysis list)

Analysis  ← /api/analyses/recent     (latest analysis details)
          ← /api/download/{id}/*     (overlay.png, output.nc, mask.png)

Exports   ← /api/exports             (list all downloadable outputs)
```

## API Reference

| Method | Endpoint | Description | Response |
|--------|----------|-------------|----------|
| POST | `/api/auth/signup` | Create account | `{access_token, user}` |
| POST | `/api/auth/login` | Login | `{access_token, user}` |
| GET | `/api/auth/verify` | Verify JWT token | `{user}` |
| POST | `/api/upload` | Upload H5/image → inference | `{analysis_id, tcc_count, detections[], outputs}` |
| POST | `/api/mosdac/download` | Fetch from MOSDAC → inference | `{results[]}` |
| GET | `/api/analyses/recent` | Recent analyses with results | `[{analysis_id, filename, results}]` |
| GET | `/api/dashboard/stats` | Aggregated KPIs | `{active_tccs, min_bt, avg_cloud_height, mean_radius}` |
| GET | `/api/analysis/clusters` | All clusters for map/table | `[{id, centroidLat, centroidLon, avgBT, minBT, radius, area}]` |
| GET | `/api/download/{id}/{file}` | Download output file | Binary file |
| GET | `/api/exports` | List all exportable outputs | `[{analysis_id, files, download_urls}]` |

## Model Architecture

```
U-Net with MobileNetV2 Encoder:

Input: 256×256×1 (IR brightness temperature)
   │
   ▼
MobileNetV2 Encoder (pretrained, adapted for 1-channel)
   ├─ Block 1: 64 features  ──────────────────┐
   ├─ Block 2: 24 features  ─────────────┐    │
   ├─ Block 3: 32 features  ────────┐    │    │
   ├─ Block 4: 96 features  ───┐    │    │    │
   └─ Block 5: 320 features    │    │    │    │
                                │    │    │    │
                Decoder:        │    │    │    │
   ├─ Up + Concat ◄────────────┘    │    │    │
   ├─ Up + Concat ◄─────────────────┘    │    │
   ├─ Up + Concat ◄──────────────────────┘    │
   ├─ Up + Concat ◄───────────────────────────┘
   └─ Conv 1×1 → Sigmoid
                                │
                                ▼
Output: 256×256×1 (TCC probability map)
```

**Training:** Self-supervised with pseudo-labels from physics-based thresholding (BT < 235K) + morphological refinement. No manual annotation required.

## Key Design Decisions

1. **MobileNetV2 encoder** — lightweight enough for real-time inference on CPU/MPS, accurate enough for TCC detection
2. **Tiled inference** — handles arbitrary resolution by splitting into 256×256 patches with overlap
3. **Physics-based classification** — BT thresholds from meteorological literature (Hennon et al., 2011)
4. **SQLite** — zero-config database suitable for single-user deployment
5. **NetCDF output** — CF-compliant format standard in atmospheric science
