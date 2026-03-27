/**
 * Tests for MentionAutocomplete component and useMentionAutocomplete hook.
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import MentionAutocomplete from "../components/MentionAutocomplete.jsx";

const MEMBERS = [
  { user_id: "u-1", display_name: "Alice Smith", email: "alice@example.com" },
  { user_id: "u-2", display_name: "Bob Jones", email: "bob@example.com" },
  { user_id: "u-3", display_name: "Charlie Brown", email: "charlie@example.com" },
];

describe("MentionAutocomplete", () => {
  it("renders all members when query is empty", () => {
    const onSelect = vi.fn();
    render(
      <MentionAutocomplete
        members={MEMBERS}
        query=""
        onSelect={onSelect}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={0}
      />
    );
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    expect(screen.getByText("Charlie Brown")).toBeInTheDocument();
  });

  it("filters members by display name", () => {
    render(
      <MentionAutocomplete
        members={MEMBERS}
        query="ali"
        onSelect={vi.fn()}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={0}
      />
    );
    expect(screen.getByText("Alice Smith")).toBeInTheDocument();
    expect(screen.queryByText("Bob Jones")).not.toBeInTheDocument();
    expect(screen.queryByText("Charlie Brown")).not.toBeInTheDocument();
  });

  it("filters members by email", () => {
    render(
      <MentionAutocomplete
        members={MEMBERS}
        query="bob@"
        onSelect={vi.fn()}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={0}
      />
    );
    expect(screen.getByText("Bob Jones")).toBeInTheDocument();
    expect(screen.queryByText("Alice Smith")).not.toBeInTheDocument();
  });

  it("returns null when no members match", () => {
    const { container } = render(
      <MentionAutocomplete
        members={MEMBERS}
        query="zzz-no-match"
        onSelect={vi.fn()}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={0}
      />
    );
    expect(container.querySelector(".mention-autocomplete")).toBeNull();
  });

  it("calls onSelect when a member is clicked", () => {
    const onSelect = vi.fn();
    render(
      <MentionAutocomplete
        members={MEMBERS}
        query=""
        onSelect={onSelect}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={0}
      />
    );
    fireEvent.mouseDown(screen.getByText("Bob Jones"));
    expect(onSelect).toHaveBeenCalledWith(MEMBERS[1]);
  });

  it("highlights the active item", () => {
    render(
      <MentionAutocomplete
        members={MEMBERS}
        query=""
        onSelect={vi.fn()}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={1}
      />
    );
    const items = screen.getAllByRole("option");
    expect(items[0]).not.toHaveClass("mention-autocomplete-item--active");
    expect(items[1]).toHaveClass("mention-autocomplete-item--active");
    expect(items[1]).toHaveAttribute("aria-selected", "true");
  });

  it("renders avatar initials", () => {
    render(
      <MentionAutocomplete
        members={[MEMBERS[0]]}
        query=""
        onSelect={vi.fn()}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={0}
      />
    );
    expect(screen.getByText("A")).toBeInTheDocument();
  });

  it("has a listbox role with accessible label", () => {
    render(
      <MentionAutocomplete
        members={MEMBERS}
        query=""
        onSelect={vi.fn()}
        
        anchorPosition={{ top: 100, left: 50 }}
        activeIndex={0}
      />
    );
    expect(screen.getByRole("listbox", { name: /mention suggestions/i })).toBeInTheDocument();
  });
});
