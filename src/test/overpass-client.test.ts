import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('overpassClient', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-02T00:00:00.000Z'));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    vi.resetModules();
  });

  it('returns a degraded result on 429 and enters cooldown without throwing', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
    } as Response);
    vi.stubGlobal('fetch', fetchMock);

    const { fetchOverpassJson } = await import('@/lib/overpassClient');

    const first = await fetchOverpassJson<{ elements: unknown[] }>({
      cacheKey: 'overpass:roads:nepal',
      query: '[out:json];node(0,0,1,1);out;',
      cooldownMs: 60_000,
    });
    const second = await fetchOverpassJson<{ elements: unknown[] }>({
      cacheKey: 'overpass:roads:nepal:retry',
      query: '[out:json];node(0,0,1,1);out;',
      cooldownMs: 60_000,
    });

    expect(first.ok).toBe(false);
    const firstDegraded = first as any;
    expect(firstDegraded.reason).toBe('rate_limited');
    expect(firstDegraded.message).toMatch(/rate-limited/i);
    expect(second.ok).toBe(false);
    const secondDegraded = second as any;
    expect(secondDegraded.reason).toBe('cooldown');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('dedupes identical in-flight requests and resolves both callers safely', async () => {
    let resolveFetch!: (response: Response) => void;
    const pendingResponse = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    const fetchMock = vi.fn().mockReturnValue(pendingResponse);
    vi.stubGlobal('fetch', fetchMock);

    const { fetchOverpassJson } = await import('@/lib/overpassClient');

    const firstPromise = fetchOverpassJson<{ elements: Array<{ id: number }> }>({
      cacheKey: 'overpass:infra:nepal',
      query: '[out:json];way(0,0,1,1);out;',
    });
    const secondPromise = fetchOverpassJson<{ elements: Array<{ id: number }> }>({
      cacheKey: 'overpass:infra:nepal',
      query: '[out:json];way(0,0,1,1);out;',
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);

    resolveFetch({
      ok: true,
      status: 200,
      json: async () => ({ elements: [{ id: 1 }] }),
    } as Response);

    const [first, second] = await Promise.all([firstPromise, secondPromise]);

    expect(first.ok).toBe(true);
    expect(second.ok).toBe(true);
    if (!first.ok || !second.ok) {
      throw new Error('Expected successful responses');
    }
    expect(first.data).toEqual({ elements: [{ id: 1 }] });
    expect(second.data).toEqual({ elements: [{ id: 1 }] });
  });
});
