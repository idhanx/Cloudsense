import { useEffect, useRef, useState } from 'react';
import apiClient from '@/services/api';

const WorldMap = () => {
  const canvasRef = useRef(null);
  const [clusters, setClusters] = useState([]);

  useEffect(() => {
    const fetchClusters = async () => {
      try {
        const response = await fetch(`${apiClient.baseURL}/api/analysis/clusters?limit=100`, {
          headers: { 'Authorization': `Bearer ${apiClient.getToken()}` }
        });
        if (response.ok) {
          const data = await response.json();
          // Map backend data format to visualization format
          const mapped = data.map(c => ({
            id: c.id,
            lat: c.centroidLat || 0,
            lon: c.centroidLon || 0,
            radius: c.radius || 50,
            intensity: c.intensity || 0.5
          }));
          setClusters(mapped);
        }
      } catch (error) {
        console.error("Failed to fetch map clusters", error);
      }
    };

    fetchClusters();
    const interval = setInterval(fetchClusters, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId;

    const resize = () => {
      const rect = canvas.parentElement?.getBoundingClientRect();
      if (rect) {
        canvas.width = rect.width;
        canvas.height = rect.height;
      }
    };

    const latLonToXY = (lat, lon) => {
      const x = ((lon + 180) / 360) * canvas.width;
      const y = ((90 - lat) / 180) * canvas.height;
      return { x, y };
    };

    const drawMap = () => {
      // Background
      ctx.fillStyle = 'hsl(220, 20%, 5%)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Grid
      ctx.strokeStyle = 'rgba(0, 180, 216, 0.08)';
      ctx.lineWidth = 0.5;

      // Latitude lines
      for (let lat = -60; lat <= 60; lat += 30) {
        const { y } = latLonToXY(lat, 0);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }

      // Longitude lines
      for (let lon = -120; lon <= 120; lon += 30) {
        const { x } = latLonToXY(0, lon);
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }

      // Tropical zone boundaries (5°N to 5°S)
      const tropicNorth = latLonToXY(5, -180);
      const tropicSouth = latLonToXY(-5, -180);

      ctx.fillStyle = 'rgba(0, 180, 216, 0.03)';
      ctx.fillRect(0, tropicSouth.y, canvas.width, tropicNorth.y - tropicSouth.y);

      // Equator
      const equator = latLonToXY(0, -180);
      ctx.strokeStyle = 'rgba(0, 180, 216, 0.2)';
      ctx.lineWidth = 1;
      ctx.setLineDash([5, 5]);
      ctx.beginPath();
      ctx.moveTo(0, equator.y);
      ctx.lineTo(canvas.width, equator.y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Draw clusters
      const time = Date.now() * 0.002;

      clusters.forEach((cluster) => {
        const { x, y } = latLonToXY(cluster.lat, cluster.lon);
        const pulseSize = cluster.radius + Math.sin(time + cluster.intensity * 10) * 3;

        // Outer glow
        const glowGradient = ctx.createRadialGradient(x, y, 0, x, y, pulseSize * 3);
        glowGradient.addColorStop(0, `rgba(0, 180, 216, ${cluster.intensity * 0.4})`);
        glowGradient.addColorStop(1, 'rgba(0, 180, 216, 0)');
        ctx.fillStyle = glowGradient;
        ctx.beginPath();
        ctx.arc(x, y, pulseSize * 3, 0, Math.PI * 2);
        ctx.fill();

        // Inner circle
        ctx.fillStyle = `rgba(0, 220, 255, ${cluster.intensity * 0.8})`;
        ctx.beginPath();
        ctx.arc(x, y, pulseSize * 0.4, 0, Math.PI * 2);
        ctx.fill();

        // Border ring
        ctx.strokeStyle = `rgba(0, 220, 255, ${cluster.intensity * 0.6})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(x, y, pulseSize, 0, Math.PI * 2);
        ctx.stroke();
      });
    };

    const animate = () => {
      drawMap();
      animationId = requestAnimationFrame(animate);
    };

    resize();
    window.addEventListener('resize', resize);
    animate();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationId);
    };
  }, [clusters]);

  return (
    <div className="bg-card rounded-lg p-4 border border-border h-full">
      {/* Legend */}
      <div className="flex items-center gap-4 mb-4">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-cyan-400"></div>
          <span className="text-xs text-muted-foreground">Active TCC</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-8 h-1 bg-cyan-900/50"></div>
          <span className="text-xs text-muted-foreground">Tropical Zone</span>
        </div>
      </div>

      {/* Active count */}
      <div className="text-center mb-4">
        <span className="text-xs text-muted-foreground uppercase tracking-wider">
          ACTIVE CLUSTERS
        </span>
        <div className="text-2xl font-bold text-white">{clusters.length}</div>
      </div>

      <div className="relative h-[300px]">
        <canvas ref={canvasRef} className="w-full h-full" />
      </div>
    </div>
  );
};

export default WorldMap;

