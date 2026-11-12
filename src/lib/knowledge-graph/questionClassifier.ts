/**
 * Question classification system for the knowledge graph explainer.
 *
 * Classifies free-form user questions into:
 *  - An audience-appropriate category (maps to required sections)
 *  - A suggested audience (novice / ml_expert / technical_customer)
 *  - A list of section IDs that should be generated for the answer
 *
 * Unknown or ambiguous questions become "custom" with conservative context limits.
 * This module is deterministic, has no network/model/UI dependencies, and is
 * safe to unit-test in isolation.
 */

import type { AudienceId } from './audienceModel';

export type QuestionCategory =
  | 'purpose'
  | 'inputs_outputs'
  | 'trust_limits'
  | 'glossary'
  | 'guided_next_step'
  | 'labels_features'
  | 'splits_leakage'
  | 'metrics_calibration'
  | 'shap_artifact_provenance'
  | 'interfaces_ownership'
  | 'slo_reliability'
  | 'rbac_observability'
  | 'licensing_integration'
  | 'custom';

export interface QuestionClassification {
  category: QuestionCategory;
  audience: AudienceId;
  sections: string[];
  isCustom: boolean;
  confidence: 'high' | 'medium' | 'low';
}

interface KeywordRule {
  keywords: string[];
  category: QuestionCategory;
  audience: AudienceId;
  sections: string[];
}

// Keyword rules ordered by specificity. Domain-specific rules come first so
// that "What is the PSS?" matches metrics_calibration before the generic
// purpose rule. First match wins.
const RULES: KeywordRule[] = [
  // ML expert: labels/features (specific terms first)
  {
    keywords: ['feature engineering', 'labels and features', 'label', 'feature', 'target variable', 'predictor', 'input feature', 'signal'],
    category: 'labels_features',
    audience: 'ml_expert',
    sections: ['labels_features'],
  },
  // ML expert: splits/leakage
  {
    keywords: ['train test split', 'temporal split', 'cross validation', 'split', 'validation', 'leakage', 'data leak', 'overfit', 'holdout'],
    category: 'splits_leakage',
    audience: 'ml_expert',
    sections: ['splits_leakage'],
  },
  // ML expert: metrics/calibration
  {
    keywords: ['pss', 'brier', 'auc', 'roc', 'calibration', 'skill score', 'peirce', 'metric', 'accuracy', 'precision', 'recall', 'f1', 'evaluation'],
    category: 'metrics_calibration',
    audience: 'ml_expert',
    sections: ['metrics_calibration'],
  },
  // ML expert: SHAP/artifact/provenance
  {
    keywords: ['shap', 'shapley', 'artifact', 'provenance', 'model version', 'reproducibility', 'replay', 'manifest', 'checkpoint'],
    category: 'shap_artifact_provenance',
    audience: 'ml_expert',
    sections: ['shap_artifact_provenance'],
  },

  // Technical customer: interfaces/ownership
  {
    keywords: ['api endpoint', 'interface', 'ownership', 'who owns', 'maintainer', 'contact', 'responsibility', 'integration point', 'api'],
    category: 'interfaces_ownership',
    audience: 'technical_customer',
    sections: ['interfaces_ownership'],
  },
  // Technical customer: SLO/reliability
  {
    keywords: ['slo', 'sla', 'uptime', 'availability', 'latency', 'throughput', 'failure', 'recovery', 'incident', 'reliability'],
    category: 'slo_reliability',
    audience: 'technical_customer',
    sections: ['slo_reliability'],
  },
  // Technical customer: RBAC/observability
  {
    keywords: ['rbac', 'role based', 'permission', 'access control', 'jwt', 'observability', 'logging', 'monitoring', 'audit', 'trace', 'auth'],
    category: 'rbac_observability',
    audience: 'technical_customer',
    sections: ['rbac_observability'],
  },
  // Technical customer: licensing/integration
  {
    keywords: ['license', 'licensing', 'dependency', 'integration', 'deploy', 'deployment', 'onboard', 'setup', 'configuration', 'environment variable'],
    category: 'licensing_integration',
    audience: 'technical_customer',
    sections: ['licensing_integration'],
  },

  // Novice: purpose (generic terms last so domain terms win)
  {
    keywords: ['what is this', 'what does this do', "what's this", 'purpose', 'why does this exist', 'overview', 'introduction', 'what is it'],
    category: 'purpose',
    audience: 'novice',
    sections: ['purpose'],
  },
  // Novice: inputs/outputs
  {
    keywords: ['input', 'output', 'parameter', 'argument', 'return value', 'consume', 'produce', 'data in', 'data out'],
    category: 'inputs_outputs',
    audience: 'novice',
    sections: ['inputs_outputs'],
  },
  // Novice: trust limits
  {
    keywords: ['trust', 'trust limit', 'caveat', 'warning', 'safe to use', 'reliable', 'confidence', 'uncertainty', 'should i trust'],
    category: 'trust_limits',
    audience: 'novice',
    sections: ['trust_limits'],
  },
  // Novice: glossary
  {
    keywords: ['glossary', 'define', 'definition', 'what does it mean', 'explain term', 'jargon', 'terminology'],
    category: 'glossary',
    audience: 'novice',
    sections: ['glossary'],
  },
  // Novice: guided next step
  {
    keywords: ['next step', 'how do i start', 'where do i begin', 'getting started', 'first step', 'guide me', 'how to start'],
    category: 'guided_next_step',
    audience: 'novice',
    sections: ['guided_next_step'],
  },
];

