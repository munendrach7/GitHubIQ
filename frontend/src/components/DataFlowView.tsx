import { useState } from "react";
import type { DataFlow } from "../types";

export default function DataFlowView({ flow }: { flow: DataFlow }) {
  const [active, setActive] = useState(0);
  if (!flow.steps.length) {
    return <div className="glass empty">No data flow was traced for this repository.</div>;
  }
  const step = flow.steps[Math.min(active, flow.steps.length - 1)];
  const atStart = active <= 0;
  const atEnd = active >= flow.steps.length - 1;

  return (
    <div>
      <div className="page-head" style={{ paddingTop: 0 }}>
        <h2 style={{ fontSize: 24 }}>🐬 {flow.title}</h2>
        {flow.trigger && (
          <p className="muted"><span className="tag orange">trigger</span> {flow.trigger}</p>
        )}
        <p>{flow.summary}</p>
        <p className="dim" style={{ fontSize: 13, marginTop: 4 }}>
          Click a step on the rail — or press Next — to walk the request through the system.
        </p>
      </div>

      {/* Interactive flow rail */}
      <div className="flow-rail">
        {flow.steps.map((s, i) => (
          <button
            key={s.index}
            className={`rail-node ${i === active ? "on" : ""} ${i < active ? "done" : ""}`}
            onClick={() => setActive(i)}
          >
            <span className={`rail-num ${s.kind}`}>{s.index}</span>
            <span className="rail-actor">{s.actor}</span>
            {i < flow.steps.length - 1 && <span className="rail-arrow">→</span>}
          </button>
        ))}
      </div>

      {/* Active step detail */}
      <div className="glass card flow-active" key={step.index}>
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
          <span className="dim">{active + 1} of {flow.steps.length}</span>
          <button className="btn accent" disabled={atEnd} onClick={() => setActive(active + 1)}>Next step →</button>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        {flow.rationale && (
          <div className="glass card">
            <h4>🧠 Why it's built this way</h4>
            <p>{flow.rationale}</p>
          </div>
        )}
        {(flow.alternatives || []).length > 0 && (
          <div className="glass card">
            <h4>🔀 Other notable flows</h4>
            <ul style={{ margin: "8px 0 0 18px" }}>
              {flow.alternatives.map((a) => (
                <li key={a} style={{ margin: "4px 0", color: "var(--muted)" }}>{a}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
