import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { get, upload } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { ActionButton, Detail, ErrorBox, FilterBar, PageHead, RecordForm, RecordTable, Tone, dateTimeFmt, rowsOf, useFilters, type FieldDef } from "../components/records";
import type { Page } from "../types";

interface Rev { id: number; rev: string; file_name: string; size: number; note: string; status: string; uploaded_by_name: string; uploaded_at: string }
interface Doc { id: number; site: number; site_name: string; project: number | null; project_name: string; category: string; number: string; title: string;
  discipline: string; archived: boolean; current_rev: string; revisions: Rev[]; created_by_name: string }

const CATEGORY: Record<string, string> = { drawing: "Drawing", specification: "Specification", contract: "Contract / agreement", approval: "Statutory approval",
  report: "Report / test certificate", method: "Method statement", other: "Other" };
const REV_STATUS = ["For information", "For approval", "For construction", "Superseded"];

function UploadRevision({ doc, onDone }: { doc: Doc; onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [rev, setRev] = useState("");
  const [status, setStatus] = useState("For construction");
  const [note, setNote] = useState("");
  const send = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append("file", file!); fd.append("rev", rev); fd.append("status", status); fd.append("note", note); return upload(`/documents/${doc.id}/upload/`, fd); },
    onSuccess: () => { setFile(null); setRev(""); setNote(""); onDone(); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (file) send.mutate(); };
  return (
    <form onSubmit={submit} className="space-y-3 rounded-xl border border-slate-200 p-4">
      <div className="font-medium text-navy">Upload a new revision</div>
      <p className="text-xs text-slate-500">Earlier revisions are kept. A new “For construction” revision marks the previous one as superseded.</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="sm:col-span-3"><input aria-label="Revision file" type="file" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required /></div>
        <div><label className="label" htmlFor="u-rev">Revision</label><input id="u-rev" className="input" placeholder={`R${doc.revisions.length}`} value={rev} onChange={(e) => setRev(e.target.value)} /></div>
        <div><label className="label" htmlFor="u-st">Issued</label><select id="u-st" className="input" value={status} onChange={(e) => setStatus(e.target.value)}>{REV_STATUS.slice(0, 3).map((s) => <option key={s}>{s}</option>)}</select></div>
        <div><label className="label" htmlFor="u-note">What changed</label><input id="u-note" className="input" value={note} onChange={(e) => setNote(e.target.value)} /></div>
      </div>
      <ErrorBox error={send.error} />
      <button className="btn-primary" disabled={!file || send.isPending}>{send.isPending ? "Uploading…" : "Upload revision"}</button>
    </form>
  );
}

