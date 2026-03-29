/**
 * Tests for CloneDialog component.
 */

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, it, expect, beforeEach } from "vitest";
import CloneDialog from "../components/CloneDialog";
import { WorkspaceProvider } from "../WorkspaceContext";
import { UserProvider } from "../UserContext";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock("../api", async () => {
  const actual = await vi.importActual("../api");
  return {
    ...actual,
    cloneCampaign: vi.fn(),
    getMe: vi.fn(),
    listWorkspaces: vi.fn(),
  };
});
import * as api from "../api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const SOURCE_WS = "ws-1";

const WORKSPACES = [
  { id: "ws-1", name: "Source Workspace", is_personal: false, role: "creator" },
  { id: "ws-2", name: "Target Workspace", is_personal: false, role: "contributor" },
];

const CAMPAIGN = {
  id: "camp-1",
  product_or_service: "Test Product",
  workspace_id: SOURCE_WS,
  is_template: false,
  template_parameters: null,
};

const TEMPLATE_CAMPAIGN = {
  ...CAMPAIGN,
  is_template: true,
  template_parameters: [
    { name: "Product Name", type: "text", default: "Acme Widget", description: "Name of the product" },
    { name: "Launch Date", type: "date", default: null, description: "When to launch" },
  ],
};

function renderDialog(props = {}) {
  api.getMe.mockResolvedValue({
    id: "user-1",
    email: "test@example.com",
    display_name: "Test User",
    roles: ["campaign_builder"],
    is_admin: false,
    can_build: true,
    is_viewer: false,
  });
  api.listWorkspaces.mockResolvedValue(WORKSPACES);

  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    campaign: CAMPAIGN,
    sourceWorkspaceId: SOURCE_WS,
    ...props,
  };

  return render(
    <MemoryRouter>
      <UserProvider>
        <WorkspaceProvider>
          <CloneDialog {...defaultProps} />
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CloneDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders nothing when isOpen is false", () => {
    renderDialog({ isOpen: false });
    expect(screen.queryByText("Clone Campaign")).not.toBeInTheDocument();
  });

  it("renders the dialog title when open", () => {
    renderDialog();
    expect(screen.getByText("Clone Campaign")).toBeInTheDocument();
  });

  it("shows the campaign name in the subtitle", () => {
    renderDialog();
    expect(screen.getByText(/Test Product/)).toBeInTheDocument();
  });

  it("renders all four depth options", () => {
    renderDialog();
    expect(screen.getByText("Brief Only")).toBeInTheDocument();
    expect(screen.getByText("Brief + Strategy")).toBeInTheDocument();
    expect(screen.getByText("Brief + Strategy + Content")).toBeInTheDocument();
    expect(screen.getByText("Full Campaign")).toBeInTheDocument();
  });

  it("renders workspace dropdown", async () => {
    renderDialog();
    await waitFor(() => {
      const select = screen.getByLabelText("Target Workspace");
      expect(select).toBeInTheDocument();
    });
  });

  it("does not show template parameters for non-template campaigns", () => {
    renderDialog();
    expect(screen.queryByText("Template Parameters")).not.toBeInTheDocument();
  });

  it("shows template parameters for template campaigns", () => {
    renderDialog({ campaign: TEMPLATE_CAMPAIGN });
    expect(screen.getByText("Template Parameters")).toBeInTheDocument();
    expect(screen.getByLabelText(/Product Name/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Launch Date/)).toBeInTheDocument();
  });

  it("calls cloneCampaign and navigates on success", async () => {
    api.cloneCampaign.mockResolvedValue({ id: "new-camp-1" });
    const onClose = vi.fn();
    renderDialog({ onClose });

    const cloneBtn = screen.getByRole("button", { name: "Clone" });
    fireEvent.click(cloneBtn);

    await waitFor(() => {
      expect(api.cloneCampaign).toHaveBeenCalledWith(SOURCE_WS, "camp-1", expect.objectContaining({
        depth: "brief",
      }));
    });

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/workspaces/ws-1/campaigns/new-camp-1/edit");
    });

    expect(onClose).toHaveBeenCalled();
  });

  it("displays error on 403", async () => {
    api.cloneCampaign.mockRejectedValue(new api.ApiError(403, "Forbidden"));
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Clone" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/permission/i);
    });
  });

  it("displays error on 409", async () => {
    api.cloneCampaign.mockRejectedValue(new api.ApiError(409, "Conflict"));
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Clone" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/conflict/i);
    });
  });

  it("calls onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    renderDialog({ onClose });

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("shows loading state during clone", async () => {
    let resolveClone;
    api.cloneCampaign.mockImplementation(
      () => new Promise((resolve) => { resolveClone = resolve; })
    );
    renderDialog();

    fireEvent.click(screen.getByRole("button", { name: "Clone" }));

    await waitFor(() => {
      expect(screen.getByText("Cloning…")).toBeInTheDocument();
    });

    resolveClone({ id: "new-camp-1" });
  });
});
