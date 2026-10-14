import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { get, post } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { ErrorBox, FilterBar, PageHead, RecordForm, RecordTable, Tabs, Tone, dateFmt, money, num, rowsOf, useFilters, useProjects, useSites, type FieldDef } from "../components/records";
import type { Page } from "../types";

interface Worker { id: number; site: number; site_name: string; name: string; worker_code: string; trade: string; contractor: string; mobile: string;
  daily_wage: string; ot_rate: string; active: boolean }
interface Mark { id: number; worker: number; worker_name: string; trade: string; contractor: string; site: number; site_name: string; project: number | null;
  date: string; status: string; ot_hours: string; wage: string; note: string; approved: boolean }
interface Summary { by_day: { date: string; present: number; half: number; absent: number; leave: number; ot_hours: string; wages: string }[];
  by_worker: { worker: number; worker__name: string; worker__trade: string; worker__contractor: string; days: string; ot_hours: string; wages: string; absent: number }[];
  total_wages: string; total_ot_hours: string; man_days: string }

const STATUS = [["present", "P", "Present"], ["half", "½", "Half day"], ["absent", "A", "Absent"], ["leave", "L", "Leave"]];
const TABS = [{ key: "", label: "Mark attendance" }, { key: "workers", label: "Muster roll" }, { key: "summary", label: "Summary & wages" }];
const today = () => new Date().toISOString().slice(0, 10);

