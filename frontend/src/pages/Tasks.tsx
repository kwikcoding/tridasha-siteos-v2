import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { ActionButton, Detail, FilterBar, PageHead, RecordForm, RecordTable, Tabs, Tone, dateFmt, rowsOf, useFilters, type FieldDef } from "../components/records";
import type { Page } from "../types";

interface Task { id: number; site: number; site_name: string; project: number | null; project_name: string; title: string; description: string;
  assignee: number | null; assignee_name: string; priority: string; status: string; start_date: string | null; due_date: string | null;
  progress: number; depends_on: number | null; depends_on_title: string; overdue: boolean; days_overdue: number; completed_at: string | null; created_by_name: string }

const STATUS: Record<string, { label: string; tone: "slate" | "blue" | "red" | "green" | "amber" }> = {
  todo: { label: "To do", tone: "slate" }, in_progress: { label: "In progress", tone: "blue" }, blocked: { label: "Blocked", tone: "red" },
  done: { label: "Done", tone: "green" }, cancelled: { label: "Cancelled", tone: "slate" },
};
const PRIORITY = [{ value: "low", label: "Low" }, { value: "normal", label: "Normal" }, { value: "high", label: "High" }, { value: "critical", label: "Critical" }];
const TABS = [{ key: "open", label: "Open" }, { key: "mine", label: "Assigned to me" }, { key: "overdue", label: "Overdue" }, { key: "done", label: "Done" }, { key: "all", label: "All" }];

