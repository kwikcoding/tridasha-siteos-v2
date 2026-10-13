import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { get, post } from "../api";
import { useAuth } from "../auth";
import type { Notification, Page, Pending } from "../types";

function Bell() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const nav = useNavigate();
  const unread = useQuery({ queryKey: ["unread"], queryFn: () => get<{ count: number }>("/notifications/unread/"), refetchInterval: 30_000 });
  const list = useQuery({ queryKey: ["notifications"], queryFn: () => get<Page<Notification>>("/notifications/"), enabled: open });
  const readAll = useMutation({
    mutationFn: () => post("/notifications/read-all/"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["unread"] }),
  });
  const count = unread.data?.count ?? 0;

  async function openItem(n: Notification) {
    setOpen(false);
    if (!n.read_at) await post(`/notifications/${n.id}/read/`);
    qc.invalidateQueries({ queryKey: ["unread"] });
    if (n.link) nav(n.link);
  }

  return (
    <div className="relative">
      <button className="relative rounded-lg p-2 text-white/80 hover:bg-white/10" onClick={() => setOpen(!open)} aria-label="Alerts">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.7 21a2 2 0 0 1-3.4 0" /></svg>
        {count > 0 && <span className="absolute -right-0.5 -top-0.5 rounded-full bg-gold px-1.5 text-[10px] font-bold text-white">{count}</span>}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 max-w-[90vw] overflow-hidden rounded-xl border border-slate-200 bg-white text-slate-800 shadow-lg">
          <div className="flex items-center justify-between border-b px-4 py-2.5">
            <span className="text-sm font-semibold">Alerts</span>
            <button className="text-xs text-navy hover:underline" onClick={() => readAll.mutate()}>Mark all read</button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {list.data?.results.length === 0 && <p className="p-4 text-sm text-slate-500">Nothing yet.</p>}
            {list.data?.results.map((n) => (
              <button key={n.id} onClick={() => openItem(n)} className={`block w-full border-b px-4 py-3 text-left hover:bg-slate-50 ${n.read_at ? "" : "bg-gold-50"}`}>
                <div className="text-sm font-medium">{n.title}</div>
                <div className="mt-0.5 whitespace-pre-line text-xs text-slate-500">{n.body}</div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Sidebar: the same groups as v1. Only modules that exist in v2 and that the person may view are shown. */
const NAV: { group: string; items: { module: string; label: string; to: string; admin?: boolean }[] }[] = [
  { group: "Overview", items: [{ module: "dashboard", label: "Dashboard", to: "/" }] },
  { group: "Resources", items: [
    { module: "materials", label: "Materials & Stock", to: "/materials" },
    { module: "indents", label: "Indents & Purchase", to: "/indents" },
  ] },
  { group: "Administration", items: [
    { module: "team", label: "Team & Roles", to: "/team" },
    { module: "settings", label: "Settings", to: "/settings", admin: true },
  ] },
];

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { me, can } = useAuth();
  const pending = useQuery({ queryKey: ["pending"], queryFn: () => get<Pending>("/auth/pending/"), refetchInterval: 30_000, enabled: !!me });
  const link = ({ isActive }: { isActive: boolean }) =>
    `flex items-center justify-between rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/5 hover:text-white"}`;
  return (
    <nav className="space-y-5 px-3 py-4">
      {NAV.map((g) => {
        const items = g.items.filter((it) => can(it.module) && (!it.admin || me?.is_admin));
        if (!items.length) return null;
        return (
          <div key={g.group}>
            <div className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-widest text-gold/80">{g.group}</div>
            {items.map((it) => (
              <NavLink key={it.to} to={it.to} end={it.to === "/"} className={link} onClick={onNavigate}>
                <span>{it.label}</span>
                {it.module === "indents" && (pending.data?.total ?? 0) > 0 && (
                  <span className="rounded-full bg-gold px-1.5 text-[10px] font-bold text-white">{pending.data?.total}</span>
                )}
              </NavLink>
            ))}
          </div>
        );
      })}
    </nav>
  );
}

export default function Layout() {
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen lg:flex">
      {/* sidebar — fixed on desktop, slide-over on phones */}
      <aside className={`fixed inset-y-0 left-0 z-30 w-64 transform bg-navy transition lg:static lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}>
        <Link to="/" className="flex items-center gap-2 border-b border-white/10 px-5 py-4 font-semibold tracking-tight text-white" onClick={() => setOpen(false)}>
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-gold text-sm font-bold">T</span>
          Tridasha SiteOS
        </Link>
        <Sidebar onNavigate={() => setOpen(false)} />
      </aside>
      {open && <div className="fixed inset-0 z-20 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 bg-navy px-4 py-2.5 text-white lg:bg-white lg:text-slate-800 lg:shadow-sm">
          <button className="rounded-lg p-2 hover:bg-white/10 lg:hidden" onClick={() => setOpen(true)} aria-label="Menu">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
          </button>
          <div className="flex-1" />
          <div className="rounded-lg bg-navy lg:rounded-full"><Bell /></div>
          <Link to="/profile" className="text-right text-xs leading-tight hover:underline">
            <div className="font-medium">{me?.name}</div>
            <div className="opacity-60">{me?.is_admin ? "Administrator" : me?.roles.map((r) => r.label).join(", ")}</div>
          </Link>
          <button className="rounded-lg px-2 py-1 text-xs opacity-70 hover:opacity-100" onClick={async () => { await logout(); nav("/login"); }}>
            Log out
          </button>
        </header>
        <main className="mx-auto w-full max-w-6xl px-4 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
