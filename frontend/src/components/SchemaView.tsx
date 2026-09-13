import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Schema } from "../types";
import { useDraggable } from "../hooks/useDraggable";
import { useCanvasViewport } from "../hooks/useCanvasViewport";

const CARD_W = 236;
const GAP_X = 90;
const GAP_Y = 48;
const PAD = 26;
const ROW_H = 34;
const HEAD_H = 40;

interface Conn {
  key: string;
  path: string;
  lx: number;
  ly: number;
  card: string;
  active: boolean;
}

export default function SchemaView({ schema }: { schema: Schema }) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const cardRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const rowRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [conns, setConns] = useState<Conn[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<string | null>(null);

  const tables = schema.tables || [];

  // Initial masonry-ish layout (2 columns).
  const { initial, canvasH } = useMemo(() => {
    const colH = [PAD, PAD];
    const init: Record<string, { x: number; y: number }> = {};
    tables.forEach((t) => {
      const ci = colH[0] <= colH[1] ? 0 : 1;
      init[t.name] = { x: PAD + ci * (CARD_W + GAP_X), y: colH[ci] };
      colH[ci] += HEAD_H + t.columns.length * ROW_H + GAP_Y;
    });
    return { initial: init, canvasH: Math.max(colH[0], colH[1]) + PAD };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema]);

  const resetKey = useMemo(() => tables.map((t) => t.name).join(","), [schema]);
  const vp = useCanvasViewport();
  const { pos, onDown, justDragged, reset } = useDraggable(initial, resetKey, vp.zoomRef);

  // Build FK -> PK connections.
  const links = useMemo(() => {
    const pkOf = (tbl: string) => {
      const t = tables.find((x) => x.name === tbl);
      const pk = t?.columns.find((c) => c.key === "pk");
      return pk?.name || "id";
    };
    const known = new Set(tables.map((t) => t.name));
    const out: { src: string; srcCol: string; dst: string; dstCol: string; card: string }[] = [];
    for (const t of tables) {
      for (const c of t.columns) {
        if (c.key !== "fk" && !c.ref) continue;
        const ref = c.ref || "";
        let dst = ref.split(".")[0] || "";
        // fall back: guess table from column name like "owner_id" -> owner/users
        if (!known.has(dst)) {
          const rel = schema.relationships?.find(
            (r) => r.source === t.name || r.target === t.name
          );
          dst = rel ? (rel.source === t.name ? rel.target : rel.source) : dst;
        }
        if (!known.has(dst)) continue;
        const dstCol = ref.split(".")[1] || pkOf(dst);
        out.push({ src: t.name, srcCol: c.name, dst, dstCol, card: "N:1" });
      }
    }
    // fall back to declared relationships if no FK columns found
    if (!out.length && schema.relationships) {
      for (const r of schema.relationships) {
        if (known.has(r.source) && known.has(r.target)) {
          out.push({ src: r.target, srcCol: pkOf(r.target), dst: r.source, dstCol: pkOf(r.source), card: r.cardinality });
        }
      }
    }
    return out;
  }, [schema, tables]);

  const recompute = () => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    let cw = 0;
    let ch = 0;
    for (const t of tables) {
      const el = cardRefs.current[t.name];
      if (!el) continue;
      cw = Math.max(cw, el.offsetLeft + el.offsetWidth);
      ch = Math.max(ch, el.offsetTop + el.offsetHeight);
    }
    setSize({ w: cw + PAD, h: ch + PAD });
    const rowMid = (tbl: string, col: string) => {
      const card = cardRefs.current[tbl];
      const row = rowRefs.current[`${tbl}::${col}`];
      const p = pos[tbl];
      if (!card || !p) return null;
      const y = p.y + (row ? row.offsetTop + row.offsetHeight / 2 : HEAD_H / 2);
      return { left: p.x, right: p.x + card.offsetWidth, y };
    };
    const next: Conn[] = [];
    links.forEach((l, i) => {
      const s = rowMid(l.src, l.srcCol);
      const d = rowMid(l.dst, l.dstCol);
      if (!s || !d) return;
      const rightward = d.left >= s.left;
      const sx = rightward ? s.right : s.left;
      const dx = rightward ? d.left : d.right;
      const dir = dx >= sx ? 1 : -1;
      const c1 = sx + dir * 55;
      const c2 = dx - dir * 55;
      const active = hover === l.src || hover === l.dst;
      next.push({
        key: `${l.src}.${l.srcCol}-${l.dst}.${l.dstCol}-${i}`,
        path: `M ${sx} ${s.y} C ${c1} ${s.y}, ${c2} ${d.y}, ${dx} ${d.y}`,
        lx: (sx + dx) / 2,
        ly: (s.y + d.y) / 2,
        card: l.card,
        active,
      });
    });
    setConns(next);
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
  }, [schema, pos, hover]);

  if (!tables.length) {
    return (
      <div className="glass card">
        <h4>🗄️ Database schema</h4>
        <p>{schema.summary || "This project has no relational database."}</p>
        {schema.plain_english && <p style={{ marginTop: 10 }}>{schema.plain_english}</p>}
      </div>
    );
  }

  return (
    <div className="schema-layout">
      <div>
        <div className="canvas-frame glass" ref={vp.frameRef}>
          <div className="canvas-toolbar">
            <span className="dim" style={{ fontSize: 12.5 }}>🖐️ Drag to pan · scroll to zoom · drag a table to move it</span>
            <div className="canvas-tools">
              <button className="icon-btn sm" title="Zoom out" onClick={vp.zoomOut}>−</button>
              <span className="zoom-label">{Math.round(vp.zoom * 100)}%</span>
              <button className="icon-btn sm" title="Zoom in" onClick={vp.zoomIn}>+</button>
              <button className="btn ghost sm" onClick={vp.resetView}>⟲ View</button>
              <button className="btn ghost sm" onClick={reset}>⟲ Layout</button>
              <button className="btn ghost sm" onClick={vp.toggleFullscreen}>{vp.fullscreen ? "✕ Exit" : "⛶ Fullscreen"}</button>
            </div>
          </div>
          <div
            className="drag-canvas er-canvas canvas-viewport"
            ref={(el) => { wrapRef.current = el; vp.viewportRef.current = el; }}
            onPointerDown={vp.onBackgroundPointerDown}
          >
            <div
              className="canvas-stage"
              style={{ width: size.w || undefined, height: size.h || canvasH, transform: `translate(${vp.pan.x}px, ${vp.pan.y}px) scale(${vp.zoom})` }}
            >
              <svg className="drag-edges" width={size.w} height={size.h}>
            <defs>
              <marker id="er-dot" markerWidth="8" markerHeight="8" refX="4" refY="4">
                <circle cx="4" cy="4" r="3" fill="var(--purple)" />
              </marker>
              <marker id="er-arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
                <path d="M0,0 L7,3 L0,6 Z" fill="var(--purple)" />
              </marker>
            </defs>
            {conns.map((c) => (
              <g key={c.key}>
                <path
                  d={c.path}
                  fill="none"
                  stroke="var(--purple)"
                  strokeWidth={c.active ? 2.6 : 1.7}
                  strokeOpacity={c.active ? 1 : 0.6}
                  markerStart="url(#er-dot)"
                  markerEnd="url(#er-arrow)"
                />
                <text x={c.lx} y={c.ly - 4} textAnchor="middle" className="er-card-label">{c.card}</text>
              </g>
            ))}
          </svg>

          {tables.map((t) => {
            const p = pos[t.name] || { x: 0, y: 0 };
            return (
              <div
                key={t.name}
                ref={(el) => (cardRefs.current[t.name] = el)}
                className={`drag-node er-table ${hover === t.name ? "hl" : ""}`}
                style={{ left: p.x, top: p.y, width: CARD_W }}
                onPointerDown={(e) => onDown(t.name, e)}
                onMouseEnter={() => !justDragged() && setHover(t.name)}
                onMouseLeave={() => setHover(null)}
              >
                <div className="er-th">🗂️ {t.name}</div>
                {t.columns.map((c) => (
                  <div
                    className="er-col"
                    key={c.name}
                    ref={(el) => (rowRefs.current[`${t.name}::${c.name}`] = el)}
                  >
                    <span className="er-col-name">
                      {c.key === "pk" && <span className="key-pk">🔑</span>}
                      {c.key === "fk" && <span className="key-fk">🔗</span>}
                      {c.name}
                    </span>
                    <span className="er-col-type mono">{c.ref ? `→ ${c.ref}` : c.type}</span>
                  </div>
                ))}
              </div>
            );
          })}
            </div>
          </div>
        </div>
      </div>

      <div className="schema-side">
        <div className="glass card">
          <div className="side-label">🔗 RELATIONSHIPS</div>
          {schema.relationships?.length ? (
            schema.relationships.map((r, i) => (
              <div key={i} className="rel-row">
                <span className="mono">{r.source} → {r.target}</span>
                <span className="tag purple">{r.cardinality}</span>
              </div>
            ))
          ) : (
            <p className="muted" style={{ fontSize: 13 }}>No explicit relationships detected.</p>
          )}
        </div>
        <div className="glass card">
          <div className="side-label">💡 PLAIN-ENGLISH</div>
          <p style={{ marginTop: 8 }}>{schema.plain_english || schema.summary}</p>
        </div>
      </div>
    </div>
  );
}
