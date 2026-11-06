import { useSession } from "@/stores/session";

/**
 * network: cannot reach the server (offline, timeout) - the submit queue keeps the item and retries later
 * auth: session expired - the queue pauses until the user signs in again
 * business: the server rejected it under business rules (over-receipt, insufficient stock, ...) - retrying will not help, a person must act
 * server: internal server error - kept and retried later
 */
export type ApiErrorKind = "network" | "auth" | "business" | "server";

export class ApiError extends Error {
  constructor(
    public kind: ApiErrorKind,
    message: string,
    public status?: number,
  ) {
    super(message);
  }
}

const TIMEOUT_MS = 15000;

function detailMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg).join("; ");
  return `Request failed (${status})`;
}

function encodeForm(values: Record<string, string>): string {
  return Object.entries(values)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&");
}

function parse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: { form?: boolean; headers?: Record<string, string> } = {},
): Promise<T> {
  const { serverUrl, token } = useSession.getState();
  const headers: Record<string, string> = {};
  let payload: string | undefined;
  if (body !== undefined) {
    if (options.form) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
      payload = encodeForm(body as Record<string, string>);
    } else {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }
  }
  if (token) headers.Authorization = `Bearer ${token}`;
  Object.assign(headers, options.headers);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(serverUrl.replace(/\/+$/, "") + path, {
      method,
      headers,
      body: payload,
      signal: controller.signal,
    });
  } catch {
    throw new ApiError("network", "Cannot reach the server (network down or server not responding)");
  } finally {
    clearTimeout(timer);
  }

  const data = parse(await response.text());
  if (response.ok) return data as T;
  if (response.status === 401) throw new ApiError("auth", detailMessage(data, 401), 401);
  if (response.status >= 500) throw new ApiError("server", "Server error, please try again later", response.status);
  throw new ApiError("business", detailMessage(data, response.status), response.status);
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Operation failed";
}
