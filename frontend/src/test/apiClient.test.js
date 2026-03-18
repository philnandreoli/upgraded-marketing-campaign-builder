/**
 * Unit tests for the shared API client module.
 *
 * Tests cover:
 *  - ApiError / RateLimitError class shapes
 *  - Error normalization (400 with detail, 500 without body, 204 no-content)
 *  - 429 retry with Retry-After header (mock 429 → success sequence)
 *  - Auth header injection and Content-Type defaulting
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock the auth module before importing apiClient
vi.mock("../lib/auth.js", () => ({
  authHeaders: vi.fn().mockResolvedValue({}),
}));

import { request, ApiError, RateLimitError } from "../lib/apiClient.js";
import { authHeaders } from "../lib/auth.js";

// ---------------------------------------------------------------------------
// Helper — build a minimal fetch Response-like object
// ---------------------------------------------------------------------------
function makeResponse(status, body = null, extraHeaders = {}) {
  const headerMap = {};
  for (const [k, v] of Object.entries(extraHeaders)) {
    headerMap[k.toLowerCase()] = v;
  }
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    headers: {
      get: (key) => headerMap[key.toLowerCase()] ?? null,
    },
    json: body !== null
      ? vi.fn().mockResolvedValue(body)
      : vi.fn().mockRejectedValue(new SyntaxError("no body")),
    text: vi.fn().mockResolvedValue(body ? JSON.stringify(body) : ""),
  };
}

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  vi.clearAllMocks();
  authHeaders.mockResolvedValue({});
});

// ---------------------------------------------------------------------------
// ApiError
// ---------------------------------------------------------------------------
describe("ApiError", () => {
  it("exposes status, detail, and body properties", () => {
    const err = new ApiError(400, "Bad input", { detail: "Bad input" });
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("ApiError");
    expect(err.status).toBe(400);
    expect(err.detail).toBe("Bad input");
    expect(err.body).toEqual({ detail: "Bad input" });
    expect(err.message).toBe("Bad input");
  });

  it("uses a default message when detail is null", () => {
    const err = new ApiError(500, null, null);
    expect(err.message).toBe("Request failed: 500");
    expect(err.detail).toBeNull();
    expect(err.body).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// RateLimitError
// ---------------------------------------------------------------------------
describe("RateLimitError", () => {
  it("is an instance of ApiError and Error", () => {
    const err = new RateLimitError(429, "Rate limited", 30);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("RateLimitError");
    expect(err.status).toBe(429);
    expect(err.retryAfter).toBe(30);
  });
});

// ---------------------------------------------------------------------------
// Error normalization
// ---------------------------------------------------------------------------
describe("request — error normalization", () => {
  it("throws ApiError with detail field on 400 with JSON detail", async () => {
    mockFetch.mockResolvedValue(makeResponse(400, { detail: "Invalid input" }));
    await expect(request("GET", "/api/test")).rejects.toMatchObject({
      name: "ApiError",
      status: 400,
      detail: "Invalid input",
      body: { detail: "Invalid input" },
    });
  });

  it("throws ApiError with statusText when JSON body has no detail", async () => {
    mockFetch.mockResolvedValue(makeResponse(403, { message: "forbidden" }));
    await expect(request("GET", "/api/test")).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
    });
  });

  it("throws ApiError on 500 without a JSON body", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      headers: { get: () => null },
      json: vi.fn().mockRejectedValue(new SyntaxError("not json")),
    });
    await expect(request("GET", "/api/test")).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
    });
  });

  it("returns undefined on 204 No Content", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: vi.fn(),
    });
    const result = await request("DELETE", "/api/test");
    expect(result).toBeUndefined();
  });

  it("returns parsed JSON on success", async () => {
    const payload = { id: "abc", name: "Campaign" };
    mockFetch.mockResolvedValue(makeResponse(200, payload));
    const result = await request("GET", "/api/test");
    expect(result).toEqual(payload);
  });
});

// ---------------------------------------------------------------------------
// 429 retry with backoff
// ---------------------------------------------------------------------------
describe("request — 429 retry", () => {
  let origSetTimeout;

  beforeEach(() => {
    // Replace setTimeout so retries resolve immediately without real delays
    origSetTimeout = globalThis.setTimeout;
    globalThis.setTimeout = (fn) => { fn(); return 0; };
  });

  afterEach(() => {
    globalThis.setTimeout = origSetTimeout;
  });

  it("retries on 429 and returns the result of the next successful attempt", async () => {
    const successBody = { id: "1" };
    mockFetch
      .mockResolvedValueOnce(makeResponse(429, null, { "Retry-After": "1" }))
      .mockResolvedValueOnce(makeResponse(200, successBody));

    const result = await request("GET", "/api/test");
    expect(result).toEqual(successBody);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("retries up to the configured retries count before throwing RateLimitError", async () => {
    mockFetch.mockResolvedValue(makeResponse(429, null, { "Retry-After": "1" }));

    await expect(request("GET", "/api/test", { retries: 1 })).rejects.toMatchObject({
      name: "RateLimitError",
      retryAfter: 1,
    });
    // 1 initial attempt + 1 retry = 2 total
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("throws RateLimitError immediately when retries = 0", async () => {
    mockFetch.mockResolvedValue(makeResponse(429, null, { "Retry-After": "5" }));

    await expect(request("GET", "/api/test", { retries: 0 })).rejects.toMatchObject({
      name: "RateLimitError",
      retryAfter: 5,
    });
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("reads the Retry-After header to determine wait time", async () => {
    const setTimeoutSpy = vi.fn().mockImplementation((fn) => { fn(); return 0; });
    globalThis.setTimeout = setTimeoutSpy;

    const successBody = { ok: true };
    mockFetch
      .mockResolvedValueOnce(makeResponse(429, null, { "Retry-After": "42" }))
      .mockResolvedValueOnce(makeResponse(200, successBody));

    await request("GET", "/api/test");
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 42_000);
  });

  it("defaults to 60 s wait when Retry-After header is absent", async () => {
    const setTimeoutSpy = vi.fn().mockImplementation((fn) => { fn(); return 0; });
    globalThis.setTimeout = setTimeoutSpy;

    mockFetch
      .mockResolvedValueOnce(makeResponse(429, null, {}))
      .mockResolvedValueOnce(makeResponse(200, { ok: true }));

    await request("GET", "/api/test");
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 60_000);
  });
});

// ---------------------------------------------------------------------------
// Auth header injection & Content-Type defaulting
// ---------------------------------------------------------------------------
describe("request — headers", () => {
  it("merges auth headers into every request", async () => {
    authHeaders.mockResolvedValue({ Authorization: "Bearer token123" });
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await request("GET", "/api/test");
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/test",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer token123" }),
      }),
    );
  });

  it("sets Content-Type: application/json when a body is present", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await request("POST", "/api/test", { body: { foo: "bar" } });
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/test",
      expect.objectContaining({
        headers: expect.objectContaining({ "Content-Type": "application/json" }),
        body: JSON.stringify({ foo: "bar" }),
      }),
    );
  });

  it("does not set Content-Type when no body is present", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await request("GET", "/api/test");
    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers["Content-Type"]).toBeUndefined();
  });

  it("caller-supplied headers override defaults", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, { ok: true }));

    await request("POST", "/api/test", {
      body: { x: 1 },
      headers: { "Content-Type": "text/plain" },
    });
    const [, init] = mockFetch.mock.calls[0];
    expect(init.headers["Content-Type"]).toBe("text/plain");
  });
});
