import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { get, post } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { ActionButton, Detail, ErrorBox, FilterBar, PageHead, RecordForm, RecordTable, Tabs, Tone, dateFmt, money, num, rowsOf, useFilters, useProjects, useSites, type FieldDef } from "../components/records";
import type { Page } from "../types";

interface Alloc { id: number; site: number; site_name: string; project: number | null; project_name: string; from_date: string; to_date: string | null; note: string; by_name: string }
interface Maint { id: number; date: string; kind: string; description: string; cost: string; downtime_hours: string; done_by: string; by_name: string }
interface Equip { id: number; code: string; name: string; category: string; make_model: string; reg_no: string; ownership: string; hire_rate: string | null;
  supplier: string; status: string; site: number | null; site_name: string; project: number | null; project_name: string; service_every_days: number | null;
  next_service_due: string | null; service_overdue: boolean; notes: string; allocations: Alloc[]; maintenance: Maint[] }
interface Util { from: string; to: string; days: number; rows: { id: number; code: string; name: string; status: string; days_allocated: number;
  utilisation_pct: number; downtime_hours: number; maintenance_cost: number; hire_cost: number }[] }

const STATUS: Record<string, { label: string; tone: "green" | "blue" | "amber" | "red" | "slate" }> = {
  available: { label: "Available", tone: "green" }, in_use: { label: "In use", tone: "blue" }, maintenance: { label: "Under maintenance", tone: "amber" },
  breakdown: { label: "Breakdown", tone: "red" }, disposed: { label: "Disposed / returned", tone: "slate" },
};
const KIND: Record<string, string> = { service: "Scheduled service", repair: "Repair", breakdown: "Breakdown", inspection: "Inspection" };
const FIELDS: FieldDef[] = [
  { name: "code", label: "Code", required: true, placeholder: "MX-01" }, { name: "name", label: "Name", required: true, placeholder: "Concrete mixer 10/7" },
  { name: "category", label: "Category", placeholder: "Mixer, excavator, DG set…" }, { name: "make_model", label: "Make / model" }, { name: "reg_no", label: "Registration / serial no" },
  { name: "ownership", label: "Ownership", type: "select", options: [{ value: "owned", label: "Owned" }, { value: "hired", label: "Hired" }] },
  { name: "hire_rate", label: "Hire rate per day (₹)", type: "number" }, { name: "supplier", label: "Hired from / supplier" },
  { name: "service_every_days", label: "Service every (days)", type: "number" }, { name: "next_service_due", label: "Next service due", type: "date" },
  { name: "notes", label: "Notes", type: "textarea" },
];

