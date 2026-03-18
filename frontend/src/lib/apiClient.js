import { authHeaders } from "./auth.js";

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
      detail = body.detail ?? detail;
    } catch { /* response wasn't JSON */ }
    throw new ApiError(res.status, detail, body);
  }
  if (res.status === 204) return undefined;
  return res.json();
}

export async function request(method, path, { body, headers, retries = 2 } = {}) {
  const merged = { ...(await authHeaders()), ...headers };
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
      if (err instanceof RateLimitError && attempt < retries) {
        await new Promise((r) => setTimeout(r, err.retryAfter * 1000));
        continue;
      }
      throw err;
    }
  }
}
