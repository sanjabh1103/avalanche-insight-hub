# Himalayan Partner Source Manifest Template

Decision: `source_manifest_template_written_pending_partner_sources`

Use this JSON manifest beside the partner evidence CSVs. Every `source_ref` hash used in the CSV templates must appear here before the evidence can support a Himalayan accuracy-readiness claim.

Schema version: `himalayan_accuracy_partner_source_manifest_v1`
Validation policy: `himalayan_partner_evidence_policy_v2_coverage_references_vocab_freshness_sourcehash_govrefs_sourcemanifest`
Maximum source-review age: `365` days

| Field | Requirement |
|---|---|
| `source_id` | Stable partner-local identifier for the source package. |
| `sha256` | 64-character SHA-256 digest referenced by partner evidence `source_ref` values. |
| `source_owner` | Institution, agency, or data owner responsible for the source package. |
| `dataset_name` | Human-readable source dataset or package name. |
| `license_scope` | Controlled scope that must support research validation. |
| `date_range` | Date coverage of the source package, preferably `YYYY-MM-DD/YYYY-MM-DD`. |
| `review_status` | Must be `reviewed`. |
| `reviewer_id` | Named reviewer, review board, or partner review identifier. |
| `reviewed_at` | ISO-8601 review timestamp, no more than the maximum review age. |
| `evidence_package_ref` | SHA-256-qualified reference to the review or evidence package. |

Allowed license scopes for research validation:

`cc_by_nc_research_only`, `commercial_deployment_approved`, `internal_research_validation`, `partner_restricted_research`, `research_validation_only`

Example `source_ref` values:

- Hash only: `sha256:<64-hex-sha256-of-source-package>`
- Local file: `file:raw_sources/source_package.csv#sha256=<64-hex-sha256-of-source-package>`
