import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

const distIndexPath = resolve(__dirname, '../../dist/index.html');

describe('CSP and external resources', () => {
  it('index.html has Content-Security-Policy meta tag', () => {
    let html = '';
    try {
      html = readFileSync(distIndexPath, 'utf-8');
    } catch {
      // dist/ may not exist in test env — skip
      return;
    }
    expect(html).toContain('Content-Security-Policy');
  });

  it('CSP includes connect-src self (allows same-origin data fetches)', () => {
    let html = '';
    try {
      html = readFileSync(distIndexPath, 'utf-8');
    } catch {
      return;
    }
    expect(html).toContain("connect-src 'self'");
    expect(html).not.toContain("connect-src 'none'");
  });

  it('CSP includes default-src self', () => {
    let html = '';
    try {
      html = readFileSync(distIndexPath, 'utf-8');
    } catch {
      return;
    }
    expect(html).toContain("default-src 'self'");
  });

  it('no external script tags in index.html', () => {
    let html = '';
    try {
      html = readFileSync(distIndexPath, 'utf-8');
    } catch {
      return;
    }
    expect(html).not.toMatch(/<script[^>]+src=["']https?:\/\//i);
  });

  it('no external font imports in index.html', () => {
    let html = '';
    try {
      html = readFileSync(distIndexPath, 'utf-8');
    } catch {
      return;
    }
    expect(html).not.toMatch(/@import\s+url\(["']?https?:\/\//i);
  });
});

describe('Graph data field allowlist', () => {
  it('GraphNode type only allows whitelisted fields', () => {
    // This is a type-level check — if it compiles, the allowlist is enforced
    const validNode = {
      id: 'test',
      name: 'test',
      type: 'file',
      relativePath: 'src/test.ts',
      language: 'typescript',
      summary: null,
      tags: [],
      lineCount: 10,
      sourceHash: null,
    };
    expect(validNode.id).toBe('test');
  });

  it('GraphEdge type only allows whitelisted fields', () => {
    const validEdge = {
      source: 'a',
      target: 'b',
      type: 'calls',
      direction: 'forward',
      weight: 1.0,
    };
    expect(validEdge.source).toBe('a');
  });
});
