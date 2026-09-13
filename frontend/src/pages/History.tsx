import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import TopBar from "../components/TopBar";
import { listAnalyses } from "../api";
import { useAuth } from "../AuthContext";
import type { AnalysisSummary } from "../types";

function formatDate(ts: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function History() {
  const nav = useNavigate();
  const { user } = useAuth();
  const isAdmin = !!user?.is_admin;
  const [items, setItems] = useState<AnalysisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    listAnalyses()
      .then(setItems)
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = items.filter(
    (h) =>
      !q ||
      `${h.repo_owner}/${h.repo_name} ${h.repo_url} ${h.owner || ""}`
        .toLowerCase()
        .includes(q.toLowerCase())
  );

  return (
    <>
      <TopBar sub={isAdmin ? "all users' guides" : "your saved guides"} />

      <div className="page-head">
        <h2>🕘 {isAdmin ? "All guides" : "My guides"}</h2>
        <p>
          {isAdmin
            ? "As admin you can see every user's generated guides."
            : "Every guide you've generated — pick up where you left off."}
        </p>
      </div>

      <div className="glass repo-input" style={{ marginBottom: 20 }}>
        <span className="mono muted">🔍</span>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={isAdmin ? "Search guides by repo or user…" : "Search your guides by repo…"}
        />
        <button className="btn accent" onClick={() => nav("/")}>🧠 New guide</button>
      </div>

      {loading ? (
        <div className="empty"><span className="spinner" /> Loading…</div>
      ) : filtered.length ? (
        <div className="grid-3">
          {filtered.map((h) => {
            const done = h.status === "done";
            const to = done ? `/guide/${h.id}` : `/analysis/${h.id}`;
            return (
              <div key={h.id} className="glass card history-card" onClick={() => nav(to)}>
                <div className="history-top">
                  <span className="history-repo">📦 {h.repo_owner ? `${h.repo_owner}/` : ""}{h.repo_name || h.repo_url}</span>
                  <span className={`status-badge ${h.status}`}>{h.status}</span>
                </div>
                <div className="history-meta">
                  <span className="dim">{formatDate(h.created_at)}</span>
                  {isAdmin && h.owner && <span className="tag">👤 {h.owner}</span>}
                  {h.llm_powered && <span className="tag green">AI</span>}
                </div>
                <div className="history-open">{done ? "Open guide →" : "View progress →"}</div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="glass empty">
          {items.length ? "No guides match your search." : "No guides yet — generate your first one from the home page."}
        </div>
      )}
    </>
  );
}