function Allocate({ e, onDone }: { e: Equip; onDone: () => void }) {
  const sites = useSites();
  const projects = useProjects();
  const [v, setV] = useState({ site: "", project: "", from_date: new Date().toISOString().slice(0, 10), note: "" });
  const go = useMutation({ mutationFn: () => post(`/equipment/${e.id}/allocate/`, { ...v, project: v.project || null }), onSuccess: onDone });
  const submit = (ev: FormEvent) => { ev.preventDefault(); go.mutate(); };
  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border border-gold/40 bg-gold-50/40 p-4">
      <div className="font-medium text-navy">Send to a site</div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div><label className="label" htmlFor="al-site">Site *</label><select id="al-site" className="input" value={v.site} required onChange={(x) => setV({ ...v, site: x.target.value, project: "" })}>
          <option value="">Choose…</option>{(sites.data ?? []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div><label className="label" htmlFor="al-proj">Project</label><select id="al-proj" className="input" value={v.project} onChange={(x) => setV({ ...v, project: x.target.value })}>
          <option value="">Whole site</option>{(projects.data ?? []).filter((p) => String(p.site) === v.site).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></div>
        <div><label className="label" htmlFor="al-from">From</label><input id="al-from" type="date" className="input" value={v.from_date} onChange={(x) => setV({ ...v, from_date: x.target.value })} /></div>
      </div>
      <ErrorBox error={go.error} />
      <button className="btn-primary" disabled={go.isPending}>Allocate</button>
    </form>
  );
}

export default function EquipmentPage() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters(false);
  const tab = filters.f.tab;
  const qs = filters.query();
  const list = useQuery({ queryKey: ["equipment", qs], queryFn: () => get<Page<Equip>>(`/equipment/?${qs}&page_size=300`), enabled: tab !== "utilisation" });
  const uq = new URLSearchParams({ ...(filters.f.site ? { site: filters.f.site } : {}), ...(filters.params.get("from") ? { from: filters.params.get("from")! } : {}), ...(filters.params.get("to") ? { to: filters.params.get("to")! } : {}) }).toString();
  const util = useQuery({ queryKey: ["util", uq], queryFn: () => get<Util>(`/equipment/utilisation/?${uq}`), enabled: tab === "utilisation" });
  const [edit, setEdit] = useState<Equip | "new" | null>(null);
  const [allocating, setAllocating] = useState(false);
  const openId = Number(filters.params.get("id")) || null;
  const one = useQuery({ queryKey: ["equip", openId], queryFn: () => get<Equip>(`/equipment/${openId}/`), enabled: !!openId });
  const e = one.data;
  const refresh = () => { setAllocating(false); qc.invalidateQueries({ queryKey: ["equipment"] }); qc.invalidateQueries({ queryKey: ["equip"] }); };
  const open = (id: number | null) => { const n = new URLSearchParams(filters.params); if (id) n.set("id", String(id)); else n.delete("id"); filters.setParams(n, { replace: true }); setAllocating(false); };
  const canEdit = has("equipment.edit");

  return (
    <div>
      <PageHead title="Plant & equipment">{has("equipment.create") && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add equipment</button>}</PageHead>
      <Tabs tabs={[{ key: "", label: "Register" }, { key: "utilisation", label: "Utilisation & downtime" }]} value={tab} onChange={(k) => filters.set("tab", k)} />
      {tab === "utilisation" ? (
        <div>
          <div className="mb-4 flex flex-wrap items-end gap-2">
            <div><label className="label" htmlFor="u-from">From</label><input id="u-from" type="date" className="input" value={filters.params.get("from") || ""} onChange={(x) => filters.set("from", x.target.value)} /></div>
            <div><label className="label" htmlFor="u-to">To</label><input id="u-to" type="date" className="input" value={filters.params.get("to") || ""} onChange={(x) => filters.set("to", x.target.value)} /></div>
            {util.data && <p className="pb-2 text-sm text-slate-500">{dateFmt(util.data.from)} – {dateFmt(util.data.to)} · {util.data.days} days</p>}
          </div>
          <RecordTable rows={util.data?.rows} empty="No equipment." cols={[
            { label: "Equipment", render: (r) => <><span className="font-medium text-navy">{r.code}</span> {r.name}</> },
            { label: "Status", render: (r) => <Tone tone={STATUS[r.status]?.tone ?? "slate"}>{STATUS[r.status]?.label}</Tone> },
            { label: "Days on site", render: (r) => r.days_allocated, className: "text-right" },
            { label: "Utilisation", render: (r) => <div className="flex items-center justify-end gap-2"><div className="h-1.5 w-20 rounded bg-slate-100"><div className="h-1.5 rounded bg-navy" style={{ width: `${Math.min(r.utilisation_pct, 100)}%` }} /></div><span className="w-12 text-right tabular-nums">{r.utilisation_pct}%</span></div>, className: "text-right" },
            { label: "Downtime hrs", render: (r) => num(r.downtime_hours), className: "text-right" },
            { label: "Maintenance", render: (r) => money(r.maintenance_cost), className: "text-right tabular-nums" },
            { label: "Hire cost", render: (r) => r.hire_cost ? money(r.hire_cost) : "", className: "text-right tabular-nums" },
          ]} />
        </div>
      ) : (
        <>
          <FilterBar filters={filters} dates={false} exportUrl={`/api/equipment/export/?${qs}`} exportCode="equipment.export" searchPlaceholder="Code, name, category, reg no" />
          <RecordTable rows={rowsOf(list.data)} empty="No equipment yet." onOpen={(x) => open(x.id)} cols={[
            { label: "Code", render: (x) => <span className="font-medium text-navy">{x.code}</span> }, { label: "Name", render: (x) => x.name },
            { label: "Category", render: (x) => x.category }, { label: "Ownership", render: (x) => x.ownership === "hired" ? `Hired · ${money(x.hire_rate)}/day` : "Owned" },
            { label: "Where", render: (x) => x.site_name ? `${x.site_name}${x.project_name ? ` · ${x.project_name}` : ""}` : <span className="text-slate-400">yard / free</span> },
            { label: "Next service", render: (x) => <>{dateFmt(x.next_service_due)}{x.service_overdue && <span className="ml-1"><Tone tone="red">due</Tone></span>}</> },
            { label: "Status", render: (x) => <Tone tone={STATUS[x.status].tone}>{STATUS[x.status].label}</Tone> },
          ]} />
        </>
      )}

      {e && !edit && (
        <Modal title={`${e.code} · ${e.name}`} onClose={() => open(null)} wide>
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2"><Tone tone={STATUS[e.status].tone}>{STATUS[e.status].label}</Tone>{e.service_overdue && <Tone tone="red">service due</Tone>}</div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Detail label="Where">{e.site_name ? `${e.site_name}${e.project_name ? ` · ${e.project_name}` : ""}` : "Not allocated"}</Detail>
              <Detail label="Category">{e.category}</Detail><Detail label="Make / model">{e.make_model}</Detail><Detail label="Reg / serial">{e.reg_no}</Detail>
              <Detail label="Ownership">{e.ownership === "hired" ? `Hired from ${e.supplier || "—"} at ${money(e.hire_rate)}/day` : "Owned"}</Detail>
              <Detail label="Next service">{dateFmt(e.next_service_due)}{e.service_every_days ? ` (every ${e.service_every_days} days)` : ""}</Detail>
            </div>
            {canEdit && (
              <div className="flex flex-wrap gap-2">
                {e.status === "available" && !allocating && <button className="btn-primary" onClick={() => setAllocating(true)}>Send to a site</button>}
                {e.site && <ActionButton label="Release from site" tone="btn-ghost" url={`/equipment/${e.id}/release/`} onDone={refresh} fields={[{ name: "to_date", label: "Released on", type: "date", initial: new Date().toISOString().slice(0, 10) }]} />}
                {["maintenance", "breakdown"].includes(e.status) && <ActionButton label="Back in service" url={`/equipment/${e.id}/back-in-service/`} onDone={refresh} />}
                <ActionButton label="Log service / repair / breakdown" tone="btn-ghost" url={`/equipment/${e.id}/maintenance/`} onDone={refresh} fields={[
                  { name: "date", label: "Date", type: "date", required: true, initial: new Date().toISOString().slice(0, 10) },
                  { name: "kind", label: "Type", required: true, initial: "service", options: Object.entries(KIND).map(([value, label]) => ({ value, label })) },
                  { name: "description", label: "What was done / what failed", type: "textarea", required: true },
                  { name: "cost", label: "Cost (₹)", type: "number" }, { name: "downtime_hours", label: "Downtime (hours)", type: "number" }, { name: "done_by", label: "Done by" }]} />
                <button className="btn-ghost" onClick={() => setEdit(e)}>Edit</button>
              </div>
            )}
            {allocating && <Allocate e={e} onDone={refresh} />}
            <div className="grid gap-5 lg:grid-cols-2">
              <div><div className="label">Where it has been</div>
                {e.allocations.length === 0 && <p className="text-sm text-slate-500">Never allocated.</p>}
                <ul className="text-sm">{e.allocations.map((a) => <li key={a.id} className="border-t border-slate-100 py-1.5"><b>{a.site_name}</b>{a.project_name && ` · ${a.project_name}`} <span className="text-slate-500">{dateFmt(a.from_date)} → {a.to_date ? dateFmt(a.to_date) : "now"}</span></li>)}</ul></div>
              <div><div className="label">Maintenance & breakdowns</div>
                {e.maintenance.length === 0 && <p className="text-sm text-slate-500">Nothing logged.</p>}
                <ul className="text-sm">{e.maintenance.map((m) => <li key={m.id} className="border-t border-slate-100 py-1.5"><span className="text-slate-500">{dateFmt(m.date)}</span> <b>{KIND[m.kind]}</b> {m.description}
                  <span className="block text-xs text-slate-500">{money(m.cost)}{Number(m.downtime_hours) ? ` · ${num(m.downtime_hours)} h down` : ""}{m.done_by && ` · ${m.done_by}`}</span></li>)}</ul></div>
            </div>
          </div>
        </Modal>
      )}
      {edit && (
        <Modal title={edit === "new" ? "Add equipment" : `Edit ${edit.code}`} onClose={() => setEdit(null)} wide>
          <RecordForm fields={FIELDS} endpoint="/equipment/" id={edit === "new" ? undefined : edit.id} initial={edit === "new" ? { ownership: "owned" } : (edit as unknown as Record<string, unknown>)}
            onCancel={() => setEdit(null)} onSaved={(x) => { setEdit(null); refresh(); open(Number(x.id)); }} />
        </Modal>
      )}
    </div>
  );
}
