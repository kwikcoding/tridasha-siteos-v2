import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { get, patch, post } from "../api";
import type { Page, Role, Site, User, WorkflowMeta } from "../types";

const MODULES = ["dashboard", "reports", "sites", "tasks", "dpr", "labour", "materials", "indents", "equipment", "expenses", "quality", "docs"];

function Modal({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-black/40 p-4" onClick={onClose}>
      <div className="card max-h-[90vh] w-full max-w-lg overflow-y-auto p-6" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-navy">{title}</h2>
          <button className="text-slate-400 hover:text-slate-700" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function UserForm({ user, roles, sites, onDone }: { user: User | null; roles: Role[]; sites: Site[]; onDone: () => void }) {
  const [f, setF] = useState({
    name: user?.name ?? "", mobile: user?.mobile ?? "", email: user?.email ?? "", role: user?.role ? String(user.role) : "",
    sites: user?.sites ?? [], is_active: user?.is_active ?? true, alert_whatsapp: user?.alert_whatsapp ?? true,
    alert_email: user?.alert_email ?? false, alert_sms: user?.alert_sms ?? false, password: "",
  });
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { ...f, role: f.role ? Number(f.role) : null };
      if (!f.password) delete body.password;
      return user ? patch(`/users/${user.id}/`, body) : post("/users/", body);
    },
    onSuccess: onDone,
  });
  const toggleSite = (id: number) => setF({ ...f, sites: f.sites.includes(id) ? f.sites.filter((x) => x !== id) : [...f.sites, id] });
  const role = roles.find((r) => String(r.id) === f.role);

  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div><label className="label">Name</label><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></div>
        <div><label className="label">Mobile (login)</label><input className="input" inputMode="numeric" value={f.mobile} onChange={(e) => setF({ ...f, mobile: e.target.value })} required /></div>
        <div className="sm:col-span-2"><label className="label">Email (optional)</label><input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></div>
        <div className="sm:col-span-2">
          <label className="label">Role</label>
          <select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} required>
            <option value="">Choose…</option>
            {roles.filter((r) => r.active).map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
          {role && <p className="mt-1 text-xs text-slate-500">{role.description}</p>}
        </div>
      </div>
      {!role?.all_sites && (
        <div>
          <div className="label">Sites</div>
          <div className="flex flex-wrap gap-2">
            {sites.map((s) => (
              <label key={s.id} className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm">
                <input type="checkbox" checked={f.sites.includes(s.id)} onChange={() => toggleSite(s.id)} /> {s.name}
              </label>
            ))}
          </div>
        </div>
      )}
      <div>
        <div className="label">Alerts</div>
        <div className="flex flex-wrap gap-4 text-sm">
          {(["alert_whatsapp", "alert_email", "alert_sms"] as const).map((k) => (
            <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{k.replace("alert_", "").replace("whatsapp", "WhatsApp").replace("sms", "SMS").replace("email", "Email")}</label>
          ))}
        </div>
      </div>
      <div>
        <label className="label">{user ? "New password (leave blank to keep)" : "Password"}</label>
        <input className="input" type="password" autoComplete="new-password" minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required={!user} />
        <p className="mt-1 text-xs text-slate-500">At least 8 characters. Share it with the person privately; they can change it after signing in.</p>
      </div>
      {user && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Login active</label>}
      {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : user ? "Save" : "Create login"}</button></div>
    </form>
  );
}

function RoleForm({ role, meta, onDone }: { role: Role | null; meta: WorkflowMeta; onDone: () => void }) {
  const [f, setF] = useState({
    key: role?.key ?? "", label: role?.label ?? "", description: role?.description ?? "", view: role?.view ?? ["dashboard", "indents"],
    edit: role?.edit ?? ["indents"], stages: role?.stages ?? [], all_sites: role?.all_sites ?? false, can_approve: role?.can_approve ?? false,
  });
  const save = useMutation({
    mutationFn: () => (role ? patch(`/roles/${role.id}/`, f) : post("/roles/", f)),
    onSuccess: onDone,
  });
  const toggle = (k: "view" | "edit" | "stages", v: string) => setF({ ...f, [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v] });

  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div><label className="label">Name</label><input className="input" value={f.label} onChange={(e) => setF({ ...f, label: e.target.value, key: role ? f.key : e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30) })} required /></div>
        <div><label className="label">Key</label><input className="input bg-slate-50" value={f.key} readOnly /></div>
        <div className="sm:col-span-2"><label className="label">Description</label><input className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
      </div>
      <div>
        <div className="label">Workflow steps this role acts on</div>
        <div className="grid gap-1.5 sm:grid-cols-2">
          {meta.stages.map((s) => (
            <label key={s.key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.stages.includes(s.key)} onChange={() => toggle("stages", s.key)} /><span className="w-6 text-xs font-bold text-slate-400">{s.n}</span>{s.short}</label>
          ))}
        </div>
      </div>
      <div>
        <div className="label">Modules (see / change)</div>
        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
          {MODULES.map((mo) => (
            <div key={mo} className="flex items-center gap-2 text-sm">
              <input type="checkbox" title="See" checked={f.view.includes(mo)} onChange={() => toggle("view", mo)} />
              <input type="checkbox" title="Change" checked={f.edit.includes(mo)} disabled={!f.view.includes(mo)} onChange={() => toggle("edit", mo)} />
              <span className="capitalize">{mo}</span>
            </div>
          ))}
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.all_sites} onChange={(e) => setF({ ...f, all_sites: e.target.checked })} /> Works on all sites</label>
      {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save role"}</button></div>
    </form>
  );
}

