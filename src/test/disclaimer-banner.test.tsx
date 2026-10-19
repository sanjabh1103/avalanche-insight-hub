import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DisclaimerBanner from '@/components/DisclaimerBanner';

describe('DisclaimerBanner', () => {
  it('renders the experimental disclaimer text', () => {
    render(<DisclaimerBanner />);
    expect(screen.getByText(/Experimental AI system/i)).toBeTruthy();
    expect(screen.getByText(/Not for life-critical decisions/i)).toBeTruthy();
  });

  it('references official avalanche centers', () => {
    render(<DisclaimerBanner />);
    expect(screen.getByText(/official avalanche centers/i)).toBeTruthy();
  });

  it('renders an alert triangle icon', () => {
    const { container } = render(<DisclaimerBanner />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
  });
});
