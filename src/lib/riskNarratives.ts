import { RISK_LABELS } from '@/lib/constants';
import type { GridCell } from '@/lib/gridUtils';
import type { ShapResult } from '@/lib/shapLoader';

export type ShapSource = 'treeshap' | 'heuristic';

export interface RiskDriver {
  feature: string;
  label: string;
  value: number;
  featureValue?: number;
}

const FEATURE_LEXICON: Record<string, { label: string; positive: string; negative: string }> = {
  snowfall_24h: {
    label: '24h snowfall',
    positive: 'fresh snowfall is adding load to the slab',
    negative: 'limited fresh snowfall is reducing new load',
  },
  precipitation_24h: {
    label: '24h precipitation',
    positive: 'recent precipitation is adding stress to the snowpack',
    negative: 'lighter precipitation is easing loading pressure',
  },
  wind_loading: {
    label: 'wind loading',
    positive: 'wind transport is building lee-side loading',
    negative: 'weaker wind transport is easing slab formation',
  },
  wind_directional_loading: {
    label: 'wind direction',
    positive: 'wind direction is aligned with lee loading',
    negative: 'wind direction is less aligned with lee loading',
  },
  wind_speed: {
    label: 'wind speed',
    positive: 'strong winds are reinforcing slab formation',
    negative: 'lighter winds are reducing slab reinforcement',
  },
  slope: {
    label: 'slope angle',
    positive: 'terrain angle is supportive of release',
    negative: 'terrain angle is less supportive of release',
  },
  elevation: {
    label: 'elevation',
    positive: 'elevation keeps the cell in a more snow-retentive band',
    negative: 'lower elevation is offsetting some hazard',
  },
  temp_gradient: {
    label: 'temperature gradient',
    positive: 'the temperature gradient is supporting weak-layer behavior',
    negative: 'a muted temperature gradient is reducing weak-layer pressure',
  },
  freezing_level_proxy: {
    label: 'freezing level',
    positive: 'freezing levels are pushing stress into the snowpack',
    negative: 'lower freezing levels are easing temperature stress',
  },
  snowpack: {
    label: 'snowpack state',
    positive: 'the snowpack signal is favoring instability',
    negative: 'the snowpack signal is offsetting instability',
  },
  ram_hardness: {
    label: 'slab hardness',
    positive: 'slab-hardness signal is pushing the forecast upward',
    negative: 'slab-hardness signal is offsetting some hazard',
  },
  shear_strength: {
    label: 'shear strength',
    positive: 'shear-strength signal is pushing the forecast toward instability',
    negative: 'shear-strength signal is providing some stability',
  },
  settlement_rate: {
    label: 'settlement rate',
    positive: 'settlement behavior is not relieving the current load',
    negative: 'settlement behavior is relieving part of the load',
  },
  aspect_loading: {
    label: 'aspect loading',
    positive: 'aspect exposure is concentrating loading on this cell',
    negative: 'aspect exposure is offsetting some loading',
  },
  terrain_roughness: {
    label: 'terrain roughness',
    positive: 'terrain roughness is concentrating risk in this terrain pocket',
    negative: 'terrain roughness is diffusing some hazard',
  },
  curvature_proxy: {
    label: 'terrain curvature',
    positive: 'terrain curvature is favoring stress concentration',
    negative: 'terrain curvature is offsetting stress concentration',
  },
  northness: {
    label: 'north-facing terrain',
    positive: 'terrain orientation is favoring colder snow preservation',
    negative: 'terrain orientation is offsetting snow preservation',
  },
  eastness: {
    label: 'east-facing terrain',
    positive: 'terrain orientation is aligning with the current loading pattern',
    negative: 'terrain orientation is offsetting the current loading pattern',
  },
};

function formatFeatureLabel(feature: string): string {
  return FEATURE_LEXICON[feature]?.label ?? feature.replace(/_/g, ' ');
}

function describeDriver(driver: RiskDriver, direction: 'positive' | 'negative'): string {
  const lexicon = FEATURE_LEXICON[driver.feature];
  if (lexicon) return direction === 'positive' ? lexicon.positive : lexicon.negative;
  return direction === 'positive'
    ? `${driver.label} is pushing the forecast upward`
    : `${driver.label} is offsetting part of the hazard`;
}

export function selectRiskDrivers(cell: GridCell, shapResult?: ShapResult | null): { shapSource: ShapSource; drivers: RiskDriver[] } {
  const realShap = shapResult?.origin === 'forecast_shap_cache' ? shapResult.topFeatures : null;
  if (realShap && realShap.length > 0) {
    return {
      shapSource: 'treeshap',
      drivers: realShap.slice(0, 5).map((item) => ({
        feature: item.feature,
        label: formatFeatureLabel(item.feature),
        value: Number(item.shap_value.toFixed(3)),
        featureValue: Number(item.feature_value.toFixed(3)),
      })),
    };
  }

  return {
    shapSource: 'heuristic',
    drivers: Object.entries(cell.shapValues)
      .map(([feature, value]) => ({
        feature,
        label: formatFeatureLabel(feature),
        value: Number((value as number).toFixed(3)),
      }))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, 5),
  };
}

export function buildRiskExplanation(cell: GridCell, shapResult?: ShapResult | null): string {
  const { shapSource, drivers } = selectRiskDrivers(cell, shapResult);
  const topPositive = drivers.find((driver) => driver.value > 0);
  const secondPositive = drivers.filter((driver) => driver.value > 0)[1];
  const topNegative = drivers.find((driver) => driver.value < 0);
  const riskLevel = String(RISK_LABELS[cell.riskScore] || 'Unknown').toLowerCase();
  const intro = shapSource === 'treeshap'
    ? 'TreeSHAP indicates'
    : 'Fallback feature signals indicate';

  if (cell.riskScore >= 4) {
    const lead = topPositive
      ? describeDriver(topPositive, 'positive')
      : 'multiple aligned drivers are elevating the hazard';
    const support = secondPositive ? ` ${describeDriver(secondPositive, 'positive')}.` : '';
    const offset = topNegative
      ? ` ${describeDriver(topNegative, 'negative')}.`
      : ' No strong stabilizing driver is offsetting the current setup.';
    return `${intro} ${lead}.${support}${offset} Overall risk remains ${riskLevel}.`;
  }

  if (cell.riskScore <= 2) {
    const stabilizer = topNegative
      ? describeDriver(topNegative, 'negative')
      : 'the current driver mix is generally stable';
    const watch = topPositive
      ? ` Watch ${topPositive.label.toLowerCase()} because it is still the main upward signal.`
      : '';
    return `${intro} ${stabilizer}.${watch} Overall risk is ${riskLevel}.`;
  }

  const driver = topPositive
    ? describeDriver(topPositive, 'positive')
    : 'drivers are mixed without a single dominant trigger';
  const counter = topNegative
    ? ` ${describeDriver(topNegative, 'negative')}.`
    : '';
  return `${intro} ${driver}.${counter} Overall risk is ${riskLevel}.`;
}
