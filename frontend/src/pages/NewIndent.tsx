import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { get, post } from "../api";
import type { IndentDetail, Material, Site } from "../types";
import { MaterialPicker } from "./Materials";

export default function NewIndent() {
  const nav = useNavigate();
  const sites = useQuery({ queryKey: ["sites"], queryFn: () => get<Site[]>("/sites/") });
  const [f, setF] = useState({ site: "", item: "", item_code: "", unit: "", qty: "", need_by: "", priority: "normal", est_rate: "", purpose: "" });
  const [mat, setMat] = useState<Material | null>(null);
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  const save = useMutation({
    mutationFn: () =>
      post<IndentDetail>("/indents/", {
        ...f,
        site: Number(f.site),
        material: mat?.id ?? null,
        need_by: f.need_by || null,
        est_rate: f.est_rate || null,
      }),
    onSuccess: (d) => nav(`/indents/${d.id}`),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    save.mutate();
  }

  const activeSites = (sites.data ?? []).filter((s) => s.active);

  return (
    <form onSubmit={submit} className="card mx-auto max-w-2xl p-6">
      <h1 className="mb-1 text-xl font-semibold text-navy">Raise indent</h1>
      <p className="mb-6 text-sm text-slate-500">Step 01 — goes to the Storekeeper for a stock check.</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="label" htmlFor="ni-1">Site</label>
          <select id="ni-1" className="input" value={f.site} onChange={set("site")} required>
            <option value="">Choose a site…</option>
            {activeSites.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
          </select>
          {sites.data && activeSites.length === 0 && <p className="mt-1 text-xs text-red-600">You aren’t assigned to any site yet — ask the administrator.</p>}
        </div>
        <div className="sm:col-span-2">
          <label className="label">Material from catalogue</label>
          <MaterialPicker value={mat} siteId={f.site ? Number(f.site) : undefined}
            onPick={(m) => { setMat(m); setF({ ...f, item: m?.name ?? "", unit: m?.unit ?? f.unit, est_rate: m?.std_rate ?? f.est_rate, item_code: m?.code ?? "" }); }} />
        </div>
        {!mat && (
          <div className="sm:col-span-2">
            <label className="label" htmlFor="ni-2">…or type the material name (not in catalogue)</label>
            <input id="ni-2" className="input" value={f.item} onChange={set("item")} placeholder="e.g. Shuttering oil" required={!mat} />
          </div>
        )}
        {!mat && <div><label className="label" htmlFor="ni-3">Item code (optional)</label><input id="ni-3" className="input" value={f.item_code} onChange={set("item_code")} /></div>}
        <div><label className="label" htmlFor="ni-4">Unit</label><input id="ni-4" className="input" value={f.unit} onChange={set("unit")} placeholder="bag, cum, kg, nos" /></div>
        <div><label className="label" htmlFor="ni-5">Quantity</label><input id="ni-5" className="input" type="number" step="any" min="0" value={f.qty} onChange={set("qty")} required /></div>
        <div><label className="label" htmlFor="ni-6">Estimated rate (₹, optional)</label><input id="ni-6" className="input" type="number" step="any" min="0" value={f.est_rate} onChange={set("est_rate")} /></div>
        <div><label className="label" htmlFor="ni-7">Needed by</label><input id="ni-7" className="input" type="date" value={f.need_by} onChange={set("need_by")} /></div>
        <div>
          <label className="label" htmlFor="ni-8">Priority</label>
          <select id="ni-8" className="input" value={f.priority} onChange={set("priority")}>
            <option value="normal">Normal</option><option value="urgent">Urgent</option><option value="critical">Critical</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="label" htmlFor="ni-9">Purpose / location of use</label>
          <textarea id="ni-9" className="input" rows={3} value={f.purpose} onChange={set("purpose")} placeholder="e.g. Tower A, 5th floor slab" />
        </div>
      </div>
      {save.error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      <div className="mt-6 flex justify-end gap-2">
        <button type="button" className="btn-ghost" onClick={() => nav(-1)}>Cancel</button>
        <button className="btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Raise indent"}</button>
      </div>
    </form>
  );
}
