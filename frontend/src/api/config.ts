/**
 * Single source of truth for where the backend lives.
 *
 * Everything that talks to AETHON reads `BASE_URL` from here, and `BASE_URL`
 * reads exactly one env var. When the backend moves off localhost, set
 * `VITE_API_BASE_URL` in `.env.local` (or the deploy environment) and nothing
 * else changes.
 */
const RAW_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Base URL with any trailing slash removed, so `${BASE_URL}/api/...` is clean. */
export const BASE_URL = RAW_BASE.replace(/\/+$/, "");

/** ws(s):// origin derived from BASE_URL for the alerts socket. */
export const WS_BASE_URL = BASE_URL.replace(/^http/, "ws");

/**
 * Operator identity attached to audited, identity-sensitive calls
 * (`actor` on trajectory queries, `added_by` on watch-list edits).
 * This is NOT authentication — the backend logs it verbatim. Replace with a
 * real signed-in user once auth exists.
 */
export const OPERATOR_NAME =
  import.meta.env.VITE_OPERATOR_NAME ?? "demo_frontend";
