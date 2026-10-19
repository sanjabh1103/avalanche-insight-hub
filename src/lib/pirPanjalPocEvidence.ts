export const PIR_PANJAL_POC_REGION_KEY = 'pir_panjal_nw_himalaya';

export function isPirPanjalPocRegion(regionKey: string | null | undefined): boolean {
  return regionKey === PIR_PANJAL_POC_REGION_KEY;
}

export interface PirPanjalPocEvidence {
  caseId: string;
  site: {
    siteId: string;
    latitude: number;
    longitude: number;
    elevationM: number;
    slopeDeg: number;
    aspectDeg: number;
    aspectLabel: string;
  };
  evaluationWindow: {
    start: string;
    end: string;
  };
  scope: {
    elevationBand: string;
    elevationRange: string;
    horizonHours: number;
    ensembleMembers: number;
    problemTypes: string[];
  };
  nativeProfile: {
    layerCount: number;
    snowHeightM: number;
    bulkDensityKgM3: number;
    stabilityIndex: number;
    weakLayerDepthM: number;
    weakLayerGrainType: string;
    weakLayerShearStrengthKpa: number;
    temperatureGradientPerM: number;
    liquidWaterContentPct: number;
    profileDate: string;
  };
  rfComparison: {
    status: 'withheld';
    reason: string;
  };
  forcingQuality: {
    sampleCount: number;
    sourceSampleCount: number;
    warmupHours: number;
    targetGridM: number;
    sourceNativeResolutionM: number;
    effectiveInformationScaleM: number;
    directSnowfallAvailableSamples: number;
    sourceSnowDepthAvailableSamples: number;
  };
  provenance: {
    evidenceStatus: 'historical_mapping_audit_hold' | 'current_verified_mapping';
    runId: string;
    candidateResultSha256: string;
    forcingSource: string;
    forcingModel: string;
    forcingSha256: string;
    smetSha256: string;
    nativeIdentity: string;
    binaryVersion: string;
    imageId: string;
    imageArchiveSha256: string;
  };
  limitations: string[];
}

/**
 * Sanitized snapshot of the current verified hosted candidate run.
 *
 * This is deliberately not connected to the live grid or risk score. It is a
 * customer-demo evidence surface backed by a hosted bundle produced with the
 * corrected v2 forcing (ILWR from a named cloud-cover/temperature engineering
 * parametrization in the forcing adapter before the MeteoIO/native SNOWPACK run;
 * terrestrial_radiation is provenance-only). Both the producer gate and the
 * independent consumer release gate passed for this run.
 */
export const PIR_PANJAL_POC_EVIDENCE: PirPanjalPocEvidence = {
  caseId: 'pir-panjal-gulmarg-wd-2024-02-22',
  site: {
    siteId: 'pir-panjal-middle-candidate-34021875-74347536',
    latitude: 34.021875,
    longitude: 74.347536111,
    elevationM: 3730,
    slopeDeg: 26.262132,
    aspectDeg: 36.885404,
    aspectLabel: 'NE',
  },
  evaluationWindow: {
    start: '2024-02-22T00:00:00Z',
    end: '2024-02-24T00:00:00Z',
  },
  scope: {
    elevationBand: 'middle',
    elevationRange: '3,200–4,000 m',
    horizonHours: 48,
    ensembleMembers: 1,
    problemTypes: ['storm / new-snow', 'wind slab'],
  },
  nativeProfile: {
    layerCount: 278,
    snowHeightM: 1.533,
    bulkDensityKgM3: 227.5,
    stabilityIndex: 0.1,
    weakLayerDepthM: 1.528,
    weakLayerGrainType: 'melt_forms',
    weakLayerShearStrengthKpa: 6.0,
    temperatureGradientPerM: 4.2843,
    liquidWaterContentPct: 0,
    profileDate: '2024-02-23 12:00 UTC',
  },
  rfComparison: {
    status: 'withheld',
    reason: 'Direct snowfall is unavailable in the candidate forcing; no zero substitute is accepted.',
  },
  forcingQuality: {
    sampleCount: 3504,
    sourceSampleCount: 3552,
    warmupHours: 48,
    targetGridM: 3000,
    sourceNativeResolutionM: 13000,
    effectiveInformationScaleM: 25000,
    directSnowfallAvailableSamples: 0,
    sourceSnowDepthAvailableSamples: 3552,
  },
  provenance: {
    evidenceStatus: 'current_verified_mapping',
    runId: 'poc-2026-08-13T0636-pir_panjal_nw_himalaya-middle-d49739',
    candidateResultSha256: 'add242aeeb477fc009b0387e2206c145bbbf02f77b3e16fd8a54e5abd0fa3c9e',
    forcingSource: 'Open-Meteo historical forecast replay',
    forcingModel: 'gfs_seamless',
    forcingSha256: '8030c138568eae902f7c2d587f542b2abda5ad793dcc09b17bee6440102fdf26',
    smetSha256: 'd041892d9e40d3dd9d0c39f9b8a1b34b69d69b72ffafb1c999c1fc2cc9eb7673',
    nativeIdentity: 'hosted GitHub Actions Docker run with corrected v2 forcing; producer and independent consumer release gates passed',
    binaryVersion: 'SNOWPACK 3.7.0 · MeteoIO 2.11.0',
    imageId: 'sha256:254f4f7af9a9abfb49496a0024e5ec1cce5a9c707fa381f52e184758aad530df',
    imageArchiveSha256: '7514154b5738a9ed1a23ff71a5dee8653e710264d4e2a6830931666865acbe54',
  },
  limitations: [
    'Customer-selected geometry is deterministic SRTM-derived candidate geometry, not a Partner-approved input.',
    'The forcing is a retrospective replay, not a live operational forecast.',
    'The 3 km value is a computational target; effective source information is approximately 25 km.',
    'Direct snowfall is unavailable in all 3,552 source samples; no zero substitute was used.',
    'Source snow depth is retained for QA and is not assimilated as SNOWPACK HS.',
    'The input contains 48 provider-sourced warm-up hours before 1 October 2023; these are excluded from the 3,504 case samples.',
    'Hourly precipitation was explicitly re-accumulated by pinned MeteoIO over 3,600 seconds; the native log contains no precipitation warning.',
    'The snow-free initial state remains a candidate assumption, not an observation.',
    'The RF model is not trained or independently validated for Pir Panjal.',
    'The associated regional event is context only, not a site-specific accuracy label.',
    'The hosted producer, private Storage transfer, independent download, and release gate passed; this proves pipeline integrity, not scientific validation.',
    'The v2 corrected forcing uses ILWR from a named cloud-cover/temperature engineering parametrization in the forcing adapter before the MeteoIO/native SNOWPACK run; Open-Meteo terrestrial_radiation is provenance-only and is not mapped as ILWR.',
    'Customer acknowledgment of the RAvaFcast mapping boundary and the POC-stage interpolation profile was received on 13 August 2026; the existing internal POC-only publication boundary remains in force. This is a scope confirmation, not scientific validation.',
    'No official warning, accuracy, transferability, Partner approval, or production eligibility is claimed.',
  ],
};
