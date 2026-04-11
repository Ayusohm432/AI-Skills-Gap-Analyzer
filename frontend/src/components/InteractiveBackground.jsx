import React, { useEffect, useRef } from 'react';

export default function InteractiveBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: false });
    let animationFrameId;
    let particles = [];
    let isVisible = true;

    const mouse = { x: null, y: null, radius: 160 };

    const handleMouseMove = (e) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };

    const handleMouseLeave = () => {
      mouse.x = null;
      mouse.y = null;
    };

    // Pause animation when tab is not visible
    const handleVisibility = () => {
      isVisible = !document.hidden;
      if (isVisible) animate();
    };

    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      initParticles();
    };

    // Warm palette
    const colors = [
      [232, 168, 73],   // warm gold
      [217, 107, 93],   // coral
      [91, 184, 166],   // teal
      [155, 142, 196],  // lavender
      [200, 195, 188],  // warm gray
    ];

    class Particle {
      constructor(x, y, dx, dy, size, color) {
        this.x = x;
        this.y = y;
        this.dx = dx;
        this.dy = dy;
        this.size = size;
        this.color = color;
      }

      draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${this.color[0]},${this.color[1]},${this.color[2]},0.3)`;
        ctx.fill();
      }

      update() {
        if (this.x + this.size > canvas.width || this.x - this.size < 0) this.dx = -this.dx;
        if (this.y + this.size > canvas.height || this.y - this.size < 0) this.dy = -this.dy;
        this.x += this.dx;
        this.y += this.dy;

        if (mouse.x != null && mouse.y != null) {
          const dx = mouse.x - this.x;
          const dy = mouse.y - this.y;
          const distSq = dx * dx + dy * dy;
          const radiusSq = mouse.radius * mouse.radius;

          if (distSq < radiusSq) {
            const dist = Math.sqrt(distSq);
            const force = (mouse.radius - dist) / mouse.radius;
            this.x -= (dx / dist) * force * 1.2;
            this.y -= (dy / dist) * force * 1.2;
          }
        }

        this.draw();
      }
    }

    const initParticles = () => {
      particles = [];
      // Cap at 50 particles max for performance
      const count = Math.min(Math.floor((canvas.width * canvas.height) / 25000), 50);
      for (let i = 0; i < count; i++) {
        const size = Math.random() * 1.6 + 0.8;
        const x = Math.random() * (canvas.width - size * 2) + size;
        const y = Math.random() * (canvas.height - size * 2) + size;
        const dx = (Math.random() - 0.5) * 0.6;
        const dy = (Math.random() - 0.5) * 0.6;
        const color = colors[Math.floor(Math.random() * colors.length)];
        particles.push(new Particle(x, y, dx, dy, size, color));
      }
    };

    const connectParticles = () => {
      const len = particles.length;
      const connDist = 130;
      const connDistSq = connDist * connDist;

      for (let a = 0; a < len; a++) {
        // Only check nearby particles — skip every other one for perf
        for (let b = a + 1; b < len; b++) {
          const dx = particles[a].x - particles[b].x;
          const dy = particles[a].y - particles[b].y;
          const distSq = dx * dx + dy * dy;

          if (distSq < connDistSq) {
            const opacity = (1 - Math.sqrt(distSq) / connDist) * 0.12;
            ctx.strokeStyle = `rgba(232,168,73,${opacity})`;
            ctx.lineWidth = 0.6;
            ctx.beginPath();
            ctx.moveTo(particles[a].x, particles[a].y);
            ctx.lineTo(particles[b].x, particles[b].y);
            ctx.stroke();
          }
        }
      }

      // Mouse connections — limit to 8 nearest
      if (mouse.x != null && mouse.y != null) {
        let count = 0;
        for (let i = 0; i < len && count < 8; i++) {
          const dx = particles[i].x - mouse.x;
          const dy = particles[i].y - mouse.y;
          const distSq = dx * dx + dy * dy;
          const radiusSq = mouse.radius * mouse.radius;

          if (distSq < radiusSq) {
            const dist = Math.sqrt(distSq);
            const opacity = (1 - dist / mouse.radius) * 0.25;
            ctx.strokeStyle = `rgba(91,184,166,${opacity})`;
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(mouse.x, mouse.y);
            ctx.stroke();
            count++;
          }
        }
      }
    };

    const animate = () => {
      if (!isVisible) return;

      ctx.fillStyle = '#0f0f0f';
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      for (let i = 0; i < particles.length; i++) {
        particles[i].update();
      }
      connectParticles();
      animationFrameId = requestAnimationFrame(animate);
    };

    // Use passive listeners for scroll perf
    window.addEventListener('resize', resizeCanvas);
    window.addEventListener('mousemove', handleMouseMove, { passive: true });
    window.addEventListener('mouseleave', handleMouseLeave);
    document.addEventListener('visibilitychange', handleVisibility);

    resizeCanvas();
    animate();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseleave', handleMouseLeave);
      document.removeEventListener('visibilitychange', handleVisibility);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <>
      <canvas
        ref={canvasRef}
        className="fixed inset-0 z-[-2]"
        style={{ willChange: 'auto', pointerEvents: 'none' }}
      />
      {/* Ambient warm orbs — pure CSS, no JS cost */}
      <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden">
        <div
          className="absolute top-[15%] left-[10%] w-[400px] h-[400px] rounded-full blur-[120px] animate-float-gentle"
          style={{ background: 'radial-gradient(circle, rgba(232,168,73,0.07) 0%, transparent 70%)', transform: 'translateZ(0)' }}
        />
        <div
          className="absolute bottom-[15%] right-[10%] w-[500px] h-[500px] rounded-full blur-[130px] animate-float-alt"
          style={{ background: 'radial-gradient(circle, rgba(91,184,166,0.05) 0%, transparent 70%)', transform: 'translateZ(0)' }}
        />
      </div>
    </>
  );
}
