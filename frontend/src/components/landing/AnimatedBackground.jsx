import { useEffect, useRef } from 'react';

const AnimatedBackground = () => {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationId;
    let particles = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      initParticles();
    };

    const initParticles = () => {
      particles = [];
      const count = Math.floor((canvas.width * canvas.height) / 15000);
      for (let i = 0; i < count; i++) {
        particles.push({
          x: Math.random() * canvas.width,
          y: Math.random() * canvas.height,
          vx: (Math.random() - 0.5) * 0.5,
          vy: (Math.random() - 0.5) * 0.3,
          size: Math.random() * 2 + 1,
          opacity: Math.random() * 0.5 + 0.2,
        });
      }
    };

    const drawGrid = () => {
      ctx.strokeStyle = 'rgba(0, 180, 216, 0.03)';
      ctx.lineWidth = 1;
      const gridSize = 60;
      const offsetX = (Date.now() * 0.01) % gridSize;
      const offsetY = (Date.now() * 0.005) % gridSize;

      for (let x = -gridSize + offsetX; x < canvas.width + gridSize; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, canvas.height);
        ctx.stroke();
      }

      for (let y = -gridSize + offsetY; y < canvas.height + gridSize; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
      }
    };

    const drawParticles = () => {
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;

        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(0, 180, 216, ${p.opacity})`;
        ctx.fill();
      });

      // Draw connections
      ctx.strokeStyle = 'rgba(0, 180, 216, 0.05)';
      ctx.lineWidth = 0.5;

      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 100) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }
    };

    const drawGlobe = () => {
      const centerX = canvas.width * 0.7;
      const centerY = canvas.height * 0.5;
      const radius = Math.min(canvas.width, canvas.height) * 0.3;

      // Outer glow
      const gradient = ctx.createRadialGradient(
        centerX, centerY, radius * 0.8,
        centerX, centerY, radius * 1.5
      );
      gradient.addColorStop(0, 'rgba(0, 180, 216, 0.1)');
      gradient.addColorStop(1, 'rgba(0, 180, 216, 0)');
      ctx.fillStyle = gradient;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Globe outline
      ctx.strokeStyle = 'rgba(0, 180, 216, 0.2)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
      ctx.stroke();

      // Latitude lines
      const time = Date.now() * 0.0003;
      for (let i = -3; i <= 3; i++) {
        const lat = (i * Math.PI) / 8;
        ctx.beginPath();
        for (let lon = 0; lon <= Math.PI * 2; lon += 0.1) {
          const x = centerX + radius * Math.sin(lon) * Math.cos(lat);
          const y = centerY + radius * Math.sin(lat);
          if (lon === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // Longitude lines
      for (let i = -4; i <= 4; i++) {
        const lon = (i * Math.PI) / 4 + time;
        ctx.beginPath();
        for (let lat = -Math.PI / 2; lat <= Math.PI / 2; lat += 0.1) {
          const x = centerX + radius * Math.sin(lon) * Math.cos(lat);
          const y = centerY + radius * Math.sin(lat);
          if (lat === -Math.PI / 2) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      // Cloud clusters
      const clusters = [
        { lon: 0.5, lat: 0.2, size: 8, pulse: 0 },
        { lon: -0.3, lat: -0.1, size: 6, pulse: 2 },
        { lon: 0.1, lat: 0.4, size: 10, pulse: 4 },
        { lon: -0.6, lat: 0.3, size: 7, pulse: 1 },
      ];

      clusters.forEach((cluster) => {
        cluster.lon += 0.002;
        if (cluster.lon > Math.PI) cluster.lon -= Math.PI * 2;

        const x = centerX + radius * Math.sin(cluster.lon) * Math.cos(cluster.lat);
        const y = centerY + radius * Math.sin(cluster.lat) * 0.3;
        const visible = Math.cos(cluster.lon) > -0.2;

        if (visible) {
          const pulseSize = cluster.size + Math.sin(Date.now() * 0.003 + cluster.pulse) * 2;

          // Glow
          const glowGradient = ctx.createRadialGradient(x, y, 0, x, y, pulseSize * 3);
          glowGradient.addColorStop(0, 'rgba(0, 180, 216, 0.4)');
          glowGradient.addColorStop(1, 'rgba(0, 180, 216, 0)');
          ctx.fillStyle = glowGradient;
          ctx.beginPath();
          ctx.arc(x, y, pulseSize * 3, 0, Math.PI * 2);
          ctx.fill();

          // Core
          ctx.fillStyle = 'rgba(0, 220, 255, 0.8)';
          ctx.beginPath();
          ctx.arc(x, y, pulseSize * 0.5, 0, Math.PI * 2);
          ctx.fill();
        }
      });
    };

    const animate = () => {
      ctx.fillStyle = 'rgba(11, 14, 17, 0.95)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      drawGrid();
      drawGlobe();
      drawParticles();

      animationId = requestAnimationFrame(animate);
    };

    resize();
    window.addEventListener('resize', resize);
    animate();

    return () => {
      window.removeEventListener('resize', resize);
      cancelAnimationFrame(animationId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-full h-full pointer-events-none z-0"
    />
  );
};

export default AnimatedBackground;

