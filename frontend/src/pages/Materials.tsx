import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { get, patch, post } from "../api";
import { useAuth } from "../auth";
import ImportModal, { Modal } from "../components/ImportModal";
import { dateFmt, money, qtyFmt } from "../components/ui";
import type { Material, Page, RegisterItem, RegisterStats, Site, StockBalance, StockEntry } from "../types";

const APPLIC = ["To review", "Required", "Included in package", "Not applicable"];
const REG_STATUS = ["Not started", "Specs in review", "Specs approved", "Enquiry / quotes", "Ordered", "Partly delivered", "Delivered", "On hold"];
const APPLIC_TONE: Record<string, string> = {
  "To review": "bg-slate-100 text-slate-700", Required: "bg-green-100 text-green-800",
  "Included in package": "bg-sky-100 text-sky-800", "Not applicable": "bg-slate-50 text-slate-400",
};
const KIND_TONE: Record<string, string> = { IN: "bg-green-100 text-green-800", OUT: "bg-orange-100 text-orange-800", ADJ: "bg-slate-200 text-slate-700" };
const SOURCE_LABEL: Record<string, string> = {
  opening: "Opening stock", purchase: "Purchase (GRN)", "indent-issue": "Indent issue", transfer: "Transfer",
  return: "Return to supplier", adjust: "Count adjustment", manual: "Manual",
};

function useSites() {
  return useQuery({ queryKey: ["sites"], queryFn: () => get<Site[]>("/sites/") });
}

