"""Partner-format bulletin generator.

Generates a shadow Partner-format bulletin from forecast cells, matching
the daily district/altitude structure of official Partner bulletins.

Output structure:
  - Daily district/altitude danger level (1-5)
  - Snow condition summary
  - Avalanche likelihood description
  - Preferred action advice
  - Separate evidence map and 72-hour scenario layer
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

DANGER_LABELS = {
    1: 'low',
    2: 'moderate',
    3: 'high',
    4: 'very_high',
    5: 'extreme',
}

LIKELIHOOD_LABELS = {
    1: 'unlikely',
    2: 'possible',
    3: 'likely',
    4: 'very_likely',
    5: 'certain',
}

ACTION_ADVICE = {
    1: 'Generally favourable conditions. Travel possible in most terrain.',
    2: 'Moderate conditions. Avoid steep terrain in identified avalanche paths.',
    3: 'High danger. Avoid steep slopes (>30°). Travel only on gentle terrain.',
    4: 'Very high danger. Avoid all avalanche terrain. Travel not recommended.',
    5: 'Extreme danger. Avoid all mountain terrain. Stay in safe areas only.',
}


@dataclass
class PartnerBulletinOutput:
    """Shadow Partner-format bulletin for a single district/altitude band."""
    bulletin_date: date
    district: str
    altitude_band: str
    danger_level: int
    danger_label: str
    snow_condition: str
    avalanche_likelihood: str
    preferred_action: str
    hazard_level: int
    impact_risk_level: int
    evidence_map: dict[str, Any] = field(default_factory=dict)
    scenario_72h: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'schema_version': 'Partner-shadow-bulletin/v1',
            'bulletin_date': self.bulletin_date.isoformat(),
            'district': self.district,
            'altitude_band': self.altitude_band,
            'danger_level': self.danger_level,
            'danger_label': self.danger_label,
            'snow_condition': self.snow_condition,
            'avalanche_likelihood': self.avalanche_likelihood,
            'preferred_action': self.preferred_action,
            'hazard_level': self.hazard_level,
            'impact_risk_level': self.impact_risk_level,
            'evidence_map': self.evidence_map,
            'scenario_72h': self.scenario_72h,
            'provenance': 'avalanche_insight_hub_shadow',
        }


def generate_shadow_bulletin(
    cells: list[dict[str, Any]],
    *,
    district: str,
    altitude_band: str,
    bulletin_date: date,
) -> PartnerBulletinOutput | None:
    """Generate a shadow Partner-format bulletin from forecast cells.

    Aggregates cell-level hazard and impact-risk into a district/altitude
    bulletin matching Partner's daily format.
    """
    if not cells:
        return None

    ready_cells = [c for c in cells if c.get('status') == 'ready']
    if not ready_cells:
        return None

    # Aggregate: take max danger level across cells
    max_risk = max(int(c.get('risk_score', 0)) for c in ready_cells)
    max_hazard = max(int(c.get('risk_score', 0)) for c in ready_cells)
    max_impact = max(int(c.get('impact_risk_level', 0)) for c in ready_cells)

    # Snow condition summary
    snow_depths = [c.get('weather_inputs', {}).get('snow_depth_cm', 0) for c in ready_cells]
    snowfalls = [c.get('weather_inputs', {}).get('snowfall_24h_cm', 0) for c in ready_cells]
    avg_snow_depth = sum(snow_depths) / len(snow_depths) if snow_depths else 0
    avg_snowfall = sum(snowfalls) / len(snowfalls) if snowfalls else 0

    if avg_snowfall > 10:
        snow_condition = f'Fresh snow accumulation ({avg_snowfall:.0f}cm in 24h)'
    elif avg_snow_depth > 50:
        snow_condition = f'Deep snowpack ({avg_snow_depth:.0f}cm)'
    else:
        snow_condition = f'Moderate snowpack ({avg_snow_depth:.0f}cm)'

    # Evidence map
    evidence_map = {
        'cell_count': len(ready_cells),
        'avg_probability': sum(float(c.get('probability', 0)) for c in ready_cells) / len(ready_cells),
        'max_probability': max(float(c.get('probability', 0)) for c in ready_cells),
        'avg_impact_score': sum(float(c.get('impact_risk_score', 0)) for c in ready_cells) / len(ready_cells),
    }

    # 72-hour scenario
    scenario_72h = {
        'horizon_hours': 72,
        'trend': 'stable' if max_risk <= 2 else 'increasing' if max_risk >= 4 else 'watch',
        'peak_danger_level': max_risk,
    }

    return PartnerBulletinOutput(
        bulletin_date=bulletin_date,
        district=district,
        altitude_band=altitude_band,
        danger_level=max_risk,
        danger_label=DANGER_LABELS.get(max_risk, 'unknown'),
        snow_condition=snow_condition,
        avalanche_likelihood=LIKELIHOOD_LABELS.get(max_risk, 'unknown'),
        preferred_action=ACTION_ADVICE.get(max_risk, 'Consult official Partner bulletin.'),
        hazard_level=max_hazard,
        impact_risk_level=max_impact,
        evidence_map=evidence_map,
        scenario_72h=scenario_72h,
    )
