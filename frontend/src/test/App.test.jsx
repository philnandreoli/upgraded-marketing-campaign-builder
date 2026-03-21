/**
 * Tests for App routing — workspace routes and navigation.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { UserProvider, useUser } from '../UserContext';
import { WorkspaceProvider } from '../WorkspaceContext';

vi.mock('../api');
vi.mock('@azure/msal-react', () => ({
  useMsal: () => ({ instance: {}, accounts: [] }),
  AuthenticatedTemplate: ({ children }) => children,
  UnauthenticatedTemplate: () => null,
}));

import * as api from '../api';

function makeMeResponse({ isViewer = false, isAdmin = false } = {}) {
  return {
    id: 'user-1',
    email: 'test@example.com',
    display_name: 'Test User',
    roles: isAdmin ? ['admin'] : isViewer ? ['viewer'] : ['campaign_builder'],
    is_admin: isAdmin,
    can_build: !isViewer,
    is_viewer: isViewer,
  };
}

/** Minimal RequireBuilder guard matching App.jsx */
function RequireBuilder({ children }) {
  const { isViewer } = useUser();
  return isViewer ? <Navigate to="/" replace /> : children;
}

function ProtectedSettings() {
  return (
    <RequireBuilder>
      <div>Settings Page</div>
    </RequireBuilder>
  );
}

async function renderWithRoute(path, { isViewer = false, isAdmin = false } = {}) {
  api.getMe.mockResolvedValue(makeMeResponse({ isViewer, isAdmin }));
  api.listWorkspaces.mockResolvedValue([]);

  render(
    <MemoryRouter initialEntries={[path]}>
      <UserProvider>
        <WorkspaceProvider>
          <Routes>
            <Route path="/" element={<div>Dashboard</div>} />
            <Route path="/workspaces" element={<div>Workspaces List</div>} />
            <Route path="/workspaces/:id" element={<div>Workspace Detail</div>} />
            <Route path="/workspaces/:id/settings" element={<ProtectedSettings />} />
            <Route path="/settings" element={<div>User Settings Page</div>} />
          </Routes>
        </WorkspaceProvider>
      </UserProvider>
    </MemoryRouter>,
  );

  await waitFor(() => expect(api.getMe).toHaveBeenCalled());
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('App – workspace routes', () => {
  it('renders WorkspaceList at /workspaces', async () => {
    await renderWithRoute('/workspaces');
    expect(screen.getByText('Workspaces List')).toBeInTheDocument();
  });

  it('renders WorkspaceDetail at /workspaces/:id', async () => {
    await renderWithRoute('/workspaces/ws-1');
    expect(screen.getByText('Workspace Detail')).toBeInTheDocument();
  });

  it('renders WorkspaceSettings at /workspaces/:id/settings for builders', async () => {
    await renderWithRoute('/workspaces/ws-1/settings', { isViewer: false });
    expect(screen.getByText('Settings Page')).toBeInTheDocument();
  });

  it('redirects viewers away from /workspaces/:id/settings to Dashboard', async () => {
    await renderWithRoute('/workspaces/ws-1/settings', { isViewer: true });
    await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument());
    expect(screen.queryByText('Settings Page')).not.toBeInTheDocument();
  });
});

describe('App – user settings route', () => {
  it('renders UserSettings at /settings', async () => {
    await renderWithRoute('/settings');
    expect(screen.getByText('User Settings Page')).toBeInTheDocument();
  });

  it('is reachable for regular authenticated users', async () => {
    await renderWithRoute('/settings', { isViewer: false });
    expect(screen.getByText('User Settings Page')).toBeInTheDocument();
  });

  it('is reachable for viewer users', async () => {
    await renderWithRoute('/settings', { isViewer: true });
    expect(screen.getByText('User Settings Page')).toBeInTheDocument();
  });
});
