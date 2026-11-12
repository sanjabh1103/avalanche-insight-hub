"""Source and resolution registry for the open-forcing research lane.

The registry describes permitted roles and evidence limits. It does not fetch
data or assert that a provider's terms are satisfied; a release manifest must
carry the reviewed licence identifier and content hash for every snapshot.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Iterable

from .contracts import OpenForcingContractError, SourceSnapshot


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    product: str
    role: str
    native_resolution_m: float | None
    nominal_cadence: str
    latency_description: str
    license_review_id: str
    quantitative_allowed: bool
    provider: str
    requires_exact_model_run: bool = True
    research_only: bool = True

    def validate(self) -> None:
        if not self.source_id.strip() or not self.product.strip() or not self.role.strip():
            raise OpenForcingContractError("source definitions require source_id, product and role")
        if self.native_resolution_m is not None and self.native_resolution_m <= 0:
            raise OpenForcingContractError("native_resolution_m must be positive when provided")
        if not self.nominal_cadence.strip() or not self.latency_description.strip():
            raise OpenForcingContractError("cadence and latency descriptions are required")
        if not self.license_review_id.strip() or not self.provider.strip():
            raise OpenForcingContractError("license_review_id and provider are required")
        if not self.research_only:
            raise OpenForcingContractError("source definitions must remain research_only")


DEFAULT_SOURCE_DEFINITIONS: tuple[SourceDefinition, ...] = (
    SourceDefinition(
        source_id="open_meteo_nwp",
        product="selected NWP model",
        role="current meteorological forcing",
        native_resolution_m=None,
        nominal_cadence="model-dependent hourly fields",
        latency_description="model-run dependent; record run metadata",
        license_review_id="open_meteo_terms_review_required",
        quantitative_allowed=True,
        provider="open-meteo-single-runs",
    ),
    SourceDefinition(
        source_id="era5_land",
        product="ERA5-Land hourly reanalysis",
        role="backfill, restart initialization and retrospective comparison",
        native_resolution_m=9000.0,
        nominal_cadence="hourly",
        latency_description="preliminary updates approximately five days behind real time",
        license_review_id="copernicus_licence_review_required",
        quantitative_allowed=True,
        provider="ECMWF/Copernicus via Open-Meteo archive",
    ),
    SourceDefinition(
        source_id="gpm_imerg_early",
        product="IMERG Early precipitation",
        role="precipitation cross-check and event evidence",
        native_resolution_m=10000.0,
        nominal_cadence="30 minutes",
        latency_description="approximately four-hour early latency",
        license_review_id="nasa_gpm_terms_review_required",
        quantitative_allowed=True,
        provider="NASA GPM",
    ),
    SourceDefinition(
        source_id="srtm_dem",
        product="SRTM elevation model",
        role="terrain geometry and downscaling support",
        native_resolution_m=30.0,
        nominal_cadence="static",
        latency_description="static source; record tile version",
        license_review_id="nasa_usgs_terms_review_required",
        quantitative_allowed=True,
        provider="NASA/USGS",
        requires_exact_model_run=False,
    ),
    SourceDefinition(
        source_id="mod10a1",
        product="MODIS daily snow cover science product",
        role="physical snow-cover validation",
        native_resolution_m=500.0,
        nominal_cadence="daily",
        latency_description="observation and processing dependent",
        license_review_id="nasa_nsidc_terms_review_required",
        quantitative_allowed=True,
        provider="NASA/NSIDC",
    ),
    SourceDefinition(
        source_id="sentinel1_sar",
        product="Sentinel-1 SAR science product",
        role="shadow wet-snow and surface-evidence validation",
        native_resolution_m=None,
        nominal_cadence="revisit and acquisition dependent",
        latency_description="acquisition, processing and access dependent",
        license_review_id="copernicus_licence_review_required",
        quantitative_allowed=True,
        provider="Copernicus",
    ),
    SourceDefinition(
        source_id="sentinel2_optical",
        product="Sentinel-2 optical science product",
        role="shadow snow-cover validation",
        native_resolution_m=None,
        nominal_cadence="revisit and cloud dependent",
        latency_description="acquisition, cloud and processing dependent",
        license_review_id="copernicus_licence_review_required",
        quantitative_allowed=True,
        provider="Copernicus",
    ),
    SourceDefinition(
        source_id="gibs_visualization",
        product="NASA GIBS visualization tile",
        role="display and visual context only",
        native_resolution_m=None,
        nominal_cadence="layer dependent",
        latency_description="visualization processing dependent",
        license_review_id="nasa_gibs_acknowledgement_review_required",
        quantitative_allowed=False,
        provider="NASA GIBS",
        requires_exact_model_run=False,
    ),
)


class SourceRegistry:
    """Validated source definitions with explicit quantitative-use policy."""

    def __init__(self, definitions: Iterable[SourceDefinition] = DEFAULT_SOURCE_DEFINITIONS) -> None:
        values = tuple(definitions)
        for definition in values:
            definition.validate()
        ids = [definition.source_id for definition in values]
        if len(set(ids)) != len(ids):
            raise OpenForcingContractError("source_id values must be unique")
        self._definitions = {definition.source_id: definition for definition in values}

    def get(self, source_id: str) -> SourceDefinition:
        try:
            return self._definitions[source_id]
        except KeyError as exc:
            raise OpenForcingContractError(f"unregistered source: {source_id}") from exc

    def assert_quantitative_allowed(self, source_id: str) -> None:
        definition = self.get(source_id)
        if not definition.quantitative_allowed:
            raise OpenForcingContractError(
                f"{source_id} is visualization/context-only and cannot provide quantitative inputs"
            )

    def validate_snapshot(self, snapshot: SourceSnapshot, *, require_approved_license: bool = False) -> None:
        definition = self.get(snapshot.source_id)
        snapshot.validate()
        if definition.requires_exact_model_run and (not snapshot.model_id.strip() or not snapshot.run_id.strip()):
            raise OpenForcingContractError(
                f"{snapshot.source_id} requires exact provider model and run metadata"
            )
        if snapshot.provider != definition.provider:
            raise OpenForcingContractError(
                f"provider mismatch for {snapshot.source_id}: {snapshot.provider!r}"
            )
        if require_approved_license and snapshot.license_review_status != "approved":
            raise OpenForcingContractError(
                f"{snapshot.source_id} is not license-approved for quantitative execution"
            )
        self.assert_quantitative_allowed(snapshot.source_id)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))


@dataclass(frozen=True)
class ForcingSnapshotManifest:
    """Replay manifest linking source snapshots to a computational grid."""

    snapshots: tuple[SourceSnapshot, ...]
    target_crs: str
    target_resolution_m: float
    effective_resolution_m: float
    grid_manifest_hash: str
    missingness_policy: str = "fail_or_hold"

    def validate(
        self,
        registry: SourceRegistry | None = None,
        *,
        require_approved_license: bool = False,
    ) -> None:
        selected_registry = registry or SourceRegistry()
        if not self.snapshots:
            raise OpenForcingContractError("at least one source snapshot is required")
        if not self.target_crs.strip():
            raise OpenForcingContractError("target_crs is required")
        if self.target_resolution_m <= 0 or self.effective_resolution_m <= 0:
            raise OpenForcingContractError("target and effective resolutions must be positive")
        if not _SHA256_RE.fullmatch(self.grid_manifest_hash.lower()):
            raise OpenForcingContractError("grid_manifest_hash must be a SHA-256 digest")
        if self.effective_resolution_m < self.target_resolution_m:
            raise OpenForcingContractError(
                "effective_resolution_m cannot claim finer information than target_resolution_m"
            )
        if self.missingness_policy not in {"fail", "hold", "fail_or_hold"}:
            raise OpenForcingContractError("unsupported missingness policy")
        seen: set[str] = set()
        for snapshot in self.snapshots:
            selected_registry.validate_snapshot(
                snapshot,
                require_approved_license=require_approved_license,
            )
            if snapshot.snapshot_id in seen:
                raise OpenForcingContractError("duplicate source snapshot in manifest")
            seen.add(snapshot.snapshot_id)
            selected_registry.assert_quantitative_allowed(snapshot.source_id)

    @property
    def manifest_hash(self) -> str:
        self.validate()
        payload = {
            "target_crs": self.target_crs,
            "target_resolution_m": self.target_resolution_m,
            "effective_resolution_m": self.effective_resolution_m,
            "grid_manifest_hash": self.grid_manifest_hash,
            "missingness_policy": self.missingness_policy,
            "snapshots": [
                {
                    "source_id": item.source_id,
                    "product": item.product,
                    "issue_time": item.issue_time.isoformat(),
                    "valid_time": item.valid_time.isoformat(),
                    "retrieved_at": item.retrieved_at.isoformat(),
                    "source_as_of": item.source_as_of.isoformat(),
                    "native_resolution_m": item.native_resolution_m,
                    "license_id": item.license_id,
                    "provider": item.provider,
                    "model_id": item.model_id,
                    "run_id": item.run_id,
                    "lead_time_hours": item.lead_time_hours,
                    "assimilation_disclosure": item.assimilation_disclosure,
                    "license_review_status": item.license_review_status,
                    "research_only": item.research_only,
                    "content_sha256": item.content_sha256.lower(),
                }
                for item in sorted(self.snapshots, key=lambda value: value.snapshot_id)
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
