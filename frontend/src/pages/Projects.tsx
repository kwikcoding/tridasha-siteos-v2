import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { FilterBar, PageHead, RecordForm, RecordTable, Tone, dateFmt, money, useFilters, useProjects, useSites, type FieldDef, type Project } from "../components/records";

const STATUS: Record<string, { label: string; tone: "green" | "amber" | "slate" | "blue" }> = {
  planned: { label: "Planned", tone: "blue" }, active: { label: "Active", tone: "green" },
  on_hold: { label: "On hold", tone: "amber" }, completed: { label: "Completed", tone: "slate" },
};

const FIELDS: FieldDef[] = [
  { name: "site", label: "Site", type: "site", required: true },
  { name: "code", label: "Code", required: true, placeholder: "TA" },
  { name: "name", label: "Project", required: true, placeholder: "Tower A", wide: true },
  { name: "status", label: "Status", type: "select", options: Object.entries(STATUS).map(([value, s]) => ({ value, label: s.label })) },
  { name: "head", label: "Project head", type: "person" },
  { name: "start_date", label: "Start", type: "date" },
  { name: "end_date", label: "Planned finish", type: "date" },
  { name: "budget", label: "Budget (₹)", type: "number" },
  { name: "description", label: "Scope / notes", type: "textarea" },
];

export default function Projects() {
  const { has, me } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters(false);
  const sites = useSites();
  const projects = useProjects();
  const [edit, setEdit] = useState<Project | "new" | null>(null);
  const { f } = filters;
  const rows = projects.data?.filter((p) => (!f.site || String(p.site) === f.site) && (!f.project || String(p.id) === f.project)
    && (!f.search || `${p.code} ${p.name}`.toLowerCase().includes(f.search.toLowerCase())));
  const canEdit = has("sites.edit");

  return (
    <div>
      <PageHead title="Sites & projects">
        {has("sites.create") && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add project</button>}
      </PageHead>
      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(sites.data ?? []).map((s) => {
          const ps = (projects.data ?? []).filter((p) => p.site === s.id);
          return (
            <div key={s.id} className="card p-4">
              <div className="flex items-center gap-2"><span className="font-semibold text-navy">{s.name}</span>{!s.active && <Tone tone="slate">closed</Tone>}</div>
              <div className="text-xs text-slate-500">{s.code}{s.address && ` · ${s.address}`}</div>
              <div className="mt-2 text-sm">{ps.filter((p) => p.status === "active").length} active · {ps.length} projects</div>
            </div>
          );
        })}
      </div>
      <FilterBar filters={filters} dates={false} exportUrl={`/api/projects/export/?${filters.query()}`} exportCode="sites.export" searchPlaceholder="Code or name" />
      <RecordTable rows={rows} empty="No projects yet." onOpen={canEdit ? (p) => setEdit(p) : undefined} cols={[
        { label: "Site", render: (p) => p.site_name },
        { label: "Code", render: (p) => <span className="font-medium text-navy">{p.code}</span> },
        { label: "Project", render: (p) => p.name },
        { label: "Status", render: (p) => <Tone tone={STATUS[p.status]?.tone ?? "slate"}>{STATUS[p.status]?.label ?? p.status}</Tone> },
        { label: "Head", render: (p) => p.head_name },
        { label: "Start → finish", render: (p) => `${dateFmt(p.start_date) || "—"} → ${dateFmt(p.end_date) || "—"}` },
        { label: "Budget", render: (p) => money(p.budget), className: "text-right tabular-nums" },
      ]} />
      {me?.is_admin && <p className="mt-3 text-xs text-slate-500">Sites themselves are added under Team &amp; Roles → Sites.</p>}
      {edit && (
        <Modal title={edit === "new" ? "Add project" : `Edit ${edit.code}`} onClose={() => setEdit(null)} wide>
          <RecordForm fields={edit === "new" ? FIELDS : FIELDS.filter((x) => x.name !== "site")} endpoint="/projects/" id={edit === "new" ? undefined : edit.id}
            initial={edit === "new" ? { status: "active", site: f.site ? Number(f.site) : "" } : (edit as unknown as Record<string, unknown>)}
            onCancel={() => setEdit(null)} onSaved={() => { setEdit(null); qc.invalidateQueries({ queryKey: ["projects"] }); }} />
        </Modal>
      )}
    </div>
  );
}
