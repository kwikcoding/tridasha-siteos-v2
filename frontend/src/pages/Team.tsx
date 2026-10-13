import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { get, patch, post } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { dateTimeFmt } from "../components/ui";
import type { AuditEntry, Department, Page, PermCatalogue, Role, Site, User } from "../types";

const err = (e: unknown) => (e ? <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(e as Error).message}</p> : null);

function useTeamData() {
  const users = useQuery({ queryKey: ["users"], queryFn: () => get<Page<User>>("/users/?page_size=500") });
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => get<Role[]>("/roles/") });
  const sites = useQuery({ queryKey: ["sites"], queryFn: () => get<Site[]>("/sites/") });
  const depts = useQuery({ queryKey: ["departments"], queryFn: () => get<Department[]>("/departments/") });
  const cat = useQuery({ queryKey: ["perm-catalogue"], queryFn: () => get<PermCatalogue>("/permissions/"), staleTime: 3600_000 });
  return { users, roles, sites, depts, cat };
}

/* ------------------------------------------------------------------ people */
function UserForm({ user, onDone }: { user: User | null; onDone: () => void }) {
  const { users, roles, sites, depts } = useTeamData();
  const [f, setF] = useState({
    name: user?.name ?? "", mobile: user?.mobile ?? "", email: user?.email ?? "", employee_id: user?.employee_id ?? "",
    designation: user?.designation ?? "", department: user?.department ? String(user.department) : "",
    reporting_manager: user?.reporting_manager ? String(user.reporting_manager) : "",
    role: user?.role ? String(user.role) : "", extra_roles: user?.extra_roles ?? [], sites: user?.sites ?? [],
    is_active: user?.is_active ?? true, alert_whatsapp: user?.alert_whatsapp ?? true, alert_email: user?.alert_email ?? false,
    alert_sms: user?.alert_sms ?? false, password: "",
  });
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        ...f, role: f.role ? Number(f.role) : null, department: f.department ? Number(f.department) : null,
        reporting_manager: f.reporting_manager ? Number(f.reporting_manager) : null, employee_id: f.employee_id || null,
      };
      if (user) delete body.password;
      return user ? patch(`/users/${user.id}/`, body) : post("/users/", body);
    },
    onSuccess: onDone,
  });
  const toggle = (k: "sites" | "extra_roles", id: number) => setF({ ...f, [k]: f[k].includes(id) ? f[k].filter((x) => x !== id) : [...f[k], id] });
  const allRoles = roles.data?.filter((r) => r.active) ?? [];
  const chosen = allRoles.filter((r) => String(r.id) === f.role || f.extra_roles.includes(r.id));
  const needsSites = !chosen.some((r) => r.all_sites);
  const inp = (k: keyof typeof f, label: string, type = "text", extra: Record<string, unknown> = {}) => (
    <div><label className="label" htmlFor={`u-${k}`}>{label}</label>
      <input id={`u-${k}`} className="input" type={type} value={String(f[k])} onChange={(e) => setF({ ...f, [k]: e.target.value })} {...extra} /></div>
  );

  return (
    <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        {inp("name", "Full name", "text", { required: true })}
        {inp("mobile", "Mobile (login)", "text", { required: true, inputMode: "numeric" })}
        {inp("employee_id", "Employee ID")}
        {inp("email", "Email", "email")}
        {inp("designation", "Designation")}
        <div><label className="label" htmlFor="u-dept">Department</label>
          <select id="u-dept" className="input" value={f.department} onChange={(e) => setF({ ...f, department: e.target.value })}>
            <option value="">—</option>{depts.data?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select></div>
        <div className="sm:col-span-2"><label className="label" htmlFor="u-mgr">Reporting manager</label>
          <select id="u-mgr" className="input" value={f.reporting_manager} onChange={(e) => setF({ ...f, reporting_manager: e.target.value })}>
            <option value="">—</option>{users.data?.results.filter((u) => u.id !== user?.id && u.is_active).map((u) => <option key={u.id} value={u.id}>{u.name} — {u.designation || u.role_label}</option>)}
          </select></div>
      </div>
      <div><label className="label" htmlFor="u-role">Main role</label>
        <select id="u-role" className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value, extra_roles: f.extra_roles.filter((x) => String(x) !== e.target.value) })} required>
          <option value="">Choose…</option>{allRoles.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
        </select></div>
      <div>
        <div className="label">Additional roles (optional)</div>
        <div className="flex flex-wrap gap-2">
          {allRoles.filter((r) => String(r.id) !== f.role && r.key !== "admin").map((r) => (
            <label key={r.id} className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm">
              <input type="checkbox" checked={f.extra_roles.includes(r.id)} onChange={() => toggle("extra_roles", r.id)} /> {r.label}
            </label>
          ))}
        </div>
      </div>
      {needsSites && (
        <div>
          <div className="label">Sites / projects</div>
          <div className="flex flex-wrap gap-2">
            {sites.data?.map((s) => (
              <label key={s.id} className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm">
                <input type="checkbox" checked={f.sites.includes(s.id)} onChange={() => toggle("sites", s.id)} /> {s.code} — {s.name}
              </label>
            ))}
          </div>
        </div>
      )}
      <div>
        <div className="label">Alerts</div>
        <div className="flex flex-wrap gap-4 text-sm">
          {([["alert_whatsapp", "WhatsApp"], ["alert_email", "Email"], ["alert_sms", "SMS"]] as const).map(([k, l]) => (
            <label key={k} className="flex items-center gap-1.5"><input type="checkbox" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{l}</label>
          ))}
        </div>
      </div>
      {!user && (
        <div>
          <label className="label" htmlFor="u-pw">Temporary password</label>
          <input id="u-pw" className="input" type="password" autoComplete="new-password" minLength={8} value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required />
          <p className="mt-1 text-xs text-slate-500">Share it privately. They must set their own password at first sign-in.</p>
        </div>
      )}
      {user && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> Login active</label>}
      {err(save.error)}
      <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : user ? "Save" : "Create login"}</button></div>
    </form>
  );
}

