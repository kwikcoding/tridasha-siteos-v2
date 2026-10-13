import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import { PriorityChip, StatusChip, dateFmt, qtyFmt } from "../components/ui";
import type { IndentRow, Page } from "../types";

const TABS = [
  { key: "queue", label: "Waiting for me" },
  { key: "open", label: "Open" },
  { key: "purchases", label: "Purchases" },
  { key: "raised", label: "Raised by me" },
  { key: "closed", label: "Closed" },
  { key: "rejected", label: "Rejected / cancelled" },
  { key: "all", label: "All" },
];

export default function Indents() {
  const { can } = useAuth();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") || "queue";
  const [search, setSearch] = useState("");
  const qs = new URLSearchParams({ tab, ...(search ? { search } : {}) }).toString();
  const { data, isLoading, error } = useQuery({
    queryKey: ["indents", tab, search],
    queryFn: () => get<Page<IndentRow>>(`/indents/?${qs}`),
    refetchInterval: 30_000,
  });

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold text-navy">Indents</h1>
        <div className="flex-1" />
        <input className="input max-w-xs" placeholder="Search number, item, PO, supplier…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <a className="btn-ghost" href={`/api/indents/export/?${qs}`}>Download Excel</a>
        {can("indents", "edit") && <Link to="/indents/new" className="btn-gold">+ Raise indent</Link>}
      </div>

      <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setParams({ tab: t.key })}
            className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === t.key ? "border-gold text-navy" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {error && <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{(error as Error).message}</p>}
      {isLoading && <p className="p-6 text-center text-slate-500">Loading…</p>}
      {data && data.results.length === 0 && (
        <div className="card p-10 text-center text-slate-500">{tab === "queue" ? "Nothing is waiting for you right now." : "No indents here."}</div>
      )}

      {data && data.results.length > 0 && (
        <>
          {/* table on desktop */}
          <div className="card hidden overflow-hidden md:block">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2.5">Indent</th>
                  <th className="px-4 py-2.5">Material</th>
                  <th className="px-4 py-2.5 text-right">Qty</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5">Waiting with</th>
                  <th className="px-4 py-2.5">Need by</th>
                </tr>
              </thead>
              <tbody>
                {data.results.map((i) => (
                  <tr key={i.id} onClick={() => nav(`/indents/${i.id}`)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-navy">{i.number}</div>
                      <div className="text-xs text-slate-500">{i.site_name} · {i.raised_by_name}</div>
                    </td>
                    <td className="px-4 py-3">{i.item} <PriorityChip priority={i.priority} /></td>
                    <td className="px-4 py-3 text-right tabular-nums">{qtyFmt(i.approved_qty ?? i.qty)} {i.unit}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1"><StatusChip status={i.status} />{i.pstatus && <StatusChip status={i.pstatus} />}</div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {i.waiting_with || i.purchase_with}
                      {i.allowed_actions.length > 0 && <span className="ml-1.5 chip bg-gold-100 text-gold-600">you</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{dateFmt(i.need_by)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* cards on phones */}
          <div className="space-y-2 md:hidden">
            {data.results.map((i) => (
              <Link key={i.id} to={`/indents/${i.id}`} className="card block p-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium text-navy">{i.number}</div>
                    <div className="text-sm">{i.item} — {qtyFmt(i.approved_qty ?? i.qty)} {i.unit}</div>
                    <div className="text-xs text-slate-500">{i.site_name} · with {i.waiting_with || i.purchase_with || "—"}</div>
                  </div>
                  <StatusChip status={i.status} />
                </div>
              </Link>
            ))}
          </div>
          <p className="mt-3 text-xs text-slate-500">{data.count} indent(s)</p>
        </>
      )}
    </div>
  );
}
