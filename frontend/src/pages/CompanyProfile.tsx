import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, get, patch, upload } from "../api";
import { useAuth } from "../auth";
import { ErrorBox, dateTimeFmt } from "../components/records";

export interface Company { name: string; legal_name: string; gstin: string; pan: string; cin: string; address: string; city: string; state: string;
  pincode: string; phone: string; email: string; website: string; financial_year_start: number; has_logo: boolean; updated_by_name: string; updated_at: string }

export const useCompany = () => useQuery({ queryKey: ["company"], queryFn: () => get<Company>("/company/"), staleTime: 10 * 60_000 });

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const FIELDS: { k: keyof Company; label: string; wide?: boolean; placeholder?: string; type?: string }[] = [
  { k: "name", label: "Short name (shown in the app) *" }, { k: "legal_name", label: "Registered name", placeholder: "Tridasha Infra Pvt Ltd" },
  { k: "gstin", label: "GSTIN", placeholder: "36ABCDE1234F1Z5" }, { k: "pan", label: "PAN", placeholder: "ABCDE1234F" }, { k: "cin", label: "CIN" },
  { k: "phone", label: "Phone" }, { k: "email", label: "Email", type: "email" }, { k: "website", label: "Website", type: "url", placeholder: "https://tridashaimperial.com" },
  { k: "address", label: "Address", wide: true }, { k: "city", label: "City" }, { k: "state", label: "State", placeholder: "Telangana" }, { k: "pincode", label: "PIN code" },
];

export default function CompanyProfile() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const co = useCompany();
  const [v, setV] = useState<Partial<Company>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  const [logo, setLogo] = useState<File | null>(null);
  const [logoKey, setLogoKey] = useState(0);
  useEffect(() => { if (co.data) setV(co.data); }, [co.data]);
  const canEdit = !!me?.is_admin;
  const save = useMutation({
    mutationFn: () => patch<Company>("/company/", Object.fromEntries(FIELDS.map((f) => [f.k, v[f.k] ?? ""]).concat([["financial_year_start", v.financial_year_start ?? 4]]))),
    onSuccess: (d) => { setSaved(true); qc.setQueryData(["company"], d); },
    onError: (e) => {
      const d = e instanceof ApiError ? (e.data as Record<string, unknown>) : null;
      setErrors(d ? Object.fromEntries(Object.entries(d).map(([k, x]) => [k, Array.isArray(x) ? String(x[0]) : String(x)])) : {});
    },
  });
  const sendLogo = useMutation({
    mutationFn: () => { const fd = new FormData(); fd.append("file", logo!); return upload<Company>("/company/logo/", fd); },
    onSuccess: (d) => { setLogo(null); setLogoKey((k) => k + 1); qc.setQueryData(["company"], d); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); setSaved(false); setErrors({}); save.mutate(); };
  if (!co.data) return <p className="p-6 text-center text-slate-500">Loading…</p>;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <form onSubmit={submit} className="card space-y-4 p-6">
        <div><h2 className="font-semibold text-navy">Company profile</h2>
          <p className="text-sm text-slate-500">Shown in the app header and at the top of downloaded reports.{co.data.updated_by_name && ` Last changed by ${co.data.updated_by_name}, ${dateTimeFmt(co.data.updated_at)}.`}</p></div>
        <div className="grid gap-4 sm:grid-cols-2">
          {FIELDS.map((f) => (
            <div key={f.k} className={f.wide ? "sm:col-span-2" : ""}>
              <label className="label" htmlFor={`co-${f.k}`}>{f.label}</label>
              {f.wide ? <textarea id={`co-${f.k}`} className="input" rows={2} value={String(v[f.k] ?? "")} disabled={!canEdit} onChange={(e) => setV({ ...v, [f.k]: e.target.value })} />
                : <input id={`co-${f.k}`} className="input" type={f.type ?? "text"} placeholder={f.placeholder} value={String(v[f.k] ?? "")} disabled={!canEdit} onChange={(e) => setV({ ...v, [f.k]: e.target.value })} />}
              {errors[f.k] && <p className="mt-1 text-xs text-red-600">{errors[f.k]}</p>}
            </div>
          ))}
          <div>
            <label className="label" htmlFor="co-fy">Financial year starts in</label>
            <select id="co-fy" className="input" value={v.financial_year_start ?? 4} disabled={!canEdit} onChange={(e) => setV({ ...v, financial_year_start: Number(e.target.value) })}>
              {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </div>
        </div>
        {errors.detail && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{errors.detail}</p>}
        {saved && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">Company profile saved.</p>}
        {canEdit && <div className="flex justify-end"><button className="btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save company profile"}</button></div>}
      </form>
      <section className="card space-y-3 p-6">
        <h2 className="font-semibold text-navy">Logo</h2>
        {co.data.has_logo ? <img key={logoKey} src={`/api/company/logo/?v=${logoKey}`} alt={`${co.data.name} logo`} className="h-16 w-auto rounded border border-slate-200 bg-white p-1" />
          : <p className="text-sm text-slate-500">No logo yet.</p>}
        {canEdit && (
          <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (logo) sendLogo.mutate(); }}>
            <input aria-label="Logo image" type="file" accept="image/png,image/jpeg,image/webp" className="text-sm" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
            <button className="btn-ghost" disabled={!logo || sendLogo.isPending}>Upload logo</button>
            <span className="text-xs text-slate-500">PNG, JPG or WEBP, under 2 MB.</span>
          </form>
        )}
        <ErrorBox error={sendLogo.error} />
      </section>
    </div>
  );
}
