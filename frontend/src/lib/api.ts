import type { Warning } from "./types";

const TOKEN_KEY = "asystent_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* tryb prywatny itp. */
  }
}

export class ApiError extends Error {
  status: number;
  warnings: Warning[];
  constructor(status: number, message: string, warnings: Warning[] = []) {
    super(message);
    this.status = status;
    this.warnings = warnings;
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`/api${path}`, { ...init, headers, body });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    setToken(null);
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- celowy pełny reload po wygaśnięciu sesji
    window.location.href = "/login";
    throw new ApiError(401, "Sesja wygasła");
  }
  if (!res.ok) {
    let message = `Błąd ${res.status}`;
    let warnings: Warning[] = [];
    try {
      const data = await res.json();
      const detail = data.detail;
      if (typeof detail === "string") message = detail;
      else if (detail?.message) {
        message = detail.message;
        warnings = detail.warnings ?? [];
      } else if (Array.isArray(detail)) message = detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch {
      /* brak JSON */
    }
    throw new ApiError(res.status, message, warnings);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
