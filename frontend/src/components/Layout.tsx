import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { get, post } from "../api";
import { useAuth } from "../auth";
import type { Notification, Page } from "../types";

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

export default function Layout() {
  const { me, logout, can } = useAuth();
  const nav = useNavigate();
  const link = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-1.5 text-sm font-medium ${isActive ? "bg-white/15 text-white" : "text-white/70 hover:text-white"}`;

  return (
    <div className="min-h-screen">
      <header className="bg-navy text-white">
        <div className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-gold text-sm font-bold">T</span>
            <span className="hidden sm:inline">Tridasha SiteOS</span>
          </Link>
          <nav className="flex flex-1 gap-1">
            {can("indents") && <NavLink to="/indents" className={link}>Indents</NavLink>}
            {me?.is_admin && <NavLink to="/team" className={link}>Team &amp; roles</NavLink>}
          </nav>
          <Bell />
          <div className="hidden text-right text-xs leading-tight sm:block">
            <div className="font-medium">{me?.name}</div>
            <div className="text-white/60">{me?.is_admin ? "Administrator" : me?.role?.label}</div>
          </div>
          <button className="rounded-lg px-2 py-1 text-xs text-white/70 hover:bg-white/10" onClick={async () => { await logout(); nav("/login"); }}>
            Log out
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
