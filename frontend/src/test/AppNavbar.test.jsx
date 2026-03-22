/**
 * Tests for AppNavbar — user settings navigation entry.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, describe, it, expect } from 'vitest';
import AppNavbar from '../components/AppNavbar';
import { ThemeProvider } from '../ThemeContext';

vi.mock('../NotificationContext', () => ({
  useNotifications: () => ({ notifications: [], unreadCount: 0, markAsRead: vi.fn(), markAllAsRead: vi.fn() }),
}));

vi.mock('../api', () => ({
  getMeSettings: vi.fn().mockResolvedValue({ theme: 'dark' }),
  patchMeSettings: vi.fn().mockResolvedValue({}),
}));

function renderNavbar(props = {}) {
  const defaults = {
    connected: true,
    activeAccount: { name: 'Test User', username: 'test@example.com' },
    isAdmin: false,
    authEnabled: true,
    onLogout: vi.fn(),
  };
  return render(
    <MemoryRouter>
      <ThemeProvider>
        <AppNavbar {...defaults} {...props} />
      </ThemeProvider>
    </MemoryRouter>,
  );
}

describe('AppNavbar – settings link', () => {
  it('renders a settings link in the navbar', () => {
    renderNavbar();
    const link = screen.getByRole('link', { name: /user settings/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/settings');
  });

  it('renders settings link even when auth is disabled', () => {
    renderNavbar({ authEnabled: false, activeAccount: undefined });
    const link = screen.getByRole('link', { name: /user settings/i });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '/settings');
  });
});