function ResetPassword({ user, onDone }: { user: User; onDone: () => void }) {
  const [pw, setPw] = useState("");
  const run = useMutation({ mutationFn: () => post(`/users/${user.id}/reset-password/`, { password: pw }), onSuccess: onDone });
  return (
    <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); run.mutate(); }}>
      <p className="text-sm text-slate-600">Set a temporary password for <b>{user.name}</b>. They’ll be asked to choose their own at their next sign-in. This is recorded in the audit log.</p>
      <label className="label" htmlFor="rp">Temporary password</label>
      <input id="rp" className="input" type="password" autoComplete="new-password" minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} required />
      {err(run.error)}
      <div className="flex justify-end"><button className="btn-primary" disabled={run.isPending}>Reset password</button></div>
    </form>
  );
}

function PeopleTab() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { users, sites } = useTeamData();
  const [edit, setEdit] = useState<User | null | "new">(null);
  const [reset, setReset] = useState<User | null>(null);
  const [q, setQ] = useState("");
  const refresh = () => { setEdit(null); setReset(null); qc.invalidateQueries({ queryKey: ["users"] }); qc.invalidateQueries({ queryKey: ["roles"] }); };
  const siteCode = (id: number) => sites.data?.find((s) => s.id === id)?.code ?? id;
  const rows = (users.data?.results ?? []).filter((u) => !q || `${u.name} ${u.mobile} ${u.employee_id ?? ""} ${u.designation} ${u.department_name}`.toLowerCase().includes(q.toLowerCase()));
  const admin = me?.is_admin;

  return (
    <section className="card">
      <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
        <h2 className="font-semibold text-navy">People — one login per person</h2>
        <div className="flex-1" />
        <input className="input max-w-[220px]" placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
        {admin && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add person</button>}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr><th className="px-4 py-2">Name</th><th className="px-4 py-2">Mobile</th><th className="px-4 py-2">Roles</th><th className="px-4 py-2">Department</th><th className="px-4 py-2">Sites</th><th className="px-4 py-2">Last sign-in</th><th className="px-4 py-2">Status</th>{admin && <th />}</tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="border-t">
                <td className="px-4 py-2.5"><div className="font-medium">{u.name}</div><div className="text-xs text-slate-500">{[u.employee_id, u.designation].filter(Boolean).join(" · ")}</div></td>
                <td className="px-4 py-2.5 tabular-nums">{u.mobile}</td>
                <td className="px-4 py-2.5">{u.all_role_labels.join(", ") || <span className="text-red-600">No role</span>}</td>
                <td className="px-4 py-2.5 text-slate-600">{u.department_name}</td>
                <td className="px-4 py-2.5 text-slate-500">{u.sites.map(siteCode).join(", ")}</td>
                <td className="px-4 py-2.5 text-xs text-slate-500">{dateTimeFmt(u.last_login) || "never"}</td>
                <td className="px-4 py-2.5">
                  {u.is_active ? <span className="chip bg-green-100 text-green-800">Active</span> : <span className="chip bg-slate-200 text-slate-600">Off</span>}
                  {u.must_change_password && <span className="ml-1 chip bg-gold-100 text-gold-600">temp password</span>}
                </td>
                {admin && <td className="whitespace-nowrap px-4 py-2.5 text-right">
                  <button className="text-xs font-medium text-navy hover:underline" onClick={() => setEdit(u)}>Edit</button>
                  <button className="ml-3 text-xs font-medium text-navy hover:underline" onClick={() => setReset(u)}>Reset password</button>
                </td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {edit && <Modal title={edit === "new" ? "Add person" : `Edit ${edit.name}`} onClose={() => setEdit(null)} wide><UserForm user={edit === "new" ? null : edit} onDone={refresh} /></Modal>}
      {reset && <Modal title="Reset password" onClose={() => setReset(null)}><ResetPassword user={reset} onDone={refresh} /></Modal>}
    </section>
  );
}