function MarkDay() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const sites = useSites();
  const projects = useProjects();
  const [site, setSite] = useState<number | "">("");
  const [project, setProject] = useState<number | "">("");
  const [date, setDate] = useState(today());
  useEffect(() => { if (!site && sites.data?.length) setSite(sites.data.find((s) => s.active)?.id ?? ""); }, [sites.data, site]);
  const workers = useQuery({ queryKey: ["workers", site, "active"], queryFn: () => get<Page<Worker>>(`/workers/?site=${site}&active=1&page_size=500`), enabled: !!site });
  const marks = useQuery({ queryKey: ["attendance", site, date], queryFn: () => get<Page<Mark>>(`/attendance/?site=${site}&from=${date}&to=${date}&page_size=500`), enabled: !!site });
  const [rows, setRows] = useState<Record<number, { status: string; ot_hours: string }>>({});
  useEffect(() => {
    const m: Record<number, { status: string; ot_hours: string }> = {};
    for (const x of marks.data?.results ?? []) m[x.worker] = { status: x.status, ot_hours: String(Number(x.ot_hours) || "") };
    setRows(m);
  }, [marks.data]);
  const locked = (marks.data?.results ?? []).some((x) => x.approved);
  const save = useMutation({
    mutationFn: () => post<Mark[]>("/attendance/mark/", { site, project: project || null, date,
      entries: Object.entries(rows).filter(([, r]) => r.status).map(([w, r]) => ({ worker: Number(w), status: r.status, ot_hours: r.ot_hours || 0 })) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["attendance"] }); qc.invalidateQueries({ queryKey: ["pending"] }); },
  });
  const approve = useMutation({ mutationFn: () => post("/attendance/approve-day/", { site, date }), onSuccess: () => qc.invalidateQueries({ queryKey: ["attendance"] }) });
  const list = rowsOf(workers.data) ?? [];
  const setAll = (status: string) => setRows(Object.fromEntries(list.map((w) => [w.id, { status, ot_hours: rows[w.id]?.ot_hours ?? "" }])));
  const counts = STATUS.map(([k, , l]) => `${Object.values(rows).filter((r) => r.status === k).length} ${l.toLowerCase()}`).join(" · ");
  const canMark = has("labour.create") && !locked;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-2">
        <div><label className="label" htmlFor="m-site">Site</label>
          <select id="m-site" className="input" value={site} onChange={(e) => { setSite(e.target.value ? Number(e.target.value) : ""); setProject(""); }}>
            {(sites.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div><label className="label" htmlFor="m-proj">Project</label>
          <select id="m-proj" className="input" value={project} onChange={(e) => setProject(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Whole site</option>{(projects.data ?? []).filter((p) => p.site === site && p.status !== "completed").map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></div>
        <div><label className="label" htmlFor="m-date">Date</label><input id="m-date" type="date" className="input" max={today()} value={date} onChange={(e) => setDate(e.target.value)} /></div>
        <div className="flex-1" />
        {canMark && <><button className="btn-ghost" onClick={() => setAll("present")}>All present</button><button className="btn-ghost" onClick={() => setAll("absent")}>All absent</button></>}
      </div>
      {locked && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">This day is approved — attendance is locked.</p>}
      {list.length === 0 ? <div className="card p-10 text-center text-slate-500">No active workers on this site's muster roll yet — add them under “Muster roll”.</div> : (
        <div className="card divide-y">
          {list.map((w) => {
            const r = rows[w.id] ?? { status: "", ot_hours: "" };
            return (
              <div key={w.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <div className="min-w-[160px] flex-1"><div className="font-medium">{w.name} <span className="text-xs text-slate-400">{w.worker_code}</span></div>
                  <div className="text-xs text-slate-500">{w.trade}{w.contractor && ` · ${w.contractor}`} · {money(w.daily_wage)}/day</div></div>
                <div className="flex gap-1" role="group" aria-label={`Attendance for ${w.name}`}>
                  {STATUS.map(([k, short, label]) => (
                    <button key={k} type="button" title={label} aria-pressed={r.status === k} disabled={!canMark}
                      onClick={() => setRows({ ...rows, [w.id]: { ...r, status: k } })}
                      className={`h-9 w-9 rounded-lg border text-sm font-semibold ${r.status === k ? (k === "present" ? "border-green-600 bg-green-600 text-white" : k === "half" ? "border-amber-500 bg-amber-500 text-white" : "border-slate-600 bg-slate-600 text-white") : "border-slate-300 bg-white text-slate-600"}`}>{short}</button>
                  ))}
                </div>
                <input aria-label={`Overtime hours for ${w.name}`} className="input w-24" type="number" min="0" max="12" step="0.5" placeholder="OT hrs" disabled={!canMark || !["present", "half"].includes(r.status)}
                  value={r.ot_hours} onChange={(e) => setRows({ ...rows, [w.id]: { ...r, ot_hours: e.target.value } })} />
              </div>
            );
          })}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-600">{counts}</span><div className="flex-1" />
        {canMark && list.length > 0 && <button className="btn-primary" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? "Saving…" : "Save attendance"}</button>}
        {has("labour.approve") && !locked && (marks.data?.results.length ?? 0) > 0 && <button className="btn-gold" onClick={() => approve.mutate()} disabled={approve.isPending}>Approve this day</button>}
      </div>
      {save.isSuccess && <p className="text-sm text-green-700">Saved {save.data.length} marks.</p>}
      <ErrorBox error={save.error || approve.error} />
    </div>
  );
}

const WORKER_FIELDS: FieldDef[] = [
  { name: "site", label: "Site", type: "site", required: true }, { name: "name", label: "Name", required: true },
  { name: "worker_code", label: "Worker code" }, { name: "trade", label: "Trade", placeholder: "Mason, helper, bar bender…" },
  { name: "contractor", label: "Labour contractor", help: "Leave blank for departmental labour." }, { name: "mobile", label: "Mobile" },
  { name: "daily_wage", label: "Daily wage (₹)", type: "number", required: true }, { name: "ot_rate", label: "Overtime rate per hour (₹)", type: "number" },
  { name: "active", label: "Active", type: "checkbox", help: "On the muster roll" },
];

function Workers() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters(false);
  const qs = filters.query();
  const list = useQuery({ queryKey: ["workers", qs], queryFn: () => get<Page<Worker>>(`/workers/?${qs}&page_size=500`) });
  const [edit, setEdit] = useState<Worker | "new" | null>(null);
  return (
    <div>
      <FilterBar filters={filters} dates={false} exportUrl={`/api/workers/export/?${qs}`} exportCode="labour.export" searchPlaceholder="Name, code, trade, contractor">
        {has("labour.create") && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add worker</button>}
      </FilterBar>
      <RecordTable rows={rowsOf(list.data)} empty="No workers yet." onOpen={has("labour.edit") ? (w) => setEdit(w) : undefined} cols={[
        { label: "Name", render: (w) => <span className="font-medium text-navy">{w.name}</span> }, { label: "Code", render: (w) => w.worker_code },
        { label: "Trade", render: (w) => w.trade }, { label: "Contractor", render: (w) => w.contractor || "Departmental" }, { label: "Site", render: (w) => w.site_name },
        { label: "Wage / day", render: (w) => money(w.daily_wage), className: "text-right tabular-nums" }, { label: "OT / hr", render: (w) => money(w.ot_rate), className: "text-right tabular-nums" },
        { label: "Status", render: (w) => w.active ? <Tone tone="green">Active</Tone> : <Tone tone="slate">Inactive</Tone> },
      ]} />
      {edit && (
        <Modal title={edit === "new" ? "Add worker" : `Edit ${edit.name}`} onClose={() => setEdit(null)} wide>
          <RecordForm fields={WORKER_FIELDS} endpoint="/workers/" id={edit === "new" ? undefined : edit.id}
            initial={edit === "new" ? { active: true, site: filters.f.site ? Number(filters.f.site) : "" } : (edit as unknown as Record<string, unknown>)}
            onCancel={() => setEdit(null)} onSaved={() => { setEdit(null); qc.invalidateQueries({ queryKey: ["workers"] }); }} />
        </Modal>
      )}
    </div>
  );
}

function SummaryTab() {
  const filters = useFilters();
  const qs = filters.query();
  const s = useQuery({ queryKey: ["att-summary", qs], queryFn: () => get<Summary>(`/attendance/summary/?${qs}`) });
  return (
    <div>
      <FilterBar filters={filters} exportUrl={`/api/attendance/export/?${qs}`} exportCode="labour.export" searchPlaceholder="—" />
      {s.data && (
        <div className="space-y-5">
          <div className="grid grid-cols-3 gap-3">
            <div className="card p-4"><div className="label">Man-days</div><div className="text-2xl font-semibold tabular-nums text-navy">{num(s.data.man_days)}</div></div>
            <div className="card p-4"><div className="label">Overtime hours</div><div className="text-2xl font-semibold tabular-nums text-navy">{num(s.data.total_ot_hours)}</div></div>
            <div className="card p-4"><div className="label">Wages</div><div className="text-2xl font-semibold tabular-nums text-navy">{money(s.data.total_wages)}</div></div>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <section><h2 className="mb-2 text-sm font-semibold text-navy">By day</h2>
              <RecordTable rows={s.data.by_day.map((d, i) => ({ ...d, id: i }))} empty="No attendance in this period." cols={[
                { label: "Date", render: (d) => dateFmt(d.date) }, { label: "Present", render: (d) => d.present, className: "text-right" },
                { label: "Half", render: (d) => d.half, className: "text-right" }, { label: "Absent", render: (d) => d.absent, className: "text-right" },
                { label: "OT hrs", render: (d) => num(d.ot_hours), className: "text-right" }, { label: "Wages", render: (d) => money(d.wages), className: "text-right tabular-nums" },
              ]} /></section>
            <section><h2 className="mb-2 text-sm font-semibold text-navy">By worker</h2>
              <RecordTable rows={s.data.by_worker.map((w) => ({ ...w, id: w.worker }))} empty="No attendance in this period." cols={[
                { label: "Worker", render: (w) => <><span className="font-medium">{w.worker__name}</span> <span className="text-xs text-slate-500">{w.worker__trade}</span></> },
                { label: "Contractor", render: (w) => w.worker__contractor || "Departmental" }, { label: "Days", render: (w) => num(w.days), className: "text-right" },
                { label: "OT hrs", render: (w) => num(w.ot_hours), className: "text-right" }, { label: "Wages", render: (w) => money(w.wages), className: "text-right tabular-nums" },
              ]} /></section>
          </div>
        </div>
      )}
    </div>
  );
}

export default function Labour() {
  const filters = useFilters();
  const tab = filters.f.tab;
  return (
    <div>
      <PageHead title="Labour & attendance" />
      <Tabs tabs={TABS} value={tab} onChange={(k) => filters.set("tab", k)} />
      {tab === "" && <MarkDay />}
      {tab === "workers" && <Workers />}
      {tab === "summary" && <SummaryTab />}
    </div>
  );
}
