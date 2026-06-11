export type AvalancheLocale = 'en' | 'hi' | 'ne';

export type AvalancheCopyKey =
  | 'danger.low'
  | 'danger.moderate'
  | 'danger.considerable'
  | 'danger.high'
  | 'danger.very_high'
  | 'problem.new_snow'
  | 'problem.wind_slab'
  | 'problem.persistent_weak_layers'
  | 'problem.wet_snow'
  | 'problem.gliding_snow'
  | 'validation.synthetic_demo_boundary'
  | 'validation.scientist_decision_support';

const COPY: Record<AvalancheLocale, Record<AvalancheCopyKey, string>> = {
  en: {
    'danger.low': 'Low',
    'danger.moderate': 'Moderate',
    'danger.considerable': 'Considerable',
    'danger.high': 'High',
    'danger.very_high': 'Very high',
    'problem.new_snow': 'New snow',
    'problem.wind_slab': 'Wind slab',
    'problem.persistent_weak_layers': 'Persistent weak layers',
    'problem.wet_snow': 'Wet snow',
    'problem.gliding_snow': 'Gliding snow',
    'validation.synthetic_demo_boundary': 'Synthetic demo only, not scientific evidence',
    'validation.scientist_decision_support': 'Scientist decision support, not autonomous warning authority',
  },
  hi: {
    'danger.low': 'कम',
    'danger.moderate': 'मध्यम',
    'danger.considerable': 'महत्वपूर्ण',
    'danger.high': 'उच्च',
    'danger.very_high': 'बहुत उच्च',
    'problem.new_snow': 'नई बर्फ',
    'problem.wind_slab': 'विंड स्लैब',
    'problem.persistent_weak_layers': 'स्थायी कमजोर परतें',
    'problem.wet_snow': 'गीली बर्फ',
    'problem.gliding_snow': 'फिसलती बर्फ',
    'validation.synthetic_demo_boundary': 'केवल सिंथेटिक डेमो, वैज्ञानिक प्रमाण नहीं',
    'validation.scientist_decision_support': 'वैज्ञानिक निर्णय सहायता, स्वचालित चेतावनी अधिकार नहीं',
  },
  ne: {
    'danger.low': 'कम',
    'danger.moderate': 'मध्यम',
    'danger.considerable': 'उल्लेखनीय',
    'danger.high': 'उच्च',
    'danger.very_high': 'धेरै उच्च',
    'problem.new_snow': 'नयाँ हिउँ',
    'problem.wind_slab': 'हावाले थुपारेको स्ल्याब',
    'problem.persistent_weak_layers': 'दिगो कमजोर तहहरू',
    'problem.wet_snow': 'भिजेको हिउँ',
    'problem.gliding_snow': 'सर्ने हिउँ',
    'validation.synthetic_demo_boundary': 'केवल सिंथेटिक डेमो, वैज्ञानिक प्रमाण होइन',
    'validation.scientist_decision_support': 'वैज्ञानिक निर्णय सहयोग, स्वचालित चेतावनी अधिकार होइन',
  },
};

export function resolveAvalancheCopy(key: AvalancheCopyKey, locale: AvalancheLocale = 'en'): string {
  return COPY[locale]?.[key] ?? COPY.en[key];
}

export function availableAvalancheLocales(): AvalancheLocale[] {
  return ['en', 'hi', 'ne'];
}
