import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { post } from "../api";
import { useAuth } from "../auth";
import { Field, dateTimeFmt } from "../components/ui";

export default function Profile() {
  const { me, refresh } = useAuth();
  const nav = useNavigate();
  const [f, setF] = useState({ current: "", new: "", confirm: "" });
  const [done, setDone] = useState(false);
  const save = useMutation({
    mutationFn: () => {
      if (f.new !== f.confirm) throw new Error("The two new passwords don’t match.");
      return post("/auth/password/", { current: f.current, new: f.new });
    },
    onSuccess: async () => {
      const forced = me?.must_change_password;
      setF({ current: "", new: "", confirm: "" });
      setDone(true);
      await refresh();
      if (forced) nav("/");
    },
  });
  if (!me) return null;
  const forced = me.must_change_password;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {forced && (
        <div className="rounded-xl border border-gold bg-gold-50 px-4 py-3 text-sm text-navy">
          <b>Set your own password to continue.</b> The administrator gave you a temporary one.
        </div>
      )}
      <section className="card grid gap-4 p-6 sm:grid-cols-3">
        <div className="sm:col-span-3"><h1 className="text-xl font-semibold text-navy">{me.name}</h1></div>
        <Field label="Mobile (login)">{me.mobile}</Field>
        <Field label="Employee ID">{me.employee_id}</Field>
        <Field label="Email">{me.email}</Field>
        <Field label="Designation">{me.designation}</Field>
        <Field label="Department">{me.department_name}</Field>
        <Field label="Reports to">{me.manager_name}</Field>
        <Field label="Roles">{me.is_admin ? "Administrator" : me.roles.map((r) => r.label).join(", ")}</Field>
        <Field label="Workflow steps">{me.is_admin ? "All (as administrator)" : me.stages.join(", ")}</Field>
        <Field label="Last sign-in">{dateTimeFmt(me.last_login)}</Field>
      </section>

      <form className="card space-y-4 p-6" onSubmit={(e: FormEvent) => { e.preventDefault(); setDone(false); save.mutate(); }}>
        <h2 className="font-semibold text-navy">Change password</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <div><label className="label" htmlFor="pw-cur">Current password</label><input id="pw-cur" className="input" type="password" autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} required /></div>
          <div><label className="label" htmlFor="pw-new">New password</label><input id="pw-new" className="input" type="password" autoComplete="new-password" minLength={8} value={f.new} onChange={(e) => setF({ ...f, new: e.target.value })} required /></div>
          <div><label className="label" htmlFor="pw-conf">Repeat new password</label><input id="pw-conf" className="input" type="password" autoComplete="new-password" minLength={8} value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} required /></div>
        </div>
        <p className="text-xs text-slate-500">At least 8 characters, not a common password.</p>
        {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
        {done && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">Password changed.</p>}
        <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>Change password</button></div>
      </form>

      {!me.is_admin && (
        <details className="card p-6 text-sm">
          <summary className="cursor-pointer font-semibold text-navy">What I can do ({me.permissions.length} permissions)</summary>
          <ul className="mt-3 grid grid-cols-2 gap-1 text-xs text-slate-600 sm:grid-cols-3">{me.permissions.map((p) => <li key={p}>{p}</li>)}</ul>
        </details>
      )}
    </div>
  );
}
