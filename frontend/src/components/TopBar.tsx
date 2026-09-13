import { useTheme } from "../ThemeContext";
import { useAuth, formatCooldown } from "../AuthContext";
import { Link, useNavigate } from "react-router-dom";

interface Props {
  sub?: string;
  nav?: { label: string; to: string; active?: boolean }[];
  right?: React.ReactNode;
}

export default function TopBar({ sub = "your Project Tutor", nav, right }: Props) {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const cooling = user && !user.is_admin && !user.rate?.can_generate;

  return (
    <div className="topbar">
      <Link to="/" className="brand">
        <div className="logo">🧠</div>
        <div>
          <div className="name">
            GitHub<b>IQ</b>
          </div>
          <div className="sub">{sub}</div>
        </div>
      </Link>

      {nav && (
        <div className="nav">
          {nav.map((n) => (
            <Link key={n.label} to={n.to} className={n.active ? "active" : ""}>
              {n.label}
            </Link>
          ))}
        </div>
      )}

      <div className="top-actions">
        {right}
        {user && (
          <div className="user-chip">
            <Link to="/history" className="myguides-link" title="Your saved guides">🕘 My guides</Link>
            <span className="user-name">
              {user.is_admin && <span className="admin-badge">ADMIN</span>}
              {user.username}
            </span>
            {cooling && (
              <span className="cooldown" title="Time until your next generation">
                ⏳ {formatCooldown(user.rate.seconds_left)}
              </span>
            )}
            <button className="link-btn" onClick={() => { logout(); navigate("/login"); }}>
              Log out
            </button>
          </div>
        )}
        <button
          className="icon-btn"
          onClick={toggle}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? "☀️" : "🌙"}
        </button>
      </div>
    </div>
  );
}