export default function Tasks() {
  const { has, me } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters();
  const tab = filters.f.tab || "open";
  const extra: Record<string, string> = tab === "mine" ? { mine: "1", open: "1" } : tab === "overdue" ? { overdue: "1" } : tab === "done" ? { status: "done" } : tab === "open" ? { open: "1" } : {};
  const qs = filters.query(extra);
  const list = useQuery({ queryKey: ["tasks", qs], queryFn: () => get<Page<Task>>(`/tasks/?${qs}&page_size=200`) });
  const openId = Number(filters.params.get("id")) || null;
  const [editing, setEditing] = useState<Task | "new" | null>(null);
  const rows = rowsOf(list.data);
  const one = useQuery({ queryKey: ["task", openId], queryFn: () => get<Task>(`/tasks/${openId}/`), enabled: !!openId });
  const current = one.data ?? null;     // fetched on its own, so it stays open after it leaves the current tab
  const refresh = () => { qc.invalidateQueries({ queryKey: ["tasks"] }); qc.invalidateQueries({ queryKey: ["task"] }); qc.invalidateQueries({ queryKey: ["pending"] }); };
  const open = (id: number | null) => { const n = new URLSearchParams(filters.params); if (id) n.set("id", String(id)); else n.delete("id"); filters.setParams(n, { replace: true }); };
  const others = (rows ?? []).filter((t) => t.id !== (editing !== "new" ? editing?.id : 0)).map((t) => ({ value: String(t.id), label: t.title }));

  const fields: FieldDef[] = [
    { name: "site", label: "Site", type: "site", required: true }, { name: "project", label: "Project", type: "project" },
    { name: "title", label: "Task", required: true, wide: true }, { name: "description", label: "Details", type: "textarea" },
    { name: "assignee", label: "Assigned to", type: "person", help: has("tasks.assign") ? undefined : "Your role can assign tasks only to yourself." },
    { name: "priority", label: "Priority", type: "select", options: PRIORITY },
    { name: "start_date", label: "Start", type: "date" }, { name: "due_date", label: "Due", type: "date" },
    { name: "depends_on", label: "Can start after", type: "select", options: others },
    ...(editing !== "new" ? [{ name: "status", label: "Status", type: "select" as const, options: Object.entries(STATUS).map(([value, s]) => ({ value, label: s.label })) },
      { name: "progress", label: "Progress (%)", type: "number" as const }] : []),
  ];

  return (
    <div>
      <PageHead title="Tasks & schedule">
        {has("tasks.create") && <button className="btn-gold" onClick={() => setEditing("new")}>+ Add task</button>}
      </PageHead>
      <Tabs tabs={TABS} value={tab} onChange={(k) => filters.set("tab", k)} />
      <FilterBar filters={filters} exportUrl={`/api/tasks/export/?${qs}`} exportCode="tasks.export" searchPlaceholder="Task or details" />
      {list.error && <p className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{(list.error as Error).message}</p>}
      <RecordTable rows={rows} empty="No tasks here." onOpen={(t) => open(t.id)} cols={[
        { label: "Task", render: (t) => <span className="font-medium text-navy">{t.title}</span> },
        { label: "Site / project", render: (t) => `${t.site_name}${t.project_name ? ` · ${t.project_name}` : ""}` },
        { label: "Assigned to", render: (t) => t.assignee_name || <span className="text-slate-400">—</span> },
        { label: "Due", render: (t) => <>{dateFmt(t.due_date)}{t.overdue && <span className="ml-1.5"><Tone tone="red">{t.days_overdue}d late</Tone></span>}</> },
        { label: "Priority", render: (t) => t.priority !== "normal" ? <Tone tone={t.priority === "low" ? "slate" : "amber"}>{t.priority}</Tone> : "" },
        { label: "Status", render: (t) => <><Tone tone={STATUS[t.status].tone}>{STATUS[t.status].label}</Tone> <span className="text-xs text-slate-500">{t.progress}%</span></> },
      ]} />

      {current && !editing && (
        <Modal title={current.title} onClose={() => open(null)} wide>
          <div className="grid gap-4 sm:grid-cols-3">
            <Detail label="Site">{current.site_name}</Detail><Detail label="Project">{current.project_name}</Detail>
            <Detail label="Assigned to">{current.assignee_name}</Detail>
            <Detail label="Start">{dateFmt(current.start_date)}</Detail><Detail label="Due">{dateFmt(current.due_date)}{current.overdue && ` · ${current.days_overdue} days late`}</Detail>
            <Detail label="Status"><Tone tone={STATUS[current.status].tone}>{STATUS[current.status].label}</Tone> {current.progress}%</Detail>
            <Detail label="Can start after">{current.depends_on_title}</Detail><Detail label="Added by">{current.created_by_name}</Detail>
            <Detail label="Completed">{dateFmt(current.completed_at)}</Detail>
            <div className="sm:col-span-3"><Detail label="Details">{current.description}</Detail></div>
          </div>
          <div className="mt-5 flex flex-wrap gap-2">
            {(current.assignee === me?.id || has("tasks.edit")) && !["done", "cancelled"].includes(current.status) && <>
              {current.status !== "in_progress" && <ActionButton label="Start" body={{ status: "in_progress" }} url={`/tasks/${current.id}/progress/`} fields={[{ name: "note", label: "Note" }]} onDone={refresh} />}
              <ActionButton label="Update progress" tone="btn-ghost" url={`/tasks/${current.id}/progress/`} fields={[{ name: "progress", label: "Progress (%)", type: "number", initial: String(current.progress) }, { name: "note", label: "Note" }]} onDone={refresh} />
              <ActionButton label="Mark blocked" tone="btn-danger" body={{ status: "blocked" }} url={`/tasks/${current.id}/progress/`} fields={[{ name: "note", label: "What's blocking it", required: true }]} onDone={refresh} />
              <ActionButton label="Mark done" body={{ status: "done" }} url={`/tasks/${current.id}/progress/`} fields={[{ name: "note", label: "Note" }]} onDone={refresh} />
            </>}
            {has("tasks.edit") && <button className="btn-ghost" onClick={() => setEditing(current)}>Edit</button>}
          </div>
          <p className="mt-2 text-xs text-slate-500">“Start”, “Mark blocked” and “Mark done” set the status; “Update progress” changes only the %.</p>
        </Modal>
      )}
      {editing && (
        <Modal title={editing === "new" ? "Add task" : `Edit — ${editing.title}`} onClose={() => setEditing(null)} wide>
          <RecordForm fields={fields} endpoint="/tasks/" id={editing === "new" ? undefined : editing.id}
            initial={editing === "new" ? { priority: "normal", site: filters.f.site ? Number(filters.f.site) : "", assignee: has("tasks.assign") ? "" : me?.id } : (editing as unknown as Record<string, unknown>)}
            onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); refresh(); }} />
        </Modal>
      )}
    </div>
  );
}
