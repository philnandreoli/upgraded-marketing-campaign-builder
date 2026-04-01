import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Admin from "../pages/Admin.jsx";

const confirmMock = vi.fn();

vi.mock("../ConfirmDialogContext", () => ({
  useConfirm: () => confirmMock,
}));

vi.mock("../api", () => ({
  listUsers: vi.fn(),
  updateUserRoles: vi.fn(),
  deactivateUser: vi.fn(),
  reactivateUser: vi.fn(),
  listAllCampaigns: vi.fn(),
  listAdminWorkspaces: vi.fn(),
  searchEntraUsers: vi.fn(),
  provisionUser: vi.fn(),
  getUserWorkspaces: vi.fn(),
  getAdminTemplateAnalytics: vi.fn(),
  deactivateWorkspaceAdmin: vi.fn(),
  reactivateWorkspaceAdmin: vi.fn(),
}));

import * as api from "../api";

function setupApi({ workspaces }) {
  api.listUsers.mockResolvedValue({ users: [], totalCount: 0 });
  api.listAllCampaigns.mockResolvedValue({ campaigns: [], totalCount: 0 });
  api.getAdminTemplateAnalytics.mockResolvedValue({
    total_templates: 0,
    total_clones: 0,
  });
  api.listAdminWorkspaces.mockResolvedValue(workspaces);
  api.deactivateWorkspaceAdmin.mockResolvedValue({});
  api.reactivateWorkspaceAdmin.mockResolvedValue({});
}

function renderAdmin() {
  return render(
    <MemoryRouter>
      <Admin />
    </MemoryRouter>,
  );
}

function getWorkspaceRowByName(name) {
  const nameCell = screen.getByText(name);
  return nameCell.closest("tr");
}

beforeEach(() => {
  vi.clearAllMocks();
  confirmMock.mockResolvedValue(true);
});

describe("Admin workspaces tab", () => {
  it("deactivates an active team workspace", async () => {
    setupApi({
      workspaces: [
        {
          id: "ws-team",
          name: "Team Alpha",
          owner_id: "u1",
          owner_display_name: "Owner",
          member_count: 4,
          campaign_count: 2,
          is_personal: false,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    });

    renderAdmin();

    await waitFor(() => expect(api.listAdminWorkspaces).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Workspaces" }));

    const row = await waitFor(() => getWorkspaceRowByName("Team Alpha"));
    const deactivateBtn = within(row).getByRole("button", { name: "Deactivate" });
    fireEvent.click(deactivateBtn);

    await waitFor(() => expect(api.deactivateWorkspaceAdmin).toHaveBeenCalledWith("ws-team"));
    await waitFor(() => expect(within(row).getByText("Inactive")).toBeInTheDocument());
    expect(within(row).getByRole("button", { name: "Reactivate" })).toBeInTheDocument();
  });

  it("reactivates an inactive team workspace", async () => {
    setupApi({
      workspaces: [
        {
          id: "ws-team",
          name: "Team Beta",
          owner_id: "u2",
          owner_display_name: "Owner 2",
          member_count: 3,
          campaign_count: 1,
          is_personal: false,
          is_active: false,
          created_at: "2026-01-02T00:00:00Z",
        },
      ],
    });

    renderAdmin();

    await waitFor(() => expect(api.listAdminWorkspaces).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Workspaces" }));

    const row = await waitFor(() => getWorkspaceRowByName("Team Beta"));
    const reactivateBtn = within(row).getByRole("button", { name: "Reactivate" });
    fireEvent.click(reactivateBtn);

    await waitFor(() => expect(api.reactivateWorkspaceAdmin).toHaveBeenCalledWith("ws-team"));
    await waitFor(() => expect(within(row).getByText("Active")).toBeInTheDocument());
    expect(within(row).getByRole("button", { name: "Deactivate" })).toBeInTheDocument();
  });

  it("does not show action button for personal workspaces", async () => {
    setupApi({
      workspaces: [
        {
          id: "ws-personal",
          name: "My Personal",
          owner_id: "u3",
          owner_display_name: "Owner 3",
          member_count: 1,
          campaign_count: 0,
          is_personal: true,
          is_active: true,
          created_at: "2026-01-03T00:00:00Z",
        },
      ],
    });

    renderAdmin();

    await waitFor(() => expect(api.listAdminWorkspaces).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("button", { name: "Workspaces" }));

    const row = await waitFor(() => getWorkspaceRowByName("My Personal"));
    expect(within(row).getByText("Not allowed")).toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Deactivate" })).not.toBeInTheDocument();
    expect(within(row).queryByRole("button", { name: "Reactivate" })).not.toBeInTheDocument();
  });
});
