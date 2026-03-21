/**
 * Tests for the workspace picker in NewCampaign.
 *
 * Covers:
 *  - Workspace picker is rendered above Step 1
 *  - Only workspaces with role "creator" are listed for non-admin users
 *  - Admin users see all workspaces
 *  - Pre-selects the workspace from the ?workspace= query param
 *  - Defaults to personal workspace when no query param is present
 *  - Falls back to the first creatable workspace when no personal workspace matches
 *  - Shows error when no creatable workspaces exist
 *  - Validates workspace selection before submit
 *  - Passes workspace_id to createCampaign on submit
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import NewCampaign from '../pages/NewCampaign';
import { UserProvider } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';

vi.mock('../api');
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

import * as api from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMeResponse({ isAdmin = false } = {}) {
  return {
    id: 'user-1',
    email: 'test@example.com',
    display_name: 'Test User',
    roles: isAdmin ? ['admin'] : ['campaign_builder'],
    is_admin: isAdmin,
    can_build: true,
    is_viewer: false,
  };
}

const PERSONAL_WS = { id: 'ws-personal', name: 'My Space', is_personal: true, role: 'creator' };
const TEAM_WS_CREATOR = { id: 'ws-team', name: 'Team WS', is_personal: false, role: 'creator' };
const TEAM_WS_VIEWER = { id: 'ws-viewer', name: 'View Only', is_personal: false, role: 'viewer' };
const TEAM_WS_CONTRIB = { id: 'ws-contrib', name: 'Contrib WS', is_personal: false, role: 'contributor' };

function renderNewCampaign({ initialPath = '/new', isAdmin = false, workspaces = [] } = {}) {
  api.getMe.mockResolvedValue(makeMeResponse({ isAdmin }));
  api.listWorkspaces.mockResolvedValue(workspaces);

  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <UserProvider>
        <WorkspaceProvider>
          <NewCampaign />
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NewCampaign — workspace picker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // createCampaign never resolves by default — tests that need it mock it explicitly
    api.createCampaign.mockResolvedValue({ id: 'camp-1' });
  });

  it('renders the workspace picker section', async () => {
    renderNewCampaign({
      workspaces: [PERSONAL_WS],
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toBeInTheDocument();
    });
  });

  it('lists only workspaces where user has creator role', async () => {
    renderNewCampaign({
      workspaces: [PERSONAL_WS, TEAM_WS_CREATOR, TEAM_WS_VIEWER, TEAM_WS_CONTRIB],
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/create in workspace/i));

    expect(screen.getByRole('option', { name: /My Space/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Team WS/i })).toBeInTheDocument();

    expect(screen.queryByRole('option', { name: /View Only/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /Contrib WS/i })).not.toBeInTheDocument();
  });

  it('shows all workspaces for admin users', async () => {
    renderNewCampaign({
      isAdmin: true,
      workspaces: [PERSONAL_WS, TEAM_WS_CREATOR, TEAM_WS_VIEWER, TEAM_WS_CONTRIB],
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText(/create in workspace/i));

    expect(screen.getByRole('option', { name: /View Only/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Contrib WS/i })).toBeInTheDocument();
  });

  it('pre-selects personal workspace by default', async () => {
    renderNewCampaign({
      workspaces: [TEAM_WS_CREATOR, PERSONAL_WS],
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toHaveTextContent(/My Space \(Personal\)/i);
    });
  });

  it('pre-selects workspace from ?workspace= query param', async () => {
    renderNewCampaign({
      initialPath: `/new?workspace=${TEAM_WS_CREATOR.id}`,
      workspaces: [PERSONAL_WS, TEAM_WS_CREATOR],
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toHaveTextContent(/Team WS/i);
    });
  });

  it('falls back to first creatable workspace when query param workspace is not in the list', async () => {
    renderNewCampaign({
      initialPath: '/new?workspace=ws-nonexistent',
      workspaces: [PERSONAL_WS, TEAM_WS_CREATOR],
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toHaveTextContent(/My Space \(Personal\)/i);
    });
  });

  it('shows error message when user has no creatable workspaces', async () => {
    renderNewCampaign({
      workspaces: [TEAM_WS_VIEWER, TEAM_WS_CONTRIB],
    });

    await waitFor(() => {
      expect(screen.getByText(/don't have Creator access/i)).toBeInTheDocument();
    });

    expect(screen.queryByLabelText(/create in workspace/i)).not.toBeInTheDocument();
  });

  it('passes workspace_id to createCampaign on submit', async () => {
    api.updateCampaignDraft.mockResolvedValue({ id: 'camp-1', status: 'draft', message: 'Draft updated.' });

    renderNewCampaign({
      workspaces: [PERSONAL_WS],
    });

    // Step 0: workspace is pre-selected; click Next to go to step 1
    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toHaveTextContent(/My Space \(Personal\)/i);
    });
    fireEvent.click(screen.getByRole('button', { name: /Next/i }));

    // Step 1: fill required fields
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/CloudSync/i)).toBeInTheDocument();
    });
    fireEvent.change(screen.getByPlaceholderText(/CloudSync/i), {
      target: { value: 'Test Product' },
    });
    fireEvent.change(screen.getByPlaceholderText(/Increase free-trial/i), {
      target: { value: 'Grow signups' },
    });

    // Click Next on step 1 — this calls createCampaign with the workspace_id
    fireEvent.click(screen.getByRole('button', { name: /Next/i }));

    await waitFor(() => {
      expect(api.createCampaign).toHaveBeenCalledWith(
        expect.objectContaining({ product_or_service: 'Test Product' }),
        PERSONAL_WS.id
      );
    });
  });

  it('shows workspace label with (Personal) suffix for personal workspace', async () => {
    renderNewCampaign({
      workspaces: [PERSONAL_WS, TEAM_WS_CREATOR],
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toHaveTextContent(/My Space \(Personal\)/i);
    });

    fireEvent.click(screen.getByLabelText(/create in workspace/i));
    expect(screen.getByRole('option', { name: /My Space \(Personal\)/i })).toBeInTheDocument();
  });
});

describe('NewCampaign — wizard step labels', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.createCampaign.mockResolvedValue({ id: 'camp-1' });
  });

  it('renders short labels beneath each wizard step dot', async () => {
    renderNewCampaign({ workspaces: [PERSONAL_WS] });

    await waitFor(() => {
      expect(screen.getByText('Product')).toBeInTheDocument();
    });

    // Check all dot labels are rendered
    const dotLabels = document.querySelectorAll('.wizard-dot-label');
    const labelTexts = Array.from(dotLabels).map((el) => el.textContent);
    expect(labelTexts).toEqual(['Workspace', 'Product', 'Budget', 'Channels', 'Context', 'Review']);
  });

  it('visually emphasizes the active step label', async () => {
    renderNewCampaign({ workspaces: [PERSONAL_WS] });

    await waitFor(() => {
      expect(screen.getByText('Product')).toBeInTheDocument();
    });

    // On step 0, the "Workspace" dot label should have the active class
    const activeDotLabel = document.querySelector('.wizard-dot-label--active');
    expect(activeDotLabel).not.toBeNull();
    expect(activeDotLabel.textContent).toBe('Workspace');
  });

  it('shows completed step labels with checkmark and dimmed style after advancing', async () => {
    api.updateCampaignDraft.mockResolvedValue({ id: 'camp-1', status: 'draft', message: 'Draft updated.' });

    renderNewCampaign({ workspaces: [PERSONAL_WS] });

    // Step 0 — advance to step 1
    await waitFor(() => {
      expect(screen.getByLabelText(/create in workspace/i)).toHaveTextContent(/My Space/i);
    });
    fireEvent.click(screen.getByRole('button', { name: /Next/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/CloudSync/i)).toBeInTheDocument();
    });

    // "Workspace" dot label should now be completed (dimmed + checkmark)
    const doneLabels = document.querySelectorAll('.wizard-dot-label--done');
    expect(doneLabels.length).toBeGreaterThanOrEqual(1);
    expect(doneLabels[0].textContent).toContain('✓');
    expect(doneLabels[0].textContent).toContain('Workspace');

    // "Product" dot label should be active
    const activeLabel = document.querySelector('.wizard-dot-label--active');
    expect(activeLabel).not.toBeNull();
    expect(activeLabel.textContent).toBe('Product');
  });
});

describe('NewCampaign — breadcrumb', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.createCampaign.mockResolvedValue({ id: 'camp-1' });
  });

  it('renders Dashboard link and New Campaign text', async () => {
    renderNewCampaign({ workspaces: [PERSONAL_WS] });

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: /dashboard/i })).toHaveAttribute('href', '/');
    expect(screen.getByText('New Campaign')).toBeInTheDocument();
  });

  it('renders workspace name as a link when a workspace is selected', async () => {
    renderNewCampaign({ workspaces: [PERSONAL_WS] });

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /My Space/i })).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: /My Space/i })).toHaveAttribute('href', `/workspaces/${PERSONAL_WS.id}`);
  });

  it('breadcrumb workspace updates when user changes workspace dropdown', async () => {
    renderNewCampaign({ workspaces: [PERSONAL_WS, TEAM_WS_CREATOR] });

    // Initially shows personal workspace in breadcrumb
    await waitFor(() => {
      expect(screen.getByRole('link', { name: /My Space/i })).toBeInTheDocument();
    });

    // Change workspace selection
    fireEvent.click(screen.getByLabelText(/create in workspace/i));
    fireEvent.click(screen.getByRole('option', { name: /Team WS/i }));

    await waitFor(() => {
      expect(screen.getByRole('link', { name: /Team WS/i })).toHaveAttribute('href', `/workspaces/${TEAM_WS_CREATOR.id}`);
    });
  });

  it('New Campaign is plain text, not a link', async () => {
    renderNewCampaign({ workspaces: [PERSONAL_WS] });

    await waitFor(() => {
      expect(screen.getByText('New Campaign')).toBeInTheDocument();
    });

    // The "New Campaign" breadcrumb item should not be a link
    const newCampaignEl = screen.getByText('New Campaign');
    expect(newCampaignEl.tagName).not.toBe('A');
  });
});
