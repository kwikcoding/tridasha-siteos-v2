import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { del, get, patch, post } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { ActionButton, Attachments, Detail, ErrorBox, FilterBar, PageHead, RecordTable, Tabs, Tone, dateFmt, dateTimeFmt, num, rowsOf, useFilters, useProjects, useSites } from "../components/records";
import type { Page } from "../types";

type Row = Record<string, string | number>;
interface Report { id: number; site: number; site_name: string; project: number | null; project_name: string; date: string; weather: string;
  summary: string; work_items: Row[]; manpower: Row[]; manpower_total: number; materials_used: Row[]; issues: string; tomorrow_plan: string;
  status: string; editable: boolean; created_by: number; created_by_name: string; submitted_at: string | null; reviewed_by_name: string;
  reviewed_at: string | null; review_note: string; labour_marked: { present: number; half: number } | null }
interface ProjSummary { site: string; project: string; reports: number; approved: number; manpower: number; activities: Record<string, number> }

const STATUS: Record<string, { label: string; tone: "slate" | "amber" | "green" | "red" }> = {
  draft: { label: "Draft", tone: "slate" }, submitted: { label: "Waiting approval", tone: "amber" },
  approved: { label: "Approved", tone: "green" }, returned: { label: "Returned", tone: "red" },
};
const WEATHER = [["clear", "Clear"], ["cloudy", "Cloudy"], ["rain", "Rain"], ["heavy_rain", "Heavy rain"], ["hot", "Very hot"]];
const TABS = [{ key: "", label: "Reports" }, { key: "waiting", label: "Waiting approval" }, { key: "summary", label: "Project progress" }];

function RowsEditor({ rows, cols, onChange, addLabel }: { rows: Row[]; cols: { key: string; label: string; type?: string; w?: string }[]; onChange: (r: Row[]) => void; addLabel: string }) {
  const list = rows.length ? rows : [{}];
  const upd = (i: number, k: string, v: string) => onChange(list.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <div className="space-y-2">
      {list.map((r, i) => (
        <div key={i} className="flex flex-wrap gap-2">
          {cols.map((c) => <input key={c.key} aria-label={c.label} placeholder={c.label} type={c.type ?? "text"} step="any" min={c.type === "number" ? 0 : undefined}
            className={`input ${c.w ?? "min-w-[90px] flex-1"}`} value={String(r[c.key] ?? "")} onChange={(e) => upd(i, c.key, e.target.value)} />)}
          <button type="button" className="text-xs text-slate-400 hover:text-red-600" onClick={() => onChange(list.filter((_, j) => j !== i))} aria-label="Remove row">✕</button>
        </div>
      ))}
      <button type="button" className="text-xs font-medium text-navy hover:underline" onClick={() => onChange([...list, {}])}>+ {addLabel}</button>
    </div>
  );
}

