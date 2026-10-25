"use client";

import { useEffect, useRef } from "react";
import { useReducedMotion } from "motion/react";

const QUANTE = 40;
const DISTANZA = 80;

/** Le particelle che scorrono dietro il login, nel colore del brand (`--primary`).
 *  Con "riduci movimento" non c'è niente. */
export function Particelle({ className }: { className?: string }) {
  const shouldReduce = useReducedMotion();
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (shouldReduce || !ref.current) return;
    const canvas = ref.current;
    const ctx = canvas.getContext("2d")!;
    // il token così com'è scritto (oklch, hex…): il canvas accetta qualunque colore CSS
    const colore = getComputedStyle(canvas).getPropertyValue("--primary").trim() || "oklch(0.72 0.11 65)";
    let raf: number;
    let particelle: { x: number; y: number; vx: number }[] = [];

    function resize() {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    }

    function init() {
      resize();
      particelle = Array.from({ length: QUANTE }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: 0.15 + Math.random() * 0.35,
      }));
    }

    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.strokeStyle = colore;
      ctx.fillStyle = colore;
      ctx.lineWidth = 0.5;
      // le linee fra le particelle vicine, più tenui quanto più sono lontane
      for (let i = 0; i < particelle.length; i++) {
        for (let j = i + 1; j < particelle.length; j++) {
          const dist = Math.hypot(particelle[i].x - particelle[j].x, particelle[i].y - particelle[j].y);
          if (dist < DISTANZA) {
            ctx.globalAlpha = (1 - dist / DISTANZA) * 0.12;
            ctx.beginPath();
            ctx.moveTo(particelle[i].x, particelle[i].y);
            ctx.lineTo(particelle[j].x, particelle[j].y);
            ctx.stroke();
          }
        }
      }
      ctx.globalAlpha = 0.25;
      for (const p of particelle) {
        p.x += p.vx;
        if (p.x > canvas.width + 10) p.x = -10;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 1.3, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    }

    init();
    draw();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, [shouldReduce]);

  if (shouldReduce) return null;
  return <canvas ref={ref} className={`pointer-events-none absolute inset-0 h-full w-full ${className ?? ""}`} />;
}
