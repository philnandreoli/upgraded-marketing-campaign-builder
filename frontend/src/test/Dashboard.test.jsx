/**
 * Tests for Dashboard conditional rendering based on user role.
 *
 * The RBAC rules in Dashboard.jsx are:
 *  - "New Campaign" button/link: hidden for isViewer, shown for builders and admins
 *  - "Delete" button: shown only when isAdmin OR (not isViewer AND owner_id matches user.id)
 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import Dashboard from '../pages/Dashboard';
import { UserProvider } from '../UserContext';

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
    role: isAdmin ? 'admin' : isViewer ? 'viewer' : 'campaign_builder',
    is_admin: isAdmin,
    can_build: !isViewer,
    is_viewer: isViewer,
  };
}

/**
 * Render Dashboard with UserProvider (which calls getMe) + MemoryRouter.
 */
async function renderDashboard({ isViewer = false, isAdmin = false, userId = 'user-1' } = {}, campaigns = []) {
  api.getMe.mockResolvedValue(makeMeResponse({ isViewer, isAdmin, userId }));
  api.listCampaigns.mockResolvedValue(campaigns);
  api.deleteCampaign.mockResolvedValue(undefined);

  render(
    <MemoryRouter>
      <UserProvider>
        <Dashboard events={[]} />
      </UserProvider>
    </MemoryRouter>,
  );

  // Wait for the loading spinner to disappear (getMe + listCampaigns resolved)
  await waitFor(() => expect(screen.queryByText(/loading/i)).not.toBeInTheDocument());
}

// ---------------------------------------------------------------------------
// Tests: "New Campaign" button visibility
// ---------------------------------------------------------------------------

const campaignForOwner = {
  id: 'camp-new',
  product_or_service: 'MyProduct',
  goal: 'Grow',
  status: 'draft',
  owner_id: 'user-1',
};

describe('Dashboard – New Campaign button', () => {
  it('is shown for campaign_builder role', async () => {
    // Provide a campaign so Dashboard renders the header with the "New Campaign" link
    await renderDashboard({ isViewer: false, isAdmin: false, userId: 'user-1' }, [campaignForOwner]);
    await waitFor(() => screen.getByText('MyProduct'));
    expect(screen.getByText(/\+ new campaign/i)).toBeInTheDocument();
  });

  it('is shown for admin role', async () => {
    await renderDashboard({ isAdmin: true, isViewer: false, userId: 'user-1' }, [campaignForOwner]);
    await waitFor(() => screen.getByText('MyProduct'));
    expect(screen.getByText(/\+ new campaign/i)).toBeInTheDocument();
  });

  it('is hidden for viewer role', async () => {
    // With empty campaigns: the empty-state "Create your first campaign" link should also be absent
    await renderDashboard({ isViewer: true, isAdmin: false });
    expect(screen.queryByText(/new campaign/i)).not.toBeInTheDocument();
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

const sampleCampaign = {
  id: 'camp-1',
  product_or_service: 'TestProduct',
  goal: 'Test goal',
  status: 'draft',
  owner_id: OWNER_ID,
};

describe('Dashboard – Delete button', () => {
  it('is shown for the campaign owner (campaign_builder)', async () => {
    await renderDashboard({ isViewer: false, isAdmin: false, userId: OWNER_ID }, [sampleCampaign]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });

  it('is shown for admin regardless of ownership', async () => {
    await renderDashboard({ isAdmin: true, isViewer: false, userId: OTHER_USER_ID }, [sampleCampaign]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
  });

  it('is hidden for a viewer (even if they are the owner)', async () => {
    await renderDashboard({ isViewer: true, isAdmin: false, userId: OWNER_ID }, [sampleCampaign]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });

  it('is hidden for a builder who does not own the campaign', async () => {
    await renderDashboard({ isViewer: false, isAdmin: false, userId: OTHER_USER_ID }, [sampleCampaign]);
    await waitFor(() => screen.getByText('TestProduct'));
    expect(screen.queryByRole('button', { name: /delete/i })).not.toBeInTheDocument();
  });
});
