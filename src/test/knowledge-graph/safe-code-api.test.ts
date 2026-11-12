import { describe, it, expect } from 'vitest';
import {
  validateCodePath,
  CODE_API_LIMITS,
} from '@/lib/knowledge-graph/safeCodeApi';

describe('safeCodeApi path validation', () => {
  it('allows paths in allowlisted directories', () => {
    expect(validateCodePath('backend/common/features.py').valid).toBe(true);
    expect(validateCodePath('src/App.tsx').valid).toBe(true);
    expect(validateCodePath('docs/MVP4/progress_codex.md').valid).toBe(true);
    expect(validateCodePath('supabase/functions/_shared/auth.ts').valid).toBe(true);
    expect(validateCodePath('tests/e2e/smoke.spec.ts').valid).toBe(true);
  });

  it('rejects paths outside allowlisted directories', () => {
    expect(validateCodePath('.env').valid).toBe(false);
    expect(validateCodePath('package.json').valid).toBe(false);
    expect(validateCodePath('vite.config.ts').valid).toBe(false);
    expect(validateCodePath('some/random/file.py').valid).toBe(false);
  });

  it('rejects path traversal attempts', () => {
    expect(validateCodePath('backend/../.env').valid).toBe(false);
    expect(validateCodePath('backend/../../etc/passwd').valid).toBe(false);
    expect(validateCodePath('../secret.key').valid).toBe(false);
  });

  it('rejects absolute paths', () => {
    expect(validateCodePath('/etc/passwd').valid).toBe(false);
    expect(validateCodePath('C:/Windows/System32/config').valid).toBe(false);
  });

  it('rejects null bytes', () => {
    expect(validateCodePath('backend/common\0/../../../.env').valid).toBe(false);
  });

  it('rejects blocked file extensions', () => {
    expect(validateCodePath('backend/.env').valid).toBe(false);
    expect(validateCodePath('backend/secret.key').valid).toBe(false);
    expect(validateCodePath('backend/cert.pem').valid).toBe(false);
    expect(validateCodePath('backend/model.pt').valid).toBe(false);
    expect(validateCodePath('backend/cache.sqlite').valid).toBe(false);
  });

  it('rejects blocked directories', () => {
    expect(validateCodePath('node_modules/react/index.js').valid).toBe(false);
    expect(validateCodePath('.git/config').valid).toBe(false);
    expect(validateCodePath('.venv/lib/python/site.py').valid).toBe(false);
    expect(validateCodePath('dist/index.html').valid).toBe(false);
    expect(validateCodePath('__pycache__/module.cpython-312.pyc').valid).toBe(false);
  });

  it('allows .env.example for documentation', () => {
    expect(validateCodePath('backend/.env.example').valid).toBe(true);
  });

  it('exposes limits as constants', () => {
    expect(CODE_API_LIMITS.MAX_LINES).toBe(200);
    expect(CODE_API_LIMITS.MAX_BYTES).toBe(256 * 1024);
    expect(CODE_API_LIMITS.ALLOWED_PREFIXES).toContain('backend/');
    expect(CODE_API_LIMITS.BLOCKED_EXTENSIONS).toContain('.env');
  });
});
