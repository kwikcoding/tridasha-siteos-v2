// Thin fetch wrapper: same-origin session cookie + Django CSRF header.
export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, message: string, data: unknown) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

function cookie(name: string): string {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : "";
}

function messageFrom(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object") return fallback;
  const d = data as Record<string, unknown>;
  if (typeof d.detail === "string") return d.detail;
  const first = Object.entries(d)[0];
  if (first) {
    const [k, v] = first;
    const text = Array.isArray(v) ? String(v[0]) : typeof v === "string" ? v : JSON.stringify(v);
    return k === "non_field_errors" ? text : `${k.replace(/_/g, " ")}: ${text}`;
  }
  return fallback;
}

let csrfReady: Promise<unknown> | null = null;
export function ensureCsrf() {
  if (!csrfReady) csrfReady = fetch("/api/auth/csrf/", { credentials: "same-origin" });
  return csrfReady;
}

export async function api<T = unknown>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const method = opts.method || "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (method !== "GET") {
    await ensureCsrf();
    headers["X-CSRFToken"] = cookie("csrftoken");
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch("/api" + path, {
    method,
    headers,
    credentials: "same-origin",
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) throw new ApiError(res.status, messageFrom(data, `Request failed (${res.status})`), data);
  return data as T;
}

export const get = <T,>(p: string) => api<T>(p);
export const post = <T,>(p: string, body?: unknown) => api<T>(p, { method: "POST", body: body ?? {} });
export const patch = <T,>(p: string, body: unknown) => api<T>(p, { method: "PATCH", body });
export const del = (p: string) => api(p, { method: "DELETE" });
