import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import AccessDenied from "./pages/AccessDenied";
import Dashboard from "./pages/Dashboard";
import IndentDetail from "./pages/IndentDetail";
import Indents from "./pages/Indents";
import Login from "./pages/Login";
import Materials from "./pages/Materials";
import NewIndent from "./pages/NewIndent";
import Profile from "./pages/Profile";
import Settings from "./pages/Settings";
import Team from "./pages/Team";

/** Hides what a role can't use. The server enforces the same rules on every request. */
function Protected({ children, module, code, admin }: { children: ReactNode; module?: string; code?: string; admin?: boolean }) {
  const { me, loading, can, has } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="p-10 text-center text-slate-500">Loading…</div>;
  if (!me) return <Navigate to="/login" replace />;
  if (me.must_change_password && loc.pathname !== "/profile") return <Navigate to="/profile" replace />;
  if ((admin && !me.is_admin) || (module && !can(module)) || (code && !has(code))) return <AccessDenied />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Protected module="dashboard"><Dashboard /></Protected>} />
        <Route path="/indents" element={<Protected module="indents"><Indents /></Protected>} />
        <Route path="/indents/new" element={<Protected code="indents.create"><NewIndent /></Protected>} />
        <Route path="/indents/:id" element={<Protected module="indents"><IndentDetail /></Protected>} />
        <Route path="/materials" element={<Protected module="materials"><Materials /></Protected>} />
        <Route path="/team" element={<Protected module="team"><Team /></Protected>} />
        <Route path="/settings" element={<Protected admin><Settings /></Protected>} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/denied" element={<AccessDenied />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
