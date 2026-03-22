/**
 * Tests for Dashboard conditional rendering based on user role.
 *
 * The RBAC rules in Dashboard.jsx are:
 *  - "New Campaign" button/link: hidden for isViewer, shown for builders and admins
 *  - "Delete" button: shown only when isAdmin OR (not isViewer AND owner_id matches user.id)
 *  - Workspace sections: campaigns grouped by workspace_id
 *  - Orphaned section: visible only to admins
 */

import { render, screen, waitFor, fireEvent, act, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import Dashboard from '../pages/Dashboard';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';
import { ConfirmDialogProvider } from '../ConfirmDialogContext';
import { ToastProvider } from '../ToastContext';

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
  api.listCampaigns.mockResolvedValue({
    items: campaigns,
    pagination: {
      total_count: campaigns.length,
      offset: 0,
      limit: 50,
      returned_count: campaigns.length,
      has_more: false,
    },
  });
  api.deleteCampaign.mockResolvedValue(undefined);
  api.listWorkspaces.mockResolvedValue(workspaces);

  render(
    <MemoryRouter>
      <UserProvider>
        <WorkspaceProvider>
          <ConfirmDialogProvider>
            <ToastProvider>
              <Dashboard events={[]} />
            </ToastProvider>
          </ConfirmDialogProvider>
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
  status: 'strategy',
  owner_id: 'user-1',
  workspace_id: 'ws-owner',
  workspace_name: "Owner Workspace",
};

describe('Dashboard – New Campaign button', () => {
  it('is shown for campaign_builder role', async () => {
    // Provide a campaign so Dashboard renders the workspace header with the "+" create link
    await renderDashboard({ isViewer: false, isAdmin: false, userId: 'user-1' }, [campaignForOwner], [WS_OWNER]);
    await waitFor(() => screen.getByText('MyProduct'));
    expect(screen.getByLabelText(/create campaign in owner workspace/i)).toBeInTheDocument();
  });

  it('is shown for admin role', async () => {
    await renderDashboard({ isAdmin: true, isViewer: false, userId: 'user-1' }, [campaignForOwner], [WS_OWNER]);
    await waitFor(() => screen.getByText('MyProduct'));
    expect(screen.getByLabelText(/create campaign in owner workspace/i)).toBeInTheDocument();
  });

  it('is hidden for viewer role', async () => {
    // With empty campaigns: the empty-state CTA buttons should also be absent
    await renderDashboard({ isViewer: true, isAdmin: false });
    expect(screen.queryByText(/create campaign/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/browse workspaces/i)).not.toBeInTheDocument();
  });

  it('shows "Browse Workspaces" link for builder when no campaigns exist', async () => {
    await renderDashboard({ isViewer: false, isAdmin: false });
    expect(screen.getByRole('link', { name: /browse workspaces/i })).toBeInTheDocument();
  });

  it('shows "Create Campaign" link when builder has a personal workspace', async () => {
    const personalWs = { id: 'ws-personal', name: 'My Workspace', is_personal: true, role: 'creator' };
    await renderDashboard({ isViewer: false, isAdmin: false }, [], [personalWs]);
    const link = screen.getByRole('link', { name: /create campaign/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/workspaces/ws-personal/campaigns/new');
  });

  it('hides "Create Campaign" link when builder has no personal workspace', async () => {
    const teamWs = { id: 'ws-team', name: 'Team Workspace', is_personal: false, role: 'creator' };
    await renderDashboard({ isViewer: false, isAdmin: false }, [], [teamWs]);
    expect(screen.getByRole('link', { name: /browse workspaces/i })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /create campaign/i })).not.toBeInTheDocument();
  });

  it('hides empty state CTA buttons for viewer when no campaigns exist', async () => {
    await renderDashboard({ isViewer: true, isAdmin: false });
    expect(screen.queryByRole('link', { name: /browse workspaces/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /create campaign/i })).not.toBeInTheDocument();
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
  status: 'strategy',
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
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal, wsTeam]);
    await waitFor(() => screen.getByText('My Workspace'));
    expect(screen.getByText('My Workspace')).toBeInTheDocument();
    expect(screen.getByText('Team Workspace')).toBeInTheDocument();
  });

  it('places campaigns inside their workspace section', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('ProductA'));
    expect(screen.getByText('ProductA')).toBeInTheDocument();
  });

  it('shows the workspace role badge', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('Creator'));
    expect(screen.getByText('Creator')).toBeInTheDocument();
  });

  it('shows "+" create button for creator workspaces', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('My Workspace'));
    expect(screen.getByLabelText(/create campaign in my workspace/i)).toBeInTheDocument();
  });

  it('hides "+" create button for contributor workspaces', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'TeamProduct', goal: 'GoalB', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-team', workspace_name: 'Team Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsTeam]);
    await waitFor(() => screen.getByText('TeamProduct'));
    expect(screen.queryByLabelText(/create campaign in team workspace/i)).not.toBeInTheDocument();
  });

  it('shows orphaned section only to admins', async () => {
    const campaigns = [
      { id: 'c-orphan', product_or_service: 'OrphanProduct', goal: 'G', status: 'strategy', owner_id: 'user-1', workspace_id: null, workspace_name: null },
    ];
    // Non-admin should NOT see orphaned campaigns or the orphaned section
    await renderDashboard({ isAdmin: false, userId: 'user-1' }, campaigns, []);
    await waitFor(() => expect(api.listCampaigns).toHaveBeenCalled());
    expect(screen.queryByText('Orphaned Campaigns')).not.toBeInTheDocument();
    expect(screen.queryByText('OrphanProduct')).not.toBeInTheDocument();
  });

  it('shows orphaned section to admins with assign dropdown', async () => {
    const campaigns = [
      { id: 'c-orphan', product_or_service: 'OrphanProduct', goal: 'G', status: 'strategy', owner_id: 'user-1', workspace_id: null, workspace_name: null },
    ];
    await renderDashboard({ isAdmin: true, userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('Orphaned Campaigns'));
    expect(screen.getByText('Orphaned Campaigns')).toBeInTheDocument();
    expect(screen.getByLabelText(/assign to workspace/i)).toBeInTheDocument();
  });

  it('shows workspace count in stats bar', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'ProductA', goal: 'GoalA', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal, wsTeam]);
    await waitFor(() => screen.getByText('Workspaces'));
    expect(screen.getByText('Workspaces')).toBeInTheDocument();
  });

  it('shows status sub-groups within a workspace', async () => {
    const campaigns = [
      { id: 'c1', product_or_service: 'DraftProd', goal: 'G', status: 'strategy', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
      { id: 'c2', product_or_service: 'ApprovedProd', goal: 'G', status: 'approved', owner_id: 'user-1', workspace_id: 'ws-personal', workspace_name: 'My Workspace' },
    ];
    await renderDashboard({ userId: 'user-1' }, campaigns, [wsPersonal]);
    await waitFor(() => screen.getByText('DraftProd'));
    expect(screen.getAllByText('In Progress').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Approved').length).toBeGreaterThanOrEqual(1);
  });
});

