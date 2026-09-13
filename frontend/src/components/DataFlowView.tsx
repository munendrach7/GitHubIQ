import { useState } from "react";
import type { DataFlow } from "../types";

export default function DataFlowView({ flow }: { flow: DataFlow }) {
  const [open, setOpen] = useState(0);
  if (!flow.steps.length) {
    return <div className="glass empty">No data flow was traced for this repository.</div>;
  }

  return (
    <div>
      <div className="page-head" style={{ paddingTop: 0 }}>
        <h2 style={{ fontSize: 24 }}>🐬 {flow.title}</h2>
        {flow.trigger && (
          <p className="muted"><span className="tag orange">trigger</span> {flow.trigger}</p>
        )}
        <p>{flow.summary}</p>
        <p className="dim" style={{ fontSize: 13, marginTop: 4 }}>
          Tap any step to see exactly what happens, the data in/out, and the files involved.
        </p>
      </div>

      <div className="flow-timeline">
        {flow.steps.map((s, i) => {
          const isOpen = open === i;
          return (
            <div key={s.index} className={`glass flow-item ${isOpen ? "open" : ""}`}>
              <button className="flow-item-head" onClick={() => setOpen(isOpen ? -1 : i)}>
                <span className={`flow-idx ${s.kind}`}>{s.index}</span>
                <span className="flow-item-main">
                  <span className="flow-actor">{s.actor}</span>
                  <span className="flow-label">{s.label}</span>
                </span>
                <span className={`tag ${s.kind === "async" ? "purple" : "blue"}`}>{s.kind}</span>
                <span className="flow-caret">{isOpen ? "▾" : "▸"}</span>
              </button>

              {isOpen && (
                <div className="flow-item-body">
                  {s.detail && <p className="flow-detail">{s.detail}</p>}
                  {(s.data_in || s.data_out) && (
                    <div className="flow-data">
                      <div className="flow-data-cell">
                        <div className="io-label">Data in</div>
                        <code className="mono">{s.data_in || "—"}</code>
                      </div>
                      <div className="flow-data-arrow">→</div>
                      <div className="flow-data-cell">
                        <div className="io-label">Data out</div>
                        <code className="mono">{s.data_out || "—"}</code>
                      </div>
                    </div>
                  )}
                  {s.code && <pre className="mono flow-code">{s.code}</pre>}
                  {(s.files || []).length > 0 && (
                    <div className="flow-files">
                      {s.files.map((f) => <span key={f} className="tag green mono">{f}</span>)}
                    </div>
                  )}
                  {s.note && <div className="flow-note">💡 {s.note}</div>}
                </div>
              )}
            </div>
          );
        })}
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
