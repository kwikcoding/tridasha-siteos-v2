import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { get, post } from "../api";
import { useAuth } from "../auth";
import { Field, PriorityChip, StatusChip, dateFmt, dateTimeFmt, money, qtyFmt } from "../components/ui";
import type { IndentDetail as Detail, Quote, WorkflowMeta } from "../types";

type FieldType = "text" | "number" | "date" | "textarea" | "quotes";
const FIELD_META: Record<string, { label: string; type: FieldType }> = {
  stock_note: { label: "Stock & open orders note", type: "textarea" },
  stock_seen: { label: "Quantity in stock", type: "number" },
  spec_note: { label: "Specification note", type: "textarea" },
  boq_ref: { label: "BOQ reference", type: "text" },
  budget_note: { label: "Budget note", type: "textarea" },
  quotes: { label: "Quotations", type: "quotes" },
  purchase_note: { label: "Purchase note", type: "textarea" },
  vendor_final: { label: "Approved supplier", type: "text" },
  rate: { label: "Approved rate (₹)", type: "number" },
  lead_days: { label: "Lead time (days)", type: "number" },
  vendor_note: { label: "Comparison note", type: "textarea" },
  po_no: { label: "PO number", type: "text" },
  po_date: { label: "PO date", type: "date" },
  po_vendor: { label: "PO supplier", type: "text" },
  po_rate: { label: "PO rate (₹)", type: "number" },
  po_expected: { label: "Expected delivery", type: "date" },
  tracking: { label: "Delivery update", type: "textarea" },
  grn_no: { label: "GRN number", type: "text" },
  inspection: { label: "Inspection result", type: "textarea" },
  issued_to: { label: "Issued to (team / location)", type: "text" },
  inv_no: { label: "Invoice number", type: "text" },
  inv_date: { label: "Invoice date", type: "date" },
  inv_amount: { label: "Invoice amount before GST (₹)", type: "number" },
  inv_gst: { label: "GST (₹)", type: "number" },
  inv_note: { label: "Invoice note", type: "textarea" },
  pay_auth_amount: { label: "Amount authorised (₹)", type: "number" },
  paid_on: { label: "Paid on", type: "date" },
  pay_mode: { label: "Payment mode", type: "text" },
  pay_ref: { label: "Payment reference / UTR", type: "text" },
  pay_amount: { label: "Amount paid now (₹)", type: "number" },
};

const BUTTON_TONE: Record<string, string> = {
  approve: "btn-primary", issue: "btn-primary", purchase: "btn-gold", po: "btn-primary", receive: "btn-primary",
  issueClose: "btn-primary", verifyInv: "btn-primary", pay: "btn-primary", resubmit: "btn-primary", resume: "btn-primary",
  reject: "btn-danger", cancel: "btn-danger", rejectVendor: "btn-danger", rejectReceipt: "btn-danger", returnInv: "btn-danger",
};

function buttonLabel(meta: WorkflowMeta, d: Detail, action: string) {
  if (action === "approve") return meta.stages.find((s) => s.key === d.stage)?.approve_label ?? "Approve";
  return meta.button_labels?.[action] ?? meta.action_labels[action] ?? action;
}

/** Sensible starting values so people don't retype what the previous step already recorded. */
function prefill(d: Detail, field: string): unknown {
  const cur = d[field];
  if (cur !== null && cur !== undefined && cur !== "") return cur;
  const quotes = (d.quotes ?? []).filter((q) => q.vendor && q.rate !== undefined && q.rate !== "");
  const best = quotes.sort((a, b) => Number(a.rate) - Number(b.rate))[0];
  if (field === "vendor_final") return best?.vendor ?? "";
  if (field === "rate") return best?.rate ?? "";
  if (field === "po_vendor") return d.vendor_final || best?.vendor || "";
  if (field === "po_rate") return d.rate ?? best?.rate ?? "";
  if (field === "po_date" || field === "inv_date" || field === "paid_on") return new Date().toISOString().slice(0, 10);
  if (field === "pay_auth_amount") return d.money?.payable || "";
  if (field === "pay_amount") return d.money?.outstanding || "";
  return "";
}

/** Steps 11–12: what the invoice is matched against and how much may still be paid. */
function MoneyPanel({ d, action }: { d: Detail; action: string }) {
  const m = d.money;
  if (!m) return null;
  return (
    <div className="grid gap-2 rounded-lg bg-white px-3 py-2 text-sm sm:grid-cols-3">
      <div><div className="label">PO rate × received</div>{m.expected > 0 ? money(m.expected) : <span className="text-amber-700">no PO rate / GRN</span>}</div>
      {action === "verifyInv" ? (
        <div className="sm:col-span-2 text-xs text-slate-600">An invoice (before GST) more than {m.tolerance_pct}% away from this needs a reason in Remarks.</div>
      ) : (
        <>
          <div><div className="label">Invoice incl. GST</div>{money(m.invoice_total) || "—"}</div>
          {action === "pay" ? (
            <div><div className="label">Authorised · paid · left</div>{money(m.authorised ?? m.payable)} · {money(m.paid)} · <b>{money(m.outstanding)}</b></div>
          ) : (
            <div><div className="label">Can authorise up to</div><b>{money(m.payable)}</b></div>
          )}
        </>
      )}
    </div>
  );
}