// ---------------------------------------------------------------------------
// Tests: Filter tabs
// ---------------------------------------------------------------------------

const WS_FILTER = { id: 'ws-filter', name: 'Filter Workspace', is_personal: true, role: 'creator' };

const campaignDraft = {
  id: 'cf-1',
  product_or_service: 'DraftCampaign',
  goal: 'G',
  status: 'strategy',
  owner_id: 'user-1',
  workspace_id: 'ws-filter',
  workspace_name: 'Filter Workspace',
};
const campaignApproved = {
  id: 'cf-2',
  product_or_service: 'ApprovedCampaign',
  goal: 'G',
  status: 'approved',
  owner_id: 'user-1',
  workspace_id: 'ws-filter',
  workspace_name: 'Filter Workspace',
};
const campaignAwaiting = {
  id: 'cf-3',
  product_or_service: 'AwaitingCampaign',
  goal: 'G',
  status: 'content_approval',
  owner_id: 'user-1',
  workspace_id: 'ws-filter',
  workspace_name: 'Filter Workspace',
};
const campaignOtherOwner = {
  id: 'cf-4',
  product_or_service: 'OtherOwnerCampaign',
  goal: 'G',
  status: 'strategy',
  owner_id: 'user-other',
  workspace_id: 'ws-filter',
  workspace_name: 'Filter Workspace',
};
// A campaign in wizard-draft state (not yet launched)
const campaignWizardDraft = {
  id: 'cf-5',
  product_or_service: 'WizardDraftCampaign',
  goal: 'G',
  status: 'draft',
  wizard_step: 2,
  owner_id: 'user-1',
  workspace_id: 'ws-filter',
  workspace_name: 'Filter Workspace',
};

