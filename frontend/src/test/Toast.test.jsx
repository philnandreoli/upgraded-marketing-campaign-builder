/**
 * Tests for Toast hover-to-pause behavior.
 */

import { render, screen, act, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import Toast from "../components/Toast";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Toast – hover pause/resume", () => {
  it("renders a toast from an event", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting strategy", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    expect(screen.getByText("Starting strategy")).toBeInTheDocument();
    expect(screen.getByText("Strategy")).toBeInTheDocument();
  });

  it("auto-dismisses after DISPLAY_MS + EXIT_MS", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting strategy", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    expect(screen.getByText("Starting strategy")).toBeInTheDocument();

    // Advance past DISPLAY_MS (3500) + EXIT_MS (200)
    act(() => vi.advanceTimersByTime(3700));

    expect(screen.queryByText("Starting strategy")).not.toBeInTheDocument();
  });

  it("pauses dismiss timer on mouse enter and resumes on mouse leave", () => {
    const events = [
      { type: "stage_start", stage: "strategy", message: "Starting strategy", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    const toast = screen.getByText("Starting strategy").closest(".toast");

    // Advance 2000ms (less than 3500ms)
    act(() => vi.advanceTimersByTime(2000));

    // Mouse enter to pause
    act(() => {
      fireEvent.mouseEnter(toast);
    });

    // Even after waiting a long time, the toast should still be there
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.getByText("Starting strategy")).toBeInTheDocument();

    // Mouse leave to resume
    act(() => {
      fireEvent.mouseLeave(toast);
    });

    // Should still be visible for the remaining time (~1500ms)
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText("Starting strategy")).toBeInTheDocument();

    // Advance past remaining + EXIT_MS
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.queryByText("Starting strategy")).not.toBeInTheDocument();
  });

  it("has onMouseEnter and onMouseLeave handlers on toast elements", () => {
    const events = [
      { type: "stage_complete", stage: "content", message: "Content done", timestamp: "2026-01-01T00:00:00Z" },
    ];

    render(<Toast events={events} />);

    const toastEl = screen.getByText("Content done").closest(".toast");
    expect(toastEl).toBeInTheDocument();

    // Verify it doesn't throw when we fire the events
    expect(() => {
      fireEvent.mouseEnter(toastEl);
      fireEvent.mouseLeave(toastEl);
    }).not.toThrow();
  });
});
