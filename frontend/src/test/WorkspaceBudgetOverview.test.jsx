/**
 * Tests for WorkspaceBudgetOverview component.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";

vi.mock("../api");

import * as api from "../api";
import WorkspaceBudgetOverview from "../components/WorkspaceBudgetOverview.jsx";

const overview = {
  workspace_id: "ws-1",
  currency: "USD",
  campaign_count: 2,
  planned_total: 5000,
  actual_total: 3000,
  variance: 2000,
  spent_ratio: 0.6,
  items: [
    {
      campaign_id: "c-1",
      campaign_name: "Spring Launch",
      summary: {
        campaign_id: "c-1",
        currency: "USD",
        planned_total: 3000,
        actual_total: 2000,
        variance: 1000,
        spent_ratio: 0.67,
        alert_threshold_pct: 0.8,
        is_alert_triggered: false,
      },
    },
    {
      campaign_id: "c-2",
      campaign_name: "Summer Sale",
      summary: {
        campaign_id: "c-2",
        currency: "USD",
        planned_total: 2000,
        actual_total: 1000,
        variance: 1000,
        spent_ratio: 0.5,
        alert_threshold_pct: 0.8,
        is_alert_triggered: false,
      },
    },
  ],
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe("WorkspaceBudgetOverview", () => {
  it("renders nothing when loading", () => {
    api.getWorkspaceBudgetOverview.mockReturnValue(new Promise(() => {}));
    const { container } = render(<WorkspaceBudgetOverview workspaceId="ws-1" />);
    // While loading, returns null
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when there are no campaigns", async () => {
    api.getWorkspaceBudgetOverview.mockResolvedValue({
      ...overview,
      campaign_count: 0,
      items: [],
    });

    const { container } = render(<WorkspaceBudgetOverview workspaceId="ws-1" />);
    await waitFor(() => expect(api.getWorkspaceBudgetOverview).toHaveBeenCalled());
    expect(container.querySelector("[data-testid='workspace-budget-overview']")).toBeNull();
  });

  it("renders budget overview with stats", async () => {
    api.getWorkspaceBudgetOverview.mockResolvedValue(overview);

    render(<WorkspaceBudgetOverview workspaceId="ws-1" />);

    await waitFor(() => screen.getByTestId("workspace-budget-overview"));
    expect(screen.getByText("💰 Budget Overview")).toBeInTheDocument();
    expect(screen.getByText("Total Planned")).toBeInTheDocument();
    expect(screen.getByText("Total Actual")).toBeInTheDocument();
    expect(screen.getByText("Variance")).toBeInTheDocument();
    expect(screen.getAllByText("Utilization").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("renders per-campaign breakdown table", async () => {
    api.getWorkspaceBudgetOverview.mockResolvedValue(overview);

    render(<WorkspaceBudgetOverview workspaceId="ws-1" />);

    await waitFor(() => screen.getByText("Per-Campaign Breakdown"));
    expect(screen.getByText("Spring Launch")).toBeInTheDocument();
    expect(screen.getByText("Summer Sale")).toBeInTheDocument();
  });

  it("renders nothing on API error", async () => {
    api.getWorkspaceBudgetOverview.mockRejectedValue(new Error("Network error"));

    const { container } = render(<WorkspaceBudgetOverview workspaceId="ws-1" />);
    await waitFor(() => expect(api.getWorkspaceBudgetOverview).toHaveBeenCalled());
    expect(container.querySelector("[data-testid='workspace-budget-overview']")).toBeNull();
  });
});
