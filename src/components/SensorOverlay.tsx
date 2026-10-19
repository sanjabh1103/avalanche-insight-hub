import { useMemo } from 'react';
import { CircleMarker, Pane, Popup, Tooltip } from 'react-leaflet';

export interface SensorEvent {
  event_id: string;
  timestamp: string;
  lat: number;
  lng: number;
  sensor_type: string;
  velocity_ms: number | null;
  mass_kg: number | null;
  depth_m: number | null;
  impact_pressure_kpa: number | null;
  rtsp_url: string | null;
  image_url: string | null;
  color?: string;
  label?: string;
}

interface Props {
  events: SensorEvent[];
  visible: boolean;
}

const SENSOR_COLORS: Record<string, string> = {
  radar: '#ef4444',
  geophone: '#3b82f6',
  stmet: '#22c55e',
  mpp: '#f59e0b',
  unknown: '#6b7280',
};

const SENSOR_LABELS: Record<string, string> = {
  radar: 'Ground Radar',
  geophone: 'Geophone',
  stmet: 'STMET',
  mpp: 'MPP Probe',
  unknown: 'Unknown Sensor',
};

function isRecent(timestamp: string): boolean {
  const eventTime = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - eventTime.getTime();
  return diffMs < 60 * 60 * 1000; // < 1 hour
}

function formatTimestamp(timestamp: string): string {
  const dt = new Date(timestamp);
  return dt.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export default function SensorOverlay({ events, visible }: Props) {
  const cappedEvents = useMemo(() => events.slice(0, 100), [events]);

  if (!visible || cappedEvents.length === 0) return null;

  return (
    <Pane name="sensor-overlay" style={{ zIndex: 460 }}>
      {cappedEvents.map((event) => {
        const color = event.color ?? SENSOR_COLORS[event.sensor_type] ?? SENSOR_COLORS.unknown;
        const label = event.label ?? SENSOR_LABELS[event.sensor_type] ?? SENSOR_LABELS.unknown;
        const recent = isRecent(event.timestamp);
        const radius = recent ? 10 : 7;

        return (
          <CircleMarker
            key={`sensor-${event.event_id}`}
            center={[event.lat, event.lng]}
            radius={radius}
            pathOptions={{
              color,
              fillColor: color,
              fillOpacity: recent ? 0.6 : 0.4,
              weight: 2,
            }}
          >
            <Tooltip>
              <div className="text-xs">
                <div className="font-semibold">{label}</div>
                <div>{formatTimestamp(event.timestamp)}</div>
                {event.velocity_ms != null && <div>Velocity: {event.velocity_ms.toFixed(1)} m/s</div>}
                {event.impact_pressure_kpa != null && <div>Impact: {event.impact_pressure_kpa.toFixed(1)} kPa</div>}
              </div>
            </Tooltip>
            <Popup>
              <div className="space-y-1 text-xs">
                <div className="text-sm font-semibold">{label} Event</div>
                <div>ID: {event.event_id}</div>
                <div>Time: {formatTimestamp(event.timestamp)}</div>
                <div>Location: {event.lat.toFixed(4)}, {event.lng.toFixed(4)}</div>
                {event.velocity_ms != null && <div>Velocity: {event.velocity_ms.toFixed(1)} m/s</div>}
                {event.mass_kg != null && <div>Mass: {event.mass_kg.toFixed(1)} kg</div>}
                {event.depth_m != null && <div>Depth: {event.depth_m.toFixed(2)} m</div>}
                {event.impact_pressure_kpa != null && <div>Impact Pressure: {event.impact_pressure_kpa.toFixed(1)} kPa</div>}
                {event.rtsp_url && (
                  <div className="pt-1">
                    <a href={event.rtsp_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                      View RTSP Stream
                    </a>
                  </div>
                )}
                {event.image_url && (
                  <div className="pt-1">
                    <a href={event.image_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">
                      View Image
                    </a>
                  </div>
                )}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}
    </Pane>
  );
}
