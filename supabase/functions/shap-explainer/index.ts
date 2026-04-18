import { serve } from "https://deno.land/std@0.168.0/http/server.ts";

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

interface TopFeature {
  feature: string;
  shap_value: number;
  feature_value: number;
  rank: number;
}

function normalizeTopFeatures(value: unknown): TopFeature[] {
  if (!value || typeof value !== 'object') return [];
  const top = (value as Record<string, unknown>).top_features ?? (value as Record<string, unknown>).topFeatures;
  if (!Array.isArray(top)) return [];
  return top
    .filter((item) => item && typeof item === 'object')
    .map((item) => {
      const row = item as Record<string, unknown>;
      return {
        feature: String(row.feature ?? ''),
        shap_value: Number(row.shap_value ?? 0),
        feature_value: Number(row.feature_value ?? 0),
        rank: Number(row.rank ?? 0),
      };
    })
    .filter((item) => item.feature.length > 0);
}

function featureLabel(name: string): string {
  return name.replace(/_/g, ' ');
}

function fallbackSummary(features: TopFeature[], problemType: string): string {
  const lead = features[0];
  const second = features[1];
  const sentenceOne = lead
    ? `${problemType} risk is being driven most strongly by ${featureLabel(lead.feature)} (${lead.feature_value.toFixed(3)} input, SHAP ${lead.shap_value.toFixed(3)}).`
    : `${problemType} risk is elevated by the current combination of terrain and weather inputs.`;
  const sentenceTwo = second
    ? `Secondary pressure is coming from ${featureLabel(second.feature)} (${second.feature_value.toFixed(3)} input, SHAP ${second.shap_value.toFixed(3)}), reinforcing the current hazard score.`
    : `The explanation is limited to the current feature contributions and does not provide safety advice.`;
  return `${sentenceOne} ${sentenceTwo}`;
}

async function generateGeminiSummary(features: TopFeature[], riskScore: number, problemType: string): Promise<string | null> {
  const apiKey = Deno.env.get('GEMINI_API_KEY');
  if (!apiKey || features.length === 0) return null;

  const prompt = [
    'You are an avalanche risk translator.',
    'You are an explainer, not a forecaster. Never declare a slope safe or stable.',
    'Do not provide safety advice. Do not suggest actions. Only explain the physical factors driving the current hazard score.',
    'Reply in exactly two concise sentences.',
    '',
    `Risk score: ${riskScore}`,
    `Problem type: ${problemType}`,
    `Top features: ${JSON.stringify(features)}`,
  ].join('\n');

  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=${apiKey}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0,
          maxOutputTokens: 120,
        },
      }),
    },
  );
  if (!response.ok) return null;
  const payload = await response.json();
  const text = String(payload?.candidates?.[0]?.content?.parts?.[0]?.text ?? '').trim();
  if (!text) return null;
  const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean).slice(0, 2);
  if (sentences.length === 0) return null;
  return sentences.join(' ');
}

serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const body = await req.json();
    const topFeatures = normalizeTopFeatures(body?.shap_context);
    const riskScore = Number(body?.risk_score ?? 0);
    const problemType = String(body?.problem_type ?? 'Avalanche');
    const summary = await generateGeminiSummary(topFeatures, riskScore, problemType)
      ?? fallbackSummary(topFeatures, problemType);

    return new Response(JSON.stringify({
      summary,
      model: Deno.env.get('GEMINI_API_KEY') ? 'gemini-1.5-flash-latest' : 'deterministic-fallback-v1',
      guardrail_version: 'negative-constraint-v1',
    }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
