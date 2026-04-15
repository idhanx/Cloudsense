/**
 * CloudSense — TCC Cluster Map
 * Leaflet dark map with correct field names, clear-on-new-data, and Home button.
 */

import { useEffect, useState, useRef, memo } from 'react';
import { MapPin, RefreshCw, Trash2 } from 'lucide-react';
import apiClient from '@/services/api';

const CLASSIFICATION_COLOR = {
  'Confirmed TCC': '#ef4444',
  'Probable TCC': '#f59e0b',
  'Possible TCC': '#06b6d4',
  'Cloud Cluster': '#64748b',
};

const ClusterMap = () => {
  const mapRef = useRef(null);
  const mapInstance = useRef(null);
  const markersRef = useRef([]);
  const [clusters, setClusters] = useState([]);
  const [leafletLoaded, setLeafletLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  // ── Load Leaflet once ──
  useEffect(() => {
    if (window.L) { setLeafletLoaded(true); return; }

    const css = document.createElement('link');
    css.rel = 'stylesheet';
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
    document.head.appendChild(css);

    const js = document.createElement('script');
    js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
    js.onload = () => setLeafletLoaded(true);
    document.head.appendChild(js);
  }, []);

  // ── Fetch clusters ──
  const fetchClusters = async () => {
    setLoading(true);
    try {
      const data = await apiClient.getClusters(100);
      setClusters(Array.isArray(data) ? data : []);
      setLastUpdated(new Date());
    } catch { setClusters([]); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchClusters();
    const t = setInterval(fetchClusters, 60000);
    return () => clearInterval(t);
  }, []);

  // ── Init map ──
  useEffect(() => {
    if (!leafletLoaded || !mapRef.current || mapInstance.current) return;
    const L = window.L;
    const map = L.map(mapRef.current, {
      center: [15, 80],
      zoom: 4,
      zoomControl: true,
      attributionControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 18,
    }).addTo(map);

    // Attribution small
    L.control.attribution({ prefix: false, position: 'bottomright' })
      .addAttribution('© <a href="https://carto.com/" style="color:#64748b">CARTO</a>')
      .addTo(map);

    mapInstance.current = map;
    return () => { map.remove(); mapInstance.current = null; };
  }, [leafletLoaded]);

  // ── Update markers ──
  useEffect(() => {
    if (!mapInstance.current || !window.L) return;
    const L = window.L;
    const map = mapInstance.current;

    // Clear old markers
    markersRef.current.forEach(l => map.removeLayer(l));
    markersRef.current = [];

    if (clusters.length === 0) return;

    clusters.forEach((c) => {
      const lat = c.centroid_lat;
      const lon = c.centroid_lon;
      if (lat == null || lon == null) return;

      const cls = c.classification || 'Cloud Cluster';
      const color = CLASSIFICATION_COLOR[cls] || '#06b6d4';
      const area = c.area_km2 || 0;
      const r = c.radius_mean_km || c.radius_km || Math.sqrt(area / Math.PI) || 100;

      // Radius circle
      const circle = L.circle([lat, lon], {
        radius: r * 1000,
        color,
        fillColor: color,
        fillOpacity: 0.12,
        weight: 1.5,
        dashArray: '4 4',
      }).addTo(map);

      // Center dot
      const dot = L.circleMarker([lat, lon], {
        radius: 7,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        fillOpacity: 1,
      }).addTo(map);

      const popupHtml = `
        <div style="font:13px/1.5 system-ui;min-width:180px;color:#e2e8f0;background:#0f172a;padding:4px">
          <b style="color:${color};font-size:14px">TCC-${c.cluster_id || '?'}</b>
          <div style="color:#94a3b8;font-size:11px;margin-bottom:6px">${cls}</div>
          <div>📍 ${lat.toFixed(2)}°, ${lon.toFixed(2)}°</div>
          ${area ? `<div>� Area: ${area.toLocaleString()} km²</div>` : ''}
          ${r ? `<div>� Radius: ${r.toFixed(0)} km</div>` : ''}
          ${c.min_bt ? `<div>❄️ Min BT: ${c.min_bt.toFixed(1)} K</div>` : ''}
          ${c.mean_bt ? `<div>🌡 Mean BT: ${c.mean_bt.toFixed(1)} K</div>` : ''}
        </div>`;

      dot.bindPopup(popupHtml, { className: 'tcc-popup' });
      circle.bindPopup(popupHtml, { className: 'tcc-popup' });

      markersRef.current.push(circle, dot);
    });

    // Fit bounds if we have markers
    if (markersRef.current.length > 0) {
      try {
        const latlngs = clusters
          .filter(c => c.centroid_lat != null && c.centroid_lon != null)
          .map(c => [c.centroid_lat, c.centroid_lon]);
        if (latlngs.length > 0) {
          map.fitBounds(L.latLngBounds(latlngs), { padding: [40, 40], maxZoom: 6 });
        }
      } catch { /* ignore */ }
    }
  }, [clusters, leafletLoaded]);

  const clearClusters = () => {
    if (!mapInstance.current || !window.L) return;
    markersRef.current.forEach(l => mapInstance.current.removeLayer(l));
    markersRef.current = [];
    setClusters([]);
  };

  const resetView = () => {
    if (mapInstance.current) mapInstance.current.setView([15, 80], 4);
  };

  return (
    <div className="relative h-full w-full bg-[#0a0e1a]">
      {/* Popup style injection */}
      <style>{`
        .tcc-popup .leaflet-popup-content-wrapper {
          background: #0f172a;
          border: 1px solid #1e293b;
          border-radius: 8px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.5);
        }
        .tcc-popup .leaflet-popup-tip { background: #0f172a; }
        .leaflet-popup-close-button { color: #64748b !important; }
      `}</style>

      {/* Map container */}
      <div ref={mapRef} className="h-full w-full" />

      {/* Top-right controls */}
      <div className="absolute top-3 right-3 z-[1000] flex gap-2">
        <button
          onClick={fetchClusters}
          title="Refresh"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900/90 border border-slate-700 rounded-lg text-xs text-slate-300 hover:text-white hover:bg-slate-800 transition-colors backdrop-blur-sm"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
        <button
          onClick={clearClusters}
          title="Clear all markers"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900/90 border border-slate-700 rounded-lg text-xs text-slate-300 hover:text-red-400 hover:bg-slate-800 transition-colors backdrop-blur-sm"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Clear
        </button>
        <button
          onClick={resetView}
          title="Reset view"
          className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900/90 border border-slate-700 rounded-lg text-xs text-slate-300 hover:text-cyan-400 hover:bg-slate-800 transition-colors backdrop-blur-sm"
        >
          <MapPin className="w-3.5 h-3.5" />
          Home
        </button>
      </div>

      {/* Bottom legend */}
      <div className="absolute bottom-3 left-3 z-[1000] bg-slate-900/90 border border-slate-700 rounded-lg px-3 py-2 backdrop-blur-sm">
        <div className="flex flex-wrap gap-3 text-xs text-slate-400">
          {Object.entries(CLASSIFICATION_COLOR).map(([label, color]) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
              <span>{label}</span>
            </div>
          ))}
          <span className="text-slate-500 border-l border-slate-700 pl-3">
            {clusters.length} cluster{clusters.length !== 1 ? 's' : ''}
            {lastUpdated && ` · ${lastUpdated.toLocaleTimeString()}`}
          </span>
        </div>
      </div>

      {/* Empty state */}
      {!loading && clusters.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-[999]">
          <div className="bg-slate-900/80 border border-slate-700 rounded-xl px-6 py-4 text-center backdrop-blur-sm">
            <MapPin className="w-8 h-8 text-slate-600 mx-auto mb-2" />
            <p className="text-sm text-slate-400">No clusters detected yet</p>
            <p className="text-xs text-slate-600 mt-1">Upload satellite data to see detections</p>
          </div>
        </div>
      )}
    </div>
  );
};

export default memo(ClusterMap);
