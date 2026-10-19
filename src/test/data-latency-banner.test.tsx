import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import DataLatencyBanner from '@/components/DataLatencyBanner';

describe('DataLatencyBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-21T12:00:00Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders fresh banner when data age is under 12h', () => {
    render(
      <DataLatencyBanner
        publishedAt="2026-06-21T06:00:00Z"
        freshnessHours={5}
      />,
    );
    expect(screen.getByTestId('data-latency-banner')).toBeTruthy();
    expect(screen.getByText(/Fresh/i)).toBeTruthy();
  });

  it('renders aging banner when data age is between 12h and 24h', () => {
    render(
      <DataLatencyBanner
        publishedAt="2026-06-20T16:00:00Z"
      />,
    );
    expect(screen.getByText(/Aging/i)).toBeTruthy();
  });

  it('renders stale banner when data age exceeds 24h', () => {
    render(
      <DataLatencyBanner
        publishedAt="2026-06-19T12:00:00Z"
      />,
    );
    expect(screen.getByText(/Stale/i)).toBeTruthy();
    expect(screen.getByText(/more than 24 hours ago/i)).toBeTruthy();
  });

  it('renders nothing when no timestamps or freshness are provided', () => {
    const { container } = render(<DataLatencyBanner />);
    expect(container.firstChild).toBeNull();
  });

  it('uses freshnessHours when provided over computed age', () => {
    render(
      <DataLatencyBanner
        publishedAt="2026-06-19T12:00:00Z"
        freshnessHours={3}
      />,
    );
    expect(screen.getByText(/Fresh/i)).toBeTruthy();
  });

  it('formats age correctly for sub-hour freshness', () => {
    render(
      <DataLatencyBanner freshnessHours={0.5} />,
    );
    expect(screen.getByText(/<1 hour/i)).toBeTruthy();
  });

  it('formats age correctly for multi-day freshness', () => {
    render(
      <DataLatencyBanner freshnessHours={50} />,
    );
    expect(screen.getByText(/2d 2h/i)).toBeTruthy();
  });
});
