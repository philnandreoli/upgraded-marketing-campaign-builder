/**
 * Tests for BudgetCharts component.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import BudgetCharts from "../components/BudgetCharts.jsx";

const summary = {
  campaign_id: "c-1",
  currency: "USD",
  planned_total: 1000,
  actual_total: 600,
  variance: 400,
  spent_ratio: 0.6,
  alert_threshold_pct: 0.8,
  is_alert_triggered: false,
};

describe("BudgetCharts", () => {
  it("returns null when summary is null", () => {
    const { container } = render(<BudgetCharts summary={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders budget overview heading", () => {
    render(<BudgetCharts summary={summary} />);
    expect(screen.getByText("Budget Overview")).toBeInTheDocument();
  });

  it("renders planned and actual stat values", () => {
    render(<BudgetCharts summary={summary} />);
    expect(screen.getAllByText("Planned").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Actual").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Variance")).toBeInTheDocument();
  });

  it("renders bar chart with correct widths", () => {
    render(<BudgetCharts summary={summary} />);
    const plannedBar = screen.getByTestId("budget-bar-planned");
    const actualBar = screen.getByTestId("budget-bar-actual");
    expect(plannedBar.style.width).toBe("100%");
    expect(actualBar.style.width).toBe("60%");
  });

  it("renders utilization progress bar", () => {
    render(<BudgetCharts summary={summary} />);
    expect(screen.getByText("Budget Utilization")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
    const fill = screen.getByTestId("budget-progress-fill");
    expect(fill.style.width).toBe("60%");
  });

  it("adds over-budget class when spent_ratio > 1", () => {
    const overSummary = { ...summary, actual_total: 1200, spent_ratio: 1.2 };
    render(<BudgetCharts summary={overSummary} />);
    const actualBar = screen.getByTestId("budget-bar-actual");
    expect(actualBar.className).toContain("budget-bar--over");
    const fill = screen.getByTestId("budget-progress-fill");
    expect(fill.className).toContain("budget-progress-fill--over");
  });

  it("adds warning class when spent_ratio exceeds threshold but not over 1", () => {
    const warningSummary = { ...summary, actual_total: 850, spent_ratio: 0.85 };
    render(<BudgetCharts summary={warningSummary} />);
    const fill = screen.getByTestId("budget-progress-fill");
    expect(fill.className).toContain("budget-progress-fill--warning");
  });

  it("has correct ARIA attributes on utilization progress bar", () => {
    render(<BudgetCharts summary={summary} />);
    const progressbar = screen.getByRole("progressbar");
    expect(progressbar).toHaveAttribute("aria-valuenow", "60");
    expect(progressbar).toHaveAttribute("aria-valuemin", "0");
    expect(progressbar).toHaveAttribute("aria-valuemax", "100");
  });
});