function Tracker({ d }: { d: Detail }) {
  return (
    <ol className="flex gap-1 overflow-x-auto pb-1">
      {d.steps.map((s) => (
        <li key={s.key} className={`min-w-[96px] flex-1 rounded-lg border px-2 py-2 text-center text-[11px] leading-tight ${
          s.state === "current" ? "border-gold bg-gold-50 font-semibold text-navy" : s.state === "done" ? "border-green-200 bg-green-50 text-green-800" : "border-slate-200 bg-white text-slate-400"}`}>
          <div className="text-xs font-bold">{s.n}</div>
          <div>{s.short ?? s.label}</div>
          {s.lane === "purchase" && <div className="mt-0.5 text-[10px] uppercase tracking-wide opacity-70">purchase</div>}
        </li>
      ))}
    </ol>
  );
}

function QuotesEditor({ value, onChange }: { value: Quote[]; onChange: (q: Quote[]) => void }) {
  const rows = value.length ? value : [{}];
  const upd = (ix: number, k: keyof Quote, v: string) => onChange(rows.map((r, j) => (j === ix ? { ...r, [k]: v } : r)));
  return (
    <div className="space-y-2">
      {rows.map((q, ix) => (
        <div key={ix} className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <input className="input sm:col-span-2" placeholder="Supplier" value={q.vendor ?? ""} onChange={(e) => upd(ix, "vendor", e.target.value)} />
          <input className="input" placeholder="Rate ₹" type="number" step="any" value={q.rate ?? ""} onChange={(e) => upd(ix, "rate", e.target.value)} />
          <input className="input" placeholder="Delivery days" type="number" value={q.delivery_days ?? ""} onChange={(e) => upd(ix, "delivery_days", e.target.value)} />
          <input className="input" placeholder="Terms" value={q.terms ?? ""} onChange={(e) => upd(ix, "terms", e.target.value)} />
        </div>
      ))}
      {rows.length < 10 && <button type="button" className="text-xs font-medium text-navy hover:underline" onClick={() => onChange([...rows, {}])}>+ Add quotation</button>}
    </div>
  );
}

