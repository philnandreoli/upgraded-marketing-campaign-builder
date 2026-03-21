/**
 * Tests for UserSettings page — loading, error, success, and tab scaffold.
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import UserSettings from '../pages/UserSettings';

vi.mock('../api');

import * as api from '../api';

function makeMeResponse() {
  return {
    id: 'user-1',
    email: 'test@example.com',
    display_name: 'Test User',
    roles: ['campaign_builder'],
    is_admin: false,
    can_build: true,
    is_viewer: false,
  };
}

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={['/settings']}>
      <Routes>
        <Route path="/settings" element={<UserSettings />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('UserSettings – loading state', () => {
  it('shows loading indicator initially', () => {
    api.getMe.mockReturnValue(new Promise(() => {})); // never resolves
    renderSettings();
    expect(screen.getByTestId('settings-loading')).toBeInTheDocument();
    expect(screen.getByText(/loading settings/i)).toBeInTheDocument();
  });
});

describe('UserSettings – error state', () => {
  it('shows error message on API failure', async () => {
    api.getMe.mockRejectedValue(new Error('Network error'));
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('settings-error')).toBeInTheDocument());
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('shows retry button on error', async () => {
    api.getMe.mockRejectedValue(new Error('Network error'));
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('settings-error')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('retries loading when retry button is clicked', async () => {
    api.getMe.mockRejectedValueOnce(new Error('Network error'));
    api.getMe.mockResolvedValueOnce(makeMeResponse());
    renderSettings();

    await waitFor(() => expect(screen.getByTestId('settings-error')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(api.getMe).toHaveBeenCalledTimes(2);
  });
});

describe('UserSettings – success state', () => {
  it('renders page with user info after load', async () => {
    api.getMe.mockResolvedValue(makeMeResponse());
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByText(/test user/i)).toBeInTheDocument();
  });

  it('renders breadcrumb with link to dashboard', async () => {
    api.getMe.mockResolvedValue(makeMeResponse());
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: /dashboard/i })).toHaveAttribute('href', '/');
  });
});

describe('UserSettings – tab scaffold', () => {
  it('shows Profile, Preferences, and Notifications tabs', async () => {
    api.getMe.mockResolvedValue(makeMeResponse());
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: 'Profile' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Preferences' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Notifications' })).toBeInTheDocument();
  });

  it('Profile tab is selected by default', async () => {
    api.getMe.mockResolvedValue(makeMeResponse());
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: 'Profile' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-profile')).toBeInTheDocument();
  });

  it('switches to Preferences tab on click', async () => {
    api.getMe.mockResolvedValue(makeMeResponse());
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));
    expect(screen.getByRole('tab', { name: 'Preferences' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-preferences')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-profile')).not.toBeInTheDocument();
  });

  it('switches to Notifications tab on click', async () => {
    api.getMe.mockResolvedValue(makeMeResponse());
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Notifications' }));
    expect(screen.getByRole('tab', { name: 'Notifications' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-notifications')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-profile')).not.toBeInTheDocument();
  });
});
