import { useMemo } from 'react';
import { MapPin, AlertTriangle } from 'lucide-react';

export interface AAVDSEventData {
  event_id: string;
  lat: number;
  lng: number;
  timestamp: string;
  detection_confidence: number;
  signal_type: string;
  victim_id?: string | null;
  burial_depth_m?: number | null;
  color?: string;
}

interface AAVDSOverlayProps {
  events: AAVDSEventData[];
  onSelectEvent?: (event: AAVDSEventData) => void;
  selectedEventId?: string | null;
}

function confidenceColor(confidence: number): string {
  if (confidence > 0.8) return '#22c55e';
  if (confidence > 0.5) return '#f59e0b';
  return '#ef4444';
}

export function AAVDSOverlay({ events, onSelectEvent, selectedEventId }: AAVDSOverlayProps) {
  const sortedEvents = useMemo(
    () => [...events].sort((a, b) => b.detection_confidence - a.detection_confidence),
    [events],
  );

  if (sortedEvents.length === 0) {
    return (
      <div className="rounded-xl border border-border/60 bg-card/50 p-4 text-sm text-muted-foreground">
        No AAVDS detection events.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border/60 bg-card/50 p-4 space-y-2">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 text-cyan-400" />
        <h3 className="text-xs font-mono uppercase tracking-[0.2em] text-muted-foreground">
          AAVDS Detections ({sortedEvents.length})
        </h3>
      </div>

      <div className="space-y-1.5 max-h-64 overflow-y-auto">
        {sortedEvents.map((event) => {
          const color = event.color ?? confidenceColor(event.detection_confidence);
          const isSelected = event.event_id === selectedEventId;

          return (
            <button
              key={event.event_id}
              onClick={() => onSelectEvent?.(event)}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors ${
                isSelected
                  ? 'bg-background/60 ring-1 ring-cyan-500/40'
                  : 'bg-background/20 hover:bg-background/40'
              }`}
            >
              <MapPin className="h-3.5 w-3.5 shrink-0" style={{ color }} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-foreground truncate">
                    {event.signal_type}
                  </span>
                  {event.victim_id && (
                    <span className="rounded bg-cyan-500/15 px-1 py-0.5 text-[9px] font-mono text-cyan-400">
                      ID: {event.victim_id}
                    </span>
                  )}
                </div>
                <span className="text-[10px] text-muted-foreground">
                  {event.lat.toFixed(3)}°, {event.lng.toFixed(3)}°
                </span>
              </div>
              <div className="flex flex-col items-end shrink-0">
                <span
                  className="text-[10px] font-mono font-semibold"
                  style={{ color }}
                >
                  {(event.detection_confidence * 100).toFixed(0)}%
                </span>
                {event.burial_depth_m != null && (
                  <span className="text-[9px] text-muted-foreground">
                    {event.burial_depth_m.toFixed(1)}m
                  </span>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
