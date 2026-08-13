import { describe, expect, it } from 'vitest';
import { normalizeGridCells } from '@/lib/gridUtils';

describe('normalizeGridCells — Wave D verification fields', () => {
  it('normalizes verification_packet from snake_case backend fields', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      verification_packet: {
        baseline_p25: 0.3,
        baseline_p50: 0.5,
        baseline_p75: 0.7,
        observed: 0.9,
        residual_zscore: 2.1,
        anomaly_state: 'watch',
        attribution_bucket: 'forcing_error',
        confidence: 0.85,
        contributing_sensors: ['sar', 'optical'],
        packet_version: 'v2',
      },
    }]);
    const cell = cells[0];
    expect(cell.verificationPacket).toBeDefined();
    expect(cell.verificationPacket?.baseline_p50).toBe(0.5);
    expect(cell.verificationPacket?.observed).toBe(0.9);
    expect(cell.verificationPacket?.residual_zscore).toBe(2.1);
    expect(cell.verificationPacket?.anomaly_state).toBe('watch');
    expect(cell.verificationPacket?.attribution_bucket).toBe('forcing_error');
    expect(cell.verificationPacket?.contributing_sensors).toEqual(['sar', 'optical']);
    expect(cell.verificationPacket?.packet_version).toBe('v2');
  });

  it('normalizes fusion_evidence from snake_case backend fields', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      fusion_evidence: {
        snow_depth_m: 1.2,
        snow_cover_fraction: 0.85,
        wet_snow_fraction: 0.1,
        loading_rate_24h: 5.0,
        uncertainty: 0.15,
        consensus_score: 0.78,
        contributing_sensors: ['s1', 'optical', 'weather'],
      },
    }]);
    const cell = cells[0];
    expect(cell.fusionEvidence).toBeDefined();
    expect(cell.fusionEvidence?.snow_depth_m).toBe(1.2);
    expect(cell.fusionEvidence?.snow_cover_fraction).toBe(0.85);
    expect(cell.fusionEvidence?.consensus_score).toBe(0.78);
    expect(cell.fusionEvidence?.contributing_sensors).toEqual(['s1', 'optical', 'weather']);
  });

  it('normalizes anomaly_score and discrepancy_reasons', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      anomaly_score: 0.72,
      discrepancy_reasons: ['sar_loading_optical_bare', 'rapid_loading_anomaly'],
    }]);
    const cell = cells[0];
    expect(cell.anomalyScore).toBe(0.72);
    expect(cell.discrepancyReasons).toEqual(['sar_loading_optical_bare', 'rapid_loading_anomaly']);
  });

  it('handles null anomaly_score correctly', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      anomaly_score: null,
    }]);
    expect(cells[0].anomalyScore).toBeNull();
  });

  it('normalizes verification_summary from snake_case', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      verification_summary: {
        total_cells: 400,
        anomaly_count: 5,
        watch_count: 12,
        normal_count: 380,
        unverified_count: 3,
        attribution_breakdown: { forcing_error: 5, sensing_gap: 3 },
      },
    }]);
    const cell = cells[0];
    expect(cell.verificationSummary).toBeDefined();
    expect(cell.verificationSummary?.total_cells).toBe(400);
    expect(cell.verificationSummary?.anomaly_count).toBe(5);
    expect(cell.verificationSummary?.attribution_breakdown).toEqual({ forcing_error: 5, sensing_gap: 3 });
  });

  it('returns undefined for missing verification fields', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
    }]);
    const cell = cells[0];
    expect(cell.verificationPacket).toBeUndefined();
    expect(cell.fusionEvidence).toBeUndefined();
    expect(cell.anomalyScore).toBeUndefined();
    expect(cell.discrepancyReasons).toBeUndefined();
    expect(cell.verificationSummary).toBeUndefined();
  });

  it('normalizes snowpack provenance from camelCase backend fields and clamps warning eligibility', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      snowpack_proxy: {
        sourceClass: 'proxy',
        source: 'open_meteo_archive',
        qualityFlags: ['candidate_source'],
        runId: 'run-001',
        executionStatus: 'fallback_proxy',
        officialWarningEligible: true,
        leadTimeH: 48,
        profileAvailable: false,
      },
    }]);
    expect(cells[0].snowpackProxy?.source_class).toBe('proxy');
    expect(cells[0].snowpackProxy?.source).toBe('open_meteo_archive');
    expect(cells[0].snowpackProxy?.quality_flags).toEqual(['candidate_source']);
    expect(cells[0].snowpackProxy?.run_id).toBe('run-001');
    expect(cells[0].snowpackProxy?.execution_status).toBe('fallback_proxy');
    expect(cells[0].snowpackProxy?.official_warning_eligible).toBe(false);
    expect(cells[0].snowpackProxy?.lead_time_h).toBe(48);
    expect(cells[0].snowpackProxy?.profile_available).toBe(false);
  });

  it('rejects invalid anomaly_state values', () => {
    const cells = normalizeGridCells([{
      row: 0,
      col: 0,
      lat: 39,
      lng: -106,
      latEnd: 39.1,
      lngEnd: -105.9,
      riskScore: 3,
      hazard: 0.5,
      exposure: 0.3,
      vulnerability: 0.2,
      problemType: 'Wind Slab',
      shapValues: {},
      verification_packet: {
        anomaly_state: 'invalid_state',
      },
    }]);
    expect(cells[0].verificationPacket?.anomaly_state).toBeUndefined();
  });
});
