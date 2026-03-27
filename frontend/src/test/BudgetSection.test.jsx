/**
 * Tests for BudgetSection component.
 */

import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";

vi.mock("../api");

import * as api from "../api";
import BudgetSection from "../components/BudgetSection.jsx";

const summaryBase = {
  campaign_id: "c-1",
  currency: "USD",
  planned_total: 1000,
  actual_total: 400,
  variance: 600,
  spent_ratio: 0.4,
  alert_threshold_pct: 0.8,
  is_alert_triggered: false,
};

const entries = [
  {
    id: "e1",
    campaign_id: "c-1",
    entry_type: "planned",
    amount: 1000,
    currency: "USD",
    category: "Ads",
    description: "Google Ads budget",
    entry_date: "2026-03-01",
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
  {
    id: "e2",
    campaign_id: "c-1",
    entry_type: "actual",
    amount: 400,
    currency: "USD",
    category: "Ads",
    description: "March spend",
    entry_date: "2026-03-15",
    created_at: "2026-03-15T00:00:00Z",
    updated_at: "2026-03-15T00:00:00Z",
  },
];

beforeEach(() => {
  vi.resetAllMocks();
});

describe("BudgetSection – loading state", () => {
  it("shows loading spinner initially", () => {
    api.listBudgetEntries.mockReturnValue(new Promise(() => {}));
    api.getCampaignBudgetSummary.mockReturnValue(new Promise(() => {}));

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    expect(screen.getByText(/loading budget data/i)).toBeInTheDocument();
  });
});

describe("BudgetSection – data loaded", () => {
  it("renders budget entries grouped by type", async () => {
    api.listBudgetEntries.mockResolvedValue(entries);
    api.getCampaignBudgetSummary.mockResolvedValue(summaryBase);

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    await waitFor(() => screen.getByText("Google Ads budget"));
    // "Planned" appears in charts and entries group heading
    expect(screen.getAllByText("Planned").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Actual Spend")).toBeInTheDocument();
    expect(screen.getByText("Google Ads budget")).toBeInTheDocument();
    expect(screen.getByText("March spend")).toBeInTheDocument();
  });

  it("shows empty state when no entries", async () => {
    api.listBudgetEntries.mockResolvedValue([]);
    api.getCampaignBudgetSummary.mockResolvedValue(summaryBase);

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    await waitFor(() => screen.getByText(/no budget entries yet/i));
    expect(screen.getByText(/no budget entries yet/i)).toBeInTheDocument();
  });
});

describe("BudgetSection – spend entry form", () => {
  it("toggles form open and closed", async () => {
    api.listBudgetEntries.mockResolvedValue([]);
    api.getCampaignBudgetSummary.mockResolvedValue(summaryBase);

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    await waitFor(() => screen.getByRole("button", { name: /add entry/i }));
    const addBtn = screen.getByRole("button", { name: /add entry/i });

    fireEvent.click(addBtn);
    expect(screen.getByText("Save Entry")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Cancel"));
    expect(screen.queryByText("Save Entry")).not.toBeInTheDocument();
  });

  it("hides add entry button for viewers", async () => {
    api.listBudgetEntries.mockResolvedValue([]);
    api.getCampaignBudgetSummary.mockResolvedValue(summaryBase);

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" isViewer />);

    await waitFor(() => screen.getByText(/no budget entries yet/i));
    expect(screen.queryByRole("button", { name: /add entry/i })).not.toBeInTheDocument();
  });

  it("submits new entry and reloads", async () => {
    api.listBudgetEntries.mockResolvedValue([]);
    api.getCampaignBudgetSummary.mockResolvedValue(summaryBase);
    api.createBudgetEntry.mockResolvedValue({ id: "e-new" });

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    await waitFor(() => screen.getByRole("button", { name: /add entry/i }));
    fireEvent.click(screen.getByRole("button", { name: /add entry/i }));

    // Fill in amount (required field)
    const amountInput = screen.getByPlaceholderText("0.00");
    fireEvent.change(amountInput, { target: { value: "500", name: "amount" } });

    await act(async () => {
      fireEvent.click(screen.getByText("Save Entry"));
    });

    expect(api.createBudgetEntry).toHaveBeenCalledWith("ws-1", "c-1", expect.objectContaining({
      amount: 500,
      entry_type: "actual",
    }));
  });
});

describe("BudgetSection – delete entry", () => {
  it("calls delete API and reloads", async () => {
    api.listBudgetEntries.mockResolvedValue(entries);
    api.getCampaignBudgetSummary.mockResolvedValue(summaryBase);
    api.deleteBudgetEntry.mockResolvedValue(undefined);

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    await waitFor(() => screen.getByText("Google Ads budget"));

    const deleteButtons = screen.getAllByRole("button", { name: /delete entry/i });
    await act(async () => {
      fireEvent.click(deleteButtons[0]);
    });

    expect(api.deleteBudgetEntry).toHaveBeenCalledWith("ws-1", "c-1", "e1");
  });
});

describe("BudgetSection – alert banner", () => {
  it("shows alert banner when threshold is triggered", async () => {
    api.listBudgetEntries.mockResolvedValue(entries);
    api.getCampaignBudgetSummary.mockResolvedValue({
      ...summaryBase,
      actual_total: 900,
      variance: 100,
      spent_ratio: 0.9,
      is_alert_triggered: true,
    });

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    await waitFor(() => screen.getByTestId("budget-alert-banner"));
    expect(screen.getByTestId("budget-alert-banner")).toBeInTheDocument();
  });

  it("does not show alert banner when threshold is not triggered", async () => {
    api.listBudgetEntries.mockResolvedValue(entries);
    api.getCampaignBudgetSummary.mockResolvedValue(summaryBase);

    render(<BudgetSection workspaceId="ws-1" campaignId="c-1" />);

    await waitFor(() => screen.getByText("Google Ads budget"));
    expect(screen.queryByTestId("budget-alert-banner")).not.toBeInTheDocument();
  });
});
