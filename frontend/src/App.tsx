import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Landing from "./pages/Landing";
import Questionnaire from "./pages/Questionnaire";
import Analysis from "./pages/Analysis";
import Guide from "./pages/Guide";
import Login from "./pages/Login";
import History from "./pages/History";
import Admin from "./pages/Admin";
import { useAuth } from "./AuthContext";
import type { ReactElement } from "react";

function RequireAuth({ children }: { children: ReactElement }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="empty"><span className="spinner" /> Loading…</div>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return children;
}

export default function App() {
  return (
    <>
      <div className="grid-overlay" />
      <div className="app-shell">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/history" element={<RequireAuth><History /></RequireAuth>} />
          <Route path="/admin" element={<RequireAuth><Admin /></RequireAuth>} />
          <Route path="/tailor" element={<RequireAuth><Questionnaire /></RequireAuth>} />
          <Route path="/analysis/:id" element={<RequireAuth><Analysis /></RequireAuth>} />
          <Route path="/guide/:id" element={<RequireAuth><Guide /></RequireAuth>} />
          <Route path="/guide/:id/:tab" element={<RequireAuth><Guide /></RequireAuth>} />
        </Routes>
      </div>
    </>
  );
}
