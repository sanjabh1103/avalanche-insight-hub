import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import PirPanjalPocEvidenceCard from '@/components/PirPanjalPocEvidenceCard';
import { isPirPanjalPocRegion, PIR_PANJAL_POC_EVIDENCE } from '@/lib/pirPanjalPocEvidence';

describe('PirPanjalPocEvidenceCard', () => {
  it('renders the frozen candidate scope and pipeline-proof boundary', () => {
    render(<PirPanjalPocEvidenceCard />);

    expect(screen.getByTestId('pir-panjal-poc-evidence-card')).toBeTruthy();
    expect(screen.getByText(/Pipeline proof only/i)).toBeTruthy();
    expect(screen.getByText(/3,200–4,000 m/i)).toBeTruthy();
    expect(screen.getByText(/48h · 1 member/i)).toBeTruthy();
    expect(screen.getByText(/storm \/ new-snow/i)).toBeTruthy();
    expect(screen.getByText(/SNOWPACK native profile/i)).toBeTruthy();
    expect(screen.getByText(/RF comparison baseline/i)).toBeTruthy();
    expect(screen.getByText(/withheld/i)).toBeTruthy();
    expect(screen.getAllByText(/direct snowfall is unavailable/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Verified hosted candidate · corrected v2 forcing/i)).toBeTruthy();
    expect(screen.getByText(/36.885404° NE aspect/i)).toBeTruthy();
    expect(screen.getByText(/Target computational scale/i)).toBeTruthy();
    expect(screen.getByText(/~25 km/i)).toBeTruthy();
    expect(screen.getByText(/Official-warning eligible: no/i)).toBeTruthy();
  });

  it('shows the hosted candidate identity and limitations instead of live-warning language', () => {
    render(<PirPanjalPocEvidenceCard />);

    expect(screen.getByText(/poc-2026-08-13T0636-pir_panjal_nw_himalaya-middle-d49739/i)).toBeTruthy();
    expect(screen.getByText(/add242aeeb477fc009b0387e2206c145bbbf02f77b3e16fd8a54e5abd0fa3c9e/i)).toBeTruthy();
    expect(screen.getByText(/producer and independent consumer release gates passed/i)).toBeTruthy();
    expect(screen.getByText(/provenance-only/i)).toBeTruthy();
    expect(screen.getByText(/not a site-specific accuracy label/i)).toBeTruthy();
    expect(screen.getByText(/Native log warnings: none/i)).toBeTruthy();
    expect(screen.getAllByText(/re-accumulated by pinned MeteoIO/i)).toHaveLength(2);
    expect(PIR_PANJAL_POC_EVIDENCE.limitations).toContain(
      'The v2 corrected forcing uses ILWR from a named cloud-cover/temperature engineering parametrization in the forcing adapter before the MeteoIO/native SNOWPACK run; Open-Meteo terrestrial_radiation is provenance-only and is not mapped as ILWR.',
    );
    expect(PIR_PANJAL_POC_EVIDENCE.limitations.join(' ')).not.toMatch(/computed by MeteoIO/i);
    expect(PIR_PANJAL_POC_EVIDENCE.limitations.join(' ')).toMatch(/customer acknowledgment.*was received/i);
    expect(PIR_PANJAL_POC_EVIDENCE.limitations.join(' ')).toMatch(/internal POC-only publication boundary remains in force/i);
    expect(screen.queryByText(/precipitation re-accumulation advisory/i)).toBeNull();
    expect(screen.queryByText(/official warning capability/i)).toBeNull();
  });

  it('only authorizes the card for the frozen Pir Panjal region key', () => {
    expect(isPirPanjalPocRegion('pir_panjal_nw_himalaya')).toBe(true);
    expect(isPirPanjalPocRegion('himalayas_nepal')).toBe(false);
    expect(isPirPanjalPocRegion(null)).toBe(false);
    expect(isPirPanjalPocRegion(undefined)).toBe(false);
  });
});
