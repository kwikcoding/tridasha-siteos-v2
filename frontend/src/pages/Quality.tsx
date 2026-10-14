import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { ActionButton, Attachments, Detail, FilterBar, PageHead, RecordForm, RecordTable, Tabs, Tone, dateFmt, dateTimeFmt, rowsOf, useFilters, type FieldDef } from "../components/records";
import type { Page } from "../types";

interface Obs { id: number; site: number; site_name: string; project: number | null; project_name: string; kind: string; ref_no: string; title: string;
  description: string; location: string; date: string; severity: string; assigned_to: number | null; assigned_to_name: string; due_date: string | null;
  corrective_action: string; status: string; needs_evidence: boolean; evidence_files: number | null; overdue: boolean; closure_note: string;
  closed_by_name: string; closed_at: string | null; created_by_name: string }

export const KIND: Record<string, string> = { inspection: "Quality inspection", safety: "Safety observation", incident: "Safety incident", ncr: "NCR — non-conformance", near_miss: "Near miss" };
const SEV: Record<string, "slate" | "amber" | "red"> = { low: "slate", medium: "amber", high: "red", critical: "red" };
const STATUS: Record<string, { label: string; tone: "red" | "blue" | "green" }> = { open: { label: "Open", tone: "red" }, in_progress: { label: "In progress", tone: "blue" }, closed: { label: "Closed", tone: "green" } };
const TABS = [{ key: "", label: "Open" }, { key: "overdue", label: "Overdue" }, { key: "closed", label: "Closed" }, { key: "all", label: "All" }];

