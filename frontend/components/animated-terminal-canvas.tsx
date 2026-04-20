"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";

type CanvasVariant = "market" | "signal";
type IdleCallback = () => void;
type IdleWindow = Window & {
  requestIdleCallback?: (callback: IdleCallback, options?: { timeout: number }) => number;
  cancelIdleCallback?: (handle: number) => void;
};

function resizeCanvas(canvas: HTMLCanvasElement, context: CanvasRenderingContext2D) {
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.floor(canvas.offsetWidth * ratio);
  canvas.height = Math.floor(canvas.offsetHeight * ratio);
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function drawMarketGrid(canvas: HTMLCanvasElement) {
  const context = canvas.getContext("2d");
  if (!context) return () => undefined;

  let frame = 0;
  let animation = 0;
  const resize = () => resizeCanvas(canvas, context);

  const draw = () => {
    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    context.clearRect(0, 0, width, height);
    context.globalAlpha = 0.8;
    context.strokeStyle = "rgba(0,255,136,0.11)";
    context.lineWidth = 1;

    for (let x = (frame % 42) - 42; x < width; x += 42) {
      context.beginPath();
      context.moveTo(x, 0);
      context.lineTo(x, height);
      context.stroke();
    }
    for (let y = 0; y < height; y += 42) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }

    const baseY = height * 0.56;
    const step = Math.max(14, width / 74);
    let price = baseY;
    for (let index = -4; index < 78; index += 1) {
      const x = index * step + ((frame * 0.42) % step);
      const drift = Math.sin((index + frame * 0.02) * 0.42) * 16;
      const open = price + drift * 0.26;
      const close = open + Math.cos((index + frame * 0.04) * 0.8) * 18;
      const high = Math.min(open, close) - 18 - Math.sin(index) * 6;
      const low = Math.max(open, close) + 18 + Math.cos(index) * 6;
      const up = close <= open;
      context.strokeStyle = up ? "rgba(0,255,136,0.72)" : "rgba(255,77,102,0.68)";
      context.fillStyle = up ? "rgba(0,255,136,0.45)" : "rgba(255,77,102,0.42)";
      context.beginPath();
      context.moveTo(x, high);
      context.lineTo(x, low);
      context.stroke();
      context.fillRect(x - 3, Math.min(open, close), 6, Math.max(2, Math.abs(close - open)));
      price = close;
    }

    context.globalAlpha = 1;
    context.strokeStyle = "rgba(0,229,255,0.52)";
    context.beginPath();
    for (let index = 0; index < 120; index += 1) {
      const x = (index / 119) * width;
      const y = height * 0.72 + Math.sin(index * 0.18 + frame * 0.035) * 26;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.stroke();

    frame += 1;
    animation = window.requestAnimationFrame(draw);
  };

  resize();
  window.addEventListener("resize", resize);
  draw();
  return () => {
    window.removeEventListener("resize", resize);
    window.cancelAnimationFrame(animation);
  };
}

function drawSignalWave(canvas: HTMLCanvasElement) {
  const context = canvas.getContext("2d");
  if (!context) return () => undefined;

  let frame = 0;
  let animation = 0;
  const resize = () => resizeCanvas(canvas, context);

  const draw = () => {
    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    context.clearRect(0, 0, width, height);
    context.strokeStyle = "rgba(0,255,136,0.1)";
    for (let y = 20; y < height; y += 34) {
      context.beginPath();
      context.moveTo(0, y);
      context.lineTo(width, y);
      context.stroke();
    }

    context.beginPath();
    for (let index = 0; index < 100; index += 1) {
      const x = (index / 99) * width;
      const y = height * 0.52 + Math.sin(index * 0.22 + frame * 0.04) * 34 + Math.cos(index * 0.09) * 18;
      if (index === 0) context.moveTo(x, y);
      else context.lineTo(x, y);
    }
    context.strokeStyle = "#00ff88";
    context.lineWidth = 2;
    context.shadowColor = "rgba(0,255,136,0.45)";
    context.shadowBlur = 14;
    context.stroke();
    context.shadowBlur = 0;

    frame += 1;
    animation = window.requestAnimationFrame(draw);
  };

  resize();
  window.addEventListener("resize", resize);
  draw();
  return () => {
    window.removeEventListener("resize", resize);
    window.cancelAnimationFrame(animation);
  };
}

function shouldReduceMotion() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function AnimatedTerminalCanvas({
  variant,
  className
}: {
  variant: CanvasVariant;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!canvasRef.current || shouldReduceMotion()) {
      return undefined;
    }

    const idleWindow = window as IdleWindow;
    const start = () => (variant === "market" ? drawMarketGrid(canvasRef.current!) : drawSignalWave(canvasRef.current!));
    let cleanup: (() => void) | undefined;
    let timeoutId = 0;
    let idleId: number | undefined;

    if (idleWindow.requestIdleCallback) {
      idleId = idleWindow.requestIdleCallback(() => {
        cleanup = start();
      }, { timeout: 450 });
    } else {
      timeoutId = window.setTimeout(() => {
        cleanup = start();
      }, 160);
    }

    return () => {
      if (idleId !== undefined && idleWindow.cancelIdleCallback) {
        idleWindow.cancelIdleCallback(idleId);
      }
      if (timeoutId) {
        window.clearTimeout(timeoutId);
      }
      cleanup?.();
    };
  }, [variant]);

  return <canvas ref={canvasRef} aria-hidden className={cn("terminal-canvas", className)} />;
}
