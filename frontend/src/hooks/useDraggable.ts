import { useCallback, useEffect, useRef, useState } from "react";

export interface XY {
  x: number;
  y: number;
}

/**
 * Pointer-based dragging for absolutely-positioned nodes on a canvas.
 * Works with mouse and touch. Distinguishes a click from a drag via a 4px
 * threshold so nodes stay clickable.
 */
export function useDraggable(initial: Record<string, XY>, resetKey: string) {
  const [pos, setPos] = useState<Record<string, XY>>(initial);
  const initialRef = useRef(initial);

  useEffect(() => {
    initialRef.current = initial;
    setPos(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey]);

  const drag = useRef<
    { id: string; ox: number; oy: number; sx: number; sy: number; moved: boolean } | null
  >(null);
  const movedRef = useRef(false);

  const onDown = useCallback(
    (id: string, e: React.PointerEvent) => {
      if (e.button !== 0 && e.pointerType === "mouse") return;
      const p = pos[id] || { x: 0, y: 0 };
      drag.current = { id, ox: p.x, oy: p.y, sx: e.clientX, sy: e.clientY, moved: false };
      movedRef.current = false;
    },
    [pos]
  );

  useEffect(() => {
    const move = (e: PointerEvent) => {
      const d = drag.current;
      if (!d) return;
      const dx = e.clientX - d.sx;
      const dy = e.clientY - d.sy;
      if (Math.abs(dx) + Math.abs(dy) > 4) {
        d.moved = true;
        movedRef.current = true;
      }
      setPos((prev) => ({
        ...prev,
        [d.id]: { x: Math.max(0, d.ox + dx), y: Math.max(0, d.oy + dy) },
      }));
    };
    const up = () => {
      drag.current = null;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  const justDragged = () => movedRef.current;
  const dragging = () => drag.current !== null;
  const reset = () => setPos({ ...initialRef.current });

  return { pos, setPos, onDown, justDragged, dragging, reset };
}
