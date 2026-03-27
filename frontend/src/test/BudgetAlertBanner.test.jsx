/**
 * Tests for BudgetAlertBanner component.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import BudgetAlertBanner from "../components/BudgetAlertBanner.jsx";

const baseSummary = {
  campaign_id: "c-1",
  currency: "USD",
  planned_total: 1000,
  actual_total: 850,
  variance: 150,
  spent_ratio: 0.85,
  alert_threshold_pct: 0.8,
  is_alert_triggered: true,
};

describe("BudgetAlertBanner", () => {
  it("returns null when summary is null", () => {
    const { container } = render(<BudgetAlertBanner summary={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null when alert is not triggered", () => {
    const { container } = render(
      <BudgetAlertBanner summary={{ ...baseSummary, is_alert_triggered: false }} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders warning banner when threshold is reached but not exceeded", () => {
    render(<BudgetAlertBanner summary={baseSummary} />);
    const banner = screen.getByTestId("budget-alert-banner");
    expect(banner).toBeInTheDocument();
    expect(banner.className).toContain("budget-alert-banner--warning");
    expect(screen.getByText(/budget threshold reached/i)).toBeInTheDocument();
  });

  it("renders danger banner when budget is exceeded", () => {
    const overSummary = {
      ...baseSummary,
      actual_total: 1200,
      spent_ratio: 1.2,
      variance: -200,
    };
    render(<BudgetAlertBanner summary={overSummary} />);
    const banner = screen.getByTestId("budget-alert-banner");
    expect(banner.className).toContain("budget-alert-banner--danger");
    expect(screen.getByText(/budget exceeded/i)).toBeInTheDocument();
  });

  it("has role=alert for accessibility", () => {
    render(<BudgetAlertBanner summary={baseSummary} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