function SiteForm({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ code: "", name: "", address: "" });
  const save = useMutation({ mutationFn: () => post("/sites/", f), onSuccess: onDone });
  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-3">
      <div><label className="label">Code</label><input className="input" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} required maxLength={20} /></div>
      <div><label className="label">Name</label><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></div>
      <div><label className="label">Address</label><input className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></div>
      {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>Add site</button></div>
    </form>
  );
}

export default function Team() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["users"], queryFn: () => get<Page<User>>("/users/?page_size=200") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<Role[]>("/roles/") });
  const sites = useQuery({ queryKey: ["sites"], queryFn: () => get<Site[]>("/sites/") });
  const meta = useQuery({ queryKey: ["workflow"], queryFn: () => get<WorkflowMeta>("/workflow/") });
  const [editUser, setEditUser] = useState<User | null | "new">(null);
  const [editRole, setEditRole] = useState<Role | null | "new">(null);
  const [newSite, setNewSite] = useState(false);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["users"] });
    qc.invalidateQueries({ queryKey: ["roles"] });
    qc.invalidateQueries({ queryKey: ["sites"] });
    setEditUser(null);
    setEditRole(null);
    setNewSite(false);
  };
  const siteName = (id: number) => sites.data?.find((s) => s.id === id)?.code ?? id;

  return (
    <div className="space-y-6">
      <section className="card">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="font-semibold text-navy">Team — one login per person</h2>
          <button className="btn-gold" onClick={() => setEditUser("new")}>+ Add person</button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-5 py-2">Name</th><th className="px-5 py-2">Mobile</th><th className="px-5 py-2">Role</th><th className="px-5 py-2">Sites</th><th className="px-5 py-2">Status</th></tr>
            </thead>
            <tbody>
              {users.data?.results.map((u) => (
                <tr key={u.id} className="cursor-pointer border-t hover:bg-slate-50" onClick={() => setEditUser(u)}>
                  <td className="px-5 py-2.5 font-medium">{u.name}</td>
                  <td className="px-5 py-2.5 tabular-nums">{u.mobile}</td>
                  <td className="px-5 py-2.5">{u.role_label || <span className="text-red-600">No role</span>}</td>
                  <td className="px-5 py-2.5 text-slate-500">{u.sites.map(siteName).join(", ")}</td>
                  <td className="px-5 py-2.5">{u.is_active ? <span className="chip bg-green-100 text-green-800">Active</span> : <span className="chip bg-slate-200 text-slate-600">Off</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <div className="flex items-center justify-between border-b px-5 py-3">
            <h2 className="font-semibold text-navy">Roles</h2>
            <button className="btn-ghost" onClick={() => setEditRole("new")}>+ New role</button>
          </div>
          <ul className="divide-y">
            {roles.data?.map((r) => (
              <li key={r.id} className="flex items-start gap-3 px-5 py-3">
                <div className="flex-1">
                  <div className="font-medium">{r.label} {!r.builtin && <span className="chip bg-gold-100 text-gold-600">custom</span>}</div>
                  <div className="text-xs text-slate-500">{r.description}</div>
                  <div className="mt-1 text-xs text-slate-600">Steps: {r.stages.length ? r.stages.map((k) => meta.data?.stages.find((s) => s.key === k)?.n ?? k).join(", ") : "—"} · {r.user_count ?? 0} people</div>
                </div>
                {r.key !== "admin" && <button className="text-xs font-medium text-navy hover:underline" onClick={() => setEditRole(r)}>Edit</button>}
              </li>
            ))}
          </ul>
        </section>
        <section className="card">
          <div className="flex items-center justify-between border-b px-5 py-3">
            <h2 className="font-semibold text-navy">Sites</h2>
            <button className="btn-ghost" onClick={() => setNewSite(true)}>+ Add</button>
          </div>
          <ul className="divide-y">
            {sites.data?.map((s) => <li key={s.id} className="px-5 py-2.5 text-sm"><span className="font-medium">{s.code}</span> — {s.name}</li>)}
            {sites.data?.length === 0 && <li className="px-5 py-4 text-sm text-slate-500">Add your first site.</li>}
          </ul>
        </section>
      </div>

      {editUser && roles.data && sites.data && (
        <Modal title={editUser === "new" ? "Add person" : `Edit ${editUser.name}`} onClose={() => setEditUser(null)}>
          <UserForm user={editUser === "new" ? null : editUser} roles={roles.data} sites={sites.data} onDone={refresh} />
        </Modal>
      )}
      {editRole && meta.data && (
        <Modal title={editRole === "new" ? "New role" : `Edit ${editRole.label}`} onClose={() => setEditRole(null)}>
          <RoleForm role={editRole === "new" ? null : editRole} meta={meta.data} onDone={refresh} />
        </Modal>
      )}
      {newSite && <Modal title="Add site" onClose={() => setNewSite(false)}><SiteForm onDone={refresh} /></Modal>}
    </div>
  );
}