export default function Quality() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters();
  const tab = filters.f.tab;
  const kind = filters.params.get("kind") || "";
  const extra: Record<string, string> = { kind, ...(tab === "" ? { status: "open,in_progress" } : tab === "overdue" ? { overdue: "1" } : tab === "closed" ? { status: "closed" } : {}) };
  const qs = filters.query(extra);
  const list = useQuery({ queryKey: ["obs", qs], queryFn: () => get<Page<Obs>>(`/observations/?${qs}&page_size=200`) });
  const [edit, setEdit] = useState<Obs | "new" | null>(null);
  const openId = Number(filters.params.get("id")) || null;
  const one = useQuery({ queryKey: ["obs-one", openId], queryFn: () => get<Obs>(`/observations/${openId}/`), enabled: !!openId });
  const o = one.data;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["obs"] }); qc.invalidateQueries({ queryKey: ["obs-one"] }); qc.invalidateQueries({ queryKey: ["pending"] }); };
  const open = (id: number | null) => { const n = new URLSearchParams(filters.params); if (id) n.set("id", String(id)); else n.delete("id"); filters.setParams(n, { replace: true }); };

  const fields: FieldDef[] = [
    ...(edit === "new" ? [{ name: "site", label: "Site", type: "site" as const, required: true }, { name: "kind", label: "Type", type: "select" as const, required: true, options: Object.entries(KIND).map(([value, label]) => ({ value, label })) }] : []),
    { name: "project", label: "Project", type: "project" }, { name: "date", label: "Date", type: "date", required: true },
    { name: "title", label: "What was found", required: true, wide: true }, { name: "description", label: "Details", type: "textarea" },
    { name: "location", label: "Location", placeholder: "Tower A, L5, grid C4" },
    { name: "severity", label: "Severity", type: "select", options: [{ value: "low", label: "Low" }, { value: "medium", label: "Medium" }, { value: "high", label: "High" }, { value: "critical", label: "Critical" }] },
    { name: "assigned_to", label: "Responsible person", type: "person" }, { name: "due_date", label: "Fix by", type: "date" },
    { name: "corrective_action", label: "Corrective action", type: "textarea" },
  ];

  return (
    <div>
      <PageHead title="Quality & safety">{has("quality.create") && <button className="btn-gold" onClick={() => setEdit("new")}>+ Record</button>}</PageHead>
      <Tabs tabs={TABS} value={tab} onChange={(k) => filters.set("tab", k)} />
      <FilterBar filters={filters} exportUrl={`/api/observations/export/?${qs}`} exportCode="quality.export" searchPlaceholder="Ref, title, location">
        <div><label className="label" htmlFor="flt-kind">Type</label>
          <select id="flt-kind" className="input" value={kind} onChange={(e) => filters.set("kind", e.target.value)}>
            <option value="">All types</option>{Object.entries(KIND).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
      </FilterBar>
      <RecordTable rows={rowsOf(list.data)} empty="Nothing recorded here." onOpen={(x) => open(x.id)} cols={[
        { label: "Ref", render: (x) => <span className="font-medium text-navy">{x.ref_no}</span> }, { label: "Date", render: (x) => dateFmt(x.date) },
        { label: "Type", render: (x) => KIND[x.kind] }, { label: "What", render: (x) => x.title },
        { label: "Site / location", render: (x) => `${x.site_name}${x.location ? ` · ${x.location}` : ""}` },
        { label: "Severity", render: (x) => <Tone tone={SEV[x.severity]}>{x.severity}</Tone> },
        { label: "Responsible", render: (x) => x.assigned_to_name },
        { label: "Fix by", render: (x) => <>{dateFmt(x.due_date)}{x.overdue && <span className="ml-1"><Tone tone="red">overdue</Tone></span>}</> },
        { label: "Status", render: (x) => <Tone tone={STATUS[x.status].tone}>{STATUS[x.status].label}</Tone> },
      ]} />

      {o && !edit && (
        <Modal title={`${o.ref_no} · ${o.title}`} onClose={() => open(null)} wide>
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2"><Tone tone={STATUS[o.status].tone}>{STATUS[o.status].label}</Tone><Tone tone={SEV[o.severity]}>{o.severity}</Tone><Tone tone="slate">{KIND[o.kind]}</Tone>
              {o.overdue && <Tone tone="red">overdue</Tone>}</div>
            <div className="grid gap-4 sm:grid-cols-3">
              <Detail label="Site">{o.site_name}</Detail><Detail label="Project">{o.project_name}</Detail><Detail label="Location">{o.location}</Detail>
              <Detail label="Date">{dateFmt(o.date)}</Detail><Detail label="Responsible">{o.assigned_to_name}</Detail><Detail label="Fix by">{dateFmt(o.due_date)}</Detail>
              <div className="sm:col-span-3"><Detail label="Details">{o.description}</Detail></div>
              <div className="sm:col-span-3"><Detail label="Corrective action">{o.corrective_action}</Detail></div>
              {o.status === "closed" && <div className="sm:col-span-3"><Detail label={`Closed by ${o.closed_by_name} · ${dateTimeFmt(o.closed_at)}`}>{o.closure_note}</Detail></div>}
            </div>
            {o.needs_evidence && o.status !== "closed" && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">Closing this needs a photo or document as evidence ({o.evidence_files ?? 0} attached so far).</p>}
            <Attachments base={`/observations/${o.id}/`} canAdd={o.status !== "closed" && has("quality.edit")} title="Photos & evidence"
              purposes={[{ value: "evidence", label: "Closure evidence" }, { value: "finding", label: "Photo of the finding" }, { value: "other", label: "Other" }]} />
            <div className="flex flex-wrap gap-2 border-t pt-4">
              {o.status === "open" && has("quality.edit") && <ActionButton label="Start work" tone="btn-ghost" url={`/observations/${o.id}/start/`} onDone={refresh} />}
              {o.status !== "closed" && has("quality.edit") && <button className="btn-ghost" onClick={() => setEdit(o)}>Edit</button>}
              {o.status !== "closed" && has("quality.approve") && <ActionButton label="Close" url={`/observations/${o.id}/close/`} onDone={refresh} fields={[{ name: "note", label: "How it was resolved", type: "textarea", required: true }]} />}
              {o.status === "closed" && has("quality.approve") && <ActionButton label="Reopen" tone="btn-danger" url={`/observations/${o.id}/reopen/`} onDone={refresh} fields={[{ name: "note", label: "Why", type: "textarea", required: true }]} />}
            </div>
          </div>
        </Modal>
      )}
      {edit && (
        <Modal title={edit === "new" ? "Record an inspection, observation or incident" : `Edit ${edit.ref_no}`} onClose={() => setEdit(null)} wide>
          <RecordForm fields={fields} endpoint="/observations/" id={edit === "new" ? undefined : edit.id}
            initial={edit === "new" ? { date: new Date().toISOString().slice(0, 10), severity: "medium", kind: filters.params.get("kind") || "", site: filters.f.site ? Number(filters.f.site) : "" } : (edit as unknown as Record<string, unknown>)}
            onCancel={() => setEdit(null)} onSaved={(x) => { setEdit(null); refresh(); open(Number(x.id)); }} />
        </Modal>
      )}
    </div>
  );
}
