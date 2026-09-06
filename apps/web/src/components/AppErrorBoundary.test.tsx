// @vitest-environment jsdom
//
// The root error boundary is the anti-blank-page guard: React 18 unmounts the
// whole app on an uncaught render error, which users see as a white screen.
// These tests pin that a crashing child renders an honest error screen with a
// reload action instead.

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AppErrorBoundary } from './AppErrorBoundary';

afterEach(cleanup);

function Bomb(): never {
  throw new Error('kaboom during render');
}

describe('AppErrorBoundary', () => {
  it('renders children when nothing throws', () => {
    render(
      <AppErrorBoundary>
        <p>healthy content</p>
      </AppErrorBoundary>,
    );
    expect(screen.getByText('healthy content')).toBeTruthy();
  });

  it('renders an honest error screen (not a blank page) when a child crashes', () => {
    // React logs the caught error; keep test output clean.
    vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <AppErrorBoundary>
        <Bomb />
      </AppErrorBoundary>,
    );

    const alert = screen.getByRole('alert');
    expect(alert.textContent).toContain('unexpected error');
    // The actual error message is surfaced, never hidden.
    expect(alert.textContent).toContain('kaboom during render');
    expect(screen.getByRole('button', { name: /reload application/i })).toBeTruthy();
    // The crashed tree is gone — the boundary replaced it, not the white page.
    expect(document.body.textContent).not.toBe('');
  });
});