function ActionForm({ d, action, meta, onDone, onCancel }: { d: Detail; action: string; meta: WorkflowMeta; onDone: () => void; onCancel: () => void }) {
  const stage = meta.stages.find((s) => s.key === d.stage);
  const fields = d.action_fields[action] ?? [];
  const needsRemark = meta.needs_remark.includes(action);
  const isAdmin = !!useAuth().me?.is_admin;
  const [remarks, setRemarks] = useState("");
  const [qty, setQty] = useState("");
  const [qtyTo, setQtyTo] = useState("");
  const [to, setTo] = useState("requester");
  const [data, setData] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(fields.map((f) => [f, f === "quotes" ? (d.quotes ?? []) : prefill(d, f)])));

  const run = useMutation({
    mutationFn: () => {
      const clean: Record<string, unknown> = {};
      for (const [k, v] of Object.entries(data)) {
        if (k === "quotes") clean.quotes = (v as Quote[]).filter((q) => q.vendor);
        else if (v !== "" && v !== null) clean[k] = v;
      }
      return post<Detail>(`/indents/${d.id}/act/`, {
        action,
        remarks,
        ...(qty ? { qty } : {}),
        ...(qtyTo ? { qty_to: qtyTo } : {}),
        ...(action === "sendback" ? { to } : {}),
        data: clean,
      });
    },
    onSuccess: onDone,
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    run.mutate();
  }

  const showQty = action === "issue" || action === "receive";
  const showQtyTo = action === "approve" && stage?.can_qty;

  return (
    <form onSubmit={submit} className="mt-4 space-y-4 rounded-xl border border-gold/40 bg-gold-50/40 p-4">
      <div className="font-medium text-navy">{buttonLabel(meta, d, action)}</div>
      {showQty && (
        <div>
          <label className="label" htmlFor="f-qty">{action === "issue" ? "Quantity issued from stock" : "Accepted quantity"} ({d.unit})</label>
          <input id="f-qty" className="input max-w-[200px]" type="number" step="any" min="0" value={qty} onChange={(e) => setQty(e.target.value)} required />
        </div>
      )}
      {showQtyTo && (
        <div>
          <label className="label" htmlFor="f-qtyto">Approve a smaller quantity (optional, requested {qtyFmt(d.approved_qty ?? d.qty)})</label>
          <input id="f-qtyto" className="input max-w-[200px]" type="number" step="any" min="0" value={qtyTo} onChange={(e) => setQtyTo(e.target.value)} />
        </div>
      )}
      {action === "sendback" && (
        <div>
          <label className="label">Send back to</label>
          <select className="input max-w-xs" value={to} onChange={(e) => setTo(e.target.value)}>
            <option value="requester">The person who raised it</option>
            <option value="previous">The previous step</option>
          </select>
        </div>
      )}
      {["verifyInv", "authorizePay", "pay"].includes(action) && <MoneyPanel d={d} action={action} />}
      {fields.map((f) => {
        const m = FIELD_META[f] ?? { label: f, type: "text" as FieldType };
        const val = data[f];
        return (
          <div key={f}>
            <label className="label" htmlFor={`f-${f}`}>{m.label}</label>
            {m.type === "quotes" ? (
              <QuotesEditor value={(val as Quote[]) ?? []} onChange={(q) => setData({ ...data, quotes: q })} />
            ) : m.type === "textarea" ? (
              <textarea id={`f-${f}`} className="input" rows={2} value={String(val ?? "")} onChange={(e) => setData({ ...data, [f]: e.target.value })} />
            ) : (
              <input id={`f-${f}`} className="input max-w-sm" type={m.type} step={m.type === "number" ? "any" : undefined} value={String(val ?? "")}
                onChange={(e) => setData({ ...data, [f]: e.target.value })} />
            )}
          </div>
        );
      })}
      <div>
        <label className="label" htmlFor="f-remarks">Remarks{needsRemark ? " (required)" : isAdmin ? " (required when acting for another role)" : ""}</label>
        <textarea id="f-remarks" className="input" rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} required={needsRemark} />
      </div>
      {run.error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{(run.error as Error).message}</p>}
      <div className="flex gap-2">
        <button className={BUTTON_TONE[action] ?? "btn-primary"} disabled={run.isPending}>{run.isPending ? "Saving…" : "Confirm"}</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>Back</button>
      </div>
    </form>
  );
}

