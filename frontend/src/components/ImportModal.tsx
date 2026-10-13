import { useEffect, useState, type ReactNode } from "react";
import { upload } from "../api";
import type { ImportResult } from "../types";

export function Modal({ title, children, onClose, wide }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-30 grid place-items-center bg-black/40 p-4" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className={`card max-h-[90vh] w-full overflow-y-auto p-6 ${wide ? "max-w-3xl" : "max-w-lg"}`} onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-navy">{title}</h2>
          <button className="text-slate-400 hover:text-slate-700" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** Upload .xlsx/.csv → preview what will change → confirm. */
export default function ImportModal({ title, endpoint, help, onClose, onDone }: {
  title: string; endpoint: string; help: ReactNode; onClose: () => void; onDone: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState<ImportResult | null>(null);

  async function send(commit: boolean) {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("commit", commit ? "true" : "false");
      const res = await upload<ImportResult>(endpoint, fd);
      if (commit) {
        setDone(res);
        onDone();
      } else setPreview(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={title} onClose={onClose} wide>
      {done ? (
        <div className="space-y-4">
          <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">
            Imported: {done.create} new, {done.update} updated, {done.unchanged} unchanged{done.error_count ? `, ${done.error_count} row(s) skipped` : ""}.
          </p>
          <div className="flex justify-end"><button className="btn-primary" onClick={onClose}>Done</button></div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="text-sm text-slate-600">{help}</div>
          <input type="file" accept=".xlsx,.xlsm,.csv" className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-navy file:px-3 file:py-2 file:text-white"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null); setError(""); }} />
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
          {preview && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[["New", preview.create, "text-green-700"], ["Updated", preview.update, "text-sky-700"], ["Unchanged", preview.unchanged, "text-slate-600"], ["Skipped (errors)", preview.error_count, "text-red-700"]].map(([l, n, c]) => (
                  <div key={l as string} className="rounded-lg border p-3 text-center">
                    <div className={`text-2xl font-semibold tabular-nums ${c}`}>{n as number}</div>
                    <div className="text-xs text-slate-500">{l as string}</div>
                  </div>
                ))}
              </div>
              <details className="text-xs text-slate-600">
                <summary className="cursor-pointer">Columns read from the file</summary>
                <ul className="mt-1 grid grid-cols-2 gap-x-4">{Object.entries(preview.columns).map(([f, h]) => <li key={f}><b>{f}</b> ← {h}</li>)}</ul>
              </details>
              {preview.sample_changed.length > 0 && (
                <p className="text-xs text-slate-600">Changes, e.g. {preview.sample_changed.slice(0, 5).map((c) => `${c.key} (${c.fields.join(", ")})`).join("; ")}</p>
              )}
              {preview.errors.length > 0 && (
                <div className="max-h-48 overflow-y-auto rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800">
                  {preview.errors.map((e) => <div key={e.line}>Line {e.line}: {e.message}</div>)}
                  {preview.error_count > preview.errors.length && <div>…and {preview.error_count - preview.errors.length} more</div>}
                </div>
              )}
              <p className="text-xs text-slate-500">Blank cells never overwrite existing data. Rows with errors are skipped.</p>
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button className="btn-ghost" onClick={onClose}>Cancel</button>
            {!preview ? (
              <button className="btn-primary" disabled={!file || busy} onClick={() => send(false)}>{busy ? "Reading…" : "Check file"}</button>
            ) : (
              <button className="btn-gold" disabled={busy || preview.create + preview.update === 0} onClick={() => send(true)}>
                {busy ? "Importing…" : `Import ${preview.create + preview.update} row(s)`}
              </button>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}
