import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import { Modal } from "../components/ImportModal";
import { ActionButton, Attachments, Detail, FilterBar, PageHead, RecordForm, RecordTable, Tabs, Tone, dateFmt, dateTimeFmt, money, rowsOf, useFilters, type FieldDef } from "../components/records";
import type { Page } from "../types";

interface Payment { id: number; date: string; amount: string; mode: string; ref: string; by_name: string; at: string }
interface Expense { id: number; site: number; site_name: string; project: number | null; project_name: string; indent: number | null; indent_number: string;
  date: string; category: string; description: string; payee: string; bill_no: string; amount: string; gst: string; total: string; status: string;
  editable: boolean; submitted_at: string | null; approved_amount: string | null; approved_by: number | null; approved_by_name: string; approved_at: string | null;
  review_note: string; paid_total: string; outstanding: string; payments: Payment[]; created_by: number; created_by_name: string }
interface Summary { totals: { amount: number; gst: number; approved: number; paid: number }; outstanding: number;
  by_category: { category: string; bills: number; amount: string; gst: string; approved: string; paid: string }[] }

const STATUS: Record<string, { label: string; tone: "slate" | "amber" | "blue" | "violet" | "green" | "red" }> = {
  draft: { label: "Draft", tone: "slate" }, submitted: { label: "Waiting approval", tone: "amber" }, approved: { label: "Approved — to pay", tone: "blue" },
  part_paid: { label: "Part paid", tone: "violet" }, paid: { label: "Paid", tone: "green" }, rejected: { label: "Rejected", tone: "red" },
};
const TABS = [{ key: "", label: "All bills" }, { key: "submitted", label: "Waiting approval" }, { key: "approved,part_paid", label: "To pay" }, { key: "paid", label: "Paid" }, { key: "summary", label: "Summary" }];

