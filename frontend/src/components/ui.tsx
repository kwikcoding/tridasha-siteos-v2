import type { ReactNode } from "react";

const STATUS_TONE: Record<string, string> = {
  Requested: "bg-amber-100 text-amber-800",
  "Under Verification": "bg-sky-100 text-sky-800",
  Approved: "bg-indigo-100 text-indigo-800",
  "Sent Back": "bg-orange-100 text-orange-800",
  "On Hold": "bg-slate-200 text-slate-700",
  "Stock Issued": "bg-green-100 text-green-800",
  "Purchase Required": "bg-violet-100 text-violet-800",
  RFQ: "bg-violet-100 text-violet-800",
  "Supplier Rejected": "bg-orange-100 text-orange-800",
  "Vendor Approved": "bg-violet-100 text-violet-800",
  "PO Issued": "bg-blue-100 text-blue-900",
  "In Transit": "bg-blue-100 text-blue-900",
  "Partially Received": "bg-teal-100 text-teal-800",
  "Supplier Return / Replacement": "bg-red-100 text-red-800",
  Received: "bg-teal-100 text-teal-800",
  Closed: "bg-green-100 text-green-800",
  Rejected: "bg-red-100 text-red-800",
  Cancelled: "bg-slate-200 text-slate-600",
  "Invoice Verified": "bg-sky-100 text-sky-800",
  "Invoice On Hold": "bg-slate-200 text-slate-700",
  "Invoice Returned": "bg-orange-100 text-orange-800",
  "Payment Authorised": "bg-indigo-100 text-indigo-800",
  "Part Paid": "bg-amber-100 text-amber-800",
  "Payment On Hold": "bg-slate-200 text-slate-700",
  "Purchase Closed": "bg-green-100 text-green-800",
};

export function StatusChip({ status }: { status: string }) {
  if (!status) return null;
  return <span className={`chip ${STATUS_TONE[status] ?? "bg-slate-100 text-slate-700"}`}>{status}</span>;
}

export function PriorityChip({ priority }: { priority: string }) {
  if (priority === "normal") return null;
  return <span className={`chip ${priority === "critical" ? "bg-red-600 text-white" : "bg-red-100 text-red-700"}`}>{priority}</span>;
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="label">{label}</div>
      <div className="text-sm">{children || <span className="text-slate-400">—</span>}</div>
    </div>
  );
}

export const qtyFmt = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: 3 });

export const money = (v: string | number | null | undefined) =>
  v === null || v === undefined || v === "" ? "" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });

export const dateFmt = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) : "";

export const dateTimeFmt = (v: string | null | undefined) =>
  v ? new Date(v).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "";
