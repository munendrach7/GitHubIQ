import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import TopBar from "../components/TopBar";
import { listAdminUsers } from "../api";
import { useAuth } from "../AuthContext";
import type { AdminUserView } from "../types";

function formatDate(ts: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function Admin() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [users, setUsers] = useState<AdminUserView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<Record<string, boolean>>({});

  useEffect(() => {
    listAdminUsers()
      .then(setUsers)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  if (user && !user.is_admin) {
    return (
      <>
        <TopBar sub="admin" />
        <div className="glass empty">This area is for admins only.</div>
      </>
    );
  }

  const filtered = users.filter((u) => !q || u.username.toLowerCase().includes(q.toLowerCase()));
  const totalGuides = users.reduce((n, u) => n + u.guides.length, 0);

  return (
    <>
      <TopBar sub="all users & their guides" />

      <div className="page-head">
        <h2>👥 Users & guides</h2>
        <p>{users.length} users · {totalGuides} guides generated across the system.</p>
      </div>

      <div className="glass repo-input" style={{ marginBottom: 20 }}>
        <span className="mono muted">🔍</span>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search users…" />
        <button className="btn accent" onClick={() => nav("/history")}>🕘 All guides</button>
      </div>

      {error && (
        <div className="glass card" style={{ borderColor: "var(--pink)" }}>
          <p style={{ color: "var(--pink)" }}>{error}</p>
        </div>
      )}

      {loading ? (
        <div className="empty"><span className="spinner" /> Loading…</div>
      ) : filtered.length ? (
        <div style={{ display: "grid", gap: 12 }}>
          {filtered.map((u) => {
            const isOpen = open[u.username] ?? false;
            return (
              <div key={u.username} className="glass card">
                <div
                  style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }}
                  onClick={() => setOpen((o) => ({ ...o, [u.username]: !isOpen }))}
                >
                  <span style={{ fontSize: 20 }}>{u.is_admin ? "🛡️" : "👤"}</span>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700 }}>
                      {u.username} {u.is_admin && <span className="admin-badge">ADMIN</span>}
                    </div>
                    <div className="dim" style={{ fontSize: 12 }}>
                      {u.created_at ? `joined ${formatDate(u.created_at)}` : "—"}
                    </div>
                  </div>
                  <span className="tag">{u.guides.length} guide{u.guides.length === 1 ? "" : "s"}</span>
                  <span className="dim">{isOpen ? "▲" : "▼"}</span>
                </div>

                {isOpen && (
                  u.guides.length ? (
                    <div className="grid-3" style={{ marginTop: 14 }}>
                      {u.guides.map((h) => {
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
                              {h.llm_powered && <span className="tag green">AI</span>}
                            </div>
                            <div className="history-open">{done ? "Open guide →" : "View progress →"}</div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="dim" style={{ marginTop: 12, fontSize: 13 }}>No guides yet.</div>
                  )
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="glass empty">No users found.</div>
      )}
    </>
  );
}
