import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AudienceDepthControls } from '@/components/knowledge-graph/AudienceDepthControls';

describe('AudienceDepthControls', () => {
  it('renders safe defaults and emits approved audience/depth selections', () => {
    const onAudienceChange = vi.fn();
    const onDepthChange = vi.fn();

    render(
      <AudienceDepthControls
        audience="novice"
        depth="briefing"
        onAudienceChange={onAudienceChange}
        onDepthChange={onDepthChange}
      />,
    );

    expect(screen.getByLabelText('Audience')).toHaveValue('novice');
    expect(screen.getByLabelText('Depth')).toHaveValue('briefing');

    fireEvent.change(screen.getByLabelText('Audience'), { target: { value: 'ml_expert' } });
    fireEvent.change(screen.getByLabelText('Depth'), { target: { value: 'deep' } });

    expect(onAudienceChange).toHaveBeenCalledWith('ml_expert');
    expect(onDepthChange).toHaveBeenCalledWith('deep');
  });
});
