export const POC_REGION_KEY = "pir_panjal_nw_himalaya";
export const POC_ELEVATION_BAND = "middle";
export const POC_HORIZON_HOURS = 48;
export const POC_ENSEMBLE_MEMBERS = 1;

export interface PocSnowpackRequest {
  region_key: string;
  elevation_band: string;
  horizon_hours: number;
  ensemble_members: number;
  poc_mode: boolean;
  decision_record_sha256: string;
  toolchain_manifest_id?: string;
}

export function validateRequest(body: Partial<PocSnowpackRequest>): string[] {
  const errors: string[] = [];

  if (body.region_key !== POC_REGION_KEY) {
    errors.push(`region_key must equal ${POC_REGION_KEY}`);
  }
  if (body.elevation_band !== POC_ELEVATION_BAND) {
    errors.push(`elevation_band must equal ${POC_ELEVATION_BAND}`);
  }
  if (body.horizon_hours !== POC_HORIZON_HOURS) {
    errors.push(`horizon_hours must equal ${POC_HORIZON_HOURS}`);
  }
  if (body.ensemble_members !== POC_ENSEMBLE_MEMBERS) {
    errors.push(`ensemble_members must equal ${POC_ENSEMBLE_MEMBERS}`);
  }
  if (body.poc_mode !== true) {
    errors.push("poc_mode must be true for the Pir Panjal POC route");
  }
  if (
    typeof body.decision_record_sha256 !== "string" ||
    !/^[0-9a-fA-F]{64}$/.test(body.decision_record_sha256)
  ) {
    errors.push("decision_record_sha256 must be an exact 64-character SHA-256 digest");
  }
  return errors;
}

export function generateRunId(
  regionKey: string,
  elevationBand: string,
): string {
  const ts = new Date().toISOString().replace(/[:.]/g, "").slice(0, 15);
  const rand = Math.random().toString(36).slice(2, 8);
  return `poc-${ts}-${regionKey}-${elevationBand}-${rand}`;
}