export default function Documents() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters(false);
  const cat = filters.params.get("category") || "";
  const archived = filters.params.get("archived") || "";
  const qs = filters.query({ category: cat, archived });
  const list = useQuery({ queryKey: ["docs", qs], queryFn: () => get<Page<Doc>>(`/documents/?${qs}&page_size=200`) });
  const [edit, setEdit] = useState<Doc | "new" | null>(null);
  const openId = Number(filters.params.get("id")) || null;
  const one = useQuery({ queryKey: ["doc", openId], queryFn: () => get<Doc>(`/documents/${openId}/`), enabled: !!openId });
  const d = one.data;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["docs"] }); qc.invalidateQueries({ queryKey: ["doc"] }); };
  const open = (id: number | null) => { const n = new URLSearchParams(filters.params); if (id) n.set("id", String(id)); else n.delete("id"); filters.setParams(n, { replace: true }); };
  const fields: FieldDef[] = [
    ...(edit === "new" ? [{ name: "site", label: "Site", type: "site" as const, required: true }] : []),
    { name: "project", label: "Project", type: "project" },
    { name: "category", label: "Category", type: "select", required: true, options: Object.entries(CATEGORY).map(([value, label]) => ({ value, label })) },
    { name: "number", label: "Drawing / document number", required: true, placeholder: "TA-STR-101" }, { name: "discipline", label: "Discipline", placeholder: "Structural" },
    { name: "title", label: "Title", required: true, wide: true },
  ];

  return (
    <div>
      <PageHead title="Drawings & documents">{has("docs.create") && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add document</button>}</PageHead>
      <FilterBar filters={filters} dates={false} exportUrl={`/api/documents/export/?${qs}`} exportCode="docs.export" searchPlaceholder="Number, title, discipline">
        <div><label className="label" htmlFor="flt-cat">Category</label>
          <select id="flt-cat" className="input" value={cat} onChange={(e) => filters.set("category", e.target.value)}>
            <option value="">All</option>{Object.entries(CATEGORY).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></div>
        <label className="flex items-center gap-2 pb-2 text-sm"><input type="checkbox" checked={archived === "1"} onChange={(e) => filters.set("archived", e.target.checked ? "1" : "")} /> Show archived</label>
      </FilterBar>
      <RecordTable rows={rowsOf(list.data)} empty="No documents yet." onOpen={(x) => open(x.id)} cols={[
        { label: "Number", render: (x) => <span className="font-medium text-navy">{x.number}</span> }, { label: "Title", render: (x) => x.title },
        { label: "Category", render: (x) => CATEGORY[x.category] }, { label: "Site / project", render: (x) => `${x.site_name}${x.project_name ? ` · ${x.project_name}` : ""}` },
        { label: "Revision", render: (x) => x.current_rev ? <Tone tone="blue">{x.current_rev}</Tone> : <span className="text-slate-400">no file</span> },
        { label: "Revisions", render: (x) => x.revisions.length, className: "text-right" },
        { label: "", render: (x) => x.archived ? <Tone tone="slate">archived</Tone> : "", mobile: false },
      ]} />

      {d && !edit && (
        <Modal title={`${d.number} · ${d.title}`} onClose={() => open(null)} wide>
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-4">
              <Detail label="Site">{d.site_name}</Detail><Detail label="Project">{d.project_name}</Detail><Detail label="Category">{CATEGORY[d.category]}</Detail><Detail label="Discipline">{d.discipline}</Detail>
            </div>
            <div><div className="label">Revisions</div>
              {d.revisions.length === 0 && <p className="text-sm text-slate-500">No file uploaded yet.</p>}
              <ul className="text-sm">{d.revisions.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center gap-3 border-t border-slate-100 py-2">
                  <b className="w-10">{r.rev}</b><Tone tone={r.status === "For construction" ? "green" : r.status === "Superseded" ? "slate" : "amber"}>{r.status}</Tone>
                  <a className="font-medium text-navy hover:underline" href={`/api/documents/${d.id}/revisions/${r.id}/download/`}>{r.file_name}</a>
                  <span className="text-xs text-slate-500">{(r.size / 1024).toFixed(0)} KB · {r.uploaded_by_name} · {dateTimeFmt(r.uploaded_at)}</span>
                  {r.note && <span className="w-full pl-12 text-xs text-slate-600">{r.note}</span>}
                </li>))}</ul></div>
            {has("docs.edit") && !d.archived && <UploadRevision doc={d} onDone={refresh} />}
            <div className="flex flex-wrap gap-2 border-t pt-4">
              {has("docs.edit") && !d.archived && <button className="btn-ghost" onClick={() => setEdit(d)}>Edit details</button>}
              {has("docs.delete") && <ActionButton label={d.archived ? "Restore" : "Archive"} tone="btn-ghost" url={`/documents/${d.id}/archive/`} onDone={refresh}
                confirmText={d.archived ? undefined : "Archived documents are hidden from the list. Their files are kept."} />}
            </div>
          </div>
        </Modal>
      )}
      {edit && (
        <Modal title={edit === "new" ? "Add document" : `Edit ${edit.number}`} onClose={() => setEdit(null)} wide>
          <RecordForm fields={fields} endpoint="/documents/" id={edit === "new" ? undefined : edit.id}
            initial={edit === "new" ? { category: "drawing", site: filters.f.site ? Number(filters.f.site) : "" } : (edit as unknown as Record<string, unknown>)}
            onCancel={() => setEdit(null)} onSaved={(x) => { setEdit(null); refresh(); open(Number(x.id)); }} />
        </Modal>
      )}
    </div>
  );
}
