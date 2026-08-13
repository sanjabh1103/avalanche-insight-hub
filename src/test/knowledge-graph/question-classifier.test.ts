// Tests for the question classifier (Phase 4).
// Validates question classification, audience mapping, section routing,
// and custom fallback for unknown questions.

import { describe, expect, it } from 'vitest';
import {
  classifyQuestion,
  mapQuestionToAudience,
  mapQuestionToSections,
  getCustomContextLimits,
  isQuestionCategory,
  getQuestionCategoryLabel,
  type QuestionCategory,
} from '@/lib/knowledge-graph/questionClassifier';

describe('question classifier — novice categories', () => {
  it('classifies purpose questions', () => {
    const result = classifyQuestion('What is this module?');
    expect(result.category).toBe('purpose');
    expect(result.audience).toBe('novice');
    expect(result.sections).toContain('purpose');
    expect(result.isCustom).toBe(false);
  });

  it('classifies inputs/outputs questions', () => {
    const result = classifyQuestion('What are the inputs and outputs of this function?');
    expect(result.category).toBe('inputs_outputs');
    expect(result.audience).toBe('novice');
    expect(result.sections).toContain('inputs_outputs');
  });

  it('classifies trust limits questions', () => {
    const result = classifyQuestion('What are the trust limits and caveats?');
    expect(result.category).toBe('trust_limits');
    expect(result.audience).toBe('novice');
    expect(result.sections).toContain('trust_limits');
  });

  it('classifies glossary questions', () => {
    const result = classifyQuestion('Define the terminology used here');
    expect(result.category).toBe('glossary');
    expect(result.audience).toBe('novice');
    expect(result.sections).toContain('glossary');
  });

  it('classifies guided next step questions', () => {
    const result = classifyQuestion('How do I start using this?');
    expect(result.category).toBe('guided_next_step');
    expect(result.audience).toBe('novice');
    expect(result.sections).toContain('guided_next_step');
  });
});

describe('question classifier — ML expert categories', () => {
  it('classifies labels/features questions', () => {
    const result = classifyQuestion('What features are used in this model?');
    expect(result.category).toBe('labels_features');
    expect(result.audience).toBe('ml_expert');
    expect(result.sections).toContain('labels_features');
  });

  it('classifies splits/leakage questions', () => {
    const result = classifyQuestion('How is the train test split done? Is there leakage?');
    expect(result.category).toBe('splits_leakage');
    expect(result.audience).toBe('ml_expert');
  });

  it('classifies metrics/calibration questions', () => {
    const result = classifyQuestion('What is the PSS and Brier score calibration?');
    expect(result.category).toBe('metrics_calibration');
    expect(result.audience).toBe('ml_expert');
  });

  it('classifies SHAP/artifact/provenance questions', () => {
    const result = classifyQuestion('Show me the SHAP values and artifact provenance');
    expect(result.category).toBe('shap_artifact_provenance');
    expect(result.audience).toBe('ml_expert');
  });
});

describe('question classifier — technical customer categories', () => {
  it('classifies interfaces/ownership questions', () => {
    const result = classifyQuestion('What is the API endpoint and who owns it?');
    expect(result.category).toBe('interfaces_ownership');
    expect(result.audience).toBe('technical_customer');
  });

  it('classifies SLO/reliability questions', () => {
    const result = classifyQuestion('What is the SLO and uptime for this service?');
    expect(result.category).toBe('slo_reliability');
    expect(result.audience).toBe('technical_customer');
  });

  it('classifies RBAC/observability questions', () => {
    const result = classifyQuestion('How does RBAC and access control work?');
    expect(result.category).toBe('rbac_observability');
    expect(result.audience).toBe('technical_customer');
  });

  it('classifies licensing/integration questions', () => {
    const result = classifyQuestion('What license is this and how do I integrate it?');
    expect(result.category).toBe('licensing_integration');
    expect(result.audience).toBe('technical_customer');
  });
});

describe('question classifier — custom fallback', () => {
  it('classifies unknown questions as custom', () => {
    const result = classifyQuestion('xyz random gibberish question');
    expect(result.category).toBe('custom');
    expect(result.isCustom).toBe(true);
    expect(result.confidence).toBe('low');
  });

  it('classifies empty questions as custom', () => {
    const result = classifyQuestion('');
    expect(result.category).toBe('custom');
    expect(result.isCustom).toBe(true);
  });

  it('custom questions have conservative sections', () => {
    const result = classifyQuestion('something completely unknown');
    expect(result.sections).toContain('purpose');
    expect(result.sections).toContain('trust_limits');
  });
});

describe('question classifier — confidence levels', () => {
  it('returns high confidence for long keyword matches', () => {
    const result = classifyQuestion('What is the feature engineering process?');
    expect(result.confidence).toBe('high');
  });

  it('returns low or medium confidence for short keyword matches', () => {
    const result = classifyQuestion('Define this.');
    expect(['low', 'medium']).toContain(result.confidence);
  });
});

describe('mapQuestionToAudience', () => {
  it('maps novice questions to novice audience', () => {
    expect(mapQuestionToAudience('What is this?')).toBe('novice');
  });

  it('maps ML questions to ml_expert audience', () => {
    expect(mapQuestionToAudience('What features are used?')).toBe('ml_expert');
  });

  it('maps customer questions to technical_customer audience', () => {
    expect(mapQuestionToAudience('What is the API endpoint?')).toBe('technical_customer');
  });

  it('uses fallback for custom questions', () => {
    expect(mapQuestionToAudience('xyz gibberish', 'ml_expert')).toBe('ml_expert');
    expect(mapQuestionToAudience('xyz gibberish')).toBe('novice');
  });
});

describe('mapQuestionToSections', () => {
  it('returns sections for classified questions', () => {
    const sections = mapQuestionToSections('What are the inputs and outputs?');
    expect(sections).toContain('inputs_outputs');
  });

  it('returns conservative sections for custom questions', () => {
    const sections = mapQuestionToSections('xyz gibberish');
    expect(sections).toContain('purpose');
    expect(sections).toContain('trust_limits');
  });
});

describe('getCustomContextLimits', () => {
  it('returns conservative limits', () => {
    const limits = getCustomContextLimits();
    expect(limits.maxRelatedNodes).toBeLessThanOrEqual(10);
    expect(limits.maxSourceLines).toBeLessThanOrEqual(30);
    expect(limits.maxSummaryLength).toBeLessThanOrEqual(500);
  });
});

describe('isQuestionCategory', () => {
  it('validates known categories', () => {
    expect(isQuestionCategory('purpose')).toBe(true);
    expect(isQuestionCategory('labels_features')).toBe(true);
    expect(isQuestionCategory('custom')).toBe(true);
  });

  it('rejects unknown categories', () => {
    expect(isQuestionCategory('unknown')).toBe(false);
    expect(isQuestionCategory(123)).toBe(false);
    expect(isQuestionCategory(null)).toBe(false);
  });
});

describe('getQuestionCategoryLabel', () => {
  it('returns human-readable labels', () => {
    expect(getQuestionCategoryLabel('purpose')).toBe('Purpose');
    expect(getQuestionCategoryLabel('inputs_outputs')).toBe('Inputs & Outputs');
    expect(getQuestionCategoryLabel('labels_features')).toBe('Labels & Features');
    expect(getQuestionCategoryLabel('custom')).toBe('Custom Question');
  });

  it('returns the category string for unknown values', () => {
    expect(getQuestionCategoryLabel('unknown' as QuestionCategory)).toBe('unknown');
  });
});
