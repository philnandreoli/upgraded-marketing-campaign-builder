/**
 * Tests for TemplateConfigDialog component.
 */

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, it, expect, beforeEach } from "vitest";
import TemplateConfigDialog from "../components/TemplateConfigDialog";
import { UserProvider } from "../UserContext";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../api", async () => {
  const actual = await vi.importActual("../api");
  return {
    ...actual,
    markAsTemplate: vi.fn(),
    updateTemplate: vi.fn(),
    unmarkTemplate: vi.fn(),
    getMe: vi.fn(),
  };
});
import * as api from "../api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const CAMPAIGN = {
  id: "camp-1",
  product_or_service: "Test Product",
  workspace_id: "ws-1",
  status: "approved",
  is_template: false,
};

const TEMPLATE_CAMPAIGN = {
  ...CAMPAIGN,
  is_template: true,
  template_id: "tmpl-1",
  template_category: "Product Launch",
  template_tags: ["summer", "promo"],
  template_description: "Use for summer launches",
  template_visibility: "workspace",
  template_parameters: [
    { name: "Product", type: "text", default: "Widget", description: "Product name" },
  ],
};

function renderDialog(props = {}, { isAdmin = false } = {}) {
  api.getMe.mockResolvedValue({
    id: "user-1",
    email: "test@example.com",
    display_name: "Test User",
    roles: isAdmin ? ["admin"] : ["campaign_builder"],
    is_admin: isAdmin,
    can_build: true,
    is_viewer: false,
  });

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    campaign: CAMPAIGN,
    workspaceId: "ws-1",
    mode: "create",
    onSuccess: vi.fn(),
    ...props,
  };

  return render(
    <MemoryRouter>
      <UserProvider>
        <TemplateConfigDialog {...defaultProps} />
      </UserProvider>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TemplateConfigDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when isOpen is false", () => {
    renderDialog({ isOpen: false });
    expect(screen.queryByText("Save as Template")).not.toBeInTheDocument();
  });

  it("renders the create mode title when open", () => {
    renderDialog();
    expect(screen.getByRole("heading", { name: "Save as Template" })).toBeInTheDocument();
  });

  it("renders the edit mode title", () => {
    renderDialog({ mode: "edit", campaign: TEMPLATE_CAMPAIGN });
    expect(screen.getByText("Edit Template Settings")).toBeInTheDocument();
  });

  it("renders category dropdown with predefined options", () => {
    renderDialog();
    const select = screen.getByLabelText("Category");
    expect(select).toBeInTheDocument();
    expect(select.querySelectorAll("option").length).toBeGreaterThanOrEqual(7); // 6 + "Select" + "Custom"
  });

  it("renders tags input", () => {
    renderDialog();
    expect(screen.getByLabelText("Tags")).toBeInTheDocument();
  });

  it("renders description textarea", () => {
    renderDialog();
    expect(screen.getByLabelText("Description")).toBeInTheDocument();
  });

  it("renders visibility options", () => {
    renderDialog();
    expect(screen.getByText("Workspace Only")).toBeInTheDocument();
  });

  it("shows Organization-wide option for admins", async () => {
    renderDialog({}, { isAdmin: true });
    await waitFor(() => {
      expect(screen.getByText("Organization-wide")).toBeInTheDocument();
    });
  });

  it("does not show Organization-wide for non-admins", async () => {
    renderDialog({}, { isAdmin: false });
    // Wait for UserProvider to resolve
    await waitFor(() => {
      expect(screen.queryByText("Organization-wide")).not.toBeInTheDocument();
    });
  });

  it("renders Add Parameter button", () => {
    renderDialog();
    expect(screen.getByText("+ Add Parameter")).toBeInTheDocument();
  });

  it("adds a parameter row when Add Parameter is clicked", () => {
    renderDialog();
    fireEvent.click(screen.getByText("+ Add Parameter"));
    expect(screen.getByLabelText("Parameter 1 name")).toBeInTheDocument();
    expect(screen.getByLabelText("Parameter 1 type")).toBeInTheDocument();
  });

  it("removes a parameter row", () => {
    renderDialog();
    fireEvent.click(screen.getByText("+ Add Parameter"));
    expect(screen.getByLabelText("Parameter 1 name")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Remove parameter 1"));
    expect(screen.queryByLabelText("Parameter 1 name")).not.toBeInTheDocument();
  });

  it("calls markAsTemplate on save in create mode", async () => {
    api.markAsTemplate.mockResolvedValue({ id: "tmpl-1" });
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    renderDialog({ onSuccess, onClose });

    fireEvent.click(screen.getByRole("button", { name: "Save as Template" }));

    await waitFor(() => {
      expect(api.markAsTemplate).toHaveBeenCalledWith("ws-1", "camp-1", expect.objectContaining({
        visibility: "workspace",
      }));
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("calls updateTemplate on save in edit mode", async () => {
    api.updateTemplate.mockResolvedValue({ id: "tmpl-1" });
    const onSuccess = vi.fn();
    const onClose = vi.fn();
    renderDialog({ mode: "edit", campaign: TEMPLATE_CAMPAIGN, onSuccess, onClose });

    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => {
      expect(api.updateTemplate).toHaveBeenCalledWith("tmpl-1", expect.objectContaining({
        category: "Product Launch",
        visibility: "workspace",
      }));
    });

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalled();
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("displays error on 403", async () => {
    api.markAsTemplate.mockRejectedValue(new api.ApiError(403, "Forbidden"));
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Save as Template" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/permission/i);
    });
  });

  it("calls onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    renderDialog({ onClose });

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows character count for description", () => {
    renderDialog();
    expect(screen.getByText("0/500")).toBeInTheDocument();
  });

  it("adds a tag when Enter is pressed in tag input", async () => {
    renderDialog();
    const tagInput = screen.getByLabelText("Tags");
    await userEvent.type(tagInput, "newtag{Enter}");
    expect(screen.getByText("newtag")).toBeInTheDocument();
  });

  it("removes a tag when remove button is clicked", async () => {
    renderDialog({ mode: "edit", campaign: TEMPLATE_CAMPAIGN });
    // Template campaign has tags ["summer", "promo"]
    expect(screen.getByText("summer")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Remove tag summer"));
    expect(screen.queryByText("summer")).not.toBeInTheDocument();
  });

  it("shows loading state during save", async () => {
    let resolveSave;
    api.markAsTemplate.mockImplementation(
      () => new Promise((resolve) => { resolveSave = resolve; })
    );
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Save as Template" }));

    await waitFor(() => {
      expect(screen.getByText("Saving…")).toBeInTheDocument();
    });

    resolveSave({ id: "tmpl-1" });
  });
});
