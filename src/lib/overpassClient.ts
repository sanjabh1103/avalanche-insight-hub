const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';
const DEFAULT_TTL_MS = 30_000;
const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_COOLDOWN_MS = 60_000;

type CachedPayload = {
  expiresAt: number;
  data: unknown;
};

type OverpassOk<T> = {
  ok: true;
  data: T;
  cacheHit: boolean;
};

type OverpassDegraded = {
  ok: false;
  degraded: true;
  reason: 'cooldown' | 'rate_limited' | 'gateway_timeout' | 'network_error';
  message: string;
  cooldownUntil?: number;
};

export type OverpassResult<T> = OverpassOk<T> | OverpassDegraded;

const responseCache = new Map<string, CachedPayload>();
const inFlightRequests = new Map<string, Promise<OverpassResult<unknown>>>();
let cooldownUntil = 0;

function now() {
  return Date.now();
}

function buildDegradedResult(reason: OverpassDegraded['reason'], cooldownMs?: number): OverpassDegraded {
  const nextCooldownUntil = cooldownMs ? now() + cooldownMs : undefined;
  if (nextCooldownUntil) {
    cooldownUntil = Math.max(cooldownUntil, nextCooldownUntil);
  }
  return {
    ok: false,
    degraded: true,
    reason,
    cooldownUntil: nextCooldownUntil ?? (cooldownUntil || undefined),
    message:
      reason === 'rate_limited'
        ? 'Overpass temporarily rate-limited this region. Overlay data will retry shortly.'
        : reason === 'gateway_timeout'
          ? 'Overpass is overloaded right now. Overlay data is temporarily degraded.'
          : reason === 'cooldown'
            ? 'Overlay data is cooling down after an upstream rate limit.'
            : 'Overlay data is temporarily unavailable. Retrying shortly.',
  };
}

async function fetchWithTimeout(query: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(OVERPASS_URL, {
      method: 'POST',
      body: `data=${encodeURIComponent(query)}`,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchOverpassJson<T>(args: {
  cacheKey: string;
  query: string;
  ttlMs?: number;
  timeoutMs?: number;
  cooldownMs?: number;
}): Promise<OverpassResult<T>> {
  const cacheKey = args.cacheKey;
  const ttlMs = args.ttlMs ?? DEFAULT_TTL_MS;
  const timeoutMs = args.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const effectiveCooldownMs = args.cooldownMs ?? DEFAULT_COOLDOWN_MS;

  const cached = responseCache.get(cacheKey);
  if (cached && cached.expiresAt > now()) {
    return { ok: true, data: cached.data as T, cacheHit: true };
  }

  if (cooldownUntil > now()) {
    return buildDegradedResult('cooldown');
  }

  const inFlight = inFlightRequests.get(cacheKey);
  if (inFlight) {
    return inFlight as Promise<OverpassResult<T>>;
  }

  const requestPromise = (async (): Promise<OverpassResult<T>> => {
    try {
      const response = await fetchWithTimeout(args.query, timeoutMs);
      if (response.status === 429) {
        return buildDegradedResult('rate_limited', effectiveCooldownMs);
      }
      if (response.status === 504) {
        return buildDegradedResult('gateway_timeout', effectiveCooldownMs);
      }
      if (!response.ok) {
        return buildDegradedResult('network_error');
      }

      const data = await response.json() as T;
      responseCache.set(cacheKey, {
        expiresAt: now() + ttlMs,
        data,
      });
      return { ok: true, data, cacheHit: false };
    } catch {
      return buildDegradedResult('network_error', effectiveCooldownMs);
    } finally {
      inFlightRequests.delete(cacheKey);
    }
  })();

  inFlightRequests.set(cacheKey, requestPromise as Promise<OverpassResult<unknown>>);
  return requestPromise;
}
