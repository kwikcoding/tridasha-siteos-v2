import { Link } from "react-router-dom";

export default function AccessDenied() {
  return (
    <div className="card mx-auto max-w-md p-10 text-center">
      <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-full bg-red-50 text-xl text-red-600">!</div>
      <h1 className="text-lg font-semibold text-navy">You don’t have access to this page</h1>
      <p className="mt-2 text-sm text-slate-500">Your role doesn’t include it. If you need it for your work, ask the administrator to update your role.</p>
      <Link to="/" className="btn-primary mt-6">Back to dashboard</Link>
    </div>
  );
}
