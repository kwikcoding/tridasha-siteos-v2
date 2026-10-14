import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import { PriorityChip, StatusChip, dateFmt, qtyFmt } from "../components/ui";
import type { IndentRow, Page, Pending } from "../types";

function Stat({ label, value, to, tone }: { label: string; value: number | string; to?: string; tone?: string }) {
  const body = (
    <div className="card p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${tone ?? "text-navy"}`}>{value}</div>
    </div>
  );
  return to ? <Link to={to} className="block hover:opacity-90">{body}</Link> : body;
}

export default function Dashboard() {
  const { me, can, has } = useAuth();
  const pending = useQuery({ queryKey: ["pending"], queryFn: () => get<Pending>("/auth/pending/") });
  const queue = useQuery({ queryKey: ["indents", "queue", ""], queryFn: () => get<Page<IndentRow>>("/indents/?tab=queue"), enabled: can("indents") });
  const p = pending.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold text-navy">Good day, {me?.name.split(" ")[0]}</h1>
        <p className="text-sm text-slate-500">{me?.is_admin ? "Administrator" : me?.roles.map((r) => r.label).join(" · ")}{me?.department_name && ` · ${me.department_name}`}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {can("indents") && <Stat label="Indents waiting for you" value={p?.indents ?? "—"} to="/indents?tab=queue" tone={p?.indents ? "text-gold-600" : undefined} />}
        {can("indents") && <Stat label="Invoices & payments for you" value={p?.purchases ?? "—"} to="/indents?tab=purchases" tone={p?.purchases ? "text-gold-600" : undefined} />}
        {can("materials") && <Stat label="Items at reorder level" value={p?.low_stock ?? "—"} to="/materials?tab=stock" tone={p?.low_stock ? "text-red-600" : undefined} />}
        {can("indents") && <Stat label="Raised by you (open)" value={p?.raised_open ?? "—"} to="/indents?tab=raised" />}
      </div>

      {(() => {
        const cards: [string, number | undefined, string, boolean?][] = [
          ["Tasks assigned to you", p?.tasks_mine, "/tasks?tab=mine"], ["Overdue tasks", p?.tasks_overdue, "/tasks?tab=overdue", true],
          ["Daily reports to approve", p?.dpr_to_approve, "/dpr?tab=waiting"], ["Daily reports today", p?.dpr_today, "/dpr"],
          ["Workers present today", p?.present_today, "/labour"], ["Bills to approve", p?.bills_to_approve, "/expenses?tab=submitted"],
          ["Bills to pay", p?.bills_to_pay, "/expenses?tab=approved,part_paid"], ["Open quality & safety items", p?.observations_open, "/quality"],
          ["Q&S items assigned to you", p?.observations_mine, "/quality"], ["Equipment service due", p?.equipment_service_due, "/equipment", true],
        ];
        const shown = cards.filter(([, v]) => v !== undefined);
        if (!shown.length) return null;
        return (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-5">
            {shown.map(([label, v, to, warn]) => <Stat key={label} label={label} value={v ?? "—"} to={to} tone={v && warn ? "text-red-600" : v ? "text-gold-600" : undefined} />)}
          </div>
        );
      })()}

      {can("indents") && (
        <section className="card">
          <div className="flex items-center justify-between border-b px-5 py-3">
            <h2 className="font-semibold text-navy">Pending approvals — your queue</h2>
            <Link to="/indents?tab=queue" className="text-xs font-medium text-navy hover:underline">See all</Link>
          </div>
          {queue.data?.results.length === 0 && <p className="px-5 py-6 text-sm text-slate-500">Nothing is waiting for you right now.</p>}
          <ul className="divide-y">
            {queue.data?.results.slice(0, 8).map((i) => (
              <li key={i.id}>
                <Link to={`/indents/${i.id}`} className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-slate-50">
                  <span className="font-medium text-navy">{i.number}</span>
                  <span className="flex-1 text-sm">{i.item} — {qtyFmt(i.approved_qty ?? i.qty)} {i.unit} <PriorityChip priority={i.priority} /></span>
                  <span className="text-xs text-slate-500">{i.site_name}</span>
                  <StatusChip status={i.pstatus && i.stage === "closed" ? i.pstatus : i.status} />
                  <span className="text-xs text-slate-500">since {dateFmt(i.stage_entered_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {has("indents.create") && (
        <div className="flex gap-2">
          <Link to="/indents/new" className="btn-gold">+ Raise indent</Link>
          {can("materials") && <Link to="/materials" className="btn-ghost">Check stock</Link>}
        </div>
      )}
    </div>
  );
}
