import { RISK_LABELS } from '@/lib/constants';
import { isCellUnavailable, type GridCell } from '@/lib/gridUtils';
import { SNOWPACK_PROXY_DESCRIPTOR, SNOWPACK_PROXY_LIMITATION } from '@/lib/snowpackProxyCopy';

export type ShapSource = 'tree_shap' | 'heuristic_fallback' | 'unavailable';

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
    positive: `the ${SNOWPACK_PROXY_DESCRIPTOR} is favoring instability`,
    negative: `the ${SNOWPACK_PROXY_DESCRIPTOR} is offsetting instability`,
  },
  ram_hardness: {
    label: 'slab hardness',
    positive: 'the proxy-derived slab-hardness estimate is pushing the forecast upward',
    negative: 'the proxy-derived slab-hardness estimate is offsetting some hazard',
  },
  shear_strength: {
    label: 'shear strength',
    positive: 'the proxy-derived shear-strength estimate is pushing the forecast toward instability',
    negative: 'the proxy-derived shear-strength estimate is providing some stability',
  },
  settlement_rate: {
    label: 'settlement rate',
    positive: 'the proxy-derived settlement estimate is not relieving the current load',
    negative: 'the proxy-derived settlement estimate is relieving part of the load',
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

export function selectRiskDrivers(cell: GridCell): { shapSource: ShapSource; drivers: RiskDriver[] } {
  if (isCellUnavailable(cell)) {
    return { shapSource: 'unavailable', drivers: [] };
  }

  const topFeatures = cell.shapContext?.topFeatures;
  if (topFeatures && topFeatures.length > 0) {
    return {
      shapSource: cell.explainabilityMode === 'heuristic_fallback' ? 'heuristic_fallback' : 'tree_shap',
      drivers: topFeatures.slice(0, 5).map((item) => ({
        feature: item.feature,
        label: formatFeatureLabel(item.feature),
        value: Number(item.shap_value.toFixed(3)),
        featureValue: Number(item.feature_value.toFixed(3)),
      })),
    };
  }

  const shapValues = Object.entries(cell.shapValues ?? {});
  if (shapValues.length === 0) {
    return { shapSource: 'unavailable', drivers: [] };
  }

  return {
    shapSource: 'heuristic_fallback',
    drivers: shapValues
      .map(([feature, value]) => ({
        feature,
        label: formatFeatureLabel(feature),
        value: Number((value as number).toFixed(3)),
      }))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, 5),
  };
}

export function buildRiskExplanation(cell: GridCell): string {
  if (isCellUnavailable(cell)) {
    return 'Terrain data is unavailable for this cell within the strict DEM search radius, so the batch artifact marks it stale and no runtime forecast is synthesized.';
  }

  const { shapSource, drivers } = selectRiskDrivers(cell);
  if (drivers.length === 0) {
    return 'Explainability data is missing from the batch artifact for this cell, so the dashboard withholds a driver narrative.';
  }
  const topPositive = drivers.find((driver) => driver.value > 0);
  const secondPositive = drivers.filter((driver) => driver.value > 0)[1];
  const topNegative = drivers.find((driver) => driver.value < 0);
  const riskLevel = String(RISK_LABELS[cell.riskScore] || 'Unknown').toLowerCase();
  const intro = shapSource === 'tree_shap'
    ? 'Batch TreeSHAP indicates'
    : shapSource === 'heuristic_fallback'
      ? 'Fallback explainability indicates'
      : 'Artifact explainability indicates';

  if (cell.riskScore >= 4) {
    const lead = topPositive
      ? describeDriver(topPositive, 'positive')
      : 'multiple aligned drivers are elevating the hazard';
    const support = secondPositive ? ` ${describeDriver(secondPositive, 'positive')}.` : '';
    const offset = topNegative
      ? ` ${describeDriver(topNegative, 'negative')}.`
      : ' No strong stabilizing driver is offsetting the current setup.';
    return `${intro} ${lead}.${support}${offset} Overall risk remains ${riskLevel}; snowpack terms here are proxy-based and ${SNOWPACK_PROXY_LIMITATION}.`;
  }

  if (cell.riskScore <= 2) {
    const stabilizer = topNegative
      ? describeDriver(topNegative, 'negative')
      : 'the current driver mix is generally stable';
    const watch = topPositive
      ? ` Watch ${topPositive.label.toLowerCase()} because it is still the main upward signal.`
      : '';
    return `${intro} ${stabilizer}.${watch} Overall risk is ${riskLevel}; snowpack terms here are proxy-based and ${SNOWPACK_PROXY_LIMITATION}.`;
  }

  const driver = topPositive
    ? describeDriver(topPositive, 'positive')
    : 'drivers are mixed without a single dominant trigger';
  const counter = topNegative
    ? ` ${describeDriver(topNegative, 'negative')}.`
    : '';
  return `${intro} ${driver}.${counter} Overall risk is ${riskLevel}; snowpack terms here are proxy-based and ${SNOWPACK_PROXY_LIMITATION}.`;
}