function ReportForm({ initial, onDone, onCancel }: { initial?: Report; onDone: (r: Report) => void; onCancel: () => void }) {
  const sites = useSites();
  const projects = useProjects();
  const [v, setV] = useState<Partial<Report>>(initial ?? { site: sites.data?.length === 1 ? sites.data[0].id : undefined, date: new Date().toISOString().slice(0, 10), weather: "clear", work_items: [], manpower: [], materials_used: [] });
  const set = (k: keyof Report, x: unknown) => setV({ ...v, [k]: x });
  const clean = (rows?: Row[]) => (rows ?? []).filter((r) => Object.values(r).some((x) => x !== "" && x !== undefined));
  const save = useMutation({
    mutationFn: () => {
      const body = { site: v.site, project: v.project || null, date: v.date, weather: v.weather, summary: v.summary ?? "", issues: v.issues ?? "",
        tomorrow_plan: v.tomorrow_plan ?? "", work_items: clean(v.work_items), manpower: clean(v.manpower), materials_used: clean(v.materials_used) };
      return initial ? patch<Report>(`/dpr/${initial.id}/`, body) : post<Report>("/dpr/", body);
    },
    onSuccess: onDone,
  });
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-4">
        <div className="sm:col-span-2"><label className="label" htmlFor="d-site">Site *</label>
          <select id="d-site" className="input" value={v.site ?? ""} onChange={(e) => setV({ ...v, site: Number(e.target.value), project: null })} required disabled={!!initial}>
            <option value="">Choose…</option>{(sites.data ?? []).filter((s) => s.active).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div className="sm:col-span-2"><label className="label" htmlFor="d-proj">Project</label>
          <select id="d-proj" className="input" value={v.project ?? ""} onChange={(e) => set("project", e.target.value ? Number(e.target.value) : null)} disabled={!!initial}>
            <option value="">Whole site</option>{(projects.data ?? []).filter((p) => p.site === v.site && p.status !== "completed").map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></div>
        <div><label className="label" htmlFor="d-date">Date *</label><input id="d-date" type="date" className="input" value={v.date ?? ""} max={new Date().toISOString().slice(0, 10)} onChange={(e) => set("date", e.target.value)} required disabled={!!initial} /></div>
        <div><label className="label" htmlFor="d-w">Weather</label>
          <select id="d-w" className="input" value={v.weather} onChange={(e) => set("weather", e.target.value)}>{WEATHER.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
      </div>
      <div><label className="label" htmlFor="d-sum">Work done today</label><textarea id="d-sum" className="input" rows={3} value={v.summary ?? ""} onChange={(e) => set("summary", e.target.value)} placeholder="e.g. Tower A L5 slab poured, columns L6 shuttering 60%" /></div>
      <div><div className="label">Quantities done</div>
        <RowsEditor rows={v.work_items ?? []} onChange={(r) => set("work_items", r)} addLabel="Add activity"
          cols={[{ key: "activity", label: "Activity", w: "min-w-[160px] flex-[2]" }, { key: "location", label: "Location" }, { key: "qty", label: "Qty", type: "number", w: "w-24" }, { key: "unit", label: "Unit", w: "w-20" }, { key: "planned_qty", label: "Planned", type: "number", w: "w-24" }]} /></div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div><div className="label">Manpower on site</div>
          <RowsEditor rows={v.manpower ?? []} onChange={(r) => set("manpower", r)} addLabel="Add trade" cols={[{ key: "trade", label: "Trade" }, { key: "count", label: "Count", type: "number", w: "w-24" }]} /></div>
        <div><div className="label">Materials used</div>
          <RowsEditor rows={v.materials_used ?? []} onChange={(r) => set("materials_used", r)} addLabel="Add material" cols={[{ key: "item", label: "Material" }, { key: "qty", label: "Qty", type: "number", w: "w-24" }, { key: "unit", label: "Unit", w: "w-20" }]} /></div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <div><label className="label" htmlFor="d-iss">Hold-ups / issues</label><textarea id="d-iss" className="input" rows={2} value={v.issues ?? ""} onChange={(e) => set("issues", e.target.value)} /></div>
        <div><label className="label" htmlFor="d-tom">Plan for tomorrow</label><textarea id="d-tom" className="input" rows={2} value={v.tomorrow_plan ?? ""} onChange={(e) => set("tomorrow_plan", e.target.value)} /></div>
      </div>
      <ErrorBox error={save.error} />
      <div className="flex justify-end gap-2"><button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button><button className="btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save draft"}</button></div>
    </form>
  );
}

function ItemsTable({ rows, cols }: { rows: Row[]; cols: [string, string][] }) {
  if (!rows?.length) return <span className="text-slate-400">—</span>;
  return (
    <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-xs text-slate-500"><tr>{cols.map(([, l]) => <th key={l} className="py-1 pr-3">{l}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-slate-100">{cols.map(([k]) => <td key={k} className="py-1 pr-3">{typeof r[k] === "number" ? num(r[k]) : r[k]}</td>)}</tr>)}</tbody></table></div>
  );
}

