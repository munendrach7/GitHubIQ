import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import TopBar from "../components/TopBar";
import { useAuth, formatCooldown } from "../AuthContext";
import { listAnalyses } from "../api";
import type { AnalysisSummary } from "../types";

const FEATURES = [
  { e: "🔎", t: "Deep repo crawler", p: "A researcher agent traces entry points and maps every real component before the specialists dive in — so nothing important is missed." },
  { e: "🗺️", t: "Drag-and-drop architecture", p: "A layered, interactive map of services, data stores and externals. Drag the boxes, tap any node to see its tech and connections." },
  { e: "🐬", t: "Interactive data flow", p: "Follow the main operation hop by hop. Click any step to reveal the data in/out, the code, and the exact files involved." },
  { e: "🗄️", t: "ER schema diagram", p: "Your database reverse-engineered into a draggable ER diagram with foreign-key relationship lines — just like a real DB visualizer." },
  { e: "📚", t: "Language tutor", p: "Just-in-time lessons on the specific language and framework idioms used in this repo, matched to your experience level." },
  { e: "📄", t: "Export to PDF", p: "Download the entire guide as a polished PDF to read offline or share with your team." },
  { e: "🧩", t: "Component-wise guide", p: "A Learn-style walkthrough that starts simple — what it is, what it does, how it works — then breaks the project down component by component." },
];

const BENEFITS = [
  { c: "b", t: "Understand", d: "See how flow, architecture and data fit together — not just isolated files. Build a real mental model in minutes." },
  { c: "g", t: "Ramp up faster", d: "Skip the outdated READMEs and the constant interruptions. Onboard to any codebase without blocking your teammates." },
  { c: "p", t: "Own it", d: "Public or private, any language. Export the guide as plain HTML/PDF and keep it — no lock-in." },
];

const STEPS = [
  { e: "🔗", t: "Point at a repo", d: "Paste any public GitHub URL." },
  { e: "🎯", t: "Tailor it", d: "Tell us your role, level and goals." },
  { e: "🤖", t: "Agents analyze", d: "Seven specialists crawl it in parallel." },
  { e: "✨", t: "Compose guide", d: "Findings merge into a living guide." },
  { e: "🧠", t: "Explore & export", d: "Interact, learn, and download." },
];

function formatDate(ts: number): string {
  if (!ts) return "";
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function Landing() {
  const [repo, setRepo] = useState("");
  const nav = useNavigate();
  const { user } = useAuth();
  const cooling = user && !user.is_admin && !user.rate?.can_generate;

  const [history, setHistory] = useState<AnalysisSummary[]>([]);
  const [histLoading, setHistLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      setHistory([]);
      return;
    }
    setHistLoading(true);
    listAnalyses()
      .then(setHistory)
      .catch(() => setHistory([]))
      .finally(() => setHistLoading(false));
  }, [user]);

  const go = () => {
    if (!repo.trim()) return;
    const target = `/tailor?repo=${encodeURIComponent(repo.trim())}`;
    if (!user) {
      nav(`/login?next=${encodeURIComponent(target)}`);
      return;
    }
    nav(target);
  };

  return (
    <>
      <TopBar
        right={
          user ? (
            <span className="pill">
              <span className="dot g" /> Multi-agent engine online
            </span>
          ) : (
            <button className="btn accent" onClick={() => nav("/login")}>Sign in</button>
          )
        }
      />

      <div className="hero">
        <div>
          <span className="pill">🧠 Understand any codebase — don't just read it</span>
          <h1>
            Point it at a repo.
            <br />
            Get an <span className="g1">interactive</span>{" "}
            <span className="g2">tutor</span> for the whole project.
          </h1>
          <p className="lead">
            GitHubIQ reads an entire Git repository and generates a living,
            interactive onboarding guide — a drag-and-drop architecture map, a
            clickable data-flow trace, a reverse-engineered schema diagram and
            just-in-time language lessons. No boring wall-of-text docs.
          </p>

          {cooling && (
            <div className="glass cooldown-banner">
              ⏳ You've used your generation. Next one available in{" "}
              <b>{formatCooldown(user!.rate.seconds_left)}</b>
              {" "}(1 per {user!.rate.window_hours}h).
            </div>
          )}

          <div className="glass repo-input">
            <span className="mono muted">🔗</span>
            <input
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && go()}
              placeholder="https://github.com/your-org/sample-app"
            />
            <button className="btn primary" onClick={go}>
              🧠 X-Ray this repo
            </button>
          </div>
          <p className="muted" style={{ marginTop: 14, fontSize: 13 }}>
            {user ? "Public repo? Go straight in." : "Sign in to generate your first guide — free."}
          </p>

          <div className="stats">
            <div className="stat"><div className="num b">6</div><div className="lbl">Specialist agents</div></div>
            <div className="stat"><div className="num g">5</div><div className="lbl">Interactive views</div></div>
            <div className="stat"><div className="num p">100%</div><div className="lbl">Exportable</div></div>
          </div>
        </div>

        <div className="hero-cards">
          {FEATURES.slice(0, 4).map((c) => (
            <div key={c.t} className="glass hero-card">
              <span className="emoji">{c.e}</span>
              <div>
                <h4>{c.t}</h4>
                <p>{c.p}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {user && (
        <section className="section">
          <div className="section-head">
            <h2>🕘 Your guides</h2>
            <p>Pick up where you left off — every guide you generate is saved to your account.</p>
          </div>
          {histLoading ? (
            <div className="empty"><span className="spinner" /> Loading your guides…</div>
          ) : history.length ? (
            <div className="grid-3">
              {history.map((h) => {
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
            <div className="glass empty">No guides yet. X-Ray your first repository above ☝️</div>
          )}
        </section>
      )}

      <section className="section" id="features">
        <div className="section-head">
          <h2>Everything you get in one guide</h2>
          <p>Seven specialist agents turn a raw repository into an interactive, explorable product — every view is generated from your actual code.</p>
        </div>
        <div className="feature-grid">
          {FEATURES.map((f) => (
            <div key={f.t} className="glass feature-card">
              <div className="feature-ic">{f.e}</div>
              <h4>{f.t}</h4>
              <p>{f.p}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section">
        <div className="section-head">
          <h2>Why teams use GitHubIQ</h2>
          <p>Onboarding to a new codebase is broken. GitHubIQ fixes the painful ramp-up.</p>
        </div>
        <div className="grid-3">
          {BENEFITS.map((b) => (
            <div key={b.t} className="glass card benefit-card">
              <h3 className={`benefit-title ${b.c}`}>{b.t}</h3>
              <p>{b.d}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="section" id="how">
        <div className="section-head">
          <h2>How it works</h2>
          <p>From a repo URL to a living guide in a couple of minutes.</p>
        </div>
        <div className="how-steps">
          {STEPS.map((s, i) => (
            <div key={s.t} className="how-step">
              <div className="glass how-card">
                <span className="how-emoji">{s.e}</span>
                <h4>{s.t}</h4>
                <p>{s.d}</p>
              </div>
              {i < STEPS.length - 1 && <span className="how-arrow">→</span>}
            </div>
          ))}
        </div>
        <div className="cta-row glass">
          <div>
            <h3>Ready to understand your next repo?</h3>
            <p className="muted">Point GitHubIQ at any public repository and explore it in minutes.</p>
          </div>
          <button className="btn accent" onClick={() => (user ? go() : nav("/login"))}>
            {user ? "🧠 X-Ray a repo" : "Get started free →"}
          </button>
        </div>
      </section>
    </>
  );
}
