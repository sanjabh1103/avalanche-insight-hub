import { describe, expect, it } from 'vitest';

import {
  buildOptimisticFieldReportEvent,
  filterAvalancheEventsByBbox,
  getAvalancheEventGovernanceLabel,
  getAvalancheEventGovernanceState,
  getAvalancheEventMarkerAppearance,
  mergeAvalancheEvents,
  parseAvalancheEventRow,
} from '@/lib/avalancheEvents';

describe('Historical events layer helpers', () => {
  it('parses EWKB point geometry returned by Supabase/PostGIS', () => {
    const event = parseAvalancheEventRow({
      id: 'event-ewkb',
      location: '0101000020E61000003333333333BB5540772D211FF4FC3B40',
      severity: 3,
      confidence: 0.6,
      label_confidence: 0.6,
      description: 'EWKB event',
      source: 'field_report',
      event_type: 'unknown',
      timestamp: '2026-05-02T04:30:00.000Z',
      features: {},
    });

    expect(event).not.toBeNull();
    expect(event?.lat).toBeCloseTo(27.9881, 4);
    expect(event?.lng).toBeCloseTo(86.925, 4);
  });

  it('uses label_confidence as the canonical marker confidence and keeps popup-facing fields', () => {
    const event = parseAvalancheEventRow({
      id: 'event-1',
      location: 'SRID=4326;POINT(86.925 27.988)',
      severity: 3,
      confidence: 0.2,
      label_confidence: 0.82,
      description: 'Observed slab release above Khumbu Icefall',
      source: 'field_report',
      event_type: 'unknown',
      timestamp: '2026-05-02T04:30:00.000Z',
      verification_status: 'unverified',
      features: {
        location_name: 'Khumbu Icefall',
        client_report_id: 'field-client-1',
      },
    });

    expect(event).not.toBeNull();
    expect(event?.confidence).toBe(0.82);
    expect(event?.location_name).toBe('Khumbu Icefall');
    expect(event?.source).toBe('field_report');
    expect(event?.description).toContain('Khumbu Icefall');
    expect(event?.verificationStatus).toBe('unverified');
  });

  it('maps governed field-report events to pending, corroborated, and verified marker semantics', () => {
    const pending = parseAvalancheEventRow({
      id: 'event-pending',
      location: 'SRID=4326;POINT(86.925 27.988)',
      severity: 3,
      confidence: 0.4,
      label_confidence: 0.72,
      description: 'Pending field report',
      source: 'field_report',
      event_type: 'unknown',
      timestamp: '2026-05-02T04:30:00.000Z',
      verification_status: 'unverified',
      features: {},
    });
    const corroborated = parseAvalancheEventRow({
      id: 'event-weak',
      location: 'SRID=4326;POINT(86.926 27.989)',
      severity: 3,
      confidence: 0.5,
      label_confidence: 0.81,
      description: 'Corroborated field report',
      source: 'field_report',
      event_type: 'unknown',
      timestamp: '2026-05-02T04:31:00.000Z',
      verification_status: 'weak',
      features: {},
    });
    const verified = parseAvalancheEventRow({
      id: 'event-verified',
      location: 'SRID=4326;POINT(86.927 27.99)',
      severity: 3,
      confidence: 0.6,
      label_confidence: 0.91,
      description: 'Verified event',
      source: 'field_report',
      event_type: 'unknown',
      timestamp: '2026-05-02T04:32:00.000Z',
      verification_status: 'verified',
      features: {},
    });

    expect(pending).not.toBeNull();
    expect(corroborated).not.toBeNull();
    expect(verified).not.toBeNull();

    expect(getAvalancheEventGovernanceState(pending!)).toBe('pending_corroboration');
    expect(getAvalancheEventGovernanceLabel(pending!)).toBe('Pending corroboration');
    expect(getAvalancheEventMarkerAppearance(pending!)).toMatchObject({
      color: '#94a3b8',
      fillColor: '#f59e0b',
      fillOpacity: 0.45,
    });

    expect(getAvalancheEventGovernanceState(corroborated!)).toBe('corroborated');
    expect(getAvalancheEventGovernanceLabel(corroborated!)).toBe('Corroborated');
    expect(getAvalancheEventMarkerAppearance(corroborated!)).toMatchObject({
      color: '#f97316',
      fillColor: '#f97316',
      fillOpacity: 0.72,
    });

    expect(getAvalancheEventGovernanceState(verified!)).toBe('verified');
    expect(getAvalancheEventGovernanceLabel(verified!)).toBe('Verified');
    expect(getAvalancheEventMarkerAppearance(verified!)).toMatchObject({
      color: '#ef4444',
      fillColor: '#ef4444',
      fillOpacity: 0.82,
    });
  });

  it('reconciles an optimistic field report with the durable inserted event and filters by bbox', () => {
    const optimistic = buildOptimisticFieldReportEvent({
      clientReportId: 'field-client-2',
      lat: 27.99,
      lng: 86.91,
      description: 'Debris observed near trail',
      timestamp: '2026-05-02T04:30:00.000Z',
      locationName: 'Himalayas (Nepal)',
    });

    const durable = parseAvalancheEventRow({
      id: 'event-2',
      location: 'SRID=4326;POINT(86.91 27.99)',
      severity: 3,
      confidence: 0.58,
      label_confidence: 0.74,
      description: 'Debris observed near trail',
      source: 'field_report',
      event_type: 'unknown',
      timestamp: '2026-05-02T04:31:00.000Z',
      features: {
        location_name: 'Himalayas (Nepal)',
        field_report_id: 'field-report-row-1',
        client_report_id: 'field-client-2',
      },
    });

    const merged = mergeAvalancheEvents([optimistic], durable!);
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe('event-2');
    expect(merged[0].optimistic).toBe(false);
    expect(merged[0].clientReportId).toBe('field-client-2');
    expect(merged[0].confidence).toBe(0.74);

    const filtered = filterAvalancheEventsByBbox(merged, [27.8, 86.7, 28.1, 87.1]);
    expect(filtered).toHaveLength(1);
    expect(filterAvalancheEventsByBbox(merged, [30, 90, 31, 91])).toHaveLength(0);
  });
});
