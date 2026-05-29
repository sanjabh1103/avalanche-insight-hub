import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const {
  getSessionMock,
  getUserMock,
  signInWithPasswordMock,
  signOutMock,
  onAuthStateChangeMock,
  unsubscribeMock,
} = vi.hoisted(() => ({
  getSessionMock: vi.fn(),
  getUserMock: vi.fn(),
  signInWithPasswordMock: vi.fn(),
  signOutMock: vi.fn(),
  onAuthStateChangeMock: vi.fn(),
  unsubscribeMock: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/integrations/supabase/client', () => ({
  supabase: {
    auth: {
      getSession: getSessionMock,
      getUser: getUserMock,
      signInWithPassword: signInWithPasswordMock,
      signOut: signOutMock,
      onAuthStateChange: onAuthStateChangeMock,
    },
  },
}));

import PartnerEvidenceReadinessDashboard from '@/components/PartnerEvidenceReadinessDashboard';
import {
  PARTNER_SOURCE_MANIFEST_FILENAME,
  REQUIRED_PARTNER_EVIDENCE_FILES,
  type PartnerEvidenceRequirement,
} from '@/lib/partnerEvidenceReadiness';
import ScientistPartnerIntakePage from '@/pages/ScientistPartnerIntakePage';

function csv(requirement: PartnerEvidenceRequirement): File {
  const row = requirement.requiredColumns.map((column) => {
    if (column === 'review_status') return 'reviewed';
    if (column === 'license_scope') return 'research_validation_only';
    if (column === 'source_ref') return 'b'.repeat(64);
    return `${column}_value`;
  });
  return new File(
    [`${requirement.requiredColumns.join(',')}\n${row.join(',')}\n`],
    requirement.filename,
    { type: 'text/csv' },
  );
}

function packageFiles(): File[] {
  return [
    new File(['{"sources": []}'], PARTNER_SOURCE_MANIFEST_FILENAME, { type: 'application/json' }),
    ...REQUIRED_PARTNER_EVIDENCE_FILES.map(csv),
  ];
}

describe('ScientistPartnerIntakePage', () => {
  beforeEach(() => {
    const scientist = {
      id: 'scientist-user',
      email: 'scientist@insight-hub.local',
      app_metadata: { roles: ['scientist'] },
    };
    getSessionMock.mockReset();
    getUserMock.mockReset();
    onAuthStateChangeMock.mockReset();
    unsubscribeMock.mockReset();
    signInWithPasswordMock.mockReset();
    signOutMock.mockReset();
    getSessionMock.mockResolvedValue({
      data: { session: { user: scientist } },
      error: null,
    });
    getUserMock.mockResolvedValue({
      data: { user: scientist },
      error: null,
    });
    onAuthStateChangeMock.mockReturnValue({
      data: {
        subscription: {
          unsubscribe: unsubscribeMock,
        },
      },
    });
  });

  it('renders local partner package preflight and preserves claim locks', async () => {
    render(
      <MemoryRouter>
        <ScientistPartnerIntakePage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('Partner Evidence Intake')).toBeTruthy();
    expect(await screen.findByText('Local Package Preflight')).toBeTruthy();

    fireEvent.change(screen.getByLabelText('Upload partner evidence package files'), {
      target: { files: packageFiles() },
    });

    expect(await screen.findByText('partner_intake_preflight_ready_for_cli_triage')).toBeTruthy();
    expect(screen.getByText('Export JSON')).toBeTruthy();
    expect(screen.getByText('Export Markdown')).toBeTruthy();
    expect(screen.getByText(/production_scoring_allowed=false/i)).toBeTruthy();
    expect(screen.getByText(/himalayan_accuracy_claim_allowed=false/i)).toBeTruthy();
    await waitFor(() => expect(screen.getAllByText(/reviewed/i).length).toBeGreaterThan(0));
  });
});

describe('PartnerEvidenceReadinessDashboard', () => {
  it('summarizes readiness blockers and Colorado-to-Himalaya boundary', () => {
    render(
      <MemoryRouter>
        <PartnerEvidenceReadinessDashboard />
      </MemoryRouter>,
    );

    expect(screen.getByText('Himalayan Evidence Readiness')).toBeTruthy();
    expect(screen.getByText('station_metadata.csv')).toBeTruthy();
    expect(screen.getByText(/Colorado Rockies remains the live technical proof surface/i)).toBeTruthy();
    expect(screen.getByText(/himalayan_accuracy_claim_allowed=false/i)).toBeTruthy();
  });
});
