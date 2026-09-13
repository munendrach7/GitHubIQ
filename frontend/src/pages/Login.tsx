import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import TopBar from "../components/TopBar";
import { useAuth } from "../AuthContext";
import { ApiError } from "../api";

export default function Login() {
  const { login, signup } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";

  const [mode, setMode] = useState<"login" | "signup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (mode === "login") await login(username.trim(), password);
      else await signup(username.trim(), password);
      nav(next);
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : (err as Error).message;
      setError(msg);
      setBusy(false);
    }
  };

  return (
    <>
      <TopBar
        right={<span className="pill"><span className="dot g" /> Secure sign-in</span>}
      />
      <div className="auth-wrap">
        <div className="glass auth-card">
          <div className="auth-logo">🧠</div>
          <h2 style={{ textAlign: "center" }}>
            {mode === "login" ? "Welcome back" : "Create your account"}
          </h2>
          <p className="muted" style={{ textAlign: "center", marginTop: 6 }}>
            {mode === "login"
              ? "Sign in to X-Ray a repository."
              : "Sign up to generate an interactive onboarding guide."}
          </p>

          <div className="seg" style={{ margin: "20px auto 4px", display: "flex", width: "fit-content" }}>
            <button className={mode === "login" ? "on" : ""} onClick={() => setMode("login")}>Sign in</button>
            <button className={mode === "signup" ? "on" : ""} onClick={() => setMode("signup")}>Sign up</button>
          </div>

          <form onSubmit={submit} className="auth-form">
            <label className="auth-label">Username</label>
            <input
              className="auth-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="yourname"
              required
              minLength={3}
            />
            <label className="auth-label">Password</label>
            <input
              className="auth-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder="••••••••"
              required
              minLength={6}
            />
            {error && <div className="auth-error">{error}</div>}
            <button className="btn accent" type="submit" disabled={busy} style={{ marginTop: 16, width: "100%", justifyContent: "center" }}>
              {busy ? <><span className="spinner" /> Please wait…</> : mode === "login" ? "Sign in →" : "Create account →"}
            </button>
          </form>

          <p className="dim" style={{ textAlign: "center", marginTop: 16, fontSize: 12.5 }}>
            Each account can generate 1 analysis every 4 hours.
          </p>
        </div>
      </div>
    </>
  );
}