function useDebounced<T>(v: T, ms = 300) {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

/* ------------------------------------------------------------------ material picker (also used by NewIndent) */
export function MaterialPicker({ value, onPick, siteId }: { value: Material | null; onPick: (m: Material | null) => void; siteId?: number }) {
  const [q, setQ] = useState("");
  const dq = useDebounced(q);
  const res = useQuery({
    queryKey: ["material-search", dq, siteId],
    queryFn: () => get<Page<Material>>(`/materials/?active=true&page_size=15&search=${encodeURIComponent(dq)}${siteId ? `&site=${siteId}` : ""}`),
    enabled: dq.length >= 2 && !value,
  });
  if (value)
    return (
      <div className="flex items-center justify-between rounded-lg border border-navy/30 bg-navy-50 px-3 py-2 text-sm">
        <div><b>{value.code}</b> — {value.name} <span className="text-slate-500">({value.unit})</span>
          {value.balance !== undefined && <span className="ml-2 chip bg-white text-slate-700">In stock: {qtyFmt(value.balance)}</span>}
        </div>
        <button type="button" className="text-xs text-navy hover:underline" onClick={() => onPick(null)}>Change</button>
      </div>
    );
  return (
    <div className="relative">
      <input className="input" placeholder="Search the catalogue by code or name…" value={q} onChange={(e) => setQ(e.target.value)} />
      {dq.length >= 2 && res.data && (
        <div className="absolute z-10 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border bg-white shadow-lg">
          {res.data.results.length === 0 && <div className="px-3 py-2 text-sm text-slate-500">No match — type the name in the box below instead.</div>}
          {res.data.results.map((m) => (
            <button type="button" key={m.id} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { onPick(m); setQ(""); }}>
              <b>{m.code}</b> — {m.name} <span className="text-slate-500">{m.unit}</span>
              {m.balance !== undefined && <span className="float-right text-xs text-slate-500">stock {qtyFmt(m.balance)}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ stock tab */
function StockEntryForm({ site, onDone }: { site: Site; onDone: () => void }) {
  const [mat, setMat] = useState<Material | null>(null);
  const [f, setF] = useState({ kind: "IN", qty: "", date: "", rate: "", source: "opening", ref: "", party: "", note: "" });
  const save = useMutation({
    mutationFn: () => post("/stock/", { ...f, site: site.id, material: mat?.id, date: f.date || undefined, rate: f.rate || null }),
    onSuccess: onDone,
  });
  const sources = f.kind === "IN" ? ["opening", "purchase", "transfer", "manual"] : f.kind === "OUT" ? ["transfer", "return", "manual"] : ["adjust"];
  return (
    <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
      <div><label className="label">Material</label><MaterialPicker value={mat} onPick={setMat} siteId={site.id} /></div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div><label className="label">Type</label>
          <select className="input" value={f.kind} onChange={(e) => { const k = e.target.value; setF({ ...f, kind: k, source: k === "IN" ? "opening" : k === "OUT" ? "manual" : "adjust" }); }}>
            <option value="IN">Received (IN)</option><option value="OUT">Issued (OUT)</option><option value="ADJ">Adjustment</option>
          </select></div>
        <div><label className="label">Quantity{f.kind === "ADJ" ? " (− to reduce)" : ""}</label><input className="input" type="number" step="any" value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} required /></div>
        <div><label className="label">Date</label><input className="input" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></div>
        <div><label className="label">Source</label>
          <select className="input" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>
            {sources.map((s) => <option key={s} value={s}>{SOURCE_LABEL[s]}</option>)}
          </select></div>
        <div><label className="label">Ref (GRN / challan)</label><input className="input" value={f.ref} onChange={(e) => setF({ ...f, ref: e.target.value })} /></div>
        <div><label className="label">Rate (₹)</label><input className="input" type="number" step="any" value={f.rate} onChange={(e) => setF({ ...f, rate: e.target.value })} /></div>
      </div>
      <div><label className="label">Supplier / issued to</label><input className="input" value={f.party} onChange={(e) => setF({ ...f, party: e.target.value })} /></div>
      <div><label className="label">Note{f.kind === "ADJ" ? " (reason, required)" : ""}</label><textarea className="input" rows={2} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} required={f.kind === "ADJ"} /></div>
      <p className="text-xs text-slate-500">Material received or issued against an indent is posted automatically from the indent — use this for opening stock, transfers and counts.</p>
      {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      <div className="flex justify-end"><button className="btn-primary" disabled={!mat || save.isPending}>Save entry</button></div>
    </form>
  );
}

function StockTab() {
  const { has } = useAuth();
  const qc = useQueryClient();
  const sites = useSites();
  const [siteId, setSiteId] = useState<number | null>(null);
  const [view, setView] = useState<"balances" | "ledger">("balances");
  const [adding, setAdding] = useState(false);
  const [filter, setFilter] = useState("");
  useEffect(() => { if (!siteId && sites.data?.length) setSiteId(sites.data[0].id); }, [sites.data, siteId]);
  const site = sites.data?.find((s) => s.id === siteId);
  const bal = useQuery({ queryKey: ["stock-bal", siteId], queryFn: () => get<StockBalance[]>(`/stock/balances/?site=${siteId}`), enabled: !!siteId });
  const ledger = useQuery({ queryKey: ["stock-ledger", siteId], queryFn: () => get<Page<StockEntry>>(`/stock/?site=${siteId}&page_size=200`), enabled: !!siteId && view === "ledger" });
  const rows = (bal.data ?? []).filter((b) => !filter || `${b.code} ${b.name} ${b.category}`.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select className="input max-w-xs" value={siteId ?? ""} onChange={(e) => setSiteId(Number(e.target.value))}>
          {sites.data?.map((s) => <option key={s.id} value={s.id}>{s.code} — {s.name}</option>)}
        </select>
        <div className="flex rounded-lg border bg-white p-0.5">
          {(["balances", "ledger"] as const).map((v) => (
            <button key={v} className={`rounded-md px-3 py-1.5 text-sm ${view === v ? "bg-navy text-white" : "text-slate-600"}`} onClick={() => setView(v)}>{v === "balances" ? "Balances" : "Ledger"}</button>
          ))}
        </div>
        <input className="input max-w-xs" placeholder="Filter…" value={filter} onChange={(e) => setFilter(e.target.value)} />
        <div className="flex-1" />
        {siteId && has("materials.export") && <a className="btn-ghost" href={view === "balances" ? `/api/stock/balances/?site=${siteId}&format_xlsx=1` : `/api/stock/export/?site=${siteId}`}>Download Excel</a>}
        {has("materials.stock") && site && <button className="btn-gold" onClick={() => setAdding(true)}>+ Stock entry</button>}
      </div>
      {sites.data?.length === 0 && <div className="card p-8 text-center text-slate-500">No sites yet — the administrator adds them under Team &amp; roles.</div>}
      {view === "balances" && bal.data && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-2">Code</th><th className="px-4 py-2">Material</th><th className="px-4 py-2 text-right">Received</th><th className="px-4 py-2 text-right">Issued</th><th className="px-4 py-2 text-right">Balance</th><th className="px-4 py-2">Last movement</th></tr>
            </thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No stock recorded at this site yet.</td></tr>}
              {rows.map((b) => (
                <tr key={b.material} className="border-t">
                  <td className="px-4 py-2 font-medium tabular-nums">{b.code}</td>
                  <td className="px-4 py-2">{b.name} <span className="text-xs text-slate-500">{b.category}</span></td>
                  <td className="px-4 py-2 text-right tabular-nums">{qtyFmt(b.received)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{qtyFmt(b.issued)}</td>
                  <td className="px-4 py-2 text-right font-semibold tabular-nums">{qtyFmt(b.balance)} {b.unit}
                    {b.low && <span className="ml-1.5 chip bg-red-100 text-red-700">reorder</span>}</td>
                  <td className="px-4 py-2 text-slate-500">{dateFmt(b.last_movement)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {view === "ledger" && ledger.data && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr><th className="px-4 py-2">Date</th><th className="px-4 py-2">Material</th><th className="px-4 py-2">Type</th><th className="px-4 py-2 text-right">Qty</th><th className="px-4 py-2">Source / ref</th><th className="px-4 py-2">By</th></tr>
            </thead>
            <tbody>
              {ledger.data.results.filter((e) => !filter || `${e.material_code} ${e.material_name} ${e.ref}`.toLowerCase().includes(filter.toLowerCase())).map((e) => (
                <tr key={e.id} className="border-t">
                  <td className="px-4 py-2 text-slate-600">{dateFmt(e.date)}</td>
                  <td className="px-4 py-2"><b>{e.material_code}</b> {e.material_name}</td>
                  <td className="px-4 py-2"><span className={`chip ${KIND_TONE[e.kind]}`}>{e.kind}</span></td>
                  <td className="px-4 py-2 text-right tabular-nums">{qtyFmt(e.qty)} {e.unit}</td>
                  <td className="px-4 py-2 text-slate-600">{SOURCE_LABEL[e.source] ?? e.source}{e.indent_number && ` · ${e.indent_number}`}{e.ref && ` · ${e.ref}`}
                    {e.note && <div className="text-xs text-slate-400">{e.note}</div>}</td>
                  <td className="px-4 py-2 text-slate-500">{e.by_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {adding && site && (
        <Modal title={`Stock entry — ${site.name}`} onClose={() => setAdding(false)} wide>
          <StockEntryForm site={site} onDone={() => { setAdding(false); qc.invalidateQueries({ queryKey: ["stock-bal"] }); qc.invalidateQueries({ queryKey: ["stock-ledger"] }); }} />
        </Modal>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ catalogue tab */
function MaterialForm({ m, onDone }: { m: Material | null; onDone: () => void }) {
  const [f, setF] = useState({
    code: m?.code ?? "", name: m?.name ?? "", category: m?.category ?? "", unit: m?.unit ?? "", spec: m?.spec ?? "", hsn: m?.hsn ?? "",
    gst_rate: m?.gst_rate ?? "", std_rate: m?.std_rate ?? "", reorder_level: m?.reorder_level ?? "", active: m?.active ?? true,
  });
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, gst_rate: f.gst_rate || null, std_rate: f.std_rate || null, reorder_level: f.reorder_level || null };
      return m ? patch(`/materials/${m.id}/`, body) : post("/materials/", body);
    },
    onSuccess: onDone,
  });
  const inp = (k: keyof typeof f, label: string, type = "text") => (
    <div><label className="label">{label}</label><input className="input" type={type} step={type === "number" ? "any" : undefined} value={String(f[k])} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></div>
  );
  return (
    <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-2">
        {inp("code", "Code")}{inp("name", "Name")}{inp("category", "Category")}{inp("unit", "Unit")}
        {inp("std_rate", "Standard rate (₹)", "number")}{inp("gst_rate", "GST %", "number")}{inp("hsn", "HSN")}{inp("reorder_level", "Reorder level", "number")}
      </div>
      <div><label className="label">Specification</label><textarea className="input" rows={2} value={f.spec} onChange={(e) => setF({ ...f, spec: e.target.value })} /></div>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f.active} onChange={(e) => setF({ ...f, active: e.target.checked })} /> Active (can be indented)</label>
      {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>Save</button></div>
    </form>
  );
}

function CatalogueTab() {
  const { can, has } = useAuth();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const [edit, setEdit] = useState<Material | null | "new">(null);
  const [importing, setImporting] = useState(false);
  const cats = useQuery({ queryKey: ["mat-cats"], queryFn: () => get<{ name: string; count: number }[]>("/materials/categories/") });
  const list = useQuery({
    queryKey: ["materials", dq, cat, page],
    queryFn: () => get<Page<Material>>(`/materials/?page=${page}&search=${encodeURIComponent(dq)}${cat ? `&category=${encodeURIComponent(cat)}` : ""}`),
    placeholderData: keepPreviousData,
  });
  const refresh = () => { setEdit(null); qc.invalidateQueries({ queryKey: ["materials"] }); qc.invalidateQueries({ queryKey: ["mat-cats"] }); };
  const ed = can("materials", "edit");
  const qs = `search=${encodeURIComponent(dq)}${cat ? `&category=${encodeURIComponent(cat)}` : ""}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" placeholder="Search code, name…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select className="input max-w-[220px]" value={cat} onChange={(e) => { setCat(e.target.value); setPage(1); }}>
          <option value="">All categories</option>
          {cats.data?.map((c) => <option key={c.name} value={c.name}>{c.name} ({c.count})</option>)}
        </select>
        <div className="flex-1" />
        {has("materials.export") && <a className="btn-ghost" href={`/api/materials/export/?${qs}`}>Download Excel</a>}
        {has("materials.import") && <button className="btn-ghost" onClick={() => setImporting(true)}>Upload Excel / CSV</button>}
        {ed && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add material</button>}
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr><th className="px-4 py-2">Code</th><th className="px-4 py-2">Name</th><th className="px-4 py-2">Category</th><th className="px-4 py-2">Unit</th><th className="px-4 py-2 text-right">Rate</th><th className="px-4 py-2 text-right">Reorder</th></tr>
          </thead>
          <tbody>
            {list.data?.results.length === 0 && <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-500">No materials yet — add them or upload your catalogue.</td></tr>}
            {list.data?.results.map((m) => (
              <tr key={m.id} className={`border-t ${ed ? "cursor-pointer hover:bg-slate-50" : ""} ${m.active ? "" : "opacity-50"}`} onClick={() => ed && setEdit(m)}>
                <td className="px-4 py-2 font-medium tabular-nums">{m.code}</td>
                <td className="px-4 py-2">{m.name}</td>
                <td className="px-4 py-2 text-slate-600">{m.category}</td>
                <td className="px-4 py-2">{m.unit}</td>
                <td className="px-4 py-2 text-right tabular-nums">{money(m.std_rate)}</td>
                <td className="px-4 py-2 text-right tabular-nums">{qtyFmt(m.reorder_level)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list.data && <Pager page={page} count={list.data.count} setPage={setPage} />}
      {edit && <Modal title={edit === "new" ? "Add material" : `Edit ${edit.code}`} onClose={() => setEdit(null)}><MaterialForm m={edit === "new" ? null : edit} onDone={refresh} /></Modal>}
      {importing && (
        <ImportModal title="Upload material catalogue" endpoint="/materials/import/" onClose={() => setImporting(false)} onDone={refresh}
          help={<>An .xlsx or .csv with columns like <b>Code</b>, <b>Name</b>, Category, Unit, Rate, GST %, HSN, Reorder level. Rows are matched by code: new codes are added, existing ones updated.</>} />
      )}
    </div>
  );
}

function Pager({ page, count, setPage, size = 50 }: { page: number; count: number; setPage: (p: number) => void; size?: number }) {
  const pages = Math.max(1, Math.ceil(count / size));
  return (
    <div className="flex items-center justify-between text-xs text-slate-500">
      <span>{count.toLocaleString("en-IN")} item(s)</span>
      {pages > 1 && (
        <div className="flex items-center gap-2">
          <button className="btn-ghost px-2 py-1" disabled={page <= 1} onClick={() => setPage(page - 1)}>‹</button>
          <span>Page {page} of {pages}</span>
          <button className="btn-ghost px-2 py-1" disabled={page >= pages} onClick={() => setPage(page + 1)}>›</button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ register tab */
function RegisterForm({ r, onDone }: { r: RegisterItem | null; onDone: () => void }) {
  const [f, setF] = useState<Record<string, string>>({
    item_id: r?.item_id ?? "", trade: r?.trade ?? "", system: r?.system ?? "", item: r?.item ?? "", unit: r?.unit ?? "",
    spec: r?.spec ?? "", applicability: r?.applicability ?? "To review", zone: r?.zone ?? "", req_qty: r?.req_qty ?? "",
    grade: r?.grade ?? "", make: r?.make ?? "", vendor: r?.vendor ?? "", boq_ref: r?.boq_ref ?? "", status: r?.status ?? "Not started",
    required_by: r?.required_by ?? "", remarks: r?.remarks ?? "",
  });
  const [mat, setMat] = useState<Material | null>(r?.material ? ({ id: r.material, code: r.material_code, name: r.material_name } as Material) : null);
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, req_qty: f.req_qty || null, required_by: f.required_by || null, material: mat?.id ?? null };
      return r ? patch(`/register/${r.id}/`, body) : post("/register/", body);
    },
    onSuccess: onDone,
  });
  const inp = (k: string, label: string, type = "text", span = false) => (
    <div className={span ? "sm:col-span-2" : ""}><label className="label">{label}</label><input className="input" type={type} step={type === "number" ? "any" : undefined} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} readOnly={k === "item_id" && !!r} /></div>
  );
  const sel = (k: string, label: string, opts: string[]) => (
    <div><label className="label">{label}</label><select className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })}>{opts.map((o) => <option key={o}>{o}</option>)}</select></div>
  );
  return (
    <form className="space-y-3" onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
      <div className="grid gap-3 sm:grid-cols-2">
        {inp("item_id", "Item ID")}{inp("trade", "Trade")}{inp("item", "Material / equipment item", "text", true)}{inp("system", "System / section")}{inp("unit", "Unit")}
        {sel("applicability", "Applicability", APPLIC)}{sel("status", "Procurement status", REG_STATUS)}
        {inp("req_qty", "Required quantity", "number")}{inp("required_by", "Required by", "date")}{inp("zone", "Block / floor / zone")}{inp("grade", "Approved size / grade")}
        {inp("make", "Approved make")}{inp("vendor", "Vendor")}{inp("boq_ref", "Drawing / BOQ reference", "text", true)}
      </div>
      <div><label className="label">Specification to confirm</label><textarea className="input" rows={2} value={f.spec} onChange={(e) => setF({ ...f, spec: e.target.value })} /></div>
      <div><label className="label">Remarks</label><textarea className="input" rows={2} value={f.remarks} onChange={(e) => setF({ ...f, remarks: e.target.value })} /></div>
      <div><label className="label">Linked catalogue item (for stock &amp; indents)</label><MaterialPicker value={mat} onPick={setMat} /></div>
      {save.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(save.error as Error).message}</p>}
      <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>Save</button></div>
    </form>
  );
}

function RegisterTab() {
  const { can, has } = useAuth();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [trade, setTrade] = useState("");
  const [applic, setApplic] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const dq = useDebounced(q);
  const [edit, setEdit] = useState<RegisterItem | null | "new">(null);
  const [importing, setImporting] = useState(false);
  const qs = new URLSearchParams({ search: dq, ...(trade ? { trade } : {}), ...(applic ? { applicability: applic } : {}), ...(status ? { status } : {}) }).toString();
  const stats = useQuery({ queryKey: ["reg-stats"], queryFn: () => get<RegisterStats>("/register/stats/") });
  const list = useQuery({ queryKey: ["register", qs, page], queryFn: () => get<Page<RegisterItem>>(`/register/?page=${page}&${qs}`), placeholderData: keepPreviousData });
  const refresh = () => { setEdit(null); qc.invalidateQueries({ queryKey: ["register"] }); qc.invalidateQueries({ queryKey: ["reg-stats"] }); };
  const ed = can("materials", "edit");

  return (
    <div className="space-y-4">
      {stats.data && (
        <div className="flex flex-wrap gap-2">
          {APPLIC.map((a) => (
            <button key={a} onClick={() => { setApplic(applic === a ? "" : a); setPage(1); }}
              className={`rounded-lg border bg-white px-3 py-2 text-left text-sm ${applic === a ? "ring-2 ring-gold" : ""}`}>
              <span className={`chip ${APPLIC_TONE[a]}`}>{a}</span> <b className="ml-1 tabular-nums">{(stats.data.applicability[a] ?? 0).toLocaleString("en-IN")}</b>
            </button>
          ))}
          <span className="self-center text-xs text-slate-500">{stats.data.total.toLocaleString("en-IN")} items · {stats.data.linked.toLocaleString("en-IN")} linked to catalogue</span>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" placeholder="Search item, ID, make…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <select className="input max-w-[220px]" value={trade} onChange={(e) => { setTrade(e.target.value); setPage(1); }}>
          <option value="">All trades</option>
          {stats.data?.trades.map((t) => <option key={t.name} value={t.name}>{t.name} ({t.count})</option>)}
        </select>
        <select className="input max-w-[200px]" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">Any status</option>{REG_STATUS.map((s) => <option key={s}>{s}</option>)}
        </select>
        <div className="flex-1" />
        {has("materials.export") && <a className="btn-ghost" href={`/api/register/export/?${qs}`}>Download Excel</a>}
        {has("materials.import") && <button className="btn-ghost" onClick={() => setImporting(true)}>Upload Excel / CSV</button>}
        {ed && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add row</button>}
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr><th className="px-4 py-2">Item ID</th><th className="px-4 py-2">Item</th><th className="px-4 py-2">Applicability</th><th className="px-4 py-2 text-right">Qty</th><th className="px-4 py-2">Make / vendor</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Catalogue</th></tr>
          </thead>
          <tbody>
            {list.data?.results.length === 0 && <tr><td colSpan={7} className="px-4 py-8 text-center text-slate-500">Nothing here — upload the High-Rise Materials Register (.xlsx or .csv).</td></tr>}
            {list.data?.results.map((r) => (
              <tr key={r.id} className={`border-t ${ed ? "cursor-pointer hover:bg-slate-50" : ""}`} onClick={() => ed && setEdit(r)}>
                <td className="whitespace-nowrap px-4 py-2 tabular-nums">{r.item_id}</td>
                <td className="px-4 py-2">{r.item}<div className="text-xs text-slate-500">{[r.trade, r.system].filter(Boolean).join(" · ")}</div></td>
                <td className="px-4 py-2"><span className={`chip ${APPLIC_TONE[r.applicability]}`}>{r.applicability}</span></td>
                <td className="px-4 py-2 text-right tabular-nums">{qtyFmt(r.req_qty)} {r.req_qty && r.unit}</td>
                <td className="px-4 py-2">{r.make}<div className="text-xs text-slate-500">{r.vendor}</div></td>
                <td className="px-4 py-2 text-slate-600">{r.status}</td>
                <td className="px-4 py-2 text-xs">{r.material_code || <span className="text-slate-400">—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {list.data && <Pager page={page} count={list.data.count} setPage={setPage} />}
      {edit && <Modal title={edit === "new" ? "Add register row" : `Edit ${edit.item_id}`} onClose={() => setEdit(null)} wide><RegisterForm r={edit === "new" ? null : edit} onDone={refresh} /></Modal>}
      {importing && (
        <ImportModal title="Upload materials register" endpoint="/register/import/" onClose={() => setImporting(false)} onDone={refresh}
          help={<>The <b>High-Rise Construction Materials Master</b> works as is — download its “Materials Register” tab as .xlsx or .csv and upload it here. Title rows above the header are skipped automatically. Rows are matched by <b>Item ID</b>.</>} />
      )}
    </div>
  );
}

const TABS = [
  { key: "stock", label: "Stock" },
  { key: "catalogue", label: "Catalogue" },
  { key: "register", label: "Materials register" },
];

export default function Materials() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "stock";
  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold text-navy">Materials</h1>
      <div className="mb-5 flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setParams({ tab: t.key })}
            className={`border-b-2 px-3 py-2 text-sm font-medium ${tab === t.key ? "border-gold text-navy" : "border-transparent text-slate-500 hover:text-slate-800"}`}>{t.label}</button>
        ))}
      </div>
      {tab === "stock" && <StockTab />}
      {tab === "catalogue" && <CatalogueTab />}
      {tab === "register" && <RegisterTab />}
    </div>
  );
}
