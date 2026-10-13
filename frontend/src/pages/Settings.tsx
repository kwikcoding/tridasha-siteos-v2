import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, get } from "../api";
import { DemoData, ImportV1, V1Archive } from "./DataTools";
import type { WorkflowMeta } from "../types";

/** Workflow settings: optional steps on/off and the management approval limit. */
function WorkflowSettings() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ["workflow"], queryFn: () => get<WorkflowMeta>("/workflow/") });
  const [stages, setStages] = useState<Record<string, boolean>>({});
  const [limit, setLimit] = useState("0");
  const [never, setNever] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!meta.data) return;
    const s = meta.data.settings;
    setStages(Object.fromEntries(meta.data.stages.map((st) => [st.key, st.required || s.stages?.[st.key]?.on !== false])));
    setLimit(String(Number(s.mgmt_limit || 0)));
    setNever(!!s.mgmt_never);
  }, [meta.data]);

  const save = useMutation({
    mutationFn: () => api("/workflow/settings/", {
      method: "PUT",
      body: { stages: Object.fromEntries(Object.entries(stages).map(([k, on]) => [k, { on }])), mgmt_limit: limit || 0, mgmt_never: never },
    }),
    onSuccess: () => { setSaved(true); qc.invalidateQueries({ queryKey: ["workflow"] }); },
  });

  if (!meta.data) return <p className="p-6 text-center text-slate-500">Loading…</p>;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <section className="card p-6">
        <h2 className="mb-1 font-semibold text-navy">Steps</h2>
        <p className="mb-4 text-sm text-slate-500">Optional steps can be switched off; required steps stay on. Changes apply to indents from their next action.</p>
        <ul className="divide-y">
          {meta.data.stages.map((s) => (
            <li key={s.key} className="flex items-center gap-3 py-2.5">
              <span className="w-8 text-xs font-bold text-slate-400">{s.n}</span>
              <span className="flex-1 text-sm">{s.label}<span className="block text-xs text-slate-500">{s.dept}</span></span>
              {s.required ? <span className="chip bg-slate-100 text-slate-500">required</span> : (
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={!!stages[s.key]} onChange={(e) => setStages({ ...stages, [s.key]: e.target.checked })} /> On
                </label>
              )}
            </li>
          ))}
        </ul>
      </section>
      <section className="card space-y-3 p-6">
        <h2 className="font-semibold text-navy">Step 04 — management approval limit</h2>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={never} onChange={(e) => setNever(e.target.checked)} /> Never send indents to management (skip step 04)</label>
        {!never && (
          <div>
            <label className="label" htmlFor="lim">Send to management when indent value is at least (₹) — 0 = every indent</label>
            <input id="lim" className="input max-w-xs" type="number" min="0" step="any" value={limit} onChange={(e) => setLimit(e.target.value)} />
          </div>
        )}
      </section>
      {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      {saved && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">Saved.</p>}
      <div className="flex justify-end"><button className="btn-primary" onClick={() => { setSaved(false); save.mutate(); }} disabled={save.isPending}>Save settings</button></div>
    </div>
  );
}

const TABS = [
  { key: "workflow", label: "Workflow" },
  { key: "import", label: "Import from v1" },
  { key: "demo", label: "Demo data" },
  { key: "archive", label: "v1 archive" },
];

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "workflow";
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-navy">Settings</h1>
      <div className="mb-5 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setParams({ tab: t.key })}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === t.key ? "border-gold text-navy" : "border-transparent text-slate-500 hover:text-slate-800"}`}>{t.label}</button>
        ))}
      </div>
      {tab === "workflow" && <WorkflowSettings />}
      {tab === "import" && <ImportV1 />}
      {tab === "demo" && <DemoData />}
      {tab === "archive" && <V1Archive />}
    </div>
  );
}
