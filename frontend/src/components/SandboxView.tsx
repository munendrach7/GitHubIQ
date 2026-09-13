import { useState } from "react";
import type { Sandbox, WalkthroughScreen } from "../types";

const ELEMENT_ICON: Record<string, string> = {
  button: "🔘", input: "⌨️", list: "☰", nav: "🧭",
  card: "🗂️", text: "📝", chart: "📊", element: "▪️",
};

function ScreenMock({ screen }: { screen: WalkthroughScreen }) {
  return (
    <div className="screen-mock">
      <div className="screen-chrome">
        <span className="dot-r" /><span className="dot-y" /><span className="dot-g" />
        <span className="screen-url mono">{screen.route || screen.kind}</span>
      </div>
      <div className="screen-body">
        <div className="screen-title">{screen.title}</div>
        <div className="screen-elements">
          {(screen.elements || []).map((el, i) => (
            <div key={i} className={`screen-el el-${el.kind}`} title={el.note}>
              <span>{ELEMENT_ICON[el.kind] || "▪️"}</span> {el.label}
            </div>
          ))}
          {!(screen.elements || []).length && (
            <div className="dim" style={{ fontSize: 13 }}>{screen.description}</div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SandboxView({ sandbox }: { sandbox: Sandbox }) {
  const screens = sandbox.screens || [];
  const [active, setActive] = useState(0);
  if (!screens.length) {
    return <div className="glass empty">No app walkthrough was generated for this repository.</div>;
  }
  const current = screens[Math.min(active, screens.length - 1)];

  return (
    <div>
      <div className="page-head" style={{ paddingTop: 0 }}>
        <h2 style={{ fontSize: 24 }}>
          🎬 {sandbox.title} {sandbox.app_type && <span className="tag purple">{sandbox.app_type}</span>}
        </h2>
        <p>{sandbox.summary}</p>
        <p className="dim" style={{ fontSize: 13, marginTop: 4 }}>
          A visual tour of the app's main surfaces — follow the journey step by step.
        </p>
      </div>

      <div className="walk-strip">
        {screens.map((s, i) => (
          <button
            key={s.id || i}
            className={`walk-chip ${i === active ? "on" : ""}`}
            onClick={() => setActive(i)}
          >
            <span className="walk-chip-num">{i + 1}</span> {s.title}
          </button>
        ))}
      </div>

      <div className="walk-stage">
        <ScreenMock screen={current} />

        <div className="glass card walk-info">
          <div className="side-label">{(current.kind || "screen").toUpperCase()}</div>
          <h3 style={{ margin: "6px 0" }}>{current.title}</h3>
          {current.route && <div className="muted mono" style={{ fontSize: 12 }}>{current.route}</div>}
          <p style={{ marginTop: 10 }}>{current.description}</p>

          {(current.user_actions || []).length > 0 && (
            <>
              <div className="io-label" style={{ marginTop: 14 }}>What you can do here</div>
              <ul className="walk-actions">
                {current.user_actions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </>
          )}

          <div className="walk-nav">
            <button className="btn ghost" disabled={active <= 0} onClick={() => setActive(active - 1)}>
              ← Back
            </button>
            <button
              className="btn accent"
              disabled={active >= screens.length - 1}
              onClick={() => setActive(active + 1)}
            >
              Next screen →
            </button>
          </div>
        </div>
      </div>

      {sandbox.challenge && (
        <div className="glass card" style={{ marginTop: 16, borderColor: "var(--green)" }}>
          <h4>✅ Try it yourself</h4>
          <p>{sandbox.challenge}</p>
        </div>
      )}
    </div>
  );
}