export default function DailyProgress() {
  const { has, me } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters();
  const tab = filters.f.tab;
  const qs = filters.query(tab === "waiting" ? { status: "submitted" } : {});
  const list = useQuery({ queryKey: ["dpr", qs], queryFn: () => get<Page<Report>>(`/dpr/?${qs}&page_size=200`), enabled: tab !== "summary" });
  const summary = useQuery({ queryKey: ["dpr-summary", qs], queryFn: () => get<ProjSummary[]>(`/dpr/summary/?${qs}`), enabled: tab === "summary" });
  const [form, setForm] = useState<Report | "new" | null>(null);
  const openId = Number(filters.params.get("id")) || null;
  const one = useQuery({ queryKey: ["dpr-one", openId], queryFn: () => get<Report>(`/dpr/${openId}/`), enabled: !!openId });
  const r = one.data;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["dpr"] }); qc.invalidateQueries({ queryKey: ["dpr-one"] }); qc.invalidateQueries({ queryKey: ["pending"] }); };
  const open = (id: number | null) => { const n = new URLSearchParams(filters.params); if (id) n.set("id", String(id)); else n.delete("id"); filters.setParams(n, { replace: true }); };
  const mine = r && (r.created_by === me?.id || has("dpr.edit"));
  const remove = useMutation({ mutationFn: () => del(`/dpr/${r!.id}/`), onSuccess: () => { open(null); refresh(); } });

  return (
    <div>
      <PageHead title="Daily progress">{has("dpr.create") && <button className="btn-gold" onClick={() => setForm("new")}>+ Today's report</button>}</PageHead>
      <Tabs tabs={TABS} value={tab} onChange={(k) => filters.set("tab", k)} />
      <FilterBar filters={filters} exportUrl={`/api/dpr/export/?${qs}`} exportCode="dpr.export" searchPlaceholder="Work done or issues" />
      {tab === "summary" ? (
        <div className="space-y-3">
          {summary.data?.length === 0 && <div className="card p-10 text-center text-slate-500">No reports in this period.</div>}
          {summary.data?.map((s) => (
            <div key={s.site + s.project} className="card p-4">
              <div className="flex flex-wrap items-baseline gap-3"><span className="font-semibold text-navy">{s.project === "—" ? s.site : `${s.project}`}</span><span className="text-xs text-slate-500">{s.site}</span>
                <span className="flex-1" /><span className="text-sm">{s.reports} reports · {s.approved} approved · {num(s.manpower)} man-days reported</span></div>
              <ul className="mt-2 grid gap-1 text-sm sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(s.activities).map(([a, q]) => <li key={a} className="flex justify-between gap-2 border-t border-slate-100 py-1"><span>{a}</span><b className="tabular-nums">{num(q)}</b></li>)}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <RecordTable rows={rowsOf(list.data)} empty={tab === "waiting" ? "Nothing is waiting for approval." : "No daily reports yet."} onOpen={(x) => open(x.id)} cols={[
          { label: "Date", render: (x) => <span className="font-medium text-navy">{dateFmt(x.date)}</span> },
          { label: "Site / project", render: (x) => `${x.site_name}${x.project_name ? ` · ${x.project_name}` : ""}` },
          { label: "Work done", render: (x) => <span className="line-clamp-1 max-w-md">{x.summary || x.work_items.map((w) => w.activity).join(", ")}</span> },
          { label: "Manpower", render: (x) => x.manpower_total, className: "text-right tabular-nums" },
          { label: "By", render: (x) => x.created_by_name },
          { label: "Status", render: (x) => <Tone tone={STATUS[x.status].tone}>{STATUS[x.status].label}</Tone> },
        ]} />
      )}

      {r && !form && (
        <Modal title={`Daily report — ${r.site_name}${r.project_name ? ` · ${r.project_name}` : ""} — ${dateFmt(r.date)}`} onClose={() => open(null)} wide>
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2"><Tone tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Tone><Tone tone="slate">{WEATHER.find(([k]) => k === r.weather)?.[1]}</Tone>
              <span className="text-xs text-slate-500">by {r.created_by_name}{r.submitted_at && ` · submitted ${dateTimeFmt(r.submitted_at)}`}{r.reviewed_at && ` · ${r.status === "approved" ? "approved" : "returned"} by ${r.reviewed_by_name}`}</span></div>
            {r.review_note && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">{r.review_note}</p>}
            <Detail label="Work done">{r.summary}</Detail>
            <div><div className="label">Quantities</div><ItemsTable rows={r.work_items} cols={[["activity", "Activity"], ["location", "Location"], ["qty", "Qty"], ["unit", "Unit"], ["planned_qty", "Planned"]]} /></div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div><div className="label">Manpower ({r.manpower_total})</div><ItemsTable rows={r.manpower} cols={[["trade", "Trade"], ["count", "Count"]]} />
                <p className="mt-1 text-xs text-slate-500">Attendance marked for this day: {r.labour_marked?.present ?? 0} present, {r.labour_marked?.half ?? 0} half day.</p></div>
              <div><div className="label">Materials used</div><ItemsTable rows={r.materials_used} cols={[["item", "Material"], ["qty", "Qty"], ["unit", "Unit"]]} /></div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2"><Detail label="Hold-ups / issues">{r.issues}</Detail><Detail label="Plan for tomorrow">{r.tomorrow_plan}</Detail></div>
            <Attachments base={`/dpr/${r.id}/`} canAdd={r.editable && !!mine && has("dpr.edit")} title="Site photos" />
            <div className="flex flex-wrap gap-2 border-t pt-4">
              {r.editable && mine && <>
                <ActionButton label="Submit for approval" url={`/dpr/${r.id}/submit/`} onDone={refresh} confirmText="After submitting, the report can't be changed unless it's returned." />
                <button className="btn-ghost" onClick={() => setForm(r)}>Edit</button>
                {r.status === "draft" && <button className="btn-danger" onClick={() => remove.mutate()} disabled={remove.isPending}>Delete draft</button>}
              </>}
              {r.status === "submitted" && has("dpr.approve") && r.created_by !== me?.id && <>
                <ActionButton label="Approve" url={`/dpr/${r.id}/approve/`} onDone={refresh} />
                <ActionButton label="Send back" tone="btn-danger" url={`/dpr/${r.id}/send-back/`} fields={[{ name: "note", label: "What needs to change", type: "textarea", required: true }]} onDone={refresh} />
              </>}
            </div>
            <ErrorBox error={remove.error} />
          </div>
        </Modal>
      )}
      {form && (
        <Modal title={form === "new" ? "Daily progress report" : `Edit report — ${dateFmt(form.date)}`} onClose={() => setForm(null)} wide>
          <ReportForm initial={form === "new" ? undefined : form} onCancel={() => setForm(null)} onDone={(x) => { setForm(null); refresh(); open(x.id); }} />
        </Modal>
      )}
    </div>
  );
}
