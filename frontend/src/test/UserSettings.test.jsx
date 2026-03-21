/**
 * Tests for UserSettings page — loading, error, success, and tab scaffold.
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import UserSettings from '../pages/UserSettings';
import { ToastProvider } from '../ToastContext';

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

function makeSettingsResponse(overrides = {}) {
  return {
    theme: 'system',
    locale: 'en-US',
    timezone: 'UTC',
    default_workspace_id: null,
    notification_prefs: {},
    dashboard_prefs: {},
    ...overrides,
  };
}

function renderSettings() {
  return render(
    <MemoryRouter initialEntries={['/settings']}>
      <ToastProvider>
        <Routes>
          <Route path="/settings" element={<UserSettings />} />
        </Routes>
      </ToastProvider>
    </MemoryRouter>,
  );
}

/** Set up mocks so the page loads successfully. */
function mockSuccessfulLoad(settingsOverrides = {}) {
  api.getMe.mockResolvedValue(makeMeResponse());
  api.getMeSettings.mockResolvedValue(makeSettingsResponse(settingsOverrides));
  api.listWorkspaces.mockResolvedValue([]);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('UserSettings – loading state', () => {
  it('shows loading indicator initially', () => {
    api.getMe.mockReturnValue(new Promise(() => {})); // never resolves
    api.getMeSettings.mockReturnValue(new Promise(() => {}));
    renderSettings();
    expect(screen.getByTestId('settings-loading')).toBeInTheDocument();
    expect(screen.getByText(/loading settings/i)).toBeInTheDocument();
  });
});

describe('UserSettings – error state', () => {
  it('shows error message on API failure', async () => {
    api.getMe.mockRejectedValue(new Error('Network error'));
    api.getMeSettings.mockRejectedValue(new Error('Network error'));
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('settings-error')).toBeInTheDocument());
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('shows retry button on error', async () => {
    api.getMe.mockRejectedValue(new Error('Network error'));
    api.getMeSettings.mockRejectedValue(new Error('Network error'));
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('settings-error')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('retries loading when retry button is clicked', async () => {
    api.getMe.mockRejectedValueOnce(new Error('Network error'));
    api.getMeSettings.mockRejectedValueOnce(new Error('Network error'));
    api.getMe.mockResolvedValueOnce(makeMeResponse());
    api.getMeSettings.mockResolvedValueOnce(makeSettingsResponse());
    renderSettings();

    await waitFor(() => expect(screen.getByTestId('settings-error')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(api.getMe).toHaveBeenCalledTimes(2);
  });
});

describe('UserSettings – success state', () => {
  it('renders page with user info after load', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByDisplayValue('Test User')).toBeInTheDocument();
  });

  it('renders breadcrumb with link to dashboard', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: /dashboard/i })).toHaveAttribute('href', '/');
  });
});

describe('UserSettings – tab scaffold', () => {
  it('shows Profile, Preferences, and Notifications tabs', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: 'Profile' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Preferences' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Notifications' })).toBeInTheDocument();
  });

  it('Profile tab is selected by default', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    expect(screen.getByRole('tab', { name: 'Profile' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-profile')).toBeInTheDocument();
  });

  it('switches to Preferences tab on click', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));
    expect(screen.getByRole('tab', { name: 'Preferences' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-preferences')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-profile')).not.toBeInTheDocument();
  });

  it('switches to Notifications tab on click', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Notifications' }));
    expect(screen.getByRole('tab', { name: 'Notifications' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-notifications')).toBeInTheDocument();
    expect(screen.queryByTestId('tab-profile')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Profile tab
// ---------------------------------------------------------------------------

describe('UserSettings – Profile tab', () => {
  it('displays display name in an editable input', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('tab-profile')).toBeInTheDocument());
    const input = screen.getByLabelText(/display name/i);
    expect(input).toBeInTheDocument();
    expect(input.value).toBe('Test User');
    expect(input).not.toBeDisabled();
  });

  it('displays email as read-only', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('tab-profile')).toBeInTheDocument());
    const input = screen.getByLabelText(/email/i);
    expect(input).toBeInTheDocument();
    expect(input.value).toBe('test@example.com');
    expect(input).toBeDisabled();
  });

  it('displays roles as read-only', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('tab-profile')).toBeInTheDocument());
    const input = screen.getByLabelText(/roles/i);
    expect(input).toBeInTheDocument();
    expect(input.value).toBe('campaign_builder');
    expect(input).toBeDisabled();
  });

  it('shows save button that triggers API call', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockResolvedValue(makeSettingsResponse());
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('tab-profile')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save profile/i }));

    await waitFor(() => expect(api.patchMeSettings).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByTestId('profile-save-success')).toBeInTheDocument());
  });

  it('shows error message on save failure', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockRejectedValue(new Error('Save failed'));
    renderSettings();
    await waitFor(() => expect(screen.getByTestId('tab-profile')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save profile/i }));

    await waitFor(() => expect(screen.getByTestId('profile-save-error')).toBeInTheDocument());
    expect(screen.getByTestId('profile-save-error')).toHaveTextContent('Save failed');
  });
});

