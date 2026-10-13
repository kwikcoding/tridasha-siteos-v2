/** Shared building blocks for the site-work modules: filters, tables, forms, attachments and action buttons. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, get, patch, post, upload } from "../api";
import { useAuth } from "../auth";
import { dateFmt, dateTimeFmt } from "./ui";
import type { Site } from "../types";

export interface Project { id: number; site: number; site_name: string; code: string; name: string; status: string;
  start_date: string | null; end_date: string | null; budget: string | null; head: number | null; head_name: string; description: string }
export interface Person { id: number; name: string; designation: string; department: string }
export interface Attachment { id: number; name: string; size: number; purpose: string; uploaded_by: string; uploaded_at: string; url: string }

export const useSites = () => useQuery({ queryKey: ["sites"], queryFn: () => get<Site[]>("/sites/"), staleTime: 5 * 60_000 });
export const useProjects = () => useQuery({ queryKey: ["projects"], queryFn: () => get<Project[]>("/projects/"), staleTime: 60_000 });
export const usePeople = (site?: string | number | null) =>
  useQuery({ queryKey: ["people", site ?? ""], queryFn: () => get<Person[]>(`/people/${site ? `?site=${site}` : ""}`), staleTime: 60_000 });

export const money = (v: unknown) =>
  v === null || v === undefined || v === "" ? "" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });
export const num = (v: unknown) =>
  v === null || v === undefined || v === "" ? "" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 });

export function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{errorText(error)}</p>;
}

export function PageHead({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-3">
      <h1 className="text-xl font-semibold text-navy">{title}</h1>
      <div className="flex-1" />
      {children}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { key: string; label: string; count?: number }[]; value: string; onChange: (k: string) => void }) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map((t) => (
        <button key={t.key} onClick={() => onChange(t.key)}
          className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${value === t.key ? "border-gold text-navy" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
          {t.label}{t.count ? <span className="ml-1.5 rounded-full bg-gold px-1.5 text-[10px] font-bold text-white">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Tone({ tone, children }: { tone: "green" | "amber" | "red" | "blue" | "slate" | "violet"; children: ReactNode }) {
  const c = { green: "bg-green-100 text-green-800", amber: "bg-amber-100 text-amber-800", red: "bg-red-100 text-red-700",
    blue: "bg-sky-100 text-sky-800", slate: "bg-slate-100 text-slate-700", violet: "bg-violet-100 text-violet-800" }[tone];
  return <span className={`chip ${c}`}>{children}</span>;
}

/** Site / project / date range / search, kept in the URL so the page can be bookmarked. */
export function useFilters(withDates = true) {
  const [params, setParams] = useSearchParams();
  const f = { site: params.get("site") || "", project: params.get("project") || "", from: params.get("from") || "",
    to: params.get("to") || "", search: params.get("search") || "", tab: params.get("tab") || "" };
  const set = (k: string, v: string) => {
    const n = new URLSearchParams(params);
    if (v) n.set(k, v); else n.delete(k);
    if (k === "site") n.delete("project");
    n.delete("id");
    setParams(n, { replace: true });
  };
  const query = (extra: Record<string, string> = {}) => {
    const q = new URLSearchParams();
    for (const k of ["site", "project", "search", ...(withDates ? ["from", "to"] : [])]) if ((f as Record<string, string>)[k]) q.set(k, (f as Record<string, string>)[k]);
    for (const [k, v] of Object.entries(extra)) if (v) q.set(k, v);
    return q.toString();
  };
  return { f, set, query, params, setParams };
}

