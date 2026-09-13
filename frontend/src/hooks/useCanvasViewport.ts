import { useCallback, useEffect, useRef, useState } from "react";

const MIN = 0.35;
const MAX = 2.5;
const STEP = 0.15;
const clamp = (z: number) => Math.min(MAX, Math.max(MIN, +z.toFixed(2)));

/**
 * Zoom + pan + fullscreen for a diagram canvas. Pan starts on the canvas
 * background (not on a `.drag-node`, which keeps its own drag). `zoomRef`
 * mirrors the live zoom so node dragging can divide screen deltas by scale.
 */
export function useCanvasViewport() {
  const frameRef = useRef<HTMLDivElement>(null);      // element sent fullscreen
  const viewportRef = useRef<HTMLDivElement | null>(null);   // clipping viewport
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [fullscreen, setFullscreen] = useState(false);
  const zoomRef = useRef(1);
  useEffect(() => {
    zoomRef.current = zoom;
  }, [zoom]);

  const zoomIn = useCallback(() => setZoom((z) => clamp(z + STEP)), []);
  const zoomOut = useCallback(() => setZoom((z) => clamp(z - STEP)), []);
  const resetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  // Wheel-to-zoom, attached natively so preventDefault is honoured.
  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const dir = e.deltaY > 0 ? -1 : 1;
      setZoom((z) => clamp(z + dir * 0.1));
    };
    vp.addEventListener("wheel", onWheel, { passive: false });
    return () => vp.removeEventListener("wheel", onWheel);
  }, []);

  // Background drag to pan.
  const panStart = useRef<{ sx: number; sy: number; ox: number; oy: number } | null>(null);
  const onBackgroundPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if ((e.target as HTMLElement).closest(".drag-node")) return;
      panStart.current = { sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y };
    },
    [pan]
  );

  useEffect(() => {
    const move = (e: PointerEvent) => {
      const p = panStart.current;
      if (!p) return;
      setPan({ x: p.ox + (e.clientX - p.sx), y: p.oy + (e.clientY - p.sy) });
    };
    const up = () => {
      panStart.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  const toggleFullscreen = useCallback(() => {
    const el = frameRef.current;
    if (!el) return;
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.();
  }, []);

  useEffect(() => {
    const onChange = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  return {
    frameRef,
    viewportRef,
    zoom,
    pan,
    zoomRef,
    fullscreen,
    zoomIn,
    zoomOut,
    resetView,
    toggleFullscreen,
    onBackgroundPointerDown,
  };
}
