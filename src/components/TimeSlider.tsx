import { useState, useEffect, useRef, useCallback } from 'react';
import { Play, Pause, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';

interface Props {
  value: number;
  onChange: (value: number) => void;
  max?: number;
  playing?: boolean;
  onPlayToggle?: (playing: boolean) => void;
  className?: string;
}

export default function TimeSlider({ value, onChange, max = 24, playing: externalPlaying, onPlayToggle, className }: Props) {
  const [internalPlaying, setInternalPlaying] = useState(false);
  const playing = externalPlaying ?? internalPlaying;
  const setPlaying = onPlayToggle ?? setInternalPlaying;
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const tick = useCallback(() => {
    onChange(value >= max ? 0 : value + 1);
  }, [value, max, onChange]);

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(tick, 800);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [playing, tick]);

  return (
    <div className={`glass-panel rounded-2xl px-3 py-3 md:px-4 flex flex-wrap items-center gap-2 md:gap-3 ${className ?? ''}`} role="toolbar" aria-label="Timeline controls">
      <Button
        variant="ghost"
        size="icon"
        className="h-10 w-10 shrink-0 rounded-2xl touch-manipulation md:h-9 md:w-9"
        onClick={() => setPlaying(!playing)}
        aria-label={playing ? 'Pause timeline' : 'Play timeline'}
      >
        {playing ? <Pause className="h-5 w-5 md:h-4.5 md:w-4.5" /> : <Play className="h-5 w-5 md:h-4.5 md:w-4.5" />}
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-10 w-10 shrink-0 rounded-2xl touch-manipulation md:h-9 md:w-9"
        onClick={() => { setPlaying(false); onChange(0); }}
        aria-label="Reset timeline"
      >
        <RotateCcw className="h-4.5 w-4.5 md:h-4 md:w-4" />
      </Button>
      <div className="order-last min-w-[12rem] flex-1 basis-full sm:order-none sm:basis-[12rem]">
        <Slider
          value={[value]}
          onValueChange={([v]) => onChange(v)}
          min={0}
          max={max}
          step={1}
          className="flex-1 [&_[role=slider]]:h-5 [&_[role=slider]]:w-5 md:[&_[role=slider]]:h-4.5 md:[&_[role=slider]]:w-4.5 touch-manipulation"
          aria-label="Timeline hour offset"
          aria-valuemin={0}
          aria-valuemax={max}
          aria-valuenow={value}
          aria-valuetext={`+${value}h of ${max}h forecast`}
        />
      </div>
      <span className="font-mono text-xs text-muted-foreground w-12 text-right shrink-0">
        +{value}h
      </span>
    </div>
  );
}
