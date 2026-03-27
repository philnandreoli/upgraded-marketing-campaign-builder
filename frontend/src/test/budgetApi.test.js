/**
 * Unit tests for the budget-related API client functions.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../lib/auth.js", () => ({
  authHeaders: vi.fn().mockResolvedValue({}),
  authEnabled: false,
  redirectToLogin: vi.fn(),
}));

import {
  createBudgetEntry,
  listBudgetEntries,
  updateBudgetEntry,
  deleteBudgetEntry,
  getCampaignBudgetSummary,
  getWorkspaceBudgetOverview,
} from "../api.js";

function makeResponse(status, body = null) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    headers: { get: () => null },
    json: body !== null
      ? vi.fn().mockResolvedValue(body)
      : vi.fn().mockRejectedValue(new SyntaxError("no body")),
  };
}

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("createBudgetEntry", () => {
  it("sends POST to the correct path with body", async () => {
    const entry = { id: "e1", entry_type: "actual", amount: 100 };
    mockFetch.mockResolvedValue(makeResponse(201, entry));

    const result = await createBudgetEntry("ws-1", "c-1", {
      entry_type: "actual",
      amount: 100,
      currency: "USD",
      entry_date: "2026-03-01",
    });

    expect(result).toEqual(entry);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/workspaces/ws-1/campaigns/c-1/budget-entries",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

describe("listBudgetEntries", () => {
  it("sends GET without filter by default", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));

    await listBudgetEntries("ws-1", "c-1");

    const [url] = mockFetch.mock.calls[0];
    expect(url).toBe("/api/workspaces/ws-1/campaigns/c-1/budget-entries");
  });

  it("appends entry_type filter when provided", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, []));

    await listBudgetEntries("ws-1", "c-1", { entryType: "planned" });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("entry_type=planned");
  });
});

describe("updateBudgetEntry", () => {
  it("sends PATCH to the correct path", async () => {
    const updated = { id: "e1", amount: 200 };
    mockFetch.mockResolvedValue(makeResponse(200, updated));

    const result = await updateBudgetEntry("ws-1", "c-1", "e1", {
      amount: 200,
      currency: "USD",
      entry_date: "2026-03-02",
    });

    expect(result).toEqual(updated);
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/workspaces/ws-1/campaigns/c-1/budget-entries/e1",
      expect.objectContaining({ method: "PATCH" }),
    );
  });
});

describe("deleteBudgetEntry", () => {
  it("sends DELETE and returns undefined for 204", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 204,
      headers: { get: () => null },
      json: vi.fn(),
    });

    const result = await deleteBudgetEntry("ws-1", "c-1", "e1");

    expect(result).toBeUndefined();
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/workspaces/ws-1/campaigns/c-1/budget-entries/e1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

describe("getCampaignBudgetSummary", () => {
  it("sends GET with default threshold", async () => {
    const summary = { campaign_id: "c-1", planned_total: 1000, actual_total: 500 };
    mockFetch.mockResolvedValue(makeResponse(200, summary));

    const result = await getCampaignBudgetSummary("ws-1", "c-1");

    expect(result).toEqual(summary);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("alert_threshold_pct=0.8");
  });

  it("sends custom threshold when specified", async () => {
    mockFetch.mockResolvedValue(makeResponse(200, {}));

    await getCampaignBudgetSummary("ws-1", "c-1", { alertThresholdPct: 0.9 });

    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("alert_threshold_pct=0.9");
  });
});

describe("getWorkspaceBudgetOverview", () => {
  it("sends GET with default threshold", async () => {
    const overview = { workspace_id: "ws-1", campaign_count: 2 };
    mockFetch.mockResolvedValue(makeResponse(200, overview));

    const result = await getWorkspaceBudgetOverview("ws-1");

    expect(result).toEqual(overview);
    const [url] = mockFetch.mock.calls[0];
    expect(url).toContain("/api/workspaces/ws-1/budget-overview");
    expect(url).toContain("alert_threshold_pct=0.8");
  });
});
