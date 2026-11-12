import { useMemo } from 'react';
import { CircleMarker, Pane, Popup, Tooltip } from 'react-leaflet';
import type { GridCell } from '@/lib/gridUtils';

interface SeismicEventSummary {
  magnitude: number;
  hoursSinceEvent: number;
  windowPhase: number;
  epicenterDistanceKm: number;
  factor: number;
  epicenterLat: number;
  epicenterLng: number;
}

interface Props {
  cells: GridCell[];
  visible: boolean;
}

function extractSeismicEvents(cells: GridCell[]): SeismicEventSummary[] {
  const seen = new Set<string>();
  const events: SeismicEventSummary[] = [];
  for (const cell of cells) {
    if (!cell.seismicAmplification) continue;
    const amp = cell.seismicAmplification;
    const key = `${amp.magnitude}-${amp.hours_since_event}-${amp.window_phase}`;
    if (seen.has(key)) continue;
    seen.add(key);
    events.push({
      magnitude: amp.magnitude,
      hoursSinceEvent: amp.hours_since_event,
      windowPhase: amp.window_phase,
      epicenterDistanceKm: amp.epicenter_distance_km,
      factor: amp.factor,
      epicenterLat: amp.epicenter_lat,
      epicenterLng: amp.epicenter_lng,
    });
  }
  return events.sort((a, b) => b.magnitude - a.magnitude);
}

const WINDOW_COLORS: Record<number, string> = {
  1: '#ef4444', // red — acute
  2: '#f97316', // orange — delayed
};

const WINDOW_LABELS: Record<number, string> = {
  1: 'Window 1 — Acute (2–15h)',
  2: 'Window 2 — Delayed (38–76h)',
};

export default function SeismicOverlay({ cells, visible }: Props) {
  const events = useMemo(() => extractSeismicEvents(cells), [cells]);

  if (!visible || events.length === 0) return null;

  return (
    <Pane name="seismic-overlay" style={{ zIndex: 450 }}>
      {events.map((event, idx) => {
        const color = WINDOW_COLORS[event.windowPhase] ?? '#6b7280';
        const radius = Math.max(6, Math.min(20, event.magnitude * 3));
        return (
          <CircleMarker
            key={`seismic-${idx}`}
            center={[event.epicenterLat, event.epicenterLng]}
            radius={radius}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: 0.15,
              weight: 2,
              dashArray: '4 3',
            }}
          >
            <Tooltip>
              <div className="text-xs">
                <div className="font-semibold">M{event.magnitude.toFixed(1)} Seismic Event</div>
                <div>{WINDOW_LABELS[event.windowPhase] ?? `Window ${event.windowPhase}`}</div>
                <div>{event.hoursSinceEvent.toFixed(1)}h post-tremor</div>
                <div>Amplification factor: {event.factor.toFixed(2)}x</div>
                <div>Epicenter distance: {event.epicenterDistanceKm.toFixed(0)} km</div>
              </div>
            </Tooltip>
            <Popup>
              <div className="space-y-1 text-xs">
                <div className="font-semibold text-sm">Seismic Cascade Active</div>
                <div>Magnitude: M{event.magnitude.toFixed(1)}</div>
                <div>Phase: {WINDOW_LABELS[event.windowPhase] ?? `Window ${event.windowPhase}`}</div>
                <div>Hours since event: {event.hoursSinceEvent.toFixed(1)}h</div>
                <div>Amplification: {event.factor.toFixed(2)}x base risk</div>
                <div>Epicenter distance: {event.epicenterDistanceKm.toFixed(0)} km</div>
                <div className="text-muted-foreground pt-1">
                  Risk amplified per Shekhar et al. 2026 post-tremor windows.
                </div>
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </Pane>
  );
}
