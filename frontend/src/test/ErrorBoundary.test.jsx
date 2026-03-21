import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import ErrorBoundary from '../components/ErrorBoundary';

/** A component that always throws during render. */
function ThrowingComponent() {
  throw new Error('Test render error');
}

/** A component that renders normally. */
function GoodComponent() {
  return <div>All good</div>;
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('ErrorBoundary', () => {
  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <GoodComponent />
      </ErrorBoundary>,
    );

    expect(screen.getByText('All good')).toBeInTheDocument();
  });

  it('renders fallback UI when a child throws a render error', () => {
    // Suppress React error boundary console output during test
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>,
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(
      screen.getByText(/unexpected error occurred/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /reload page/i }),
    ).toBeInTheDocument();

    spy.mockRestore();
  });

  it('logs the error to console.error in development', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>,
    );

    expect(spy).toHaveBeenCalled();
    const loggedMessages = spy.mock.calls.map((call) => call.join(' '));
    const boundaryLog = loggedMessages.find((msg) =>
      msg.includes('ErrorBoundary caught an error'),
    );
    expect(boundaryLog).toBeTruthy();

    spy.mockRestore();
  });

  it('calls window.location.reload when the reload button is clicked', async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { ...window.location, reload: reloadMock },
      writable: true,
    });

    const user = userEvent.setup();

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>,
    );

    await user.click(screen.getByRole('button', { name: /reload page/i }));
    expect(reloadMock).toHaveBeenCalledTimes(1);

    spy.mockRestore();
  });

  it('renders the branded logo in the fallback', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>,
    );

    const svg = document.querySelector('.error-boundary-logo');
    expect(svg).toBeInTheDocument();

    spy.mockRestore();
  });
});
