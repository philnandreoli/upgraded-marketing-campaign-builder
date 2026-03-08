/**
 * Tests for Dashboard conditional rendering based on user role.
 *
 * The RBAC rules in Dashboard.jsx are:
 *  - "New Campaign" button/link: hidden for isViewer, shown for builders and admins
 *  - "Delete" button: shown only when isAdmin OR (not isViewer AND owner_id matches user.id)
 *  - Workspace sections: campaigns grouped by workspace_id
 *  - Orphaned section: visible only to admins
 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import Dashboard from '../pages/Dashboard';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';

// ---------------------------------------------------------------------------
// Module-level mocks
// ---------------------------------------------------------------------------

// api.js is mocked at the module level; individual tests configure return values
vi.mock('../api');

import * as api from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Build a /me response that makes UserProvider emit the desired role flags.
 */
function makeMeResponse({ isViewer = false, isAdmin = false, userId = 'user-1' } = {}) {
  return {
    id: userId,
    email: 'test@example.com',
    display_name: 'Test User',
    roles: isAdmin ? ['admin'] : isViewer ? ['viewer'] : ['campaign_builder'],
    is_admin: isAdmin,
    can_build: !isViewer,
    is_viewer: isViewer,
  };
}

/**
 * Render Dashboard with UserProvider + WorkspaceProvider (both call API) + MemoryRouter.
 */
async function renderDashboard(
  { isViewer = false, isAdmin = false, userId = 'user-1' } = {},
  campaigns = [],
  workspaces = [],
) {
  api.getMe.mockResolvedValue(makeMeResponse({ isViewer, isAdmin, userId }));
  api.listCampaigns.mockResolvedValue(campaigns);
  api.deleteCampaign.mockResolvedValue(undefined);
  api.listWorkspaces.mockResolvedValue(workspaces);

  render(
    <MemoryRouter>
      <UserProvider>
        <WorkspaceProvider>
          <Dashboard events={[]} />
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>,
  );

  // Wait for the loading spinner to disappear (getMe + listCampaigns resolved)
  await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
}

// ---------------------------------------------------------------------------
// Tests: "New Campaign" button visibility
// ---------------------------------------------------------------------------

const WS_OWNER = { id: 'ws-owner', name: "Owner Workspace", is_personal: true, role: 'creator' };

const campaignForOwner = {
  id: 'camp-new',
  product_or_service: 'MyProduct',
  goal: 'Grow',
  status: 'draft',
  owner_id: 'user-1',
  workspace_id: 'ws-owner',
  workspace_name: "Owner Workspace",
};

