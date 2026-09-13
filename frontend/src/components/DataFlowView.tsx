import { useMemo, useState } from "react";
import type { DataFlow, EndpointFlow } from "../types";

const METHOD_COLOR: Record<string, string> = {
  GET: "green", POST: "blue", PUT: "orange", PATCH: "orange", DELETE: "pink",
};

export default function DataFlowView({ flow }: { flow: DataFlow }) {
  // Prefer the per-endpoint flows; fall back to the single legacy flow.
  const endpoints: EndpointFlow[] = useMemo(() => {
    if (flow.endpoints && flow.endpoints.length) return flow.endpoints;
    return [
      {
        id: "main", method: "", route: "", title: flow.title,
        trigger: flow.trigger, summary: flow.summary, steps: flow.steps,
        rationale: flow.rationale,
      },
    ];
  }, [flow]);

  const [activeEp, setActiveEp] = useState(0);
  const [active, setActive] = useState(0);
  const ep = endpoints[Math.min(activeEp, endpoints.length - 1)];

  if (!ep || !ep.steps.length) {
    return <div className="glass empty">No data flow was traced for this repository.</div>;
  }

  const step = ep.steps[Math.min(active, ep.steps.length - 1)];
  const atStart = active <= 0;
  const atEnd = active >= ep.steps.length - 1;
  const selectEp = (i: number) => { setActiveEp(i); setActive(0); };

  return (
    <div>
      <div className="page-head" style={{ paddingTop: 0 }}>
        <h2 style={{ fontSize: 24 }}>🐬 Application flows</h2>
        <p>
          {endpoints.length} endpoint{endpoints.length === 1 ? "" : "s"} traced — pick one
          to walk its logic end to end.
        </p>
      </div>

      {endpoints.length > 1 && (
        <div className="flow-endpoint-tabs">
          {endpoints.map((e, i) => (
            <button
              key={e.id || i}
              className={`endpoint-tab ${i === activeEp ? "on" : ""}`}
              onClick={() => selectEp(i)}
              title={e.title}
            >
              {e.method && <span className={`tag ${METHOD_COLOR[e.method] || "blue"} mono`}>{e.method}</span>}
              <span className="mono endpoint-tab-route">{e.route || e.title}</span>
            </button>
          ))}
        </div>
      )}

      <div className="page-head" style={{ paddingTop: 0 }}>
        <h3 style={{ fontSize: 19, margin: 0, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          {ep.method && <span className={`tag ${METHOD_COLOR[ep.method] || "blue"} mono`}>{ep.method}</span>}
          <span className="mono">{ep.route || ep.title}</span>
        </h3>
        {ep.route && ep.title && ep.title !== ep.route && (
          <p className="dim" style={{ marginTop: 4 }}>{ep.title}</p>
        )}
        {ep.trigger && (
          <p className="muted" style={{ marginTop: 6 }}><span className="tag orange">trigger</span> {ep.trigger}</p>
        )}
        {ep.summary && <p>{ep.summary}</p>}
      </div>

      <div className="flow-layout">
        <div className="flow-rail-v">
          {ep.steps.map((s, i) => (
            <button
              key={s.index}
              className={`rail-node-v ${i === active ? "on" : ""} ${i < active ? "done" : ""}`}
              onClick={() => setActive(i)}
            >
              <span className={`rail-num ${s.kind}`}>{s.index}</span>
              <span className="rail-node-v-text">
                <span className="rail-actor">{s.actor}</span>
                {s.label && <span className="rail-node-v-label">{s.label}</span>}
              </span>
            </button>
          ))}
        </div>

        <div className="flow-main">
          <div className="glass card flow-active" key={`${ep.id}-${step.index}`}>
            <div className="flow-active-head">
              <span className={`flow-idx ${step.kind}`}>{step.index}</span>
              <div>
                <div className="flow-actor">{step.actor}</div>
                <div className="muted">{step.label}</div>
              </div>
              <span className={`tag ${step.kind === "async" ? "purple" : "blue"}`} style={{ marginLeft: "auto" }}>{step.kind}</span>
            </div>

            {step.detail && <p className="flow-detail">{step.detail}</p>}

            {(step.data_in || step.data_out) && (
              <div className="flow-data">
                <div className="flow-data-cell">
                  <div className="io-label">Data in</div>
                  <code className="mono">{step.data_in || "—"}</code>
                </div>
                <div className="flow-data-arrow">→</div>
                <div className="flow-data-cell">
                  <div className="io-label">Data out</div>
                  <code className="mono">{step.data_out || "—"}</code>
                </div>
              </div>
            )}

            {step.code && <pre className="mono flow-code">{step.code}</pre>}

            {(step.files || []).length > 0 && (
              <div className="flow-files">
                <span className="io-label" style={{ marginRight: 4 }}>Files:</span>
                {step.files.map((f) => <span key={f} className="tag green mono">{f}</span>)}
              </div>
            )}

            <div className="flow-nav">
              <button className="btn ghost" disabled={atStart} onClick={() => setActive(active - 1)}>← Previous</button>
              <span className="dim">{active + 1} of {ep.steps.length}</span>
              <button className="btn accent" disabled={atEnd} onClick={() => setActive(active + 1)}>Next step →</button>
            </div>
          </div>

          {ep.rationale && (
            <div className="grid-2" style={{ marginTop: 16 }}>
              <div className="glass card">
                <h4>🧠 Why it's built this way</h4>
                <p>{ep.rationale}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
