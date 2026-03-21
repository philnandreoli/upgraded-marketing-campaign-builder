/**
 * Tests for usePolling hook.
 */
import { renderHook, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import usePolling from '../hooks/usePolling';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('usePolling', () => {
  it('calls callback on each interval tick when tab is visible', () => {
    const cb = vi.fn();
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    });

    renderHook(() => usePolling(cb, 1000));

    expect(cb).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1000));
    expect(cb).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(1000));
    expect(cb).toHaveBeenCalledTimes(2);
  });

  it('does not start polling when tab is hidden on mount', () => {
    const cb = vi.fn();
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      writable: true,
      configurable: true,
    });

    renderHook(() => usePolling(cb, 1000));

    act(() => vi.advanceTimersByTime(5000));
    expect(cb).not.toHaveBeenCalled();
  });

  it('pauses polling when tab becomes hidden', () => {
    const cb = vi.fn();
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    });

    renderHook(() => usePolling(cb, 1000));

    act(() => vi.advanceTimersByTime(1000));
    expect(cb).toHaveBeenCalledTimes(1);

    // Tab goes hidden
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      writable: true,
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Advance time — should NOT fire
    act(() => vi.advanceTimersByTime(5000));
    expect(cb).toHaveBeenCalledTimes(1);
  });

  it('fires immediately and resumes polling when tab becomes visible', () => {
    const cb = vi.fn();
    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      writable: true,
      configurable: true,
    });

    renderHook(() => usePolling(cb, 1000));

    act(() => vi.advanceTimersByTime(3000));
    expect(cb).not.toHaveBeenCalled();

    // Tab becomes visible
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Immediate call on visibility
    expect(cb).toHaveBeenCalledTimes(1);

    // Regular ticks resume
    act(() => vi.advanceTimersByTime(1000));
    expect(cb).toHaveBeenCalledTimes(2);
  });

  it('does not poll when interval is null', () => {
    const cb = vi.fn();
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    });

    renderHook(() => usePolling(cb, null));

    act(() => vi.advanceTimersByTime(5000));
    expect(cb).not.toHaveBeenCalled();
  });

  it('cleans up interval and listener on unmount', () => {
    const cb = vi.fn();
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    });
    const removeSpy = vi.spyOn(document, 'removeEventListener');

    const { unmount } = renderHook(() => usePolling(cb, 1000));

    act(() => vi.advanceTimersByTime(1000));
    expect(cb).toHaveBeenCalledTimes(1);

    unmount();

    // After unmount, further ticks should not fire
    act(() => vi.advanceTimersByTime(5000));
    expect(cb).toHaveBeenCalledTimes(1);
    expect(removeSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
    removeSpy.mockRestore();
  });

  it('uses the latest callback via ref', () => {
    let count = 0;
    const cb1 = vi.fn(() => count++);
    const cb2 = vi.fn(() => (count += 10));
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    });

    const { rerender } = renderHook(({ fn }) => usePolling(fn, 1000), {
      initialProps: { fn: cb1 },
    });

    act(() => vi.advanceTimersByTime(1000));
    expect(cb1).toHaveBeenCalledTimes(1);

    rerender({ fn: cb2 });

    act(() => vi.advanceTimersByTime(1000));
    expect(cb2).toHaveBeenCalledTimes(1);
    expect(count).toBe(11); // 1 from cb1, 10 from cb2
  });
});