// ---------------------------------------------------------------------------
// Preferences tab
// ---------------------------------------------------------------------------

describe('UserSettings – Preferences tab', () => {
  it('loads existing settings into form fields', async () => {
    mockSuccessfulLoad({ theme: 'dark', locale: 'fr-FR', timezone: 'Europe/Paris' });
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => expect(screen.getByTestId('tab-preferences')).toBeInTheDocument());
    expect(screen.getByLabelText(/theme/i).value).toBe('dark');
    expect(screen.getByLabelText(/locale/i).value).toBe('fr-FR');
    expect(screen.getByLabelText(/timezone/i).value).toBe('Europe/Paris');
  });

  it('saves preferences successfully', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockResolvedValue(makeSettingsResponse({ theme: 'dark' }));
    api.listWorkspaces.mockResolvedValue([]);
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => expect(screen.getByTestId('tab-preferences')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/theme/i), { target: { value: 'dark' } });
    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    await waitFor(() => expect(api.patchMeSettings).toHaveBeenCalledWith(
      expect.objectContaining({ theme: 'dark' }),
    ));
    await waitFor(() => expect(screen.getByTestId('preferences-save-success')).toBeInTheDocument());
  });

  it('shows error message on save failure', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockRejectedValue(new Error('Server error'));
    api.listWorkspaces.mockResolvedValue([]);
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => expect(screen.getByTestId('tab-preferences')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    await waitFor(() => expect(screen.getByTestId('preferences-save-error')).toBeInTheDocument());
    expect(screen.getByTestId('preferences-save-error')).toHaveTextContent('Server error');
  });

  it('shows unsaved changes warning when form is dirty', async () => {
    mockSuccessfulLoad();
    api.listWorkspaces.mockResolvedValue([]);
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => expect(screen.getByTestId('tab-preferences')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/theme/i), { target: { value: 'dark' } });

    expect(screen.getByTestId('unsaved-changes')).toBeInTheDocument();
    expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
  });

  it('lists workspaces in the default workspace selector', async () => {
    api.getMe.mockResolvedValue(makeMeResponse());
    api.getMeSettings.mockResolvedValue(makeSettingsResponse());
    api.listWorkspaces.mockResolvedValue([
      { id: 'ws-1', name: 'Marketing' },
      { id: 'ws-2', name: 'Engineering' },
    ]);
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => expect(screen.getByTestId('tab-preferences')).toBeInTheDocument());

    const wsSelect = screen.getByLabelText(/default workspace/i);
    await waitFor(() => {
      const options = Array.from(wsSelect.querySelectorAll('option'));
      expect(options.map((o) => o.textContent)).toContain('Marketing');
      expect(options.map((o) => o.textContent)).toContain('Engineering');
    });
  });

  it('sends correct patch payload with all preferences', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockResolvedValue(makeSettingsResponse({
      theme: 'light',
      locale: 'de-DE',
      timezone: 'Europe/Berlin',
      default_workspace_id: null,
    }));
    api.listWorkspaces.mockResolvedValue([]);
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('tab', { name: 'Preferences' }));

    await waitFor(() => expect(screen.getByTestId('tab-preferences')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/theme/i), { target: { value: 'light' } });
    fireEvent.change(screen.getByLabelText(/locale/i), { target: { value: 'de-DE' } });
    fireEvent.change(screen.getByLabelText(/timezone/i), { target: { value: 'Europe/Berlin' } });

    fireEvent.click(screen.getByRole('button', { name: /save preferences/i }));

    await waitFor(() => expect(api.patchMeSettings).toHaveBeenCalledWith({
      theme: 'light',
      locale: 'de-DE',
      timezone: 'Europe/Berlin',
      default_workspace_id: null,
    }));
  });
});

// ---------------------------------------------------------------------------
// Notifications tab
// ---------------------------------------------------------------------------