export default function Expenses() {
  const { has, me } = useAuth();
  const qc = useQueryClient();
  const filters = useFilters();
  const tab = filters.f.tab;
  const qs = filters.query(tab && tab !== "summary" ? { status: tab } : {});
  const list = useQuery({ queryKey: ["expenses", qs], queryFn: () => get<Page<Expense>>(`/expenses/?${qs}&page_size=200`), enabled: tab !== "summary" });
  const summary = useQuery({ queryKey: ["exp-summary", qs], queryFn: () => get<Summary>(`/expenses/summary/?${qs}`), enabled: tab === "summary" });
  const cats = useQuery({ queryKey: ["exp-cats"], queryFn: () => get<string[]>("/expenses/categories/"), staleTime: Infinity });
  const [edit, setEdit] = useState<Expense | "new" | null>(null);
  const openId = Number(filters.params.get("id")) || null;
  const one = useQuery({ queryKey: ["expense", openId], queryFn: () => get<Expense>(`/expenses/${openId}/`), enabled: !!openId });
  const e = one.data;
  const refresh = () => { qc.invalidateQueries({ queryKey: ["expenses"] }); qc.invalidateQueries({ queryKey: ["expense"] }); qc.invalidateQueries({ queryKey: ["pending"] }); };
  const open = (id: number | null) => { const n = new URLSearchParams(filters.params); if (id) n.set("id", String(id)); else n.delete("id"); filters.setParams(n, { replace: true }); };

  const fields: FieldDef[] = [
    { name: "site", label: "Site", type: "site", required: true }, { name: "project", label: "Project", type: "project" },
    { name: "date", label: "Bill date", type: "date", required: true },
    { name: "category", label: "Category", type: "select", required: true, options: (cats.data ?? []).map((c) => ({ value: c, label: c })) },
    { name: "payee", label: "Paid to (supplier / contractor)", required: true }, { name: "bill_no", label: "Bill / invoice number", help: "The same bill from the same payee can't be entered twice." },
    { name: "description", label: "What for", required: true, wide: true },
    { name: "amount", label: "Amount before GST (₹)", type: "number", required: true }, { name: "gst", label: "GST (₹)", type: "number" },
  ];
  const mine = e && (e.created_by === me?.id || has("expenses.edit"));

  return (
    <div>
      <PageHead title="Expenses & bills">{has("expenses.create") && <button className="btn-gold" onClick={() => setEdit("new")}>+ Add bill</button>}</PageHead>
      <Tabs tabs={TABS} value={tab} onChange={(k) => filters.set("tab", k)} />
      <FilterBar filters={filters} exportUrl={`/api/expenses/export/?${qs}`} exportCode="expenses.export" searchPlaceholder="Payee, bill no, description" />
      {tab === "summary" ? summary.data && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[["Billed", summary.data.totals.amount + summary.data.totals.gst], ["Approved", summary.data.totals.approved], ["Paid", summary.data.totals.paid], ["Still to pay", summary.data.outstanding]].map(([l, v]) => (
              <div key={l as string} className="card p-4"><div className="label">{l}</div><div className="text-2xl font-semibold tabular-nums text-navy">{money(v)}</div></div>))}
          </div>
          <RecordTable rows={summary.data.by_category.map((c, i) => ({ ...c, id: i }))} empty="No bills in this period." cols={[
            { label: "Category", render: (c) => c.category }, { label: "Bills", render: (c) => c.bills, className: "text-right" },
            { label: "Billed", render: (c) => money(Number(c.amount) + Number(c.gst)), className: "text-right tabular-nums" },
            { label: "Approved", render: (c) => money(c.approved), className: "text-right tabular-nums" }, { label: "Paid", render: (c) => money(c.paid), className: "text-right tabular-nums" },
          ]} />
        </div>
      ) : (
        <RecordTable rows={rowsOf(list.data)} empty="No bills here." onOpen={(x) => open(x.id)} cols={[
          { label: "Date", render: (x) => dateFmt(x.date) }, { label: "Payee", render: (x) => <span className="font-medium text-navy">{x.payee}</span> },
          { label: "Bill no", render: (x) => x.bill_no }, { label: "Category", render: (x) => x.category },
          { label: "Site / project", render: (x) => `${x.site_name}${x.project_name ? ` · ${x.project_name}` : ""}` },
          { label: "Total", render: (x) => money(x.total), className: "text-right tabular-nums" },
          { label: "Still to pay", render: (x) => Number(x.outstanding) ? money(x.outstanding) : "", className: "text-right tabular-nums" },
          { label: "Status", render: (x) => <Tone tone={STATUS[x.status].tone}>{STATUS[x.status].label}</Tone> },
        ]} />
      )}

      {e && !edit && (
        <Modal title={`${e.payee}${e.bill_no ? ` · ${e.bill_no}` : ""}`} onClose={() => open(null)} wide>
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2"><Tone tone={STATUS[e.status].tone}>{STATUS[e.status].label}</Tone><span className="text-xs text-slate-500">entered by {e.created_by_name}{e.approved_at && ` · approved by ${e.approved_by_name} ${dateTimeFmt(e.approved_at)}`}</span></div>
            {e.review_note && <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">{e.review_note}</p>}
            <div className="grid gap-4 sm:grid-cols-3">
              <Detail label="Site">{e.site_name}</Detail><Detail label="Project">{e.project_name}</Detail><Detail label="Bill date">{dateFmt(e.date)}</Detail>
              <Detail label="Category">{e.category}</Detail><Detail label="Indent">{e.indent_number}</Detail><Detail label="What for">{e.description}</Detail>
              <Detail label="Amount">{money(e.amount)}</Detail><Detail label="GST">{money(e.gst)}</Detail><Detail label="Total"><b>{money(e.total)}</b></Detail>
              <Detail label="Approved">{money(e.approved_amount)}</Detail><Detail label="Paid">{money(e.paid_total)}</Detail><Detail label="Still to pay"><b>{money(e.outstanding)}</b></Detail>
            </div>
            {e.payments.length > 0 && (
              <div><div className="label">Payments</div>
                <ul className="text-sm">{e.payments.map((p) => <li key={p.id} className="flex flex-wrap gap-3 border-t border-slate-100 py-1.5"><span className="w-24">{dateFmt(p.date)}</span><b className="tabular-nums">{money(p.amount)}</b><span>{p.mode}</span><span className="text-slate-500">{p.ref}</span><span className="text-xs text-slate-400">by {p.by_name}</span></li>)}</ul></div>
            )}
            <Attachments base={`/expenses/${e.id}/`} canAdd={has("expenses.edit")} title="Bill copy & supporting documents" purposes={[{ value: "bill", label: "Bill copy" }, { value: "payment", label: "Payment proof" }, { value: "other", label: "Other" }]} />
            <div className="flex flex-wrap gap-2 border-t pt-4">
              {e.editable && mine && <><ActionButton label="Submit for approval" url={`/expenses/${e.id}/submit/`} onDone={refresh} confirmText="After submitting, the bill can't be changed unless it's rejected." />
                <button className="btn-ghost" onClick={() => setEdit(e)}>Edit</button></>}
              {e.status === "submitted" && has("expenses.approve") && e.created_by !== me?.id && <>
                <ActionButton label="Approve" url={`/expenses/${e.id}/approve/`} onDone={refresh} fields={[{ name: "approved_amount", label: `Amount approved (₹) — up to ${money(e.total)}`, type: "number", required: true, initial: e.total }, { name: "note", label: "Note" }]} />
                <ActionButton label="Reject" tone="btn-danger" url={`/expenses/${e.id}/reject/`} onDone={refresh} fields={[{ name: "note", label: "Why", type: "textarea", required: true }]} />
              </>}
              {["approved", "part_paid"].includes(e.status) && has("expenses.edit") && (
                e.approved_by === me?.id ? <p className="text-sm text-slate-500">You approved this bill, so someone else records the payment.</p> :
                <ActionButton label="Record payment" url={`/expenses/${e.id}/pay/`} onDone={refresh} fields={[
                  { name: "date", label: "Paid on", type: "date", required: true, initial: new Date().toISOString().slice(0, 10) },
                  { name: "amount", label: `Amount paid (₹) — up to ${money(e.outstanding)}`, type: "number", required: true, initial: e.outstanding },
                  { name: "mode", label: "Mode (NEFT, RTGS, cheque, UPI, cash)" }, { name: "ref", label: "UTR / cheque number" }]} />
              )}
            </div>
          </div>
        </Modal>
      )}
      {edit && (
        <Modal title={edit === "new" ? "Add bill" : "Edit bill"} onClose={() => setEdit(null)} wide>
          <RecordForm fields={fields} endpoint="/expenses/" id={edit === "new" ? undefined : edit.id}
            initial={edit === "new" ? { date: new Date().toISOString().slice(0, 10), gst: "0", site: filters.f.site ? Number(filters.f.site) : "" } : (edit as unknown as Record<string, unknown>)}
            onCancel={() => setEdit(null)} onSaved={(x) => { setEdit(null); refresh(); open(Number(x.id)); }} />
        </Modal>
      )}
    </div>
  );
}
