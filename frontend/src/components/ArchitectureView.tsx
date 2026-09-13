import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Architecture, ServiceNode } from "../types";
import { useDraggable } from "../hooks/useDraggable";

const KIND_COLOR: Record<string, string> = {
  request: "var(--blue)",
  event: "var(--green)",
  support: "var(--dim)",
  data: "var(--orange)",
};

const LAYER_ORDER = ["ui", "entry", "service", "data", "external"];

const NODE_W = 210;
const COL_GAP = 70;
const ROW_GAP = 66;
const NODE_H = 96;
const PAD = 28;

interface Edge2 {
  path: string;
  color: string;
  dashed: boolean;
  key: string;
  active: boolean;
  label: string;
  lx: number;
  ly: number;
}

export default function ArchitectureView({ arch }: { arch: Architecture }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [edges, setEdges] = useState<Edge2[]>([]);
  const [selected, setSelected] = useState<ServiceNode | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  // Initial layered layout: rows by layer, columns within a layer.
  const { initial, canvasH } = useMemo(() => {
    const byLayer = new Map<string, ServiceNode[]>();
    for (const n of arch.nodes) {
      const layer = LAYER_ORDER.includes(n.layer) ? n.layer : "service";
      (byLayer.get(layer) || byLayer.set(layer, []).get(layer)!).push(n);
    }
    const rows = LAYER_ORDER.filter((l) => byLayer.has(l));
    const init: Record<string, { x: number; y: number }> = {};
    rows.forEach((layer, ri) => {
      const nodes = byLayer.get(layer)!;
      nodes.forEach((n, ci) => {
        init[n.id] = { x: PAD + ci * (NODE_W + COL_GAP), y: PAD + ri * (NODE_H + ROW_GAP) };
      });
    });
    return { initial: init, canvasH: PAD * 2 + rows.length * (NODE_H + ROW_GAP) };
  }, [arch]);

  const resetKey = useMemo(() => arch.nodes.map((n) => n.id).join(","), [arch]);
  const { pos, onDown, justDragged, reset } = useDraggable(initial, resetKey);

  const recompute = () => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const box = wrap.getBoundingClientRect();
    setSize({ w: Math.max(box.width, wrap.scrollWidth), h: Math.max(box.height, wrap.scrollHeight) });
    const c: Record<string, { x: number; y: number }> = {};
    for (const n of arch.nodes) {
      const el = nodeRefs.current[n.id];
      if (!el) continue;
      c[n.id] = {
        x: el.offsetLeft + el.offsetWidth / 2,
        y: el.offsetTop + el.offsetHeight / 2,
      };
    }
    const next: Edge2[] = [];
    arch.edges.forEach((e, i) => {
      const a = c[e.source];
      const b = c[e.target];
      if (!a || !b) return;
      const active = !!selected && (selected.id === e.source || selected.id === e.target);
      const midY = (a.y + b.y) / 2;
      next.push({
        key: `${e.source}-${e.target}-${i}`,
        path: `M ${a.x} ${a.y} C ${a.x} ${midY}, ${b.x} ${midY}, ${b.x} ${b.y}`,
        color: KIND_COLOR[e.kind] || "var(--muted)",
        dashed: e.kind === "support" || e.kind === "data",
        active,
        label: e.label || "",
        lx: (a.x + b.x) / 2,
        ly: midY,
      });
    });
    setEdges(next);
  };

  useLayoutEffect(() => {
    recompute();
    const ro = new ResizeObserver(recompute);
    if (wrapRef.current) ro.observe(wrapRef.current);
    window.addEventListener("resize", recompute);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", recompute);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arch, selected, pos]);

  if (!arch.nodes.length) {
    return <div className="glass empty">No architecture detected for this repository.</div>;
  }

  return (
    <div className="arch-layout">
      <div>
        <div className="canvas-toolbar">
          <span className="dim" style={{ fontSize: 12.5 }}>🖐️ Drag components to rearrange · tap to inspect</span>
          <button className="btn ghost sm" onClick={reset}>⟲ Reset layout</button>
        </div>
        <div className="glass drag-canvas" ref={wrapRef} style={{ height: canvasH }}>
          <svg className="drag-edges" width={size.w} height={size.h}>
            <defs>
              <marker id="ah" markerWidth="9" markerHeight="9" refX="7" refY="3"
                orient="auto" markerUnits="userSpaceOnUse">
                <path d="M0,0 L7,3 L0,6 Z" fill="var(--muted)" />
              </marker>
            </defs>
            {edges.map((e) => (
              <path
                key={e.key}
                d={e.path}
                fill="none"
                stroke={e.color}
                strokeWidth={e.active ? 3 : 1.8}
                strokeOpacity={selected && !e.active ? 0.15 : 0.85}
                strokeDasharray={e.dashed ? "5 5" : undefined}
                markerEnd="url(#ah)"
              />
            ))}
          </svg>

          {arch.nodes.map((n) => {
            const p = pos[n.id] || { x: 0, y: 0 };
            const rel =
              !!selected &&
              (selected.id === n.id ||
                selected.inbound?.includes(n.id) ||
                selected.outbound?.includes(n.id) ||
                n.inbound?.includes(selected.id) ||
                n.outbound?.includes(selected.id));
            return (
              <div
                key={n.id}
                ref={(el) => (nodeRefs.current[n.id] = el)}
                className={`drag-node arch-node ${selected?.id === n.id ? "sel" : ""} ${selected && !rel ? "dim" : ""}`}
                style={{ left: p.x, top: p.y, width: NODE_W }}
                onPointerDown={(e) => onDown(n.id, e)}
                onClick={() => {
                  if (justDragged()) return;
                  setSelected(selected?.id === n.id ? null : n);
                }}
              >
                <div className="an-head">
                  <span className="an-dot" data-layer={n.layer} />
                  <span className="an-title">{n.label}</span>
                </div>
                {n.path && <div className="an-path mono">{n.path}</div>}
                {(n.tech || []).length > 0 && (
                  <div className="an-tech">
                    {n.tech.slice(0, 3).map((t) => (
                      <span key={t} className="an-badge">{t}</span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="arch-side">
        {selected ? (
          <div className="glass card">
            <div className="an-head" style={{ marginBottom: 6 }}>
              <span className="an-dot" data-layer={selected.layer} />
              <b>{selected.label}</b>
            </div>
            {selected.path && <div className="muted mono" style={{ fontSize: 12 }}>{selected.path}</div>}
            <p style={{ marginTop: 10 }}>{selected.summary}</p>
            {selected.tech?.length > 0 && (
              <div className="an-tech" style={{ marginTop: 10 }}>
                {selected.tech.map((t) => <span key={t} className="an-badge">{t}</span>)}
              </div>
            )}
            <div className="io-grid">
              <div>
                <div className="io-label">← Called by</div>
                {(selected.inbound || []).length
                  ? selected.inbound.map((id) => <span key={id} className="tag blue">{id}</span>)
                  : <span className="dim">nothing</span>}
              </div>
              <div>
                <div className="io-label">Calls →</div>
                {(selected.outbound || []).length
                  ? selected.outbound.map((id) => <span key={id} className="tag purple">{id}</span>)
                  : <span className="dim">nothing</span>}
              </div>
            </div>
            <button className="btn ghost" style={{ marginTop: 14 }} onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
        ) : (
          <div className="glass card">
            <div className="side-label">ARCHITECTURE</div>
            <p style={{ marginTop: 8 }}>{arch.summary}</p>
            <div className="legend-row"><span className="legend-line" style={{ background: "var(--blue)" }} /> Request (sync)</div>
            <div className="legend-row"><span className="legend-line" style={{ background: "var(--green)" }} /> Event (async)</div>
            <div className="legend-row"><span className="legend-line dashed" style={{ background: "var(--orange)" }} /> Data / support</div>
            <p className="dim" style={{ marginTop: 12, fontSize: 12.5 }}>
              Drag the boxes around like a whiteboard. Tap a component to see its tech and connections.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
