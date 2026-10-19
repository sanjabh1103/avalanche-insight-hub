import { describe, expect, it } from 'vitest';
import { isLoopbackAddress, safeResolvePath } from '../../../vite-plugin-code-api';

describe('safe-code-api server guards', () => {
  it('accepts loopback addresses and rejects network addresses', () => {
    expect(isLoopbackAddress('127.0.0.1')).toBe(true);
    expect(isLoopbackAddress('::1')).toBe(true);
    expect(isLoopbackAddress('::ffff:127.0.0.1')).toBe(true);
    expect(isLoopbackAddress('192.168.1.10')).toBe(false);
    expect(isLoopbackAddress(undefined)).toBe(false);
  });

  it('canonicalizes an allowlisted source file', () => {
    expect(safeResolvePath('backend/common/features.py')).toMatch(/backend\/common\/features\.py$/);
    expect(safeResolvePath('src/App.tsx')).toMatch(/src\/App\.tsx$/);
  });

  it('rejects traversal, blocked directories, and binary paths', () => {
    expect(safeResolvePath('backend/../.env')).toBeNull();
    expect(safeResolvePath('backend/%2e%2e/.env')).toBeNull();
    expect(safeResolvePath('node_modules/react/index.js')).toBeNull();
    expect(safeResolvePath('backend/model.pt')).toBeNull();
    expect(safeResolvePath('.git/config')).toBeNull();
  });

  it('rejects all AGENTS.md denylist zone files (CRITICAL security boundary)', () => {
    // These 8 denylist zones must never be accessible via the source API
    expect(safeResolvePath('backend/common/verification_exit_gates.py')).toBeNull();
    expect(safeResolvePath('backend/common/sar_acceptance_policy.py')).toBeNull();
    expect(safeResolvePath('backend/common/label_governance.py')).toBeNull();
    expect(safeResolvePath('backend/common/risk_math.py')).toBeNull();
    expect(safeResolvePath('backend/train_model.py')).toBeNull();
    expect(safeResolvePath('supabase/config.toml')).toBeNull();
    expect(safeResolvePath('backend/common/snowpack_physics.py')).toBeNull();
    // Denylist directory
    expect(safeResolvePath('backend/reproduction/run_all.py')).toBeNull();
    expect(safeResolvePath('backend/reproduction/subdir/file.py')).toBeNull();
  });

  it('rejects denylist files regardless of case or path separator', () => {
    expect(safeResolvePath('BACKEND/COMMON/RISK_MATH.PY')).toBeNull();
    expect(safeResolvePath('backend\\common\\risk_math.py')).toBeNull();
  });
});