/* ------------------------------------------------------------------ roles */
function RoleForm({ role, onDone }: { role: Role | null; onDone: () => void }) {
  const { cat } = useTeamData();
  const [f, setF] = useState({
    key: role?.key ?? "", label: role?.label ?? "", description: role?.description ?? "", stages: role?.stages ?? [],
    step_actions: role?.step_actions ?? {}, all_sites: role?.all_sites ?? false,
    permissions: role?.permissions ?? ["dashboard.view", "indents.view", "indents.create"],
  });
  const save = useMutation({ mutationFn: () => (role ? patch(`/roles/${role.id}/`, f) : post("/roles/", f)), onSuccess: onDone });
  const toggleStage = (k: string) => setF({ ...f, stages: f.stages.includes(k) ? f.stages.filter((x) => x !== k) : [...f.stages, k] });
  const toggleAction = (st: string, a: string, all: string[]) => {
    const cur = f.step_actions[st] ?? all;
    const next = cur.includes(a) ? cur.filter((x) => x !== a) : [...cur, a];
    setF({ ...f, step_actions: { ...f.step_actions, [st]: next } });
  };
  const labels: Record<string, string> = { approve: "Approve", reject: "Reject", sendback: "Send back", hold: "Hold", issue: "Issue from stock", purchase: "Send to purchase",
    rejectVendor: "Reject supplier", po: "Issue PO", track: "Update delivery", cancelBalance: "Cancel balance", receive: "Receive", rejectReceipt: "Reject delivery",
    issueClose: "Issue & close", verifyInv: "Verify invoice", holdInv: "Hold invoice", returnInv: "Return invoice", authorizePay: "Authorise payment", pay: "Settle payment", holdPay: "Hold payment" };

  return (
    <form className="space-y-4" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><label className="label" htmlFor="r-label">Name</label><input id="r-label" className="input" value={f.label} required
          onChange={(e) => setF({ ...f, label: e.target.value, key: role ? f.key : e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 30) })} /></div>
        <div><label className="label" htmlFor="r-key">Key</label><input id="r-key" className="input bg-slate-50" value={f.key} readOnly /></div>
        <div className="sm:col-span-2"><label className="label" htmlFor="r-desc">Responsibilities</label><input id="r-desc" className="input" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></div>
      </div>
      <div>
        <div className="label">Workflow steps this role acts on — and which actions within each step</div>
        <div className="space-y-1.5">
          {cat.data?.steps.map((s) => {
            const on = f.stages.includes(s.key);
            const allowed = f.step_actions[s.key] ?? s.actions;
            return (
              <div key={s.key} className={`rounded-lg border px-3 py-2 ${on ? "border-navy/30 bg-navy-50/50" : ""}`}>
                <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={on} onChange={() => toggleStage(s.key)} />
                  <span className="w-8 text-xs font-bold text-slate-400">{s.n}</span>{s.short}<span className="text-xs text-slate-400">· {s.dept}</span></label>
                {on && s.actions.length > 1 && (
                  <div className="ml-12 mt-1.5 flex flex-wrap gap-3 text-xs">
                    {s.actions.map((a) => (
                      <label key={a} className="flex items-center gap-1"><input type="checkbox" checked={allowed.includes(a)} onChange={() => toggleAction(s.key, a, s.actions)} />{labels[a] ?? a}</label>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.all_sites} onChange={(e) => setF({ ...f, all_sites: e.target.checked })} /> Works on all sites / projects</label>
      <p className="text-xs text-slate-500">Module permissions are set in the <b>Permission matrix</b> tab.</p>
      {err(save.error)}
      <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>Save role</button></div>
    </form>
  );
}

function RolesTab() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { roles, cat } = useTeamData();
  const [edit, setEdit] = useState<Role | null | "new">(null);
  const refresh = () => { setEdit(null); qc.invalidateQueries({ queryKey: ["roles"] }); };
  const stepN = (k: string) => cat.data?.steps.find((s) => s.key === k)?.n ?? k;
  return (
    <section className="card">
      <div className="flex items-center justify-between border-b px-5 py-3">
        <h2 className="font-semibold text-navy">Roles</h2>
        {me?.is_admin && <button className="btn-ghost" onClick={() => setEdit("new")}>+ New role</button>}
      </div>
      <ul className="divide-y">
        {roles.data?.map((r) => (
          <li key={r.id} className="flex items-start gap-3 px-5 py-3">
            <div className="flex-1">
              <div className="font-medium">{r.label} {!r.builtin && <span className="chip bg-gold-100 text-gold-600">custom</span>}</div>
              <div className="text-xs text-slate-500">{r.description}</div>
              <div className="mt-1 text-xs text-slate-600">
                Steps: {r.stages.length ? r.stages.map((k) => stepN(k) + (r.step_actions[k] ? "*" : "")).join(", ") : "—"} · {r.permissions.length} permissions · {r.user_count ?? 0} people
              </div>
            </div>
            {me?.is_admin && r.key !== "admin" && <button className="text-xs font-medium text-navy hover:underline" onClick={() => setEdit(r)}>Edit</button>}
          </li>
        ))}
      </ul>
      <p className="border-t px-5 py-2 text-xs text-slate-500">* = only some actions within that step</p>
      {edit && <Modal title={edit === "new" ? "New role" : `Edit ${edit.label}`} onClose={() => setEdit(null)} wide><RoleForm role={edit === "new" ? null : edit} onDone={refresh} /></Modal>}
    </section>
  );
}

/* ------------------------------------------------------------------ permission matrix */
function MatrixTab() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { roles, cat } = useTeamData();
  const [draft, setDraft] = useState<Record<number, string[]>>({});
  const [group, setGroup] = useState("");
  const [saved, setSaved] = useState("");
  useEffect(() => { if (cat.data && !group) setGroup(cat.data.modules[0].group); }, [cat.data, group]);
  const editable = (roles.data ?? []).filter((r) => r.key !== "admin");
  const codesOf = (r: Role) => draft[r.id] ?? r.permissions;
  const changed = editable.filter((r) => draft[r.id] && JSON.stringify([...draft[r.id]].sort()) !== JSON.stringify([...r.permissions].sort()));
  const save = useMutation({
    mutationFn: async () => { for (const r of changed) await patch(`/roles/${r.id}/`, { permissions: draft[r.id] }); },
    onSuccess: () => { setSaved(`Saved ${changed.length} role(s).`); setDraft({}); qc.invalidateQueries({ queryKey: ["roles"] }); qc.invalidateQueries({ queryKey: ["me"] }); },
  });
  const toggle = (r: Role, code: string) => {
    if (!me?.is_admin) return;
    const cur = codesOf(r);
    let next = cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code];
    const [mod, verb] = code.split(".");
    if (verb === "view" && !next.includes(code)) next = next.filter((c) => !c.startsWith(mod + "."));   // no view → nothing else
    if (verb !== "view" && next.includes(code) && !next.includes(`${mod}.view`)) next = [...next, `${mod}.view`];
    setDraft({ ...draft, [r.id]: next });
    setSaved("");
  };
  const g = cat.data?.modules.find((x) => x.group === group);
  const cols = useMemo(() => g?.modules.flatMap((m) => m.perms.map((p) => ({ ...p, module: m.label }))) ?? [], [g]);

  if (!cat.data || !roles.data) return <p className="p-6 text-center text-slate-500">Loading…</p>;
  return (
    <section className="card">
      <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
        <h2 className="font-semibold text-navy">Permission matrix</h2>
        <div className="flex-1" />
        <div className="flex flex-wrap gap-1">
          {cat.data.modules.map((m) => (
            <button key={m.group} onClick={() => setGroup(m.group)} className={`rounded-md px-2.5 py-1 text-xs font-medium ${group === m.group ? "bg-navy text-white" : "bg-slate-100 text-slate-600"}`}>{m.group}</button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="text-sm">
          <thead>
            <tr className="bg-slate-50 text-xs text-slate-500">
              <th className="sticky left-0 bg-slate-50 px-4 py-2 text-left">Role</th>
              {g?.modules.map((m) => <th key={m.key} colSpan={m.perms.length} className="border-l px-2 py-2 text-center font-semibold text-navy">{m.label}</th>)}
            </tr>
            <tr className="bg-slate-50 text-[11px] text-slate-500">
              <th className="sticky left-0 bg-slate-50" />
              {cols.map((c) => <th key={c.code} className={`px-2 pb-2 font-medium ${c.verb === "view" ? "border-l" : ""}`}>{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            <tr className="border-t bg-gold-50/40">
              <td className="sticky left-0 bg-gold-50 px-4 py-2 font-medium">Administrator</td>
              {cols.map((c) => <td key={c.code} className={`text-center ${c.verb === "view" ? "border-l" : ""}`}>✓</td>)}
            </tr>
            {editable.map((r) => (
              <tr key={r.id} className="border-t">
                <td className="sticky left-0 whitespace-nowrap bg-white px-4 py-2 font-medium">{r.label}{draft[r.id] && <span className="ml-1 text-gold-600">•</span>}</td>
                {cols.map((c) => (
                  <td key={c.code} className={`text-center ${c.verb === "view" ? "border-l" : ""}`}>
                    {c.admin_only ? <span className="text-xs text-slate-300">admin</span> : (
                      <input type="checkbox" aria-label={`${r.label}: ${c.module} ${c.label}`} checked={codesOf(r).includes(c.code)} disabled={!me?.is_admin} onChange={() => toggle(r, c.code)} />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 border-t px-5 py-3">
        <p className="flex-1 text-xs text-slate-500">Enforced by the server on every request. Modules not built yet keep their settings for when they arrive.</p>
        {saved && <span className="text-sm text-green-700">{saved}</span>}
        {err(save.error)}
        {me?.is_admin && <button className="btn-primary" disabled={!changed.length || save.isPending} onClick={() => save.mutate()}>Save {changed.length ? `(${changed.length})` : ""}</button>}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ departments & sites */
function DepartmentsTab() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { depts, users } = useTeamData();
  const [f, setF] = useState({ name: "", code: "", head: "" });
  const add = useMutation({
    mutationFn: () => post("/departments/", { ...f, head: f.head ? Number(f.head) : null }),
    onSuccess: () => { setF({ name: "", code: "", head: "" }); qc.invalidateQueries({ queryKey: ["departments"] }); },
  });
  return (
    <section className="card">
      <div className="border-b px-5 py-3"><h2 className="font-semibold text-navy">Departments</h2></div>
      <ul className="divide-y">
        {depts.data?.map((d) => <li key={d.id} className="flex gap-3 px-5 py-2.5 text-sm"><span className="flex-1 font-medium">{d.name} <span className="text-xs text-slate-400">{d.code}</span></span><span className="text-slate-500">{d.head_name && `Head: ${d.head_name} · `}{d.staff_count} people</span></li>)}
        {depts.data?.length === 0 && <li className="px-5 py-4 text-sm text-slate-500">No departments yet.</li>}
      </ul>
      {me?.is_admin && (
        <form className="flex flex-wrap items-end gap-2 border-t px-5 py-3" onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate(); }}>
          <div><label className="label" htmlFor="d-name">Name</label><input id="d-name" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required placeholder="e.g. Stores" /></div>
          <div><label className="label" htmlFor="d-code">Code</label><input id="d-code" className="input w-24" value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} /></div>
          <div><label className="label" htmlFor="d-head">Head</label>
            <select id="d-head" className="input" value={f.head} onChange={(e) => setF({ ...f, head: e.target.value })}><option value="">—</option>{users.data?.results.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></div>
          <button className="btn-primary" disabled={add.isPending}>Add department</button>
          {err(add.error)}
        </form>
      )}
    </section>
  );
}

function SitesTab() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const { sites } = useTeamData();
  const [f, setF] = useState({ code: "", name: "", address: "" });
  const add = useMutation({ mutationFn: () => post("/sites/", f), onSuccess: () => { setF({ code: "", name: "", address: "" }); qc.invalidateQueries({ queryKey: ["sites"] }); } });
  return (
    <section className="card">
      <div className="border-b px-5 py-3"><h2 className="font-semibold text-navy">Sites &amp; projects</h2></div>
      <ul className="divide-y">
        {sites.data?.map((s) => <li key={s.id} className="px-5 py-2.5 text-sm"><span className="font-medium">{s.code}</span> — {s.name} <span className="text-xs text-slate-400">{s.address}</span></li>)}
      </ul>
      {me?.is_admin && (
        <form className="flex flex-wrap items-end gap-2 border-t px-5 py-3" onSubmit={(e: FormEvent) => { e.preventDefault(); add.mutate(); }}>
          <div><label className="label" htmlFor="s-code">Code</label><input id="s-code" className="input w-28" value={f.code} maxLength={20} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} required /></div>
          <div><label className="label" htmlFor="s-name">Name</label><input id="s-name" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></div>
          <div><label className="label" htmlFor="s-addr">Address</label><input id="s-addr" className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></div>
          <button className="btn-primary" disabled={add.isPending}>Add site</button>
          {err(add.error)}
        </form>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ audit */
const AUDIT_FILTERS = [["", "Everything"], ["login.success", "Sign-ins"], ["login.failed", "Failed sign-ins"], ["user.create", "Logins created"],
  ["user.update", "Staff changes"], ["password.reset", "Password resets"], ["role.update", "Role changes"], ["indent.override", "Admin overrides"],
  ["stock.entry", "Stock entries"], ["import.catalogue", "Catalogue uploads"], ["import.register", "Register uploads"], ["workflow.settings", "Workflow settings"]];

function AuditTab() {
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const list = useQuery({ queryKey: ["audit", action, page], queryFn: () => get<Page<AuditEntry>>(`/audit/?page=${page}${action ? `&action=${action}` : ""}`), placeholderData: keepPreviousData });
  return (
    <section className="card">
      <div className="flex flex-wrap items-center gap-2 border-b px-5 py-3">
        <h2 className="font-semibold text-navy">Audit log</h2>
        <div className="flex-1" />
        <select className="input max-w-[220px]" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
          {AUDIT_FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr><th className="px-4 py-2">When</th><th className="px-4 py-2">Who</th><th className="px-4 py-2">What</th><th className="px-4 py-2">Details</th></tr>
          </thead>
          <tbody>
            {list.data?.results.map((a) => (
              <tr key={a.id} className="border-t align-top">
                <td className="whitespace-nowrap px-4 py-2 text-xs text-slate-500">{dateTimeFmt(a.at)}</td>
                <td className="px-4 py-2">{a.actor_name || <span className="text-slate-400">—</span>}</td>
                <td className="px-4 py-2"><span className={`chip ${a.action.includes("override") || a.action.includes("failed") ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-700"}`}>{a.action}</span><div className="mt-0.5">{a.summary}</div></td>
                <td className="px-4 py-2 text-xs text-slate-500">
                  {Object.keys(a.changes || {}).length > 0 && <details><summary className="cursor-pointer">changes</summary><pre className="mt-1 max-w-md whitespace-pre-wrap">{JSON.stringify(a.changes, null, 1)}</pre></details>}
                  {a.ip && <div>IP {a.ip}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list.data && (
        <div className="flex items-center justify-between border-t px-5 py-2 text-xs text-slate-500">
          <span>{list.data.count} entries</span>
          <div className="flex gap-2">
            <button className="btn-ghost px-2 py-1" disabled={!list.data.previous} onClick={() => setPage(page - 1)}>‹</button>
            <button className="btn-ghost px-2 py-1" disabled={!list.data.next} onClick={() => setPage(page + 1)}>›</button>
          </div>
        </div>
      )}
    </section>
  );
}

export default function Team() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const tabs = [
    { key: "people", label: "People" }, { key: "roles", label: "Roles" }, { key: "matrix", label: "Permission matrix" },
    { key: "departments", label: "Departments" }, { key: "sites", label: "Sites & projects" },
    ...(me?.is_admin ? [{ key: "audit", label: "Audit log" }] : []),
  ];
  const tab = params.get("tab") || "people";
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-navy">Team &amp; roles</h1>
      <div className="mb-5 flex gap-1 overflow-x-auto border-b border-slate-200">
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setParams({ tab: t.key })}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === t.key ? "border-gold text-navy" : "border-transparent text-slate-500 hover:text-slate-800"}`}>{t.label}</button>
        ))}
      </div>
      {tab === "people" && <PeopleTab />}
      {tab === "roles" && <RolesTab />}
      {tab === "matrix" && <MatrixTab />}
      {tab === "departments" && <DepartmentsTab />}
      {tab === "sites" && <SitesTab />}
      {tab === "audit" && me?.is_admin && <AuditTab />}
    </div>
  );
}