describe('UserSettings – Notifications tab', () => {
  function goToNotifications() {
    fireEvent.click(screen.getByRole('tab', { name: 'Notifications' }));
  }

  it('shows three notification category toggles checked by default', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    const pipeline = screen.getByLabelText(/pipeline updates/i);
    const approvals = screen.getByLabelText(/approvals required/i);
    const failures = screen.getByLabelText(/failures/i);

    expect(pipeline).toBeChecked();
    expect(approvals).toBeChecked();
    expect(failures).toBeChecked();
  });

  it('loads toggle states from backend settings', async () => {
    mockSuccessfulLoad({
      notification_prefs: {
        pipeline_updates: false,
        approvals_required: true,
        failures_errors: false,
      },
    });
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    expect(screen.getByLabelText(/pipeline updates/i)).not.toBeChecked();
    expect(screen.getByLabelText(/approvals required/i)).toBeChecked();
    expect(screen.getByLabelText(/failures/i)).not.toBeChecked();
  });

  it('saves notification preferences successfully', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockResolvedValue(makeSettingsResponse({
      notification_prefs: {
        pipeline_updates: false,
        approvals_required: true,
        failures_errors: true,
      },
    }));
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    // Uncheck pipeline updates
    fireEvent.click(screen.getByLabelText(/pipeline updates/i));

    fireEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    await waitFor(() => expect(api.patchMeSettings).toHaveBeenCalledWith({
      notification_prefs: expect.objectContaining({
        pipeline_updates: false,
        approvals_required: true,
        failures_errors: true,
      }),
    }));
    await waitFor(() => expect(screen.getByTestId('notifications-save-success')).toBeInTheDocument());
  });

  it('shows error message on save failure', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockRejectedValue(new Error('Network failure'));
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    await waitFor(() => expect(screen.getByTestId('notifications-save-error')).toBeInTheDocument());
    expect(screen.getByTestId('notifications-save-error')).toHaveTextContent('Network failure');
  });

  it('shows unsaved changes warning when a toggle is changed', async () => {
    mockSuccessfulLoad();
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/approvals required/i));

    expect(screen.getByTestId('notifications-unsaved-changes')).toBeInTheDocument();
    expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
  });

  it('sends correct patch payload with all three categories', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockResolvedValue(makeSettingsResponse({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: false,
        failures_errors: false,
      },
    }));
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    // Uncheck approvals and failures
    fireEvent.click(screen.getByLabelText(/approvals required/i));
    fireEvent.click(screen.getByLabelText(/failures/i));

    fireEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    await waitFor(() => expect(api.patchMeSettings).toHaveBeenCalledWith({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: false,
        failures_errors: false,
      },
    }));
  });

  it('shows digest frequency control when backend includes it', async () => {
    mockSuccessfulLoad({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: true,
        failures_errors: true,
        digest_frequency: 'daily',
      },
    });
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    const select = screen.getByLabelText(/digest frequency/i);
    expect(select).toBeInTheDocument();
    expect(select.value).toBe('daily');
  });

  it('does not show digest frequency when backend omits it', async () => {
    mockSuccessfulLoad({ notification_prefs: {} });
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());
    expect(screen.queryByLabelText(/digest frequency/i)).not.toBeInTheDocument();
  });

  it('shows quiet hours controls when backend includes them', async () => {
    mockSuccessfulLoad({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: true,
        failures_errors: true,
        quiet_hours_enabled: true,
        quiet_hours_start: '23:00',
        quiet_hours_end: '07:00',
      },
    });
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    expect(screen.getByLabelText(/enable quiet hours/i)).toBeChecked();
    expect(screen.getByLabelText(/start/i).value).toBe('23:00');
    expect(screen.getByLabelText(/end/i).value).toBe('07:00');
  });

  it('does not show quiet hours when backend omits them', async () => {
    mockSuccessfulLoad({ notification_prefs: {} });
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());
    expect(screen.queryByLabelText(/enable quiet hours/i)).not.toBeInTheDocument();
  });

  it('includes digest_frequency in patch when backend provides it', async () => {
    mockSuccessfulLoad({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: true,
        failures_errors: true,
        digest_frequency: 'daily',
      },
    });
    api.patchMeSettings.mockResolvedValue(makeSettingsResponse({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: true,
        failures_errors: true,
        digest_frequency: 'weekly',
      },
    }));
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText(/digest frequency/i), { target: { value: 'weekly' } });
    fireEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    await waitFor(() => expect(api.patchMeSettings).toHaveBeenCalledWith({
      notification_prefs: expect.objectContaining({
        digest_frequency: 'weekly',
      }),
    }));
  });

  it('includes quiet hours fields in patch when backend provides them', async () => {
    mockSuccessfulLoad({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: true,
        failures_errors: true,
        quiet_hours_enabled: false,
        quiet_hours_start: '22:00',
        quiet_hours_end: '08:00',
      },
    });
    api.patchMeSettings.mockResolvedValue(makeSettingsResponse({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: true,
        failures_errors: true,
        quiet_hours_enabled: true,
        quiet_hours_start: '22:00',
        quiet_hours_end: '08:00',
      },
    }));
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText(/enable quiet hours/i));
    fireEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    await waitFor(() => expect(api.patchMeSettings).toHaveBeenCalledWith({
      notification_prefs: expect.objectContaining({
        quiet_hours_enabled: true,
        quiet_hours_start: '22:00',
        quiet_hours_end: '08:00',
      }),
    }));
  });

  it('clears error state on subsequent successful save', async () => {
    mockSuccessfulLoad();
    api.patchMeSettings.mockRejectedValueOnce(new Error('Temporary error'));
    renderSettings();
    await waitFor(() => expect(screen.getByText('User Settings')).toBeInTheDocument());
    goToNotifications();

    await waitFor(() => expect(screen.getByTestId('tab-notifications')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    await waitFor(() => expect(screen.getByTestId('notifications-save-error')).toBeInTheDocument());

    // Second save succeeds
    api.patchMeSettings.mockResolvedValueOnce(makeSettingsResponse({
      notification_prefs: {
        pipeline_updates: true,
        approvals_required: true,
        failures_errors: true,
      },
    }));
    fireEvent.click(screen.getByRole('button', { name: /save notifications/i }));

    await waitFor(() => expect(screen.queryByTestId('notifications-save-error')).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('notifications-save-success')).toBeInTheDocument());
  });
});
