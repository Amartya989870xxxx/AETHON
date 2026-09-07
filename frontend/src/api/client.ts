/**
 * The one place that talks to `fetch`. Every endpoint helper goes through
 * `apiFetch`, so URL building, JSON parsing and — critically — error-shape
 * normalisation live here and nowhere else.
 *
 * AETHON returns errors in two shapes:
 *   404/400  -> { "detail": "some string" }
 *   422      -> { "detail": [ { type, loc, msg, input }, ... ] }   (an array)
 * `apiFetch` collapses both into a single `ApiError`.
 */
import { BASE_URL } from "./config";

export interface ValidationIssue {
  type: string;
  loc: (string | number)[];
  msg: string;
  input?: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  /** Present only for 422 responses. */
  readonly issues?: ValidationIssue[];

  constructor(status: number, message: string, issues?: ValidationIssue[]) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.issues = issues;
  }
}

/** Thrown when the request never reached the server (backend down, CORS, DNS). */
export class NetworkError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

type Query = Record<
  string,
  string | number | boolean | null | undefined
>;

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE" | "PUT" | "PATCH";
  query?: Query;
  body?: unknown;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(
    path.startsWith("/") ? path : `/${path}`,
    `${BASE_URL}/`,
  );
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === null || value === undefined || value === "") continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

/** Normalise FastAPI's two error bodies into one `ApiError`. */
function toApiError(status: number, body: unknown): ApiError {
  const detail = (body as { detail?: unknown } | null)?.detail;

  if (Array.isArray(detail)) {
    const issues = detail as ValidationIssue[];
    const summary =
      issues
        .map((i) => `${i.loc.filter((p) => p !== "body").join(".")}: ${i.msg}`)
        .join("; ") || "Validation failed";
    return new ApiError(status, summary, issues);
  }

  if (typeof detail === "string") return new ApiError(status, detail);
  return new ApiError(status, `Request failed (${status})`);
}

export async function apiFetch<T>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const { method = "GET", query, body, signal } = opts;
  const url = buildUrl(path, query);

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      signal,
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new NetworkError(
      `Could not reach the AETHON API at ${BASE_URL}. Is the backend running (\`./run.sh serve\`)?`,
    );
  }

  const text = await res.text();
  const parsed = text ? safeJson(text) : null;

  if (!res.ok) throw toApiError(res.status, parsed);
  return parsed as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}
