import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, PageHead, RecordTable, dateFmt, money, num, useFilters, useProjects, useSites, type Col } from "../components/records";

type Num = number;
interface Report {
  from: string; to: string; sections: string[];
  indents?: { raised: Num; closed: Num; open: Num; rejected_or_cancelled: Num; by_status: { status: string; n: Num }[]; invoiced: Num; authorised: Num; paid: Num; to_pay: Num };
  materials?: { low_stock: Num };
  dpr?: { reports: Num; approved: Num; waiting_approval: Num; manpower: Num; days_in_period: Num };
  labour?: { man_days: Num; ot_hours: Num; wages: Num; unapproved_days: Num; by_contractor: { contractor: string; man_days: Num; wages: Num }[] };
  expenses?: { bills: Num; billed: Num; approved: Num; paid: Num; outstanding: Num; waiting_approval: Num; by_category: { category: string; bills: Num; total: Num; paid: Num }[]; by_department: { department: string; bills: Num; total: Num }[] };
  tasks?: { open: Num; overdue: Num; done_in_period: Num; due_in_period: Num; by_department: { department: string; open: Num; overdue: Num }[] };
  quality?: { raised: Num; closed: Num; open: Num; overdue: Num; incidents: Num; by_kind: { kind: string; n: Num }[] };
  equipment?: { total: Num; in_use: Num; out_of_service: Num; service_due: Num; maintenance_cost: Num; downtime_hours: Num };
  projects: Record<string, string | number | null>[];
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="card p-5"><h2 className="mb-3 font-semibold text-navy">{title}</h2>{children}</section>;
}
function Figures({ items }: { items: [string, ReactNode, boolean?][] }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
      {items.map(([l, v, warn]) => <div key={l}><dt className="label">{l}</dt><dd className={`text-lg font-semibold tabular-nums ${warn ? "text-red-600" : "text-navy"}`}>{v}</dd></div>)}
    </dl>
  );
}
function MiniTable({ rows, cols }: { rows: Record<string, unknown>[]; cols: [string, string, ((v: unknown) => ReactNode)?][] }) {
  if (!rows.length) return null;
  return (
    <div className="mt-4 overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-xs uppercase tracking-wide text-slate-500"><tr>{cols.map(([, l]) => <th key={l} className="py-1 pr-4">{l}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-slate-100">{cols.map(([k, , f]) => <td key={k} className="py-1.5 pr-4 tabular-nums">{f ? f(r[k]) : String(r[k] ?? "")}</td>)}</tr>)}</tbody></table></div>
  );
}
type PRow = Record<string, string | number | null> & { id: number };
function projectCols(sections: string[]): Col<PRow>[] {
  const v = (x: string | number | null | undefined) => (x === null || x === undefined ? "" : String(x));
  const cols: Col<PRow>[] = [
    { label: "Project", render: (p) => <><span className="font-medium text-navy">{p.code}</span> {p.name}</> },
    { label: "Site", render: (p) => p.site }, { label: "Status", render: (p) => p.status },
  ];
  if (sections.includes("indents")) cols.push({ label: "Open indents", render: (p) => v(p.open_indents), className: "text-right" });
  if (sections.includes("expenses")) cols.push({ label: "Approved spend", render: (p) => money(p.approved_spend), className: "text-right tabular-nums" },
    { label: "Budget used", render: (p) => (p.budget_used_pct === null || p.budget_used_pct === undefined ? "" : `${p.budget_used_pct}% of ${money(p.budget)}`), className: "text-right" });
  if (sections.includes("dpr")) cols.push({ label: "Daily reports", render: (p) => v(p.reports), className: "text-right" });
  if (sections.includes("tasks")) cols.push({ label: "Overdue tasks", render: (p) => v(p.overdue_tasks), className: "text-right" });
  if (sections.includes("quality")) cols.push({ label: "Open Q&S items", render: (p) => v(p.open_observations), className: "text-right" });
  return cols;
}

const KIND: Record<string, string> = { inspection: "Quality inspection", safety: "Safety observation", incident: "Safety incident", ncr: "NCR", near_miss: "Near miss" };

export default function Reports() {
  const { has } = useAuth();
  const filters = useFilters();
  const sites = useSites();
  const projects = useProjects();
  const { f, set } = filters;
  const qs = filters.query();
  const q = useQuery({ queryKey: ["report", qs], queryFn: () => get<Report>(`/reports/summary/?${qs}`) });
  const r = q.data;
  return (
    <div className="space-y-5">
      <PageHead title="Reports">{has("reports.export") && <a className="btn-ghost" href={`/api/reports/export/?${qs}`}>Download Excel</a>}</PageHead>
      <div className="flex flex-wrap items-end gap-2">
        <div><label className="label" htmlFor="r-site">Site</label><select id="r-site" className="input" value={f.site} onChange={(e) => set("site", e.target.value)}>
          <option value="">All my sites</option>{(sites.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
        <div><label className="label" htmlFor="r-proj">Project</label><select id="r-proj" className="input" value={f.project} onChange={(e) => set("project", e.target.value)}>
          <option value="">All projects</option>{(projects.data ?? []).filter((p) => !f.site || String(p.site) === f.site).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}</select></div>
        <div><label className="label" htmlFor="r-from">From</label><input id="r-from" type="date" className="input" value={f.from} onChange={(e) => set("from", e.target.value)} /></div>
        <div><label className="label" htmlFor="r-to">To</label><input id="r-to" type="date" className="input" value={f.to} onChange={(e) => set("to", e.target.value)} /></div>
        {r && <p className="pb-2 text-sm text-slate-500">{dateFmt(r.from)} – {dateFmt(r.to)}</p>}
      </div>
      <ErrorBox error={q.error} />
      {!r && !q.error && <p className="p-6 text-center text-slate-500">Loading…</p>}
      {r && (
        <>
          {r.indents && <Section title="Indents & purchase">
            <Figures items={[["Raised", r.indents.raised], ["Closed", r.indents.closed], ["Open now", r.indents.open], ["Rejected / cancelled", r.indents.rejected_or_cancelled],
              ["Invoiced", money(r.indents.invoiced)], ["Authorised", money(r.indents.authorised)], ["Paid", money(r.indents.paid)], ["Still to pay", money(r.indents.to_pay), r.indents.to_pay > 0]]} />
            <MiniTable rows={r.indents.by_status} cols={[["status", "Open by status"], ["n", "Indents"]]} />
          </Section>}
          {r.expenses && <Section title="Expenses & bills">
            <Figures items={[["Bills", r.expenses.bills], ["Billed", money(r.expenses.billed)], ["Approved", money(r.expenses.approved)], ["Paid", money(r.expenses.paid)],
              ["Still to pay", money(r.expenses.outstanding), r.expenses.outstanding > 0], ["Waiting approval", r.expenses.waiting_approval, r.expenses.waiting_approval > 0]]} />
            <div className="grid gap-4 lg:grid-cols-2">
              <MiniTable rows={r.expenses.by_category} cols={[["category", "Category"], ["bills", "Bills"], ["total", "Billed", money], ["paid", "Paid", money]]} />
              <MiniTable rows={r.expenses.by_department} cols={[["department", "Entered by department"], ["bills", "Bills"], ["total", "Billed", money]]} />
            </div>
          </Section>}
          <div className="grid gap-5 lg:grid-cols-2">
            {r.dpr && <Section title="Daily progress"><Figures items={[["Reports", r.dpr.reports], ["Approved", r.dpr.approved], ["Waiting approval", r.dpr.waiting_approval, r.dpr.waiting_approval > 0], ["Man-days reported", num(r.dpr.manpower)]]} /></Section>}
            {r.labour && <Section title="Labour & attendance">
              <Figures items={[["Man-days", num(r.labour.man_days)], ["Overtime hrs", num(r.labour.ot_hours)], ["Wages", money(r.labour.wages)], ["Days not approved", r.labour.unapproved_days, r.labour.unapproved_days > 0]]} />
              <MiniTable rows={r.labour.by_contractor} cols={[["contractor", "Contractor"], ["man_days", "Man-days", num], ["wages", "Wages", money]]} />
            </Section>}
            {r.tasks && <Section title="Tasks & schedule">
              <Figures items={[["Open", r.tasks.open], ["Overdue", r.tasks.overdue, r.tasks.overdue > 0], ["Done in period", r.tasks.done_in_period], ["Due in period", r.tasks.due_in_period]]} />
              <MiniTable rows={r.tasks.by_department} cols={[["department", "Department"], ["open", "Open"], ["overdue", "Overdue"]]} />
            </Section>}
            {r.quality && <Section title="Quality & safety">
              <Figures items={[["Raised", r.quality.raised], ["Closed", r.quality.closed], ["Open now", r.quality.open], ["Overdue", r.quality.overdue, r.quality.overdue > 0], ["Incidents", r.quality.incidents, r.quality.incidents > 0]]} />
              <MiniTable rows={r.quality.by_kind} cols={[["kind", "Type", (v) => KIND[String(v)] ?? String(v)], ["n", "Raised"]]} />
            </Section>}
            {r.equipment && <Section title="Plant & equipment"><Figures items={[["Items", r.equipment.total], ["In use", r.equipment.in_use], ["Out of service", r.equipment.out_of_service, r.equipment.out_of_service > 0],
              ["Service due", r.equipment.service_due, r.equipment.service_due > 0], ["Maintenance cost", money(r.equipment.maintenance_cost)], ["Downtime hrs", num(r.equipment.downtime_hours)]]} /></Section>}
            {r.materials && <Section title="Materials & stock"><Figures items={[["Items at reorder level", r.materials.low_stock, r.materials.low_stock > 0]]} /></Section>}
          </div>
          <section>
            <h2 className="mb-2 font-semibold text-navy">Project-wise</h2>
            <RecordTable rows={r.projects.map((p) => ({ ...p, id: Number(p.id) }))} empty="No projects yet — add them under Sites & projects." cols={projectCols(r.sections)} />
          </section>
        </>
      )}
    </div>
  );
}
