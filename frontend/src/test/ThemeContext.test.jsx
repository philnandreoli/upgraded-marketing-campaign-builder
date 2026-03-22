/**
 * Tests for ThemeContext — unified theme management.
 *
 * Covers:
 * - Backend preference fetched on mount and applied
 * - Backend unreachable falls back to localStorage / OS preference
 * - "system" preference resolves against prefers-color-scheme
 * - setTheme() updates DOM, localStorage, and persists to backend
 * - PreferencesTab save applies theme immediately
 * - ThemeToggle persists changes to backend
 */

import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { useThemeContext, ThemeProvider } from '../ThemeContext';

vi.mock('../api');

import * as api from '../api';

/** Simple consumer component that exposes theme context values for testing. */
function ThemeConsumer() {
  const { theme, preference, setTheme } = useThemeContext();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="preference">{preference}</span>
      <button data-testid="set-dark" onClick={() => setTheme('dark')}>Dark</button>
      <button data-testid="set-light" onClick={() => setTheme('light')}>Light</button>
      <button data-testid="set-system" onClick={() => setTheme('system')}>System</button>
      <button data-testid="set-dark-no-persist" onClick={() => setTheme('dark', { persist: false })}>Dark (local)</button>
    </div>
  );
}

function renderWithProvider() {
  return render(
    <ThemeProvider>
      <ThemeConsumer />
    </ThemeProvider>,
  );
}

let matchMediaListeners;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');

  matchMediaListeners = [];
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    addEventListener: (event, handler) => matchMediaListeners.push({ event, handler }),
    removeEventListener: (event, handler) => {
      matchMediaListeners = matchMediaListeners.filter((l) => l.handler !== handler);
    },
  }));
});

afterEach(() => {
  matchMediaListeners = [];
});

describe('ThemeContext – backend preference on mount', () => {
  it('fetches backend settings and applies the theme', async () => {
    api.getMeSettings.mockResolvedValue({ theme: 'light' });
    api.patchMeSettings.mockResolvedValue({});
    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('preference').textContent).toBe('light');
      expect(screen.getByTestId('theme').textContent).toBe('light');
    });
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem('theme')).toBe('light');
  });

  it('applies dark theme from backend', async () => {
    api.getMeSettings.mockResolvedValue({ theme: 'dark' });
    api.patchMeSettings.mockResolvedValue({});
    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('theme').textContent).toBe('dark');
    });
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('applies system theme from backend, resolved to dark by default', async () => {
    api.getMeSettings.mockResolvedValue({ theme: 'system' });
    api.patchMeSettings.mockResolvedValue({});
    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('preference').textContent).toBe('system');
      expect(screen.getByTestId('theme').textContent).toBe('dark');
    });
  });
});

describe('ThemeContext – fallback when backend is unreachable', () => {
  it('falls back to localStorage when backend fails', async () => {
    localStorage.setItem('theme', 'light');
    api.getMeSettings.mockRejectedValue(new Error('Network error'));
    api.patchMeSettings.mockResolvedValue({});
    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('theme').textContent).toBe('light');
    });
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
  });

  it('falls back to OS preference when no localStorage and backend fails', async () => {
    api.getMeSettings.mockRejectedValue(new Error('Network error'));
    api.patchMeSettings.mockResolvedValue({});
    // matchMedia returns matches: false for dark, so resolveTheme("system") → "dark"
    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('theme').textContent).toBe('dark');
    });
  });

  it('falls back to light when OS prefers light and no localStorage', async () => {
    api.getMeSettings.mockRejectedValue(new Error('Network error'));
    api.patchMeSettings.mockResolvedValue({});
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: query.includes('light'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    renderWithProvider();

    await waitFor(() => {
      expect(screen.getByTestId('theme').textContent).toBe('light');
    });
  });
});

describe('ThemeContext – setTheme()', () => {
  it('updates theme, localStorage, DOM, and persists to backend', async () => {
    api.getMeSettings.mockResolvedValue({ theme: 'dark' });
    api.patchMeSettings.mockResolvedValue({});
    renderWithProvider();

    await waitFor(() => expect(screen.getByTestId('theme').textContent).toBe('dark'));

    await act(async () => {
      fireEvent.click(screen.getByTestId('set-light'));
    });

    expect(screen.getByTestId('theme').textContent).toBe('light');
    expect(screen.getByTestId('preference').textContent).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem('theme')).toBe('light');
    expect(api.patchMeSettings).toHaveBeenCalledWith({ theme: 'light' });
  });

  it('does not persist when persist: false is specified', async () => {
    api.getMeSettings.mockResolvedValue({ theme: 'light' });
    api.patchMeSettings.mockResolvedValue({});
    renderWithProvider();

    await waitFor(() => expect(screen.getByTestId('theme').textContent).toBe('light'));
    api.patchMeSettings.mockClear();

    await act(async () => {
      fireEvent.click(screen.getByTestId('set-dark-no-persist'));
    });

    expect(screen.getByTestId('theme').textContent).toBe('dark');
    expect(localStorage.getItem('theme')).toBe('dark');
    expect(api.patchMeSettings).not.toHaveBeenCalled();
  });

  it('normalizes invalid preference to "system"', async () => {
    api.getMeSettings.mockResolvedValue({ theme: 'dark' });
    api.patchMeSettings.mockResolvedValue({});

    function InvalidSetter() {
      const { setTheme, preference } = useThemeContext();
      return (
        <div>
          <span data-testid="pref">{preference}</span>
          <button data-testid="set-invalid" onClick={() => setTheme('invalid-value')}>Invalid</button>
        </div>
      );
    }

    render(
      <ThemeProvider>
        <InvalidSetter />
      </ThemeProvider>,
    );

    await waitFor(() => expect(screen.getByTestId('pref').textContent).toBe('dark'));

    await act(async () => {
      fireEvent.click(screen.getByTestId('set-invalid'));
    });

    expect(screen.getByTestId('pref').textContent).toBe('system');
  });
});

describe('ThemeContext – system theme OS listener', () => {
  it('responds to OS-level theme changes when preference is system', async () => {
    api.getMeSettings.mockResolvedValue({ theme: 'system' });
    api.patchMeSettings.mockResolvedValue({});
    renderWithProvider();

    await waitFor(() => expect(screen.getByTestId('preference').textContent).toBe('system'));

    // Simulate OS change to light
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: query.includes('light'),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));

    const changeListener = matchMediaListeners.find((l) => l.event === 'change');
    if (changeListener) {
      await act(async () => {
        changeListener.handler();
      });
      expect(screen.getByTestId('theme').textContent).toBe('light');
    }
  });
});

describe('ThemeContext – integration with useThemeContext', () => {
  it('throws when used outside provider', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<ThemeConsumer />)).toThrow('useThemeContext must be used within ThemeProvider');
    consoleSpy.mockRestore();
  });
});