describe('Dashboard – Filter tabs', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders all 7 filter tabs including Drafts', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    expect(screen.getByRole('tab', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'My Campaigns' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Drafts' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Awaiting My Action' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'In Progress' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Needs Approval' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Manual Review' })).not.toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Approved' })).toBeInTheDocument();
  });

  it('defaults to "All" tab and shows all campaigns', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft, campaignApproved], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('DraftCampaign')).toBeInTheDocument();
    expect(screen.getByText('ApprovedCampaign')).toBeInTheDocument();
  });

  it('"Drafts" tab shows only draft-status campaigns', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignWizardDraft, campaignDraft, campaignApproved],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('WizardDraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Drafts' }));
    expect(screen.getByText('WizardDraftCampaign')).toBeInTheDocument();
    expect(screen.queryByText('DraftCampaign')).not.toBeInTheDocument();
    expect(screen.queryByText('ApprovedCampaign')).not.toBeInTheDocument();
  });

  it('"Drafts" tab shows empty state when no draft campaigns exist', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignApproved], [WS_FILTER]);
    await waitFor(() => screen.getByText('ApprovedCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Drafts' }));
    expect(screen.getByText(/no campaigns match this filter/i)).toBeInTheDocument();
  });

  it('"In Progress" tab shows only in-progress campaigns', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft, campaignApproved], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'In Progress' }));
    expect(screen.getByText('DraftCampaign')).toBeInTheDocument();
    expect(screen.queryByText('ApprovedCampaign')).not.toBeInTheDocument();
  });

  it('"In Progress" tab does NOT show wizard-draft campaigns', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignWizardDraft, campaignDraft],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('WizardDraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'In Progress' }));
    expect(screen.getByText('DraftCampaign')).toBeInTheDocument();
    expect(screen.queryByText('WizardDraftCampaign')).not.toBeInTheDocument();
  });

  it('"Approved" tab shows only approved campaigns', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft, campaignApproved], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    expect(screen.getByText('ApprovedCampaign')).toBeInTheDocument();
    expect(screen.queryByText('DraftCampaign')).not.toBeInTheDocument();
  });

  it('"Needs Approval" tab shows content_approval campaigns', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignDraft, campaignAwaiting],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Needs Approval' }));
    expect(screen.getByText('AwaitingCampaign')).toBeInTheDocument();
    expect(screen.queryByText('DraftCampaign')).not.toBeInTheDocument();
  });

  it('"My Campaigns" tab filters to current user campaigns only', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignDraft, campaignOtherOwner],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'My Campaigns' }));
    expect(screen.getByText('DraftCampaign')).toBeInTheDocument();
    expect(screen.queryByText('OtherOwnerCampaign')).not.toBeInTheDocument();
  });

  it('shows empty-state message when no campaigns match the filter', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    expect(screen.getByText(/no campaigns match this filter/i)).toBeInTheDocument();
  });

  it('empty-state "view all campaigns" resets to All tab', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    fireEvent.click(screen.getByText(/view all campaigns/i));
    expect(screen.getByText('DraftCampaign')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true');
  });

  it('persists active filter in localStorage', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft, campaignApproved], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    expect(localStorage.getItem('dashboard-active-filter')).toBe('approved');
  });

  it('clicking "Drafts" stat card activates Drafts tab', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignWizardDraft, campaignApproved],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('WizardDraftCampaign'));
    fireEvent.click(screen.getByRole('button', { name: /filter by drafts/i }));
    expect(screen.getByRole('tab', { name: 'Drafts' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('WizardDraftCampaign')).toBeInTheDocument();
    expect(screen.queryByText('ApprovedCampaign')).not.toBeInTheDocument();
  });

  it('clicking "In Progress" stat card activates In Progress tab', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft, campaignApproved], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('button', { name: /filter by in progress/i }));
    expect(screen.getByRole('tab', { name: 'In Progress' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.queryByText('ApprovedCampaign')).not.toBeInTheDocument();
  });

  it('clicking "Awaiting Approval" stat card activates Needs Approval tab', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignDraft, campaignAwaiting],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('DraftCampaign'));
    fireEvent.click(screen.getByRole('button', { name: /filter by awaiting approval/i }));
    expect(screen.getByRole('tab', { name: 'Needs Approval' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('AwaitingCampaign')).toBeInTheDocument();
    expect(screen.queryByText('DraftCampaign')).not.toBeInTheDocument();
  });

  it('clicking "Total" stat card sets filter to "all" and shows all campaigns', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignDraft, campaignApproved, campaignAwaiting],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('DraftCampaign'));
    // First narrow down to Approved
    fireEvent.click(screen.getByRole('button', { name: /filter by approved/i }));
    expect(screen.queryByText('DraftCampaign')).not.toBeInTheDocument();
    // Now click Total to see everything
    fireEvent.click(screen.getByRole('button', { name: /filter by total/i }));
    expect(screen.getByRole('tab', { name: 'All' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('DraftCampaign')).toBeInTheDocument();
    expect(screen.getByText('ApprovedCampaign')).toBeInTheDocument();
    expect(screen.getByText('AwaitingCampaign')).toBeInTheDocument();
  });

  it('"Total" stat card has active styling when "all" filter is selected', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignDraft], [WS_FILTER]);
    await waitFor(() => screen.getByText('DraftCampaign'));
    const totalBtn = screen.getByRole('button', { name: /filter by total/i });
    // Default filter is "all", so Total should be active
    expect(totalBtn.className).toContain('stat-card--active');
    // Switch to Drafts — Total should lose active state
    fireEvent.click(screen.getByRole('button', { name: /filter by drafts/i }));
    expect(totalBtn.className).not.toContain('stat-card--active');
    // Switch back to Total
    fireEvent.click(totalBtn);
    expect(totalBtn.className).toContain('stat-card--active');
  });

  it('status filters continue to work after toggling from Total', async () => {
    await renderDashboard(
      { userId: 'user-1' },
      [campaignDraft, campaignApproved],
      [WS_FILTER],
    );
    await waitFor(() => screen.getByText('DraftCampaign'));
    // Click Total first
    fireEvent.click(screen.getByRole('button', { name: /filter by total/i }));
    expect(screen.getByText('DraftCampaign')).toBeInTheDocument();
    expect(screen.getByText('ApprovedCampaign')).toBeInTheDocument();
    // Now click Approved stat card
    fireEvent.click(screen.getByRole('button', { name: /filter by approved/i }));
    expect(screen.getByText('ApprovedCampaign')).toBeInTheDocument();
    expect(screen.queryByText('DraftCampaign')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests: Search bar
// ---------------------------------------------------------------------------

const WS_SEARCH = { id: 'ws-search', name: 'Search Workspace', is_personal: true, role: 'creator' };

const campaignAlpha = {
  id: 'cs-1',
  product_or_service: 'AlphaProduct',
  goal: 'Grow revenue',
  status: 'strategy',
  owner_id: 'user-1',
  workspace_id: 'ws-search',
  workspace_name: 'Search Workspace',
};
const campaignBeta = {
  id: 'cs-2',
  product_or_service: 'BetaService',
  goal: 'Reduce churn',
  status: 'approved',
  owner_id: 'user-1',
  workspace_id: 'ws-search',
  workspace_name: 'Search Workspace',
};

/** Helper: fire a search change and advance fake timers to trigger the debounce. */
async function typeSearch(inputValue) {
  vi.useFakeTimers();
  fireEvent.change(screen.getByPlaceholderText('Search campaigns...'), {
    target: { value: inputValue },
  });
  await act(async () => vi.advanceTimersByTime(300));
  vi.useRealTimers();
}

describe('Dashboard – Search bar', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders the search bar with placeholder text', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));
    expect(screen.getByPlaceholderText('Search campaigns...')).toBeInTheDocument();
  });

  it('filters campaigns by product/service name (debounced)', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('alpha');

    expect(screen.queryByText('BetaService')).not.toBeInTheDocument();
    expect(screen.getByText('AlphaProduct')).toBeInTheDocument();
  });

  it('filters campaigns by goal', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('reduce churn');

    expect(screen.queryByText('AlphaProduct')).not.toBeInTheDocument();
    expect(screen.getByText('BetaService')).toBeInTheDocument();
  });

  it('filters campaigns by workspace name', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('search workspace');

    // Both campaigns are in "Search Workspace", both should remain
    expect(screen.getByText('AlphaProduct')).toBeInTheDocument();
    expect(screen.getByText('BetaService')).toBeInTheDocument();
  });

  it('filters campaigns by status (with underscores replaced)', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('approved');

    expect(screen.queryByText('AlphaProduct')).not.toBeInTheDocument();
    expect(screen.getByText('BetaService')).toBeInTheDocument();
  });

  it('is case-insensitive', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('ALPHAPRODUCT');

    expect(screen.queryByText('BetaService')).not.toBeInTheDocument();
    expect(screen.getByText('AlphaProduct')).toBeInTheDocument();
  });

  it('shows "Showing X of Y campaigns" result count when search is active', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('alpha');

    expect(screen.getByText(/showing 1 of 2 campaigns/i)).toBeInTheDocument();
  });

  it('does not show result count when search is empty', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));
    expect(screen.queryByText(/showing/i)).not.toBeInTheDocument();
  });

  it('shows empty-state message when search yields no results', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('nomatch-xyz');

    expect(screen.getByText(/no campaigns match your search/i)).toBeInTheDocument();
  });

  it('clear button resets search and shows all campaigns', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('alpha');
    expect(screen.queryByText('BetaService')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /clear search/i }));

    expect(screen.getByText('BetaService')).toBeInTheDocument();
    expect(screen.getByText('AlphaProduct')).toBeInTheDocument();
    expect(screen.queryByText(/showing/i)).not.toBeInTheDocument();
  });

  it('Escape key resets search', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('alpha');
    expect(screen.queryByText('BetaService')).not.toBeInTheDocument();

    const input = screen.getByPlaceholderText('Search campaigns...');
    fireEvent.keyDown(input, { key: 'Escape' });

    expect(screen.getByText('BetaService')).toBeInTheDocument();
    expect(screen.getByText('AlphaProduct')).toBeInTheDocument();
  });

  it('search composes with active filter tab', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    // Activate "Approved" tab — only campaignBeta is visible
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    await waitFor(() => expect(screen.queryByText('AlphaProduct')).not.toBeInTheDocument());

    // Searching for "alpha" while on Approved tab should yield no results
    await typeSearch('alpha');

    expect(screen.getByText(/no campaigns match your search/i)).toBeInTheDocument();
  });

  it('search query is preserved when switching filter tabs', async () => {
    await renderDashboard({ userId: 'user-1' }, [campaignAlpha, campaignBeta], [WS_SEARCH]);
    await waitFor(() => screen.getByText('AlphaProduct'));

    await typeSearch('alpha');
    expect(screen.queryByText('BetaService')).not.toBeInTheDocument();

    // Switch to a different tab and back — search query should be preserved
    fireEvent.click(screen.getByRole('tab', { name: 'Approved' }));
    fireEvent.click(screen.getByRole('tab', { name: 'All' }));

    // The search input should still contain "alpha"
    expect(screen.getByPlaceholderText('Search campaigns...')).toHaveValue('alpha');
  });
});

