import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import TopBar from "../components/TopBar";
import { cancelAnalysis, getAnalysis } from "../api";
import type { AnalysisResult } from "../types";

const AGENT_META: Record<string, { icon: string; desc: string }> = {
  Researcher: { icon: "🔎", desc: "Crawls the repo, finds entry points & components, assigns context" },
  Architect: { icon: "🏛️", desc: "Maps components, layers & interaction edges" },
  Schema: { icon: "🗄️", desc: "Reverse-engineers DB models & relations" },
  "Data-Flow": { icon: "🐬", desc: "Traces the main operation with real data" },
  "Deep-Dive": { icon: "🔬", desc: "Writes an in-depth, code-grounded section per component" },
  Tutor: { icon: "🧑‍🏫", desc: "Explains the language idioms & patterns in this repo" },
  Presenter: { icon: "🎥", desc: "Scripts the narrated video overview" },
  Walkthrough: { icon: "🎬", desc: "Builds a visual tour of the app's screens" },
};

export default function Analysis() {
  const { id } = useParams();
  const nav = useNavigate();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState("");
  const [cancelled, setCancelled] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const timer = useRef<number>();

  useEffect(() => {
    if (!id) return;
    const poll = async () => {
      try {
        const r = await getAnalysis(id);
        setResult(r);
        if (r.status === "done") {
          window.clearInterval(timer.current);
          setTimeout(() => nav(`/guide/${id}`), 700);
        } else if (r.status === "error") {
          window.clearInterval(timer.current);
          setError(r.error || "Analysis failed");
        } else if (r.status === "cancelled") {
          window.clearInterval(timer.current);
          setCancelled(true);
        }
      } catch (e) {
        setError((e as Error).message);
      }
    };
    poll();
    // Poll every 5s — the pipeline is long-running, so a slower cadence keeps
    // the UI responsive without hammering the API.
    timer.current = window.setInterval(poll, 5000);
    return () => window.clearInterval(timer.current);
  }, [id, nav]);

  const doCancel = async () => {
    if (!id) return;
    setCancelling(true);
    try {
      const r = await cancelAnalysis(id);
      setResult(r);
      if (r.status === "cancelled") {
        window.clearInterval(timer.current);
        setCancelled(true);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCancelling(false);
    }
  };

  const inProgress =
    !!result && result.status !== "done" && result.status !== "error" &&
    result.status !== "cancelled";

  const percent = result?.percent ?? 0;
  const circumference = 2 * Math.PI * 52;

  return (
    <>
      <TopBar
        sub={result?.repo?.name || "analyzing"}
        right={
          <span style={{ display: "inline-flex", gap: 10, alignItems: "center" }}>
            <span className="pill">
              <span className="dot b" /> {result?.status === "done" ? "Complete" : cancelled ? "Cancelled" : "Analyzing…"}
            </span>
            {inProgress && (
              <button
                className="btn ghost"
                onClick={doCancel}
                disabled={cancelling}
                title="Cancel this analysis run"
              >
                {cancelling ? "Cancelling…" : "✕ Cancel"}
              </button>
            )}
          </span>
        }
      />

      <div className="page-head">
        <h2>🔬 X-Raying the repository</h2>
        <p>
          Seven specialist agents work asynchronously to understand your codebase
          and draft your guide.
          {result?.llm_powered === false && (
            <span className="tag orange" style={{ marginLeft: 10 }}>heuristic mode</span>
          )}
          {result?.llm_powered && (
            <span className="tag green" style={{ marginLeft: 10 }}>LLM-powered</span>
          )}
        </p>
      </div>

      {error && (
        <div className="glass card" style={{ borderColor: "var(--pink)" }}>
          <h4 style={{ color: "var(--pink)" }}>⚠️ Analysis error</h4>
          <p>{error}</p>
          <button className="btn" style={{ marginTop: 14 }} onClick={() => nav("/")}>
            ← Try another repo
          </button>
        </div>
      )}

      {cancelled && !error && (
        <div className="glass card" style={{ borderColor: "var(--orange, #e0a458)" }}>
          <h4>🛑 Analysis cancelled</h4>
          <p>This run was cancelled{result?.error ? `: ${result.error}` : "."}</p>
          <button className="btn" style={{ marginTop: 14 }} onClick={() => nav("/")}>
            ← Start a new analysis
          </button>
        </div>
      )}

      {!error && !cancelled && (
        <div className="analysis-grid" style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 16 }}>
          <div className="glass">
            {result?.progress.map((p) => {
              const meta = AGENT_META[p.name] || { icon: "🤖", desc: "" };
              const pct = p.status === "done" ? 100 : p.status === "running" ? 60 : 8;
              return (
                <div className="agent-row" key={p.name}>
                  <div className="agent-ic">{meta.icon}</div>
                  <div className="agent-main">
                    <div className="t">{p.name} Agent</div>
                    <div className="d">{p.detail || meta.desc}</div>
                  </div>
                  <div className="agent-right">
                    <div className="bar mini-bar"><i style={{ width: `${pct}%` }} /></div>
                    <span className={`status-badge ${p.status}`}>
                      {p.status === "running" ? "Running" : p.status === "done" ? "Done" : p.status === "error" ? "Error" : "Waiting"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="glass card" style={{ display: "grid", placeItems: "center", gap: 18 }}>
            <div style={{ color: "var(--dim)", fontSize: 12, fontWeight: 700, letterSpacing: 0.5 }}>
              OVERALL PROGRESS
            </div>
            <svg width="140" height="140" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="52" fill="none" stroke="var(--border)" strokeWidth="10" />
              <circle
                cx="60" cy="60" r="52" fill="none" stroke="var(--blue)" strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={circumference * (1 - percent / 100)}
                transform="rotate(-90 60 60)"
                style={{ transition: "stroke-dashoffset 0.5s ease" }}
              />
              <text x="60" y="67" textAnchor="middle" fontSize="26" fontWeight="800" fill="var(--text)">
                {percent}%
              </text>
            </svg>
            <div className="muted" style={{ fontSize: 13 }}>Specialist agents running in parallel</div>
          </div>
        </div>
      )}
    </>
  );
}