// Conservative context limits for custom (unclassified) questions
const CUSTOM_CONTEXT_LIMITS = {
  maxRelatedNodes: 10,
  maxSourceLines: 30,
  maxSummaryLength: 500,
};

function normalizeQuestion(question: string): string {
  return question.toLowerCase().trim().replace(/\s+/g, ' ');
}

function matchRule(question: string): { rule: KeywordRule; matchedKeyword: string } | null {
  const normalized = normalizeQuestion(question);
  for (const rule of RULES) {
    // Find the longest matching keyword for this rule
    let longestMatch = '';
    for (const kw of rule.keywords) {
      if (normalized.includes(kw) && kw.length > longestMatch.length) {
        longestMatch = kw;
      }
    }
    if (longestMatch) {
      // First rule with a match wins (rules are ordered by specificity)
      return { rule, matchedKeyword: longestMatch };
    }
  }
  return null;
}

export function classifyQuestion(question: string): QuestionClassification {
  const trimmed = question.trim();
  if (!trimmed) {
    return {
      category: 'custom',
      audience: 'novice',
      sections: ['purpose'],
      isCustom: true,
      confidence: 'low',
    };
  }

  const match = matchRule(trimmed);
  if (!match) {
    // Unknown question — conservative custom mode
    return {
      category: 'custom',
      audience: 'novice',
      sections: ['purpose', 'trust_limits'],
      isCustom: true,
      confidence: 'low',
    };
  }

  // Determine confidence based on keyword specificity
  const matchedKeyword = match.matchedKeyword;
  const confidence: 'high' | 'medium' | 'low' =
    matchedKeyword.length > 10 ? 'high' : matchedKeyword.length > 5 ? 'medium' : 'low';

  return {
    category: match.rule.category,
    audience: match.rule.audience,
    sections: match.rule.sections,
    isCustom: false,
    confidence,
  };
}

export function mapQuestionToAudience(question: string, fallback: AudienceId = 'novice'): AudienceId {
  const result = classifyQuestion(question);
  if (result.isCustom) return fallback;
  return result.audience;
}

export function mapQuestionToSections(question: string): string[] {
  return classifyQuestion(question).sections;
}

export function getCustomContextLimits() {
  return { ...CUSTOM_CONTEXT_LIMITS };
}

export function isQuestionCategory(value: unknown): value is QuestionCategory {
  return typeof value === 'string' && [
    'purpose', 'inputs_outputs', 'trust_limits', 'glossary', 'guided_next_step',
    'labels_features', 'splits_leakage', 'metrics_calibration', 'shap_artifact_provenance',
    'interfaces_ownership', 'slo_reliability', 'rbac_observability', 'licensing_integration',
    'custom',
  ].includes(value);
}

export function getQuestionCategoryLabel(category: QuestionCategory): string {
  const labels: Record<QuestionCategory, string> = {
    purpose: 'Purpose',
    inputs_outputs: 'Inputs & Outputs',
    trust_limits: 'Trust Limits',
    glossary: 'Glossary',
    guided_next_step: 'Guided Next Step',
    labels_features: 'Labels & Features',
    splits_leakage: 'Splits & Leakage',
    metrics_calibration: 'Metrics & Calibration',
    shap_artifact_provenance: 'SHAP & Artifact Provenance',
    interfaces_ownership: 'Interfaces & Ownership',
    slo_reliability: 'SLO & Reliability',
    rbac_observability: 'RBAC & Observability',
    licensing_integration: 'Licensing & Integration',
    custom: 'Custom Question',
  };
  return labels[category] || category;
}
