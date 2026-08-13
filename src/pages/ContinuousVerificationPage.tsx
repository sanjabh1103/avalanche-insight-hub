import { useCallback, useEffect, useState } from 'react';

import ContinuousVerificationDashboard from '@/components/ContinuousVerificationDashboard';
import RoleAccessGate, { type AccessState } from '@/components/RoleAccessGate';
import {
  loadContinuousVerificationDashboard,
  type ContinuousVerificationLoadResult,
} from '@/lib/continuousVerification';

export default function ContinuousVerificationPage() {
  const [result, setResult] = useState<ContinuousVerificationLoadResult>({ status: 'available' });
  const [accessState, setAccessState] = useState<AccessState>('loading');

  const handleAccessStateChange = useCallback((state: AccessState) => {
    setAccessState(state);
  }, []);

  useEffect(() => {
    if (accessState !== 'ready') return;
    let active = true;
    void loadContinuousVerificationDashboard().then((next) => {
      if (active) setResult(next);
    });
    return () => {
      active = false;
    };
  }, [accessState]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <RoleAccessGate
        allowedRoles={['scientist', 'admin']}
        gateTitle="Continuous Verification Access"
        routeLabel="continuous verification dashboard"
        sessionLabel="Scientist Session"
        onAccessStateChange={handleAccessStateChange}
      >
        <ContinuousVerificationDashboard
          data={result.data}
          status={result.status}
          unavailableReason={result.unavailable_reason}
          truncatedTables={result.truncated_tables}
        />
      </RoleAccessGate>
    </div>
  );
}
