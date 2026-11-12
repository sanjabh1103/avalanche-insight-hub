import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { TechnicalArtifactBadge } from '@/components/TechnicalArtifactBadge';

describe('TechnicalArtifactBadge', () => {
  it('renders nothing when technicalArtifactEnabled is false', () => {
    const { container } = render(
      <TechnicalArtifactBadge technicalArtifactEnabled={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders Technical Artifact badge when mode is technical_artifact and path exists', () => {
    const { getByText } = render(
      <TechnicalArtifactBadge
        artifactMode="technical_artifact"
        artifactPath="/artifacts/run_derived_artifact.json"
        technicalArtifactEnabled={true}
      />
    );
    expect(getByText('Technical Artifact')).toBeTruthy();
  });

  it('renders Artifact Blocked badge when mode is blocked', () => {
    const { getByText } = render(
      <TechnicalArtifactBadge
        artifactMode="blocked"
        artifactPath="/artifacts/run_derived_artifact.json"
        technicalArtifactEnabled={true}
      />
    );
    expect(getByText('Artifact Blocked')).toBeTruthy();
  });

  it('renders Artifact Missing badge when artifactError is set', () => {
    const { getByText } = render(
      <TechnicalArtifactBadge
        artifactMode="technical_artifact"
        artifactError="File not found"
        technicalArtifactEnabled={true}
      />
    );
    expect(getByText('Artifact Missing')).toBeTruthy();
  });

  it('renders Artifact Missing badge when artifactPath is missing', () => {
    const { getByText } = render(
      <TechnicalArtifactBadge
        artifactMode="technical_artifact"
        technicalArtifactEnabled={true}
      />
    );
    expect(getByText('Artifact Missing')).toBeTruthy();
  });

  it('renders nothing for unknown artifact mode', () => {
    const { container } = render(
      <TechnicalArtifactBadge
        artifactMode="unknown_mode"
        artifactPath="/artifacts/test.json"
        technicalArtifactEnabled={true}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('tooltip content shows run ID and truncated SHA when provided', () => {
    const { getByTestId } = render(
      <TechnicalArtifactBadge
        artifactMode="technical_artifact"
        artifactPath="/artifacts/run_derived_artifact.json"
        technicalArtifactEnabled={true}
        artifactId="rda_test-run-001_abc123def456"
        artifactSha256="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        runId="test-run-001"
      />
    );
    const detail = getByTestId('artifact-detail');
    expect(detail.textContent).toContain('test-run-001');
    expect(detail.textContent).toContain('abcdef012345');
  });

  it('renders shadow label text when shadowLabel is true', () => {
    const { getByTestId } = render(
      <TechnicalArtifactBadge
        artifactMode="technical_artifact"
        artifactPath="/artifacts/run_derived_artifact.json"
        technicalArtifactEnabled={true}
        shadowLabel={true}
      />
    );
    const detail = getByTestId('artifact-detail');
    expect(detail.textContent).toContain('Research shadow output — not an official warning');
  });

  it('missing artifactSha256 with mode technical_artifact still renders badge but detail shows unavailable', () => {
    const { getByText, getByTestId } = render(
      <TechnicalArtifactBadge
        artifactMode="technical_artifact"
        artifactPath="/artifacts/run_derived_artifact.json"
        technicalArtifactEnabled={true}
      />
    );
    expect(getByText('Technical Artifact')).toBeTruthy();
    const detail = getByTestId('artifact-detail');
    expect(detail.textContent).toContain('unavailable');
  });
});
