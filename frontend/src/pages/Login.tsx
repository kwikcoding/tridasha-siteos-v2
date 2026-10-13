import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function Login() {
  const { me, login } = useAuth();
  const nav = useNavigate();
  const [mobile, setMobile] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (me) return <Navigate to="/" replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(mobile, password);
      nav("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center bg-navy px-4">
      <form onSubmit={submit} className="card w-full max-w-sm p-7">
        <div className="mb-6 flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-gold font-bold text-white">T</span>
          <div>
            <h1 className="text-lg font-semibold text-navy">Tridasha SiteOS</h1>
            <p className="text-xs text-slate-500">Sign in with your mobile number</p>
          </div>
        </div>
        <label className="label" htmlFor="mobile">Mobile number</label>
        <input id="mobile" className="input mb-4" inputMode="numeric" autoComplete="username" placeholder="98xxxxxxxx"
          value={mobile} onChange={(e) => setMobile(e.target.value)} required />
        <label className="label" htmlFor="password">Password</label>
        <input id="password" className="input mb-5" type="password" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} required />
        {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <p className="mt-4 text-center text-xs text-slate-400">Your login is created by the administrator.</p>
      </form>
    </div>
  );
}
