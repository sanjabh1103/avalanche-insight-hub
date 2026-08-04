# Advisor Log

## Advisor Availability

- **Checked:** 2026-08-04T05:56:39Z
- **Wrapper path:** `/Users/sanjayb/codex-ecc-custom/skills/ecc-advisor/scripts/call_advisor.sh`
- **Fable dir:** `/Users/sanjayb/codex-ecc-custom/fable`
- **Status:** Available; review call returned successfully
- **advisor_available:** true

## Advisor Calls

| Call # | Timestamp | Session ID | Question | Result | Changed Plan? |
|---|---|---|---|---|---|
| 1 | 2026-08-04T05:56:39Z | — | Review residual public-release gaps and determine safe next action | NO-GO confirmed; perform local browser/evidence checks only; do not commit, deploy, unblock the map, or bypass approval/provenance gates | Yes — limited remaining work to local verification and handoff updates |
| 2 | 2026-08-04 | — | Reassess corrected provenance evidence after the dirty-path overlap was found | Attestation alone was insufficient; produce a genuinely clean scoped checkout/export and keep manifests honest | Yes — added isolated clean-snapshot workflow |
| 3 | 2026-08-04T06:58:15Z | — | Review final approved graph-only candidate and residual release gate | Approved local candidate; only public host deployment and live URL verification remain | Yes — stop local changes and keep map blocked |

## Notes

- The ECC advisor wrapper was available and returned successfully for all recorded calls.
- The final advisor review accepted the local graph-only candidate against the cited hashes and gates.
- The main source repository was not modified; deployment remains a separate release action.
- The public content review packet (`handoff/PUBLIC_CONTENT_REVIEW_PACKET.md`) is the human review gate, not the advisor.
