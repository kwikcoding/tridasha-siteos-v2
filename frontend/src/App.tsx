import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import IndentDetail from "./pages/IndentDetail";
import Indents from "./pages/Indents";
import Login from "./pages/Login";
import NewIndent from "./pages/NewIndent";
import Team from "./pages/Team";

function Protected({ children, module, admin }: { children: ReactNode; module?: string; admin?: boolean }) {
  const { me, loading, can } = useAuth();
  if (loading) return <div className="p-10 text-center text-slate-500">Loading…</div>;
  if (!me) return <Navigate to="/login" replace />;
  if (admin && !me.is_admin) return <Navigate to="/" replace />;
  if (module && !can(module)) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route index element={<Navigate to="/indents" replace />} />
        <Route path="/indents" element={<Protected module="indents"><Indents /></Protected>} />
        <Route path="/indents/new" element={<Protected module="indents"><NewIndent /></Protected>} />
        <Route path="/indents/:id" element={<Protected module="indents"><IndentDetail /></Protected>} />
        <Route path="/team" element={<Protected admin><Team /></Protected>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
