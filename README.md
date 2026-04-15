# CloudSense

**Tropical Cloud Cluster (TCC) Detection System** — Detects and classifies deep convective cloud systems from INSAT-3D/3DR satellite imagery using deep learning.

## What It Does

CloudSense processes infrared satellite imagery to automatically detect Tropical Cloud Clusters — large convective systems that can develop into tropical cyclones. The system:

1. **Ingests** satellite data — either fetched live from [MOSDAC](https://mosdac.gov.in) (INSAT-3DR) or uploaded manually as HDF5/image files
2. **Runs inference** using a U-Net segmentation model trained on IR brightness temperature data
3. **Classifies** each detection based on minimum brightness temperature:
   - 🔴 **Confirmed TCC** — min BT < 220K (deep convection)
   - 🟡 **Likely TCC** — min BT < 235K
   - ⚪ **Cloud Cluster** — min BT ≥ 235K
4. **Generates outputs** — annotated overlay PNG, binary mask, and CF-compliant NetCDF
5. **Displays results** on an interactive dashboard with detection map, cluster table, and analysis details

## Screenshots

After uploading an H5 file:
- **Dashboard** — KPI cards (active TCCs, min BT, cloud-top height, mean radius), world map with cluster positions, recent analyses feed
- **Analysis** — Side-by-side IR + TCC mask overlay, detection table with classification badges
- **Exports** — Download NetCDF and PNG outputs per analysis

## Quick Start

```bash
# 1. Install backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Install frontend
cd ../frontend
npm install

# 3. Start everything
cd ..
./run.sh
```

Open **http://localhost:5173** → Sign up → Go to **Data Upload** → Upload an `.h5` file or fetch from MOSDAC.

## Requirements

| Dependency | Version |
|------------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| PyTorch | 2.0+ |
| Model weights | `model/best_model.pth` |

## How MOSDAC Fetch Works

1. Enter your [MOSDAC](https://mosdac.gov.in/signup/) credentials on the Data Upload page
2. Set hours back (default: 6) — fetches recent INSAT-3DR imagery
3. System downloads `3RIMG_L1C_ASIA_MER` H5 files via MOSDAC API
4. Each file is automatically run through the U-Net inference pipeline
5. Results appear on the Dashboard, Analysis, and Exports pages

## Project Structure

```
cloudsense/
├── backend/                 # FastAPI + SQLite
│   ├── app.py               # API endpoints (auth, upload, MOSDAC, analysis)
│   ├── inference_engine.py  # U-Net pipeline (core ML)
│   ├── db.py                # Database (users + analyses)
│   ├── mosdac_manager.py    # MOSDAC download orchestrator
│   └── mosdac_engine/       # mdapi.py (MOSDAC Data Access API)
├── frontend/                # React + Vite + shadcn/ui
│   └── src/pages/           # Dashboard, DataUpload, Analysis, Exports
├── model/
│   └── best_model.pth       # Trained U-Net weights (26MB)
└── run.sh                   # Launch script
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| ML Model | PyTorch U-Net with MobileNetV2 encoder |
| Backend | FastAPI, SQLite, NumPy, SciPy, netCDF4 |
| Frontend | React 18, Vite, Tailwind CSS, shadcn/ui |
| Satellite Data | MOSDAC INSAT-3DR `3RIMG_L1C_ASIA_MER` |

## License

See [LICENSE](LICENSE) for details.

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design and API reference.
