import { authHeaders, authEnabled, redirectToLogin } from "./auth.js";

const API_BASE = "";

export class ApiError extends Error {
  constructor(status, detail, body) {
    super(detail || `Request failed: ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

export class RateLimitError extends ApiError {
  constructor(status, detail, retryAfter) {
    super(status, detail || `Rate limited: retry after ${retryAfter}s`);
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

function buildErrorDetail(status, statusText, url, body) {
  let detail = body?.detail ?? statusText;
  if (import.meta.env.DEV) {
    const extra = body?.traceback ?? body?.message ?? body?.error;
    if (extra && extra !== detail) {
      detail = `${detail}\n\n${extra}`;
    } else if (body && !body.detail && typeof body === "object") {
      detail = `${statusText} (${status}): ${JSON.stringify(body)}`;
    }
    console.error(`[API ${status}] ${url}`, body ?? detail);
  }
  return detail;
}

async function handleResponse(res) {
  if (res.status === 429) {
    const retryAfter = parseInt(res.headers.get("Retry-After") ?? "60", 10);
    throw new RateLimitError(res.status, null, retryAfter);
  }
  if (!res.ok) {
    let detail = res.statusText;
    let body = null;
    try {
      body = await res.json();
      detail = buildErrorDetail(res.status, res.statusText, res.url, body);
    } catch { /* response wasn't JSON */ }
    throw new ApiError(res.status, detail, body);
  }
  if (res.status === 204) return undefined;
  return res.json();
}

async function handleResponseWithHeaders(res) {
  if (res.status === 429) {
    const retryAfter = parseInt(res.headers.get("Retry-After") ?? "60", 10);
    throw new RateLimitError(res.status, null, retryAfter);
  }
  if (!res.ok) {
    let detail = res.statusText;
    let body = null;
    try {
      body = await res.json();
      detail = buildErrorDetail(res.status, res.statusText, res.url, body);
    } catch { /* response wasn't JSON */ }
    throw new ApiError(res.status, detail, body);
  }
  const data = res.status === 204 ? undefined : await res.json();
  return { data, headers: res.headers };
}

export async function requestWithHeaders(method, path, { body, headers, retries = 2 } = {}) {
  const auth = await authHeaders();
  const merged = { ...auth, ...headers };
  if (body !== undefined) merged["Content-Type"] ??= "application/json";

  for (let attempt = 0; attempt <= retries; attempt++) {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: merged,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    try {
      return await handleResponseWithHeaders(res);
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 401 &&
        authEnabled &&
        attempt < retries
      ) {
        const freshAuth = await authHeaders({ forceRefresh: true });
        if (!freshAuth.Authorization) {
          redirectToLogin();
          throw err;
        }
        Object.assign(merged, freshAuth);
        continue;
      }
      if (err instanceof RateLimitError && attempt < retries) {
        await new Promise((r) => setTimeout(r, err.retryAfter * 1000));
        continue;
      }
      throw err;
    }
  }
}

export async function request(method, path, { body, headers, retries = 2 } = {}) {
  const auth = await authHeaders();
  const merged = { ...auth, ...headers };
  if (body !== undefined) merged["Content-Type"] ??= "application/json";

  for (let attempt = 0; attempt <= retries; attempt++) {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: merged,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    try {
      return await handleResponse(res);
    } catch (err) {
      // On 401, try once more with a force-refreshed token.  This handles
      // stale cached tokens without forcing the user to re-login.
      if (
        err instanceof ApiError &&
        err.status === 401 &&
        authEnabled &&
        attempt < retries
      ) {
        const freshAuth = await authHeaders({ forceRefresh: true });
        if (!freshAuth.Authorization) {
          // No valid token available — redirect to login.
          redirectToLogin();
          throw err;
        }
        Object.assign(merged, freshAuth);
        continue;
      }
      if (err instanceof RateLimitError && attempt < retries) {
        await new Promise((r) => setTimeout(r, err.retryAfter * 1000));
        continue;
      }
      throw err;
    }
  }
}
