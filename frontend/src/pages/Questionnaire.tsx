import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import TopBar from "../components/TopBar";
import { startAnalysis, ApiError } from "../api";
import { useAuth, formatCooldown } from "../AuthContext";
import type { Depth, Familiarity, Role } from "../types";

const ROLES: { id: Role; icon: string; title: string; desc: string }[] = [
  { id: "new_to_team", icon: "🌱", title: "New to the team", desc: "I need the full end-to-end picture before my first PR." },
  { id: "frontend", icon: "🎨", title: "Frontend focus", desc: "Show me the UI layer, APIs I call and data contracts." },
  { id: "backend", icon: "⚙️", title: "Backend / infra", desc: "Services, queues, schemas and deployment flow." },
];

const FAMILIARITY: { id: Familiarity; label: string }[] = [
  { id: "brand_new", label: "Brand new" },
  { id: "some_exposure", label: "Some exposure" },
  { id: "comfortable", label: "Comfortable" },
  { id: "expert", label: "Expert" },
];

const GOALS = [
  "Request & data flow",
  "Architecture & components",
  "Database schema",
  "Auth & security",
  "Hands-on sandbox",
  "Deployment & CI/CD",
  "Language fundamentals refresher",
  "Testing strategy",
];

const DEPTHS: { id: Depth; icon: string; title: string; desc: string }[] = [
  { id: "quick", icon: "⚡", title: "Quick orientation", desc: "Just enough to find my way and ship something small." },
  { id: "guided", icon: "🧭", title: "Guided tour", desc: "Balanced walkthrough of the parts that matter most." },
  { id: "deep", icon: "🔬", title: "Deep dive", desc: "Every layer, edge case and idiom. Make me dangerous." },
];

export default function Questionnaire() {
  const [params] = useSearchParams();
  const repo = params.get("repo") || "";
  const nav = useNavigate();
  const { user, refreshRate } = useAuth();

  const [role, setRole] = useState<Role>("new_to_team");
  const [familiarity, setFamiliarity] = useState<Familiarity>("some_exposure");
  const [goals, setGoals] = useState<string[]>(["Request & data flow"]);
  const [depth, setDepth] = useState<Depth>("guided");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const cooling = user && !user.is_admin && !user.rate?.can_generate;

  const toggleGoal = (g: string) =>
    setGoals((prev) => (prev.includes(g) ? prev.filter((x) => x !== g) : [...prev, g]));

  const generate = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await startAnalysis(repo, { role, familiarity, goals, depth });
      await refreshRate();
      nav(`/analysis/${res.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        await refreshRate();
      }
      setError((e as Error).message);
      setLoading(false);
    }
  };

  const repoLabel = repo.replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "");

  return (
    <>
      <TopBar
        nav={[
          { label: "Repo", to: "/" },
          { label: "Tailor your guide", to: "#", active: true },
          { label: "Generate", to: "#" },
        ]}
        right={<span className="pill"><span className="dot g" /> Repo ready</span>}
      />

      <div className="steps-row">
        <span className="step-num done">✓</span> Repo analyzed
        <span className="step-sep" />
        <span className="step-num active">2</span> Tailor your guide
        <span className="step-sep" />
        <span className="step-num">3</span> Generate
      </div>

      <div className="page-head">
        <h2>Let's tailor your onboarding 🎯</h2>
        <p>
          We'll analyse <b>{repoLabel || "your repository"}</b>. A few quick
          questions so your guide matches exactly what <i>you</i> need to learn.
        </p>
      </div>

      <div className="field-label">
        👤 What's your role on this project? <small>— shapes depth &amp; vocabulary</small>
      </div>
      <div className="grid-3">
        {ROLES.map((r) => (
          <div
            key={r.id}
            className={`glass card selectable ${role === r.id ? "selected" : ""}`}
            onClick={() => setRole(r.id)}
          >
            <h4>{r.icon} {r.title} {role === r.id && <span style={{ marginLeft: "auto", color: "var(--blue)" }}>✓</span>}</h4>
            <p>{r.desc}</p>
          </div>
        ))}
      </div>

      <div className="field-label">🧠 How familiar are you with the tech here?</div>
      <div className="seg">
        {FAMILIARITY.map((f) => (
          <button key={f.id} className={familiarity === f.id ? "on" : ""} onClick={() => setFamiliarity(f.id)}>
            {f.label}
          </button>
        ))}
      </div>

      <div className="field-label">🎯 What do you want to walk away understanding?</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
        {GOALS.map((g) => (
          <button key={g} className={`chip ${goals.includes(g) ? "on" : ""}`} onClick={() => toggleGoal(g)}>
            {g}
          </button>
        ))}
      </div>

      <div className="field-label">🕳️ How deep should we go?</div>
      <div className="grid-3">
        {DEPTHS.map((d) => (
          <div
            key={d.id}
            className={`glass card selectable ${depth === d.id ? "selected" : ""}`}
            onClick={() => setDepth(d.id)}
          >
            <h4>{d.icon} {d.title} {depth === d.id && <span style={{ marginLeft: "auto", color: "var(--blue)" }}>✓</span>}</h4>
            <p>{d.desc}</p>
          </div>
        ))}
      </div>

      {cooling && (
        <div className="glass cooldown-banner" style={{ marginTop: 18 }}>
          ⏳ You've used your generation for this window. Next one available in{" "}
          <b>{formatCooldown(user!.rate.seconds_left)}</b>{" "}
          ({user!.rate.max_attempts} per {user!.rate.window_hours}h).
        </div>
      )}
      {error && <p style={{ color: "var(--pink)", marginTop: 18 }}>{error}</p>}

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 30, gap: 12, flexWrap: "wrap" }}>
        <span className="muted">🧩 Six specialist agents will build your guide in parallel.</span>
        <button className="btn primary" disabled={loading || !repo || !!cooling} onClick={generate}>
          {loading ? <><span className="spinner" /> Starting…</> : "Generate my interactive guide →"}
        </button>
      </div>
    </>
  );
}
