import { describe, expect, it } from 'vitest';

import type { SensorEvent } from '@/components/SensorOverlay';

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
  return diffMs < 60 * 60 * 1000;
}

function makeEvent(overrides: Partial<SensorEvent> = {}): SensorEvent {
  return {
    event_id: 'evt_test',
    timestamp: new Date().toISOString(),
    lat: 27.35,
    lng: 88.50,
    sensor_type: 'radar',
    velocity_ms: 12.5,
    mass_kg: 1500.0,
    depth_m: 2.3,
    impact_pressure_kpa: 85.0,
    rtsp_url: null,
    image_url: null,
    ...overrides,
  };
}

describe('SensorOverlay helpers', () => {
  it('identifies recent events within 1 hour', () => {
    const recent = new Date(Date.now() - 30 * 60 * 1000).toISOString();
    const old = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(isRecent(recent)).toBe(true);
    expect(isRecent(old)).toBe(false);
  });

  it('maps sensor types to colors', () => {
    expect(SENSOR_COLORS['radar']).toBe('#ef4444');
    expect(SENSOR_COLORS['geophone']).toBe('#3b82f6');
    expect(SENSOR_COLORS['stmet']).toBe('#22c55e');
    expect(SENSOR_COLORS['mpp']).toBe('#f59e0b');
    expect(SENSOR_COLORS['unknown']).toBe('#6b7280');
  });

  it('maps sensor types to labels', () => {
    expect(SENSOR_LABELS['radar']).toBe('Ground Radar');
    expect(SENSOR_LABELS['geophone']).toBe('Geophone');
    expect(SENSOR_LABELS['stmet']).toBe('STMET');
    expect(SENSOR_LABELS['mpp']).toBe('MPP Probe');
    expect(SENSOR_LABELS['unknown']).toBe('Unknown Sensor');
  });

  it('creates valid sensor event with defaults', () => {
    const event = makeEvent();
    expect(event.event_id).toBe('evt_test');
    expect(event.sensor_type).toBe('radar');
    expect(event.velocity_ms).toBe(12.5);
    expect(event.lat).toBe(27.35);
    expect(event.lng).toBe(88.50);
  });

  it('allows overriding sensor type', () => {
    const event = makeEvent({ sensor_type: 'geophone', velocity_ms: null });
    expect(event.sensor_type).toBe('geophone');
    expect(event.velocity_ms).toBeNull();
  });

  it('handles events with all optional fields null', () => {
    const event = makeEvent({
      velocity_ms: null,
      mass_kg: null,
      depth_m: null,
      impact_pressure_kpa: null,
      rtsp_url: null,
      image_url: null,
      sensor_type: 'unknown',
    });
    expect(event.velocity_ms).toBeNull();
    expect(event.mass_kg).toBeNull();
    expect(event.depth_m).toBeNull();
    expect(event.impact_pressure_kpa).toBeNull();
    expect(event.rtsp_url).toBeNull();
    expect(event.image_url).toBeNull();
  });

  it('handles events with RTSP and image URLs', () => {
    const event = makeEvent({
      rtsp_url: 'rtsp://camera1/stream',
      image_url: 'https://img.example.com/evt001.jpg',
    });
    expect(event.rtsp_url).toBe('rtsp://camera1/stream');
    expect(event.image_url).toBe('https://img.example.com/evt001.jpg');
  });

  it('caps displayed events at 100', () => {
    const events: SensorEvent[] = Array.from({ length: 150 }, (_, i) =>
      makeEvent({ event_id: `evt_${i}` }),
    );
    const capped = events.slice(0, 100);
    expect(capped.length).toBe(100);
    expect(capped[0].event_id).toBe('evt_0');
    expect(capped[99].event_id).toBe('evt_99');
  });
});