export function FilterBar({ filters, dates = true, exportUrl, exportCode, children, searchPlaceholder = "Search…" }: {
  filters: ReturnType<typeof useFilters>; dates?: boolean; exportUrl?: string; exportCode?: string; children?: ReactNode; searchPlaceholder?: string;
}) {
  const { has } = useAuth();
  const sites = useSites();
  const projects = useProjects();
  const { f, set } = filters;
  const plist = (projects.data ?? []).filter((p) => !f.site || String(p.site) === f.site);
  return (
    <div className="mb-4 flex flex-wrap items-end gap-2">
      <div className="min-w-[150px]">
        <label className="label" htmlFor="flt-site">Site</label>
        <select id="flt-site" className="input" value={f.site} onChange={(e) => set("site", e.target.value)}>
          <option value="">All my sites</option>
          {(sites.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <div className="min-w-[150px]">
        <label className="label" htmlFor="flt-project">Project</label>
        <select id="flt-project" className="input" value={f.project} onChange={(e) => set("project", e.target.value)}>
          <option value="">All projects</option>
          {plist.map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
        </select>
      </div>
      {dates && (
        <>
          <div><label className="label" htmlFor="flt-from">From</label><input id="flt-from" type="date" className="input" value={f.from} onChange={(e) => set("from", e.target.value)} /></div>
          <div><label className="label" htmlFor="flt-to">To</label><input id="flt-to" type="date" className="input" value={f.to} onChange={(e) => set("to", e.target.value)} /></div>
        </>
      )}
      <div className="min-w-[160px] flex-1">
        <label className="label" htmlFor="flt-search">Search</label>
        <input id="flt-search" className="input" placeholder={searchPlaceholder} value={f.search} onChange={(e) => set("search", e.target.value)} />
      </div>
      {children}
      {exportUrl && (!exportCode || has(exportCode)) && <a className="btn-ghost" href={exportUrl}>Download Excel</a>}
    </div>
  );
}

export interface Col<T> { label: string; render: (r: T) => ReactNode; className?: string; mobile?: boolean }

/** Table on desktop, stacked cards on phones. */
export function RecordTable<T extends { id: number }>({ rows, cols, onOpen, empty }: { rows: T[] | undefined; cols: Col<T>[]; onOpen?: (r: T) => void; empty: string }) {
  if (!rows) return <p className="p-6 text-center text-slate-500">Loading…</p>;
  if (!rows.length) return <div className="card p-10 text-center text-slate-500">{empty}</div>;
  return (
    <>
      <div className="card hidden overflow-x-auto md:block">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>{cols.map((c) => <th key={c.label} className={`px-4 py-2 ${c.className ?? ""}`}>{c.label}</th>)}</tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => (
              <tr key={r.id} className={onOpen ? "cursor-pointer hover:bg-slate-50" : ""} onClick={() => onOpen?.(r)}>
                {cols.map((c) => <td key={c.label} className={`px-4 py-2.5 ${c.className ?? ""}`}>{c.render(r)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="space-y-2 md:hidden">
        {rows.map((r) => (
          <li key={r.id} className="card p-3" onClick={() => onOpen?.(r)}>
            {cols.filter((c) => c.mobile !== false).map((c) => (
              <div key={c.label} className="flex justify-between gap-3 py-0.5 text-sm">
                <span className="text-xs text-slate-500">{c.label}</span><span className="min-w-0 text-right">{c.render(r)}</span>
              </div>
            ))}
          </li>
        ))}
      </ul>
    </>
  );
}

// ---------------------------------------------------------------- forms
export type FieldDef = {
  name: string; label: string; type?: "text" | "number" | "date" | "textarea" | "select" | "site" | "project" | "person" | "checkbox";
  options?: { value: string; label: string }[]; required?: boolean; help?: string; wide?: boolean; placeholder?: string;
};

export function RecordForm({ fields, initial, endpoint, id, onSaved, onCancel, submitLabel = "Save", extraBody }: {
  fields: FieldDef[]; initial?: Record<string, unknown>; endpoint: string; id?: number; onSaved: (r: Record<string, unknown>) => void;
  onCancel?: () => void; submitLabel?: string; extraBody?: Record<string, unknown>;
}) {
  const sites = useSites();
  const projects = useProjects();
  const [v, setV] = useState<Record<string, unknown>>(() => {
    const o: Record<string, unknown> = {};
    for (const f of fields) o[f.name] = initial?.[f.name] ?? (f.type === "checkbox" ? false : "");
    if (!o.site && fields.some((f) => f.type === "site") && sites.data?.length === 1) o.site = sites.data[0].id;
    return o;
  });
  const people = usePeople(v.site as number | undefined);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = { ...extraBody };
      for (const f of fields) {
        const x = v[f.name];
        body[f.name] = x === "" && f.type !== "text" && f.type !== "textarea" ? null : x;
      }
      return id ? patch<Record<string, unknown>>(`${endpoint}${id}/`, body) : post<Record<string, unknown>>(endpoint, body);
    },
    onSuccess: onSaved,
    onError: (e) => {
      const d = e instanceof ApiError ? (e.data as Record<string, unknown>) : null;
      const out: Record<string, string> = {};
      if (d && typeof d === "object") for (const [k, val] of Object.entries(d)) out[k] = Array.isArray(val) ? String(val[0]) : String(val);
      setErrors(out);
    },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); setErrors({}); save.mutate(); };
  const general = errors.detail || errors.non_field_errors;
  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        {fields.map((f) => {
          const fid = `fld-${f.name}`;
          const val = v[f.name];
          const set = (x: unknown) => setV({ ...v, [f.name]: x, ...(f.type === "site" ? { project: "" } : {}) });
          let input: ReactNode;
          if (f.type === "textarea") input = <textarea id={fid} className="input" rows={3} value={String(val ?? "")} placeholder={f.placeholder} onChange={(e) => set(e.target.value)} required={f.required} />;
          else if (f.type === "select") input = (
            <select id={fid} className="input" value={String(val ?? "")} onChange={(e) => set(e.target.value)} required={f.required}>
              <option value="">—</option>{f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>);
          else if (f.type === "site") input = (
            <select id={fid} className="input" value={String(val ?? "")} onChange={(e) => set(e.target.value ? Number(e.target.value) : "")} required={f.required !== false}>
              <option value="">Choose a site…</option>{(sites.data ?? []).filter((s) => s.active || s.id === val).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>);
          else if (f.type === "project") input = (
            <select id={fid} className="input" value={String(val ?? "")} onChange={(e) => set(e.target.value ? Number(e.target.value) : "")} required={f.required}>
              <option value="">{v.site ? "Whole site / no project" : "Choose the site first"}</option>
              {(projects.data ?? []).filter((p) => p.site === Number(v.site) && (p.status !== "completed" || p.id === val)).map((p) => <option key={p.id} value={p.id}>{p.code} — {p.name}</option>)}
            </select>);
          else if (f.type === "person") input = (
            <select id={fid} className="input" value={String(val ?? "")} onChange={(e) => set(e.target.value ? Number(e.target.value) : "")} required={f.required}>
              <option value="">Nobody yet</option>{(people.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}{p.designation ? ` — ${p.designation}` : ""}</option>)}
            </select>);
          else if (f.type === "checkbox") input = <label className="flex items-center gap-2 text-sm"><input id={fid} type="checkbox" checked={!!val} onChange={(e) => set(e.target.checked)} /> {f.help}</label>;
          else input = <input id={fid} className="input" type={f.type ?? "text"} step={f.type === "number" ? "any" : undefined} min={f.type === "number" ? 0 : undefined}
            value={String(val ?? "")} placeholder={f.placeholder} onChange={(e) => set(e.target.value)} required={f.required} />;
          return (
            <div key={f.name} className={f.wide || f.type === "textarea" ? "sm:col-span-2" : ""}>
              {f.type !== "checkbox" && <label className="label" htmlFor={fid}>{f.label}{f.required ? " *" : ""}</label>}
              {input}
              {f.help && f.type !== "checkbox" && <p className="mt-1 text-xs text-slate-500">{f.help}</p>}
              {errors[f.name] && <p className="mt-1 text-xs text-red-600">{errors[f.name]}</p>}
            </div>
          );
        })}
      </div>
      {general && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{general}</p>}
      {save.error && !Object.keys(errors).length && <ErrorBox error={save.error} />}
      <div className="flex justify-end gap-2">
        {onCancel && <button type="button" className="btn-ghost" onClick={onCancel}>Cancel</button>}
        <button className="btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : submitLabel}</button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- actions with a note / amount
export function ActionButton({ label, url, tone = "btn-primary", fields = [], confirmText, onDone, disabled }: {
  label: string; url: string; tone?: string; fields?: { name: string; label: string; type?: string; required?: boolean; initial?: string }[];
  confirmText?: string; onDone: () => void; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [v, setV] = useState<Record<string, string>>({});
  const run = useMutation({
    mutationFn: () => post(url, Object.fromEntries(Object.entries(v).filter(([, x]) => x !== ""))),
    onSuccess: () => { setOpen(false); setV({}); onDone(); },
  });
  if (!open) return <button className={tone} disabled={disabled} onClick={() => { setOpen(true); setV(Object.fromEntries(fields.map((f) => [f.name, f.initial ?? ""]))); }}>{label}</button>;
  return (
    <form className="w-full space-y-3 rounded-xl border border-gold/40 bg-gold-50/40 p-4" onSubmit={(e) => { e.preventDefault(); run.mutate(); }}>
      <div className="font-medium text-navy">{label}</div>
      {confirmText && <p className="text-sm text-slate-600">{confirmText}</p>}
      {fields.map((f) => (
        <div key={f.name}>
          <label className="label" htmlFor={`act-${f.name}`}>{f.label}{f.required ? " *" : ""}</label>
          {f.type === "textarea"
            ? <textarea id={`act-${f.name}`} className="input" rows={2} value={v[f.name] ?? ""} onChange={(e) => setV({ ...v, [f.name]: e.target.value })} required={f.required} />
            : <input id={`act-${f.name}`} className="input max-w-sm" type={f.type ?? "text"} step="any" value={v[f.name] ?? ""} onChange={(e) => setV({ ...v, [f.name]: e.target.value })} required={f.required} />}
        </div>
      ))}
      <ErrorBox error={run.error} />
      <div className="flex gap-2">
        <button className={tone} disabled={run.isPending}>{run.isPending ? "Saving…" : "Confirm"}</button>
        <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>Back</button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- attachments
export function Attachments({ base, canAdd, purposes, title = "Files" }: { base: string; canAdd: boolean; purposes?: { value: string; label: string }[]; title?: string }) {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["att", base], queryFn: () => get<Attachment[]>(`${base}attachments/`) });
  const [file, setFile] = useState<File | null>(null);
  const [purpose, setPurpose] = useState(purposes?.[0]?.value ?? "");
  const send = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append("file", file!); fd.append("purpose", purpose); return upload(`${base}attach/`, fd); },
    onSuccess: () => { setFile(null); qc.invalidateQueries({ queryKey: ["att", base] }); qc.invalidateQueries(); },
  });
  return (
    <div>
      <div className="label">{title}</div>
      {list.data?.length === 0 && <p className="text-sm text-slate-500">No files yet.</p>}
      <ul className="text-sm">
        {list.data?.map((a) => (
          <li key={a.id} className="flex flex-wrap gap-2 border-t border-slate-100 py-1.5">
            <a className="font-medium text-navy hover:underline" href={`/api${a.url}`}>{a.name}</a>
            {a.purpose && <Tone tone="slate">{purposes?.find((p) => p.value === a.purpose)?.label ?? a.purpose}</Tone>}
            <span className="text-xs text-slate-500">{(a.size / 1024).toFixed(0)} KB · {a.uploaded_by} · {dateTimeFmt(a.uploaded_at)}</span>
          </li>
        ))}
      </ul>
      {canAdd && (
        <form className="mt-2 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (file) send.mutate(); }}>
          <input aria-label="Choose file" type="file" className="text-sm" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {purposes && (
            <select aria-label="File is" className="input max-w-[180px]" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              {purposes.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
            </select>
          )}
          <button className="btn-ghost" disabled={!file || send.isPending}>{send.isPending ? "Uploading…" : "Upload"}</button>
          <ErrorBox error={send.error} />
        </form>
      )}
    </div>
  );
}

export function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="label">{label}</div>
      <div className="break-words text-sm">{children === "" || children === null || children === undefined ? <span className="text-slate-400">—</span> : children}</div>
    </div>
  );
}

export { dateFmt, dateTimeFmt };

/** List endpoints return pages; some return plain arrays. */
export function rowsOf<T>(d: { results: T[] } | T[] | undefined): T[] | undefined {
  if (!d) return undefined;
  return Array.isArray(d) ? d : d.results;
}