describe('Dashboard – New Campaign button', () => {
  it('is shown for campaign_builder role', async () => {
    // Provide a campaign so Dashboard renders the header with the "Create Campaign" link
    await renderDashboard({ isViewer: false, isAdmin: false, userId: 'user-1' }, [campaignForOwner], [WS_OWNER]);
    await waitFor(() => screen.getByText('MyProduct'));
    expect(screen.getByText(/\+ create campaign/i)).toBeInTheDocument();
  });

  it('is shown for admin role', async () => {
    await renderDashboard({ isAdmin: true, isViewer: false, userId: 'user-1' }, [campaignForOwner], [WS_OWNER]);
    await waitFor(() => screen.getByText('MyProduct'));
    expect(screen.getByText(/\+ create campaign/i)).toBeInTheDocument();
  });

  it('is hidden for viewer role', async () => {
    // With empty campaigns: the empty-state "Create your first campaign" link should also be absent
    await renderDashboard({ isViewer: true, isAdmin: false });
    expect(screen.queryByText(/create campaign/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/create your first campaign/i)).not.toBeInTheDocument();
  });

  it('shows "Create your first campaign" link for builder when no campaigns exist', async () => {
    await renderDashboard({ isViewer: false, isAdmin: false });
    expect(screen.getByText(/create your first campaign/i)).toBeInTheDocument();
  });

  it('hides "Create your first campaign" link for viewer when no campaigns exist', async () => {
    await renderDashboard({ isViewer: true, isAdmin: false });
    expect(screen.queryByText(/create your first campaign/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: "Delete" button visibility on campaign cards
// ---------------------------------------------------------------------------

const OWNER_ID = 'user-owner';
const OTHER_USER_ID = 'user-other';
const WS_SAMPLE = { id: 'ws-sample', name: 'Sample Workspace', is_personal: true, role: 'creator' };

const sampleCampaign = {
  id: 'camp-1',
  product_or_service: 'TestProduct',
  goal: 'Test goal',
  status: 'draft',
  owner_id: OWNER_ID,
  workspace_id: 'ws-sample',
  workspace_name: 'Sample Workspace',
};

describe('Dashboard – Delete button', () => {
  it('is shown for the campaign owner (campaign_builder)', async () => {
    await renderDashboard({ isViewer: false, isAdmin: false, userId: OWNER_ID }, [sampleCampaign], [WS_SAMPLE]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });

  it('is shown for admin regardless of ownership', async () => {
    await renderDashboard({ isAdmin: true, isViewer: false, userId: OTHER_USER_ID }, [sampleCampaign], [WS_SAMPLE]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });

  it('is hidden for a viewer (even if they are the owner)', async () => {
    await renderDashboard({ isViewer: true, isAdmin: false, userId: OWNER_ID }, [sampleCampaign], [WS_SAMPLE]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('is hidden for a builder who does not own the campaign', async () => {
    await renderDashboard({ isViewer: false, isAdmin: false, userId: OTHER_USER_ID }, [sampleCampaign], [WS_SAMPLE]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Workspace grouping
// ---------------------------------------------------------------------------

const wsPersonal = { id: 'ws-personal', name: "My Workspace", is_personal: true, role: 'creator' };
const wsTeam = { id: 'ws-team', name: 'Team Workspace', is_personal: false, role: 'contributor' };

describe('Dashboard – Workspace sections', () => {
  it('renders a section for each workspace', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal, wsTeam]);
    await waitFor(() => screen.getByText('My Workspace'));
    expect(screen.getByText('My Workspace')).toBeInTheDocument();
    expect(screen.getByText('Team Workspace')).toBeInTheDocument();
  });

  it('places campaigns inside their workspace section', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('ProductA'));
    expect(screen.getByText('ProductA')).toBeInTheDocument();
  });

  it('shows the workspace role badge', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('Creator'));
    expect(screen.getByText('Creator')).toBeInTheDocument();
  });

  it('shows "+" create button for creator workspaces', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('My Workspace'));
    expect(screen.getByLabelText(/create campaign in my workspace/i)).toBeInTheDocument();
  });

  it('hides "+" create button for contributor workspaces', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'TeamProduct', goal: 'GoalB', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-team', workspace_name: 'Team Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsTeam]);
    await waitFor(() => screen.getByText('TeamProduct'));
    expect(screen.queryByLabelText(/create campaign in team workspace/i)).not.toBeInTheDocument();
  });

  it('shows orphaned section only to admins', async () => {
    const campaigns = [
      { id: 'c-orphan', product_or_service: 'OrphanProduct', goal: 'G', status: 'draft', owner_id: 'user-1', workspace_id: null, workspace_name: null },
    ];
    // Non-admin should NOT see orphaned campaigns or the orphaned section
    await renderDashboard({ isAdmin: false, userId: 'user-1' }, campaigns, []);
    await waitFor(() => expect(api.listCampaigns).toHaveBeenCalled());
    expect(screen.queryByText('Orphaned Campaigns')).not.toBeInTheDocument();
    expect(screen.queryByText('OrphanProduct')).not.toBeInTheDocument();
  });

  it('shows orphaned section to admins with assign dropdown', async () => {
    const campaigns = [
      { id: 'c-orphan', product_or_service: 'OrphanProduct', goal: 'G', status: 'draft', owner_id: 'user-1', workspace_id: null, workspace_name: null },
    ];
    await renderDashboard({ isAdmin: true, userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('Orphaned Campaigns'));
    expect(screen.getByText('Orphaned Campaigns')).toBeInTheDocument();
    expect(screen.getByLabelText(/assign to workspace/i)).toBeInTheDocument();
  });

  it('shows workspace count in stats bar', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal, wsTeam]);
    await waitFor(() => screen.getByText('Workspaces'));
    expect(screen.getByText('Workspaces')).toBeInTheDocument();
  });

  it('shows status sub-groups within a workspace', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'DraftProd', goal: 'G', status: 'draft', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
      { id: 'c2', product_or_service: 'ApprovedProd', goal: 'G', status: 'approved', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('DraftProd'));
    expect(screen.getAllByText('In Progress').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Approved').length).toBeGreaterThanOrEqual(1);
  });
});
