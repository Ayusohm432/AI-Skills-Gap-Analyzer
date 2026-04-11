import React, { useEffect, useRef } from 'react';

export default function InteractiveBackground() {
    const canvasRef = useRef(null);

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        let animationFrameId;
        let particles = [];

        // Mouse interaction state
        const mouse = {
            x: null,
            y: null,
            radius: 150 // Connection radius for mouse interaction
        };

        const handleMouseMove = (event) => {
            mouse.x = event.x;
            mouse.y = event.y;
        };

        const handleMouseLeave = () => {
            mouse.x = null;
            mouse.y = null;
        };

        const resizeCanvas = () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            initParticles();
        };

        class Particle {
            constructor(x, y, dx, dy, size) {
                this.x = x;
                this.y = y;
                this.dx = dx;
                this.dy = dy;
                this.size = size;
            }

            draw() {
                ctx.beginPath();
                ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2, false);
                ctx.fillStyle = 'rgba(56, 189, 248, 0.5)'; // Tailwind sky-400 with opacity
                ctx.fill();
                ctx.closePath();
            }

            update() {
                // Bounce off edges
                if (this.x + this.size > canvas.width || this.x - this.size < 0) this.dx = -this.dx;
                if (this.y + this.size > canvas.height || this.y - this.size < 0) this.dy = -this.dy;

                // Move particle
                this.x += this.dx;
                this.y += this.dy;

                // Interaction with mouse
                if (mouse.x != null && mouse.y != null) {
                    let dx = mouse.x - this.x;
                    let dy = mouse.y - this.y;
                    let distance = Math.sqrt(dx * dx + dy * dy);

                    if (distance < mouse.radius) {
                        // Push particles away slightly from mouse center
                        const forceDirectionX = dx / distance;
                        const forceDirectionY = dy / distance;
                        const force = (mouse.radius - distance) / mouse.radius;

                        // Push multiplier
                        this.x -= forceDirectionX * force * 1.5;
                        this.y -= forceDirectionY * force * 1.5;
                    }
                }

                this.draw();
            }
        }

        const initParticles = () => {
            particles = [];
            // Calculate number of particles based on screen size
            const numberOfParticles = (canvas.width * canvas.height) / 12000;

            for (let i = 0; i < numberOfParticles; i++) {
                let size = Math.random() * 2 + 1;
                let x = Math.random() * (canvas.width - size * 2) + size;
                let y = Math.random() * (canvas.height - size * 2) + size;
                let dx = (Math.random() - 0.5) * 1.5;
                let dy = (Math.random() - 0.5) * 1.5;

                particles.push(new Particle(x, y, dx, dy, size));
            }
        };

        // Draw lines between close particles
        const connectParticles = () => {
            for (let a = 0; a < particles.length; a++) {
                for (let b = a; b < particles.length; b++) {
                    let dx = particles[a].x - particles[b].x;
                    let dy = particles[a].y - particles[b].y;
                    let distance = Math.sqrt(dx * dx + dy * dy);

                    if (distance < 120) {
                        let opacity = 1 - (distance / 120);
                        ctx.strokeStyle = `rgba(59, 130, 246, ${opacity * 0.3})`; // Tailwind blue-500
                        ctx.lineWidth = 1;
                        ctx.beginPath();
                        ctx.moveTo(particles[a].x, particles[a].y);
                        ctx.lineTo(particles[b].x, particles[b].y);
                        ctx.stroke();
                        ctx.closePath();
                    }
                }
            }

            // Also connect to mouse
            if (mouse.x != null && mouse.y != null) {
                for (let i = 0; i < particles.length; i++) {
                    let dx = particles[i].x - mouse.x;
                    let dy = particles[i].y - mouse.y;
                    let distance = Math.sqrt(dx * dx + dy * dy);
                    if (distance < mouse.radius) {
                        let opacity = 1 - (distance / mouse.radius);
                        ctx.strokeStyle = `rgba(167, 139, 250, ${opacity * 0.5})`; // Tailwind violet-400
                        ctx.lineWidth = 1.5;
                        ctx.beginPath();
                        ctx.moveTo(particles[i].x, particles[i].y);
                        ctx.lineTo(mouse.x, mouse.y);
                        ctx.stroke();
                        ctx.closePath();
                    }
                }
            }
        };

        const animate = () => {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            for (let i = 0; i < particles.length; i++) {
                particles[i].update();
            }
            connectParticles();
            animationFrameId = requestAnimationFrame(animate);
        };

        window.addEventListener('resize', resizeCanvas);
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseleave', handleMouseLeave);

        resizeCanvas();
        animate();

        return () => {
            window.removeEventListener('resize', resizeCanvas);
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseleave', handleMouseLeave);
            cancelAnimationFrame(animationFrameId);
        };
    }, []);

    return (
        <>
            {/* Interactive Canvas Background using fixed instead of absolute so it remains in view during scrolling */}
            <canvas
                ref={canvasRef}
                className="fixed inset-0 z-[-1] pointer-events-auto"
                style={{ background: '#020617' }}
            />
            {/* Static CSS Layer overlays over canvas for extra depth */}
            <div className="fixed inset-0 z-[-1] pointer-events-none overflow-hidden">
                {/* Animated Grid */}
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#1e293b_1px,transparent_1px),linear-gradient(to_bottom,#1e293b_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-20 animation-pan-grid"></div>

                {/* Floating Orbs representing 'Nodes' of Knowledge */}
                <div className="absolute top-[20%] left-[15%] w-72 h-72 bg-blue-600/20 rounded-full blur-[100px] animate-float-slow"></div>
                <div className="absolute bottom-[20%] right-[15%] w-96 h-96 bg-indigo-600/20 rounded-full blur-[100px] animate-float-medium delay-1000"></div>
                <div className="absolute top-[40%] right-[30%] w-64 h-64 bg-cyan-600/10 rounded-full blur-[80px] animate-float-fast delay-700"></div>

                {/* Interactive Floating Education & Tech Icons */}
                <div className="absolute inset-0">
                    <div className="absolute top-[15%] left-[25%] opacity-30 animate-float-icon-1"><svg className="w-12 h-12 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M12 14l9-5-9-5-9 5 9 5z" /><path d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 14l9-5-9-5-9 5 9 5zm0 0l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14zm-4 6v-7.5l4-2.222" /></svg></div>
                    <div className="absolute top-[60%] left-[10%] opacity-20 animate-float-icon-2"><svg className="w-16 h-16 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" /></svg></div>
                    <div className="absolute top-[25%] right-[15%] opacity-20 animate-float-icon-3"><svg className="w-14 h-14 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg></div>
                    <div className="absolute bottom-[30%] right-[25%] opacity-30 animate-float-icon-4"><svg className="w-10 h-10 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" /></svg></div>
                    <div className="absolute top-[5%] right-[40%] opacity-25 animate-float-icon-5"><svg className="w-8 h-8 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" /></svg></div>
                </div>
            </div>

            {/* Inject custom CSS keyframes for the bespoke animations */}
            <style dangerouslySetInnerHTML={{
                __html: `
        @keyframes panGrid {
          0% { transform: translateY(0); }
          100% { transform: translateY(4rem); }
        }
        .animation-pan-grid {
          animation: panGrid 4s linear infinite;
        }

        @keyframes floatSlow {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(30px, -50px) scale(1.1); }
          66% { transform: translate(-20px, 20px) scale(0.9); }
        }
        .animate-float-slow {
          animation: floatSlow 15s ease-in-out infinite;
        }

        @keyframes floatMedium {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(-40px, 40px) scale(1.1); }
          66% { transform: translate(40px, -20px) scale(0.9); }
        }
        .animate-float-medium {
          animation: floatMedium 12s ease-in-out infinite;
        }

        @keyframes floatFast {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(20px, 30px) scale(0.9); }
          66% { transform: translate(-30px, -40px) scale(1.1); }
        }
        .animate-float-fast {
          animation: floatFast 9s ease-in-out infinite;
        }

        @keyframes shimmer {
          100% { transform: translateX(150%); }
        }
        .animate-shimmer {
          animation: shimmer 1.5s ease-in-out infinite;
        }

        /* Specialized Icon Animations */
        @keyframes floatIcon1 {
          0%, 100% { transform: translate(0, 0) rotate(0deg); }
          50% { transform: translate(15px, -25px) rotate(10deg); }
        }
        .animate-float-icon-1 { animation: floatIcon1 10s ease-in-out infinite; }

        @keyframes floatIcon2 {
          0%, 100% { transform: translate(0, 0) rotate(0deg); }
          50% { transform: translate(-20px, 15px) rotate(-5deg); }
        }
        .animate-float-icon-2 { animation: floatIcon2 14s ease-in-out infinite; }

        @keyframes floatIcon3 {
          0%, 100% { transform: translate(0, 0) scale(1) rotate(0deg); }
          50% { transform: translate(25px, 20px) scale(1.1) rotate(15deg); }
        }
        .animate-float-icon-3 { animation: floatIcon3 18s ease-in-out infinite; }

        @keyframes floatIcon4 {
          0%, 100% { transform: translate(0, 0) rotate(0deg); }
          50% { transform: translate(-15px, -20px) rotate(-10deg); }
        }
        .animate-float-icon-4 { animation: floatIcon4 12s ease-in-out infinite; }

        @keyframes floatIcon5 {
          0%, 100% { transform: translate(0, 0) rotate(-10deg); }
          50% { transform: translate(10px, 30px) rotate(5deg); }
        }
        .animate-float-icon-5 { animation: floatIcon5 16s ease-in-out infinite; }
      `}} />
        </>
    );
}
