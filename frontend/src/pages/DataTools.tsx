import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { get, post, upload } from "../api";
import type { Page } from "../types";

interface TabStat { created: number; updated: number; unchanged: number; skipped: number; errors: { line: number; message: string }[] }
interface V1Result {
  committed: boolean;
  tabs: Record<string, { rows: number; file: string; live: boolean }>;
  applied: Record<string, TabStat>;
  archive: Record<string, { rows: number; new: number }>;
  stock_mismatches: { site: string; code: string; v1: string; v2: string }[];
  kept_for_later: Record<string, string>;
}

const WHERE: Record<string, string> = {
  Sites: "Team & roles → Sites", Inventory: "Materials → Catalogue", "Stock Balance": "Materials → Catalogue",
  "Receipts & Issues": "Materials → Stock", "Materials Register": "Materials → Materials register",
};

/* ------------------------------------------------------------------ import from v1 */
export function ImportV1() {
  const qc = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [res, setRes] = useState<V1Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send(commit: boolean) {
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      fd.append("commit", commit ? "true" : "false");
      const r = await upload<V1Result>("/legacy/import/", fd);
      setRes(r);
      if (commit) qc.invalidateQueries();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <section className="card space-y-4 p-6">
        <h2 className="font-semibold text-navy">Bring your SiteOS v1 data across</h2>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
          <li>Open each v1 Google Sheet — <b>main</b>, <b>materials</b> and the <b>High-Rise Materials Register</b>.</li>
          <li><b>File → Download → Microsoft Excel (.xlsx)</b> for each.</li>
          <li>Choose all three files here and press <b>Check files</b>. Nothing is saved until you press Import.</li>
        </ol>
        <p className="text-xs text-slate-500">Safe to repeat: sites, materials and register rows are matched by code / Item ID, and stock entries are never doubled. The v1 export .json works too.</p>
        <input type="file" multiple accept=".xlsx,.xlsm,.json" className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-navy file:px-3 file:py-2 file:text-white"
          onChange={(e) => { setFiles(Array.from(e.target.files ?? [])); setRes(null); setError(""); }} />
        {files.length > 0 && <p className="text-xs text-slate-500">{files.map((f) => f.name).join(", ")}</p>}
        {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <div className="flex gap-2">
          <button className="btn-primary" disabled={!files.length || busy} onClick={() => send(false)}>{busy && !res ? "Reading…" : "Check files"}</button>
          {res && !res.committed && <button className="btn-gold" disabled={busy} onClick={() => send(true)}>{busy ? "Importing…" : "Import into v2"}</button>}
        </div>
      </section>

      {res && (
        <section className="card p-6">
          <h3 className={`mb-3 font-semibold ${res.committed ? "text-green-700" : "text-navy"}`}>{res.committed ? "Imported." : "Preview — nothing saved yet"}</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr><th className="px-3 py-2">v1 tab</th><th className="px-3 py-2 text-right">New</th><th className="px-3 py-2 text-right">Updated</th><th className="px-3 py-2 text-right">Same</th><th className="px-3 py-2 text-right">Skipped</th><th className="px-3 py-2">Goes to</th></tr>
              </thead>
              <tbody>
                {Object.entries(res.applied).map(([t, s]) => (
                  <tr key={t} className="border-t align-top">
                    <td className="px-3 py-2 font-medium">{t}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-green-700">{s.created}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-sky-700">{s.updated}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{s.unchanged}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-red-700">{s.skipped}
                      {s.errors.length > 0 && <details className="text-left text-xs"><summary className="cursor-pointer">why</summary>{s.errors.map((e, i) => <div key={i}>Line {e.line}: {e.message}</div>)}</details>}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{WHERE[t] ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {res.stock_mismatches.length === 0 ? (
            Object.keys(res.applied).includes("Receipts & Issues") && <p className="mt-3 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">Stock balances match v1’s Stock Balance tab.</p>
          ) : (
            <div className="mt-3 rounded-lg bg-orange-50 px-3 py-2 text-sm text-orange-800">
              <b>{res.stock_mismatches.length} balance(s) differ from v1:</b>
              {res.stock_mismatches.slice(0, 10).map((m, i) => <div key={i} className="text-xs">{m.site} · {m.code}: v1 {m.v1}, v2 {m.v2}</div>)}
            </div>
          )}
          {Object.keys(res.kept_for_later).length > 0 && (
            <p className="mt-3 text-sm text-slate-600">
              Kept safely in the <b>v1 archive</b> until their section is built in v2: {Object.entries(res.kept_for_later).map(([t, m]) => `${t} (${res.tabs[t]?.rows ?? 0} rows → ${m})`).join(", ")}.
            </p>
          )}
        </section>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ demo data */
export function DemoData() {
  const qc = useQueryClient();
  const [pw, setPw] = useState("");
  const [out, setOut] = useState("");
  const run = useMutation({
    mutationFn: (remove: boolean) => post<{ output: string }>("/legacy/demo/", remove ? { remove: true } : { password: pw }),
    onSuccess: (d) => { setOut(d.output); setPw(""); qc.invalidateQueries(); },
  });
  return (
    <section className="card max-w-2xl space-y-4 p-6">
      <h2 className="font-semibold text-navy">Demo logins for every role</h2>
      <p className="text-sm text-slate-600">
        Creates one login per role — <b>Demo – Store Keeper</b>, <b>Demo – Purchase</b>, <b>Demo – Accountant</b> and so on (mobiles 9000000001–9000000010) —
        on a separate <b>DEMO</b> site, with 14 sample indents waiting at every step, so each person can sign in and see their own queue.
        Real data isn’t touched. Demo logins never send WhatsApp, SMS or email.
      </p>
      <form className="flex flex-wrap items-end gap-2" onSubmit={(e: FormEvent) => { e.preventDefault(); run.mutate(false); }}>
        <div className="flex-1">
          <label className="label" htmlFor="demo-pw">Password for all demo logins</label>
          <input id="demo-pw" className="input" type="password" autoComplete="new-password" minLength={8} value={pw} onChange={(e) => setPw(e.target.value)} required />
        </div>
        <button className="btn-gold" disabled={run.isPending}>Create demo data</button>
        <button type="button" className="btn-danger" disabled={run.isPending} onClick={() => run.mutate(true)}>Switch demo off</button>
      </form>
      {run.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(run.error as Error).message}</p>}
      {out && <pre className="whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs text-slate-700">{out}</pre>}
      <p className="text-xs text-slate-500">“Switch demo off” deactivates the demo logins, cancels open demo indents and hides the DEMO site. History stays.</p>
    </section>
  );
}

/* ------------------------------------------------------------------ v1 archive */
interface V1Row { id: number; tab: string; row_no: number; data: Record<string, unknown>; source_file: string }

export function V1Archive() {
  const tabs = useQuery({ queryKey: ["v1tabs"], queryFn: () => get<{ tab: string; rows: number }[]>("/legacy/records/tabs/") });
  const [tab, setTab] = useState("");
  const [page, setPage] = useState(1);
  const current = tab || tabs.data?.[0]?.tab || "";
  const rows = useQuery({
    queryKey: ["v1rows", current, page],
    queryFn: () => get<Page<V1Row>>(`/legacy/records/?tab=${encodeURIComponent(current)}&page=${page}`),
    enabled: !!current, placeholderData: keepPreviousData,
  });
  const cols = rows.data?.results[0] ? Object.keys(rows.data.results[0].data) : [];
  if (tabs.data?.length === 0) return <div className="card p-8 text-center text-slate-500">Nothing imported yet — use “Import from v1”.</div>;
  return (
    <section className="card">
      <div className="flex flex-wrap gap-1 border-b px-5 py-3">
        {tabs.data?.map((t) => (
          <button key={t.tab} onClick={() => { setTab(t.tab); setPage(1); }}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${current === t.tab ? "bg-navy text-white" : "bg-slate-100 text-slate-600"}`}>{t.tab} ({t.rows})</button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="text-xs">
          <thead className="bg-slate-50 text-left text-slate-500"><tr>{cols.map((c) => <th key={c} className="whitespace-nowrap px-3 py-2">{c}</th>)}</tr></thead>
          <tbody>
            {rows.data?.results.map((r) => (
              <tr key={r.id} className="border-t">{cols.map((c) => <td key={c} className="whitespace-nowrap px-3 py-1.5">{String(r.data[c] ?? "")}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.data && (
        <div className="flex items-center justify-between border-t px-5 py-2 text-xs text-slate-500">
          <span>{rows.data.count} rows · read-only copy of v1</span>
          <div className="flex gap-2">
            <button className="btn-ghost px-2 py-1" disabled={!rows.data.previous} onClick={() => setPage(page - 1)}>‹</button>
            <button className="btn-ghost px-2 py-1" disabled={!rows.data.next} onClick={() => setPage(page + 1)}>›</button>
          </div>
        </div>
      )}
    </section>
  );
}