// ---------------------------------------------------------------------------
// Tests: Undo delete
// ---------------------------------------------------------------------------

const WS_UNDO = { id: 'ws-undo', name: 'Undo Workspace', is_personal: true, role: 'creator' };
const campaignToDelete = {
  id: 'camp-del',
  product_or_service: 'DeleteMe',
  goal: 'Delete goal',
  status: 'strategy',
  owner_id: 'user-1',
  workspace_id: 'ws-undo',
  workspace_name: 'Undo Workspace',
};

describe('Dashboard – undo delete', () => {
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('optimistically removes campaign and shows undo toast on delete confirmation', async () => {
    await renderDashboard({ isAdmin: false, userId: 'user-1' }, [campaignToDelete], [WS_UNDO]);
    await waitFor(() => screen.getByText('DeleteMe'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Confirm dialog should appear
    const dialog1 = await waitFor(() => screen.getByRole('dialog'));
    await act(async () => {
      fireEvent.click(within(dialog1).getByRole('button', { name: /^delete$/i }));
    });

    // Enable fake timers only after the confirm dialog is resolved
    vi.useFakeTimers();

    // Campaign should be removed immediately (optimistic)
    expect(screen.queryByText('DeleteMe')).not.toBeInTheDocument();
    // Undo toast should appear
    expect(screen.getByText('Campaign deleted')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /undo/i })).toBeInTheDocument();

    vi.clearAllTimers();
  });

  it('restores campaign and removes toast when Undo is clicked', async () => {
    api.listCampaigns.mockResolvedValue({
      items: [campaignToDelete],
      pagination: { total_count: 1, offset: 0, limit: 50, returned_count: 1, has_more: false },
    });
    await renderDashboard({ isAdmin: false, userId: 'user-1' }, [campaignToDelete], [WS_UNDO]);
    await waitFor(() => screen.getByText('DeleteMe'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Confirm via the modal
    const dialog2 = await waitFor(() => screen.getByRole('dialog'));
    await act(async () => {
      fireEvent.click(within(dialog2).getByRole('button', { name: /^delete$/i }));
    });

    vi.useFakeTimers();

    // Click the Undo button
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /undo/i }));
    });

    // Campaign should be restored
    expect(screen.getByText('DeleteMe')).toBeInTheDocument();
    // deleteCampaign API should NOT have been called
    expect(api.deleteCampaign).not.toHaveBeenCalled();

    vi.clearAllTimers();
  });

  it('calls deleteCampaign API after 5 seconds if Undo is not clicked', async () => {
    api.deleteCampaign.mockResolvedValue(undefined);
    await renderDashboard({ isAdmin: false, userId: 'user-1' }, [campaignToDelete], [WS_UNDO]);
    await waitFor(() => screen.getByText('DeleteMe'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Confirm via the modal — enable fake timers BEFORE clicking confirm
    // so that the setTimeout in handleDelete is captured by fake timers
    const dialog3 = await waitFor(() => screen.getByRole('dialog'));
    vi.useFakeTimers();
    await act(async () => {
      fireEvent.click(within(dialog3).getByRole('button', { name: /^delete$/i }));
    });

    // deleteCampaign should not be called yet
    expect(api.deleteCampaign).not.toHaveBeenCalled();

    // Advance past the 5-second undo window and drain all resulting async ops
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(api.deleteCampaign).toHaveBeenCalledWith('ws-undo', 'camp-del');

    // Ensure no timers leak into the next test
    vi.clearAllTimers();
    api.deleteCampaign.mockClear();
  });

  it('does not delete when confirm is cancelled', async () => {
    await renderDashboard({ isAdmin: false, userId: 'user-1' }, [campaignToDelete], [WS_UNDO]);
    await waitFor(() => screen.getByText('DeleteMe'));

    const deleteBtn = screen.getByRole('button', { name: /delete/i });
    await act(async () => {
      fireEvent.click(deleteBtn);
    });

    // Cancel via the modal
    await waitFor(() => screen.getByRole('dialog'));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    });

    // Campaign should still be visible
    expect(screen.getByText('DeleteMe')).toBeInTheDocument();
    expect(api.deleteCampaign).not.toHaveBeenCalled();
  });
});
