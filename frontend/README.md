# 3-Frontend: User Interface

## Overview
React-based dashboard for real-time tropical cloud cluster monitoring and analysis visualization.

**Framework:** React + Vite  
**UI Library:** shadcn/ui + Tailwind CSS  
**State Management:** React Query  
**Routing:** React Router

---

## Directory Structure
```
3-frontend/
├── src/
│   ├── components/
│   │   ├── dashboard/       # Dashboard components
│   │   ├── landing/         # Landing page
│   │   └── ui/             # shadcn/ui components
│   ├── pages/              # Route pages
│   ├── hooks/              # Custom React hooks
│   ├── lib/                # Utilities
│   └── main.jsx            # Entry point
├── package.json
├── vite.config.js
└── tailwind.config.js
```

---

## Setup

### 1. Install Dependencies
```bash
cd 3-frontend
npm install
```

### 2. Configure API Endpoint
Edit `src/config.js` (or create it):
```javascript
export const API_BASE_URL = "http://localhost:8000";
```

Or use environment variables:
```bash
# Create .env.local
VITE_API_URL=http://localhost:8000
```

---

## Running the App

### Development
```bash
npm run dev
```
**App will be available at:** http://localhost:5173

### Production Build
```bash
npm run build
npm run preview  # Preview production build
```

### Build Output
```bash
dist/
├── index.html
├── assets/
│   ├── index-[hash].js
│   └── index-[hash].css
```

---

## Features

### 1. Authentication
- **Login:** `/login`
- **Signup:** `/signup`
- JWT token stored in `localStorage`

### 2. Dashboard
- **Real-time Cluster Table:** Shows detected TCCs
- **Trajectory Visualization:** Kalman-smoothed path
- **KPI Cards:** Active clusters, min BT, cloud height
- **Live Sync Button:** Trigger MOSDAC data fetch

### 3. Data Upload
- **Manual Validation:** Upload H5 files for testing
- **Pipeline Status:** Real-time processing feedback

### 4. Analysis
- **Trajectory Plot:** Interactive visualization
- **Cluster Details:** Centroid, radius, status

---

## Connection to Backend

### API Integration
All API calls use Axios with JWT authentication:

```javascript
import axios from 'axios';

const API_URL = 'http://localhost:8000';

// Login
const login = async (email, password) => {
  const response = await axios.post(`${API_URL}/api/auth/login`, {
    email,
    password
  });
  localStorage.setItem('token', response.data.access_token);
  return response.data;
};

// Fetch clusters
const getClusters = async () => {
  const token = localStorage.getItem('token');
  const response = await axios.get(`${API_URL}/api/analysis/clusters`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return response.data;
};
```

### Key Components

#### ClusterTable.jsx
Fetches and displays live cluster data:
```javascript
const { data: clusters } = useQuery(['clusters'], async () => {
  const res = await axios.get(`${API_URL}/api/analysis/clusters`, {
    headers: { Authorization: `Bearer ${token}` }
  });
  return res.data;
}, { refetchInterval: 5000 }); // Auto-refresh every 5s
```

#### LiveSyncButton.jsx
Triggers MOSDAC pipeline:
```javascript
const handleSync = async () => {
  await axios.post(`${API_URL}/api/pipeline/run`, {
    username: creds.username,
    password: creds.password,
    dataset_id: "3RIMG_L1C_ASIA_MER",
    start_date: new Date().toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0]
  }, {
    headers: { Authorization: `Bearer ${token}` }
  });
};
```

---

## Pages & Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | `Landing.jsx` | Landing page |
| `/login` | `Login.jsx` | User login |
| `/signup` | `Signup.jsx` | User registration |
| `/dashboard` | `Dashboard.jsx` | Main dashboard |
| `/dashboard/upload` | `DataUpload.jsx` | Manual file upload |
| `/analysis` | `Analysis.jsx` | Trajectory visualization |

---

## Styling

### Tailwind CSS
Custom theme in `tailwind.config.js`:
```javascript
theme: {
  extend: {
    colors: {
      slate: { /* dark theme */ },
      cyan: { /* accent color */ }
    }
  }
}
```

### Component Library
Uses shadcn/ui components:
- `Button`, `Input`, `Dialog`, `Label`
- `Table`, `Card`, `Toast`
- All in `src/components/ui/`

---

## Troubleshooting

**Blank white screen:**
```bash
# Check browser console for errors
# Common issues:
# 1. Missing UI components → Run: npm install
# 2. API not running → Start backend first
# 3. CORS errors → Check backend allow_origins
```

**Build errors:**
```bash
# Clear cache and rebuild
rm -rf node_modules dist
npm install
npm run build
```

**API connection failed:**
```javascript
// Verify API URL in axios calls
console.log('API URL:', 'http://localhost:8000');

// Check if backend is running
curl http://localhost:8000/health
```

**Hot reload not working:**
```bash
# Restart dev server
npm run dev
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_API_URL` | Backend API URL | `http://localhost:8000` |

---

## Development

### Adding New Components
```bash
# Using shadcn/ui CLI
npx shadcn-ui@latest add [component-name]
```

### Code Formatting
```bash
npm run format  # If configured
```

### Linting
```bash
npm run lint
```

---

## Deployment

### Build for Production
```bash
npm run build
```

### Deploy to Vercel
```bash
vercel --prod
```

### Deploy to Netlify
```bash
netlify deploy --prod --dir=dist
```

### Environment Variables (Production)
Set `VITE_API_URL` to your production backend URL.

---

## Browser Support
- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

---

## Performance
- **Bundle Size:** ~500KB (gzipped: ~160KB)
- **First Load:** <2s
- **Lighthouse Score:** 90+
