import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TimeSlider from '@/components/TimeSlider';

describe('TimeSlider', () => {
  it('renders play button and hour display', () => {
    render(<TimeSlider value={3} onChange={vi.fn()} max={24} />);
    expect(screen.getByLabelText('Play timeline')).toBeTruthy();
    expect(screen.getByText('+3h')).toBeTruthy();
  });

  it('renders pause button when playing', () => {
    render(
      <TimeSlider value={3} onChange={vi.fn()} max={24} playing={true} onPlayToggle={vi.fn()} />,
    );
    expect(screen.getByLabelText('Pause timeline')).toBeTruthy();
  });

  it('calls onPlayToggle when play button is clicked', () => {
    const onPlayToggle = vi.fn();
    render(
      <TimeSlider value={0} onChange={vi.fn()} max={24} playing={false} onPlayToggle={onPlayToggle} />,
    );
    fireEvent.click(screen.getByLabelText('Play timeline'));
    expect(onPlayToggle).toHaveBeenCalledWith(true);
  });

  it('calls onChange(0) when reset button is clicked', () => {
    const onChange = vi.fn();
    const onPlayToggle = vi.fn();
    render(
      <TimeSlider value={5} onChange={onChange} max={24} playing={true} onPlayToggle={onPlayToggle} />,
    );
    fireEvent.click(screen.getByLabelText('Reset timeline'));
    expect(onChange).toHaveBeenCalledWith(0);
    expect(onPlayToggle).toHaveBeenCalledWith(false);
  });

  it('renders with custom max value', () => {
    render(<TimeSlider value={48} onChange={vi.fn()} max={72} />);
    expect(screen.getByText('+48h')).toBeTruthy();
  });
});