export default function IndentDetail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const [action, setAction] = useState<string | null>(null);
  const meta = useQuery({ queryKey: ["workflow"], queryFn: () => get<WorkflowMeta>("/workflow/"), staleTime: 10 * 60_000 });
  const q = useQuery({ queryKey: ["indent", id], queryFn: () => get<Detail>(`/indents/${id}/`) });

  if (q.isLoading || meta.isLoading) return <p className="p-6 text-center text-slate-500">Loading…</p>;
  if (q.error) return <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{(q.error as Error).message}</p>;
  const d = q.data!;
  const m = meta.data!;

  const done = () => {
    setAction(null);
    qc.invalidateQueries({ queryKey: ["indent", id] });
    qc.invalidateQueries({ queryKey: ["indents"] });
    qc.invalidateQueries({ queryKey: ["unread"] });
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1">
          <Link to="/indents" className="text-xs text-slate-500 hover:underline">← Indents</Link>
          <h1 className="text-xl font-semibold text-navy">{d.number} · {d.item}</h1>
          <p className="text-sm text-slate-500">{d.site_name} · raised by {d.raised_by_name} on {dateFmt(d.created_at)}</p>
        </div>
        <div className="flex flex-wrap gap-1.5"><PriorityChip priority={d.priority} /><StatusChip status={d.status} /><StatusChip status={d.pstatus} /></div>
      </div>

      <div className="card p-4"><Tracker d={d} /></div>

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          {d.allowed_actions.length > 0 && (
            <div className="card p-5">
              <div className="text-sm font-semibold text-navy">Your action</div>
              <p className="text-xs text-slate-500">{d.waiting_with && `Waiting with ${d.waiting_with}`}{d.purchase_with && ` · Purchase with ${d.purchase_with}`}</p>
              {d.stock_at_site !== null && ["stock", "avail"].includes(d.stage) && (
                <p className="mt-2 rounded-lg bg-navy-50 px-3 py-2 text-sm text-navy">Stock at {d.site_name}: <b>{qtyFmt(d.stock_at_site)} {d.unit}</b> · needed {qtyFmt(d.approved_qty ?? d.qty)} {d.unit}</p>
              )}
              {!action && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {d.allowed_actions.map((a) => (
                    <button key={a} className={BUTTON_TONE[a] ?? "btn-ghost"} onClick={() => setAction(a)}>{buttonLabel(m, d, a)}</button>
                  ))}
                </div>
              )}
              {action && <ActionForm key={action} d={d} action={action} meta={m} onDone={done} onCancel={() => setAction(null)} />}
            </div>
          )}

          <div className="card grid gap-4 p-5 sm:grid-cols-3">
            <Field label="Requested">{qtyFmt(d.qty)} {d.unit}</Field>
            <Field label="Material code">{d.item_code}</Field>
            <Field label={`In stock at ${d.site_name}`}>{d.stock_at_site !== null && `${qtyFmt(d.stock_at_site)} ${d.unit}`}</Field>
            <Field label="Approved">{d.approved_qty && `${qtyFmt(d.approved_qty)} ${d.unit}`}</Field>
            <Field label="Need by">{dateFmt(d.need_by)}</Field>
            <Field label="Issued from stock">{d.issued_qty && `${qtyFmt(d.issued_qty)} ${d.unit}`}</Field>
            <Field label="To purchase">{d.purchase_qty && `${qtyFmt(d.purchase_qty)} ${d.unit}`}</Field>
            <Field label="Received">{d.received_qty && `${qtyFmt(d.received_qty)} ${d.unit}`}</Field>
            <Field label="Supplier">{d.po_vendor || d.vendor_final}</Field>
            <Field label="PO">{d.po_no && `${d.po_no} · ${money(d.po_rate)}`}</Field>
            <Field label="Expected delivery">{dateFmt(d.po_expected)}</Field>
            <Field label="Invoice">{d.inv_no && `${d.inv_no} · ${money(d.money.invoice_total)} incl. GST`}</Field>
            <Field label="Authorised">{d.pay_auth_amount && money(d.pay_auth_amount)}</Field>
            <Field label="Paid">{d.paid_total && `${money(d.paid_total)}${d.money.outstanding > 0 ? ` · ${money(d.money.outstanding)} to pay` : ""}`}</Field>
            <Field label="Last paid on">{dateFmt(d.paid_on)}</Field>
            <Field label="Estimated rate">{money(d.est_rate)}</Field>
            <div className="sm:col-span-3"><Field label="Purpose">{d.purpose}</Field></div>
            {d.stock_entries?.length > 0 && (
              <div className="sm:col-span-3">
                <div className="label">Stock movements from this indent</div>
                <ul className="text-sm">
                  {d.stock_entries.map((e) => (
                    <li key={e.id} className="flex gap-3 border-t border-slate-100 py-1.5">
                      <span className="w-24 text-slate-500">{dateFmt(e.date)}</span>
                      <span className={`chip ${e.kind === "IN" ? "bg-green-100 text-green-800" : "bg-orange-100 text-orange-800"}`}>{e.kind}</span>
                      <span className="tabular-nums">{qtyFmt(e.qty)} {d.unit}</span>
                      <span className="text-slate-500">{e.ref} {e.note}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {d.quotes?.length > 0 && (
              <div className="sm:col-span-3">
                <div className="label">Quotations</div>
                <table className="w-full text-sm">
                  <tbody>
                    {d.quotes.map((x, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="py-1.5">{x.vendor}</td><td className="py-1.5 text-right">{money(x.rate)}</td>
                        <td className="py-1.5 pl-4 text-slate-500">{x.delivery_days && `${x.delivery_days} days`}</td><td className="py-1.5 pl-4 text-slate-500">{x.terms}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <div className="card p-5">
          <div className="mb-3 text-sm font-semibold text-navy">History</div>
          <ol className="space-y-4 border-l border-slate-200 pl-4">
            {[...d.history].reverse().map((h) => (
              <li key={h.id} className="relative">
                <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full bg-gold" />
                <div className="text-sm font-medium">{h.label}{h.override && <span className="ml-1.5 chip bg-red-100 text-red-700">admin override</span>}</div>
                <div className="text-xs text-slate-500">{h.by_name} · {dateTimeFmt(h.at)}</div>
                {h.qty && <div className="text-xs">Qty {qtyFmt(h.qty)}</div>}
                {h.qty_to && <div className="text-xs">Approved {qtyFmt(h.qty_to)}</div>}
                {h.grn_no && <div className="text-xs">GRN {h.grn_no}</div>}
                {["verifyInv", "authorizePay", "pay"].includes(h.action) && (() => {
                  const c = (h.changes ?? {}) as Record<string, unknown>;
                  const amt = h.action === "verifyInv" ? c.inv_amount : h.action === "authorizePay" ? c.pay_auth_amount : c.pay_amount;
                  return amt ? <div className="text-xs">{money(amt as string)}{h.action === "pay" && c.pay_ref ? ` · ${String(c.pay_ref)}` : ""}</div> : null;
                })()}
                {h.remarks && <div className="mt-1 rounded bg-slate-50 px-2 py-1 text-xs text-slate-700">{h.remarks}</div>}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
