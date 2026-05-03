import type { Database, Json } from '@/integrations/supabase/types';

export interface AvalancheEvent {
  id: string;
  lat: number;
  lng: number;
  severity: number;
  confidence: number;
  rawConfidence?: number | null;
  labelConfidence?: number | null;
  description: string;
  source: string;
  event_type: string;
  timestamp: string;
  location_name?: string;
  fieldReportId?: string | null;
  clientReportId?: string | null;
  verificationStatus?: string | null;
  optimistic?: boolean;
}

type AvalancheEventRow = Pick<
  Database['public']['Tables']['avalanche_events']['Row'],
  | 'id'
  | 'location'
  | 'severity'
  | 'confidence'
  | 'label_confidence'
  | 'description'
  | 'source'
  | 'event_type'
  | 'timestamp'
  | 'verification_status'
  | 'features'
>;

export type AvalancheEventGovernanceState =
  | 'pending_corroboration'
  | 'corroborated'
  | 'verified'
  | 'expert_verified'
  | 'unknown';

function asObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function toFiniteNumber(value: unknown): number | null {
  const numeric = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function normalizeDescription(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLowerCase();
}

function parseHexEncodedPoint(location: string): { lat: number; lng: number } | null {
  if (!/^[0-9a-fA-F]+$/.test(location) || location.length < 42 || location.length % 2 !== 0) {
    return null;
  }

  const bytes = new Uint8Array(location.length / 2);
  for (let index = 0; index < location.length; index += 2) {
    bytes[index / 2] = Number.parseInt(location.slice(index, index + 2), 16);
  }

  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const littleEndian = view.getUint8(0) === 1;
  const geometryType = view.getUint32(1, littleEndian);
  const hasSrid = (geometryType & 0x20000000) !== 0;
  const baseType = geometryType & 0x0fffffff;
  if (baseType !== 1) return null;

  let offset = 5;
  if (hasSrid) {
    offset += 4;
  }
  if (offset + 16 > view.byteLength) return null;

  const lng = view.getFloat64(offset, littleEndian);
  const lat = view.getFloat64(offset + 8, littleEndian);
  return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
}

function parsePointLocation(location: unknown): { lat: number; lng: number } | null {
  if (typeof location === 'string') {
    const hexPoint = parseHexEncodedPoint(location);
    if (hexPoint) return hexPoint;
    const match = location.match(/POINT\(([-\d.]+)\s+([-\d.]+)\)/);
    if (!match) return null;
    const lng = Number(match[1]);
    const lat = Number(match[2]);
    return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
  }

  const locationObject = asObject(location);
  const coordinates = Array.isArray(locationObject?.coordinates)
    ? locationObject.coordinates
    : null;
  if (!coordinates || coordinates.length < 2) return null;

  const lng = toFiniteNumber(coordinates[0]);
  const lat = toFiniteNumber(coordinates[1]);
  return lat !== null && lng !== null ? { lat, lng } : null;
}

function extractFeatureString(features: Record<string, unknown> | null, key: string): string | null {
  const value = features?.[key];
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function extractFeatureConfidence(features: Record<string, unknown> | null, key: string): number | null {
  return toFiniteNumber(features?.[key]);
}

function normalizeVerificationStatus(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const normalized = value.trim().toLowerCase();
  return normalized.length > 0 ? normalized : null;
}

export function parseAvalancheEventRow(row: Partial<AvalancheEventRow> & Record<string, unknown>): AvalancheEvent | null {
  const coordinates = parsePointLocation(row.location);
  if (!coordinates) return null;

  const features = asObject(row.features as Json | null);
  const rawConfidence = toFiniteNumber(row.confidence);
  const labelConfidence = toFiniteNumber(row.label_confidence) ?? extractFeatureConfidence(features, 'label_confidence');
  const canonicalConfidence = labelConfidence ?? rawConfidence ?? 0.5;
  const verificationStatus = normalizeVerificationStatus(
    row.verification_status ?? features?.verification_status,
  );

  return {
    id: String(row.id ?? ''),
    lat: coordinates.lat,
    lng: coordinates.lng,
    severity: toFiniteNumber(row.severity) ?? 3,
    confidence: canonicalConfidence,
    rawConfidence,
    labelConfidence,
    description: String(row.description ?? ''),
    source: String(row.source ?? 'unknown'),
    event_type: String(row.event_type ?? 'unknown'),
    timestamp: String(row.timestamp ?? ''),
    location_name: extractFeatureString(features, 'location_name') ?? '',
    fieldReportId: extractFeatureString(features, 'field_report_id'),
    clientReportId: extractFeatureString(features, 'client_report_id'),
    verificationStatus,
    optimistic: false,
  };
}

export function buildOptimisticFieldReportEvent(args: {
  clientReportId: string;
  lat: number;
  lng: number;
  description: string;
  timestamp: string;
  locationName?: string;
}): AvalancheEvent {
  return {
    id: `optimistic:${args.clientReportId}`,
    lat: args.lat,
    lng: args.lng,
    severity: 3,
    confidence: 0.6,
    rawConfidence: 0.6,
    labelConfidence: 0.6,
    description: args.description,
    source: 'field_report',
    event_type: 'unknown',
    timestamp: args.timestamp,
    location_name: args.locationName ?? '',
    clientReportId: args.clientReportId,
    verificationStatus: 'unverified',
    optimistic: true,
  };
}

export function getAvalancheEventGovernanceState(event: Pick<AvalancheEvent, 'source' | 'verificationStatus'>): AvalancheEventGovernanceState {
  const verificationStatus = normalizeVerificationStatus(event.verificationStatus);
  if (verificationStatus === 'expert_verified') return 'expert_verified';
  if (verificationStatus === 'verified') return 'verified';
  if (verificationStatus === 'weak') return 'corroborated';
  if ((event.source || '').toLowerCase().includes('field_report') && verificationStatus === 'unverified') {
    return 'pending_corroboration';
  }
  return verificationStatus === 'unverified' ? 'unknown' : 'unknown';
}

export function getAvalancheEventGovernanceLabel(event: Pick<AvalancheEvent, 'source' | 'verificationStatus'>): string {
  const state = getAvalancheEventGovernanceState(event);
  switch (state) {
    case 'pending_corroboration':
      return 'Pending corroboration';
    case 'corroborated':
      return 'Corroborated';
    case 'verified':
      return 'Verified';
    case 'expert_verified':
      return 'Expert verified';
    default:
      return 'Status unavailable';
  }
}

export function getAvalancheEventMarkerAppearance(event: Pick<AvalancheEvent, 'source' | 'verificationStatus' | 'confidence'>): {
  color: string;
  fillColor: string;
  fillOpacity: number;
  weight: number;
} {
  const state = getAvalancheEventGovernanceState(event);
  if (state === 'pending_corroboration') {
    return {
      color: '#94a3b8',
      fillColor: '#f59e0b',
      fillOpacity: 0.45,
      weight: 1,
    };
  }
  if (state === 'corroborated') {
    return {
      color: '#f97316',
      fillColor: '#f97316',
      fillOpacity: 0.72,
      weight: 2,
    };
  }
  if (state === 'verified' || state === 'expert_verified') {
    return {
      color: '#ef4444',
      fillColor: '#ef4444',
      fillOpacity: 0.82,
      weight: 2,
    };
  }
  if (event.confidence >= 0.8) {
    return { color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.8, weight: 2 };
  }
  if (event.confidence >= 0.6) {
    return { color: '#f97316', fillColor: '#f97316', fillOpacity: 0.8, weight: 2 };
  }
  if (event.confidence >= 0.4) {
    return { color: '#eab308', fillColor: '#eab308', fillOpacity: 0.8, weight: 2 };
  }
  return { color: '#84cc16', fillColor: '#84cc16', fillOpacity: 0.8, weight: 2 };
}

function sameTimestampWindow(left: string, right: string): boolean {
  const leftMs = new Date(left).getTime();
  const rightMs = new Date(right).getTime();
  if (!Number.isFinite(leftMs) || !Number.isFinite(rightMs)) return false;
  return Math.abs(leftMs - rightMs) <= 5 * 60 * 1000;
}

function sameCoordinates(left: AvalancheEvent, right: AvalancheEvent): boolean {
  return Math.abs(left.lat - right.lat) <= 0.000001 && Math.abs(left.lng - right.lng) <= 0.000001;
}

export function isSameAvalancheEvent(left: AvalancheEvent, right: AvalancheEvent): boolean {
  if (left.id && right.id && left.id === right.id) return true;
  if (left.clientReportId && right.clientReportId && left.clientReportId === right.clientReportId) return true;
  return (
    sameCoordinates(left, right)
    && normalizeDescription(left.description) === normalizeDescription(right.description)
    && sameTimestampWindow(left.timestamp, right.timestamp)
  );
}

function mergeEventRecord(current: AvalancheEvent, incoming: AvalancheEvent): AvalancheEvent {
  if (current.optimistic && !incoming.optimistic) {
    return { ...current, ...incoming, optimistic: false };
  }
  if (!current.optimistic && incoming.optimistic) {
    return { ...incoming, ...current, optimistic: false };
  }
  return { ...current, ...incoming, optimistic: current.optimistic && incoming.optimistic };
}

export function mergeAvalancheEvents(existing: AvalancheEvent[], incoming: AvalancheEvent | AvalancheEvent[]): AvalancheEvent[] {
  const nextItems = Array.isArray(incoming) ? incoming : [incoming];
  const merged = [...existing];

  nextItems.forEach((candidate) => {
    const matchIndex = merged.findIndex((item) => isSameAvalancheEvent(item, candidate));
    if (matchIndex >= 0) {
      merged[matchIndex] = mergeEventRecord(merged[matchIndex], candidate);
      return;
    }
    merged.unshift(candidate);
  });

  return merged
    .filter((event, index, items) => items.findIndex((candidate) => isSameAvalancheEvent(candidate, event)) === index)
    .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime());
}

export function removeAvalancheEvent(events: AvalancheEvent[], eventId: string): AvalancheEvent[] {
  return events.filter((event) => event.id !== eventId);
}

export function filterAvalancheEventsByBbox(
  events: AvalancheEvent[],
  bbox: [number, number, number, number],
): AvalancheEvent[] {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  return events.filter((event) => (
    Number.isFinite(event.lat)
    && Number.isFinite(event.lng)
    && event.lat >= latMin
    && event.lat <= latMax
    && event.lng >= lngMin
    && event.lng <= lngMax
  ));
}
