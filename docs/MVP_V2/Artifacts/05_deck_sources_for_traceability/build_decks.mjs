import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const screenshots = {
  workspace: 'assets/screenshots/2026-05-08_hosted-public_cell-full-grid-after-refresh.png',
  workspaceMobile: 'assets/screenshots/2026-05-08_hosted-public_mobile-cell-full-grid-after-refresh.png',
  workspaceFull: 'assets/screenshots/2026-05-07_hosted-public_workspace.png',
  share: 'assets/screenshots/2026-05-07_hosted-public_share-workflow.png',
  events: 'assets/screenshots/2026-05-07_hosted-public_events-workflow.png',
  adminGate: 'assets/screenshots/2026-05-07_hosted-admin-gate.png',
  adminAuth: 'assets/screenshots/2026-05-08_hosted-admin-auth-full-grid-run.png',
  uaStructural: 'assets/screenshots/ua-structural-overview.png',
  uaDomain: 'assets/screenshots/ua-domain-overview.png',
  uaActiveRf: 'assets/screenshots/ua-active-rf-layer.png',
  uaMtsLstm: 'assets/screenshots/ua-mts-lstm-layer.png',
  uaSarShadow: 'assets/screenshots/ua-sar-shadow-layer.png',
  uaSwiss: 'assets/screenshots/ua-swiss-ravafcast-layer.png',
  uaHimalayan: 'assets/screenshots/ua-himalayan-evidence-layer.png',
  uaEvaluation: 'assets/screenshots/ua-evaluation-governance-layer.png',
  uaModal: 'assets/screenshots/ua-modal-compute-layer.png',
  uaTests: 'assets/screenshots/ua-tests-ci-layer.png',
  uaBackend: 'assets/screenshots/ua-backend-support-layer.png',
};

const evidenceLabels = {
  live: 'Live platform',
  internal: 'Technical evidence',
  future: 'Research agenda',
};

const sharedCss = String.raw`
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=Nunito:wght@400;600;700;800&display=swap');

html, body {
  height: 100%;
  overflow-x: hidden;
}

html {
  scroll-snap-type: y mandatory;
  scroll-behavior: smooth;
}

* {
  box-sizing: border-box;
}

:root {
  --title-size: clamp(1.8rem, 4.8vw, 4.4rem);
  --h2-size: clamp(1.25rem, 2.8vw, 2.4rem);
  --h3-size: clamp(0.95rem, 1.9vw, 1.4rem);
  --body-size: clamp(0.8rem, 1.15vw, 1.05rem);
  --small-size: clamp(0.64rem, 0.9vw, 0.82rem);
  --slide-padding: clamp(1rem, 3vw, 3.2rem);
  --content-gap: clamp(0.7rem, 1.5vw, 1.5rem);
  --element-gap: clamp(0.45rem, 1vw, 0.95rem);
  --radius-lg: 1.6rem;
  --radius-md: 1rem;
  --radius-sm: 0.7rem;
  --shell-bg: #f4f1ea;
  --text-main: #0e1318;
  --text-soft: #48505a;
  --line-soft: rgba(14, 19, 24, 0.12);
  --line-strong: rgba(14, 19, 24, 0.22);
  --surface: rgba(255, 255, 255, 0.84);
  --surface-strong: rgba(255, 255, 255, 0.93);
  --ink-grid: rgba(14, 19, 24, 0.05);
  --shadow-soft: 0 24px 60px rgba(7, 10, 14, 0.08);
  --proof-live: #9f1d1d;
  --proof-internal: #134055;
  --proof-future: #0b6a61;
  --accent-main: #a11919;
  --accent-soft: rgba(161, 25, 25, 0.13);
  --accent-alt: #0b6a61;
  --accent-alt-soft: rgba(11, 106, 97, 0.14);
}

body {
  margin: 0;
  font-family: 'Nunito', 'Avenir Next', system-ui, sans-serif;
  color: var(--text-main);
  background:
    radial-gradient(circle at top left, rgba(161, 25, 25, 0.07), transparent 28%),
    radial-gradient(circle at top right, rgba(11, 106, 97, 0.06), transparent 24%),
    linear-gradient(180deg, #f7f4ee 0%, #f0ebe2 100%);
}

body.deck-collaboration {
  background:
    radial-gradient(circle at top left, rgba(11, 106, 97, 0.09), transparent 32%),
    radial-gradient(circle at top right, rgba(82, 112, 143, 0.06), transparent 24%),
    linear-gradient(180deg, #f6f3ed 0%, #eef2f0 100%);
}

body.deck-technical {
  --proof-live: #1c7c74;
  --proof-internal: #26373a;
  --proof-future: #7e9f35;
  --accent-main: #1c7c74;
  --accent-soft: rgba(28, 124, 116, 0.14);
  --accent-alt: #7e9f35;
  --accent-alt-soft: rgba(126, 159, 53, 0.15);
  background:
    radial-gradient(circle at top left, rgba(28, 124, 116, 0.10), transparent 30%),
    radial-gradient(circle at top right, rgba(126, 159, 53, 0.08), transparent 25%),
    linear-gradient(180deg, #f4f8f7 0%, #e9f0ee 100%);
}

body.deck-challenges {
  --proof-live: #2a7fa3;
  --proof-internal: #1f3340;
  --proof-future: #c9862b;
  --accent-main: #c9862b;
  --accent-soft: rgba(201, 134, 43, 0.14);
  --accent-alt: #2a7fa3;
  --accent-alt-soft: rgba(42, 127, 163, 0.14);
  background:
    radial-gradient(circle at top left, rgba(201, 134, 43, 0.10), transparent 30%),
    radial-gradient(circle at top right, rgba(42, 127, 163, 0.08), transparent 25%),
    linear-gradient(180deg, #f7fafb 0%, #edf4f6 100%);
}

body.deck-terms {
  --proof-live: #1c7c74;
  --proof-internal: #1e2a31;
  --proof-future: #c9862b;
  --accent-main: #1c7c74;
  --accent-soft: rgba(28, 124, 116, 0.13);
  --accent-alt: #c9862b;
  --accent-alt-soft: rgba(201, 134, 43, 0.14);
  background:
    radial-gradient(circle at top left, rgba(28, 124, 116, 0.08), transparent 30%),
    radial-gradient(circle at top right, rgba(201, 134, 43, 0.08), transparent 24%),
    linear-gradient(180deg, #f8f6f0 0%, #efece4 100%);
}

body.deck-ml-understanding {
  --proof-live: #1c7c74;
  --proof-internal: #1f3340;
  --proof-future: #9f6b19;
  --accent-main: #1c7c74;
  --accent-soft: rgba(28, 124, 116, 0.13);
  --accent-alt: #9f6b19;
  --accent-alt-soft: rgba(159, 107, 25, 0.14);
  background:
    radial-gradient(circle at top left, rgba(28, 124, 116, 0.10), transparent 30%),
    radial-gradient(circle at top right, rgba(159, 107, 25, 0.08), transparent 25%),
    linear-gradient(180deg, #f4f8f7 0%, #eef1ed 100%);
}

body::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(var(--ink-grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--ink-grid) 1px, transparent 1px);
  background-size: 44px 44px;
  opacity: 0.45;
}

.slide {
  width: 100vw;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  scroll-snap-align: start;
  display: flex;
  flex-direction: column;
  position: relative;
  isolation: isolate;
}

.slide::after {
  content: '';
  position: absolute;
  inset: clamp(0.7rem, 1.8vw, 1.2rem);
  border: 1px solid rgba(14, 19, 24, 0.08);
  border-radius: 1.8rem;
  pointer-events: none;
}

.slide-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-height: 100%;
  overflow: hidden;
  padding: var(--slide-padding);
  padding-bottom: calc(var(--slide-padding) + 1.65rem);
  gap: var(--content-gap);
  position: relative;
  z-index: 1;
}

.slide-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--content-gap);
}

.kicker-stack {
  display: grid;
  gap: 0.38rem;
}

.kicker {
  font-family: 'Archivo', 'Avenir Next Condensed', sans-serif;
  font-size: var(--small-size);
  letter-spacing: 0.26em;
  text-transform: uppercase;
  color: var(--accent-main);
}

.deck-collaboration .kicker {
  color: var(--accent-alt);
}

.eyebrow {
  font-size: var(--small-size);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.slide-title {
  margin: 0;
  font-family: 'Archivo', 'Avenir Next Condensed', sans-serif;
  font-size: var(--title-size);
  line-height: 0.94;
  max-width: 11ch;
}

.slide-subtitle {
  margin: 0;
  max-width: min(66ch, 94%);
  font-size: clamp(0.94rem, 1.4vw, 1.15rem);
  line-height: 1.48;
  color: var(--text-soft);
}

.proof-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 0.45rem;
  max-width: min(34rem, 48vw);
}

.proof-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.5rem 0.78rem;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: var(--small-size);
  font-weight: 800;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  background: var(--surface-strong);
  box-shadow: 0 8px 24px rgba(15, 19, 24, 0.08);
}

.proof-chip::before {
  content: '';
  width: 0.56rem;
  height: 0.56rem;
  border-radius: 999px;
  background: currentColor;
}

.proof-chip.live {
  color: var(--proof-live);
  border-color: rgba(159, 29, 29, 0.22);
}

.proof-chip.internal {
  color: var(--proof-internal);
  border-color: rgba(19, 64, 85, 0.22);
}

.proof-chip.future {
  color: var(--proof-future);
  border-color: rgba(11, 106, 97, 0.22);
}

.content-shell {
  flex: 1;
  display: grid;
  gap: var(--content-gap);
  min-height: 0;
}

.content-shell.split-2 {
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
}

.content-shell.split-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.stack {
  display: grid;
  gap: var(--element-gap);
  min-height: 0;
}

.stack.loose {
  gap: clamp(0.7rem, 1.3vw, 1.2rem);
}

.lead-panel,
.card,
.frame,
.matrix,
.metric-strip,
.timeline,
.diagram-shell {
  border: 1px solid var(--line-soft);
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
}

.lead-panel,
.matrix,
.diagram-shell {
  padding: clamp(0.9rem, 1.8vw, 1.2rem);
}

.lead-panel strong,
.card strong,
.matrix strong {
  font-weight: 800;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr));
  gap: clamp(0.55rem, 1.1vw, 0.9rem);
}

.card {
  padding: 0.95rem 1rem;
  display: grid;
  gap: 0.45rem;
}

.card h3,
.card h4,
.section-label,
.stat-number,
.matrix-title,
.phase-title {
  font-family: 'Archivo', 'Avenir Next Condensed', sans-serif;
}

.card h3,
.card h4 {
  margin: 0;
  font-size: var(--h3-size);
  line-height: 1.06;
}

.card p,
.card li,
.lead-panel p,
.matrix p,
.matrix li {
  margin: 0;
  font-size: var(--body-size);
  line-height: 1.42;
  color: var(--text-soft);
}

.bullet-list,
.compact-list {
  margin: 0;
  padding-left: 1.15rem;
  display: grid;
  gap: 0.42rem;
}

.bullet-list li,
.compact-list li {
  font-size: var(--body-size);
  line-height: 1.42;
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 165px), 1fr));
  gap: 0.7rem;
}

.stat {
  padding: 0.85rem 0.95rem;
  border-radius: 1rem;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(250, 247, 241, 0.84));
  border: 1px solid var(--line-soft);
  display: grid;
  gap: 0.25rem;
}

.deck-collaboration .stat {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(241, 248, 246, 0.84));
}

.stat-number {
  font-size: clamp(1.1rem, 2.4vw, 2.15rem);
  line-height: 0.96;
}

.stat-label {
  font-size: var(--small-size);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.frame {
  overflow: hidden;
  position: relative;
  min-height: 0;
}

.frame img {
  width: 100%;
  height: 100%;
  max-height: none;
  object-fit: cover;
  display: block;
}

.frame--wide {
  min-height: 41vh;
}

.frame--tall {
  min-height: 53vh;
}

.frame--compact {
  height: 34vh;
  min-height: 0;
}

.frame--public img {
  object-position: center top;
}

.frame--workspace img {
  object-position: 72% 24%;
}

.frame--bulletin img {
  object-position: 76% 18%;
}

.frame--workflow img {
  object-position: 78% 18%;
}

.frame--admin img {
  object-position: center top;
}

.frame--dashboard {
  background: #101010;
}

.frame--dashboard img {
  object-fit: contain;
  object-position: center center;
}

.evidence-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr));
  gap: 0.48rem;
}

.evidence-shot {
  margin: 0;
  min-height: clamp(3.7rem, 8vh, 5.4rem);
  border: 1px solid var(--line-soft);
  border-radius: 0.95rem;
  overflow: hidden;
  position: relative;
  background: #101010;
  box-shadow: var(--shadow-soft);
}

.evidence-shot img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center center;
  display: block;
}

.evidence-shot figcaption {
  position: absolute;
  left: 0.45rem;
  bottom: 0.45rem;
  max-width: calc(100% - 0.9rem);
  padding: 0.28rem 0.48rem;
  border-radius: 999px;
  background: rgba(9, 11, 16, 0.76);
  color: #f6f4ef;
  font-size: var(--small-size);
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.frame-label {
  position: absolute;
  left: 1rem;
  bottom: 1rem;
  padding: 0.5rem 0.72rem;
  border-radius: 999px;
  font-size: var(--small-size);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  background: rgba(9, 11, 16, 0.74);
  color: #f6f4ef;
}

.link-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.link-chip,
.note-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.62rem 0.82rem;
  border-radius: 999px;
  border: 1px solid var(--line-soft);
  background: var(--surface-strong);
  text-decoration: none;
  color: inherit;
  font-size: var(--small-size);
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.link-chip:hover,
.link-chip:focus-visible {
  border-color: var(--line-strong);
}

.matrix {
  display: grid;
  gap: 0.7rem;
}

.matrix-title {
  font-size: var(--h3-size);
  margin: 0;
}

.matrix-table {
  display: grid;
  gap: 0.5rem;
}

.matrix-row {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 0.75rem;
  padding: 0.72rem 0.78rem;
  border-radius: 0.95rem;
  border: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.64);
}

.matrix-row strong {
  display: block;
  margin-bottom: 0.2rem;
}

.matrix-row p {
  margin: 0;
  font-size: var(--body-size);
  line-height: 1.38;
}

.diagram-shell {
  display: grid;
  gap: 0.85rem;
}

.flow {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.55rem;
  align-items: stretch;
}

.flow-node {
  border-radius: 1rem;
  border: 1px solid var(--line-soft);
  padding: 0.72rem;
  background: rgba(255, 255, 255, 0.75);
  display: grid;
  gap: 0.35rem;
}

.flow-node strong {
  font-size: var(--small-size);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.flow-node p {
  margin: 0;
  font-size: var(--body-size);
  color: var(--text-soft);
  line-height: 1.38;
}

.flow-arrow {
  display: grid;
  place-items: center;
  color: var(--accent-main);
  font-family: 'Archivo', sans-serif;
  font-size: clamp(1.1rem, 2vw, 1.6rem);
}

.deck-collaboration .flow-arrow {
  color: var(--accent-alt);
}

.timeline {
  padding: 0.9rem 1rem;
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.55rem;
}

.timeline-step {
  display: grid;
  gap: 0.35rem;
  position: relative;
  padding-top: 0.75rem;
}

.timeline-step::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 2.2rem;
  height: 0.28rem;
  border-radius: 999px;
  background: var(--accent-main);
}

.deck-collaboration .timeline-step::before {
  background: var(--accent-alt);
}

.timeline-step strong {
  font-size: var(--small-size);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.timeline-step p {
  margin: 0;
  font-size: var(--body-size);
  line-height: 1.35;
  color: var(--text-soft);
}

.section-label {
  font-size: var(--small-size);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.quote-band {
  padding: 0.9rem 1rem;
  border-radius: 1rem;
  border-left: 0.4rem solid var(--accent-main);
  background: rgba(255, 255, 255, 0.74);
  box-shadow: var(--shadow-soft);
}

.deck-collaboration .quote-band {
  border-left-color: var(--accent-alt);
}

.quote-band p,
.quote-band small {
  margin: 0;
}

.quote-band p {
  font-size: clamp(0.95rem, 1.55vw, 1.15rem);
  line-height: 1.45;
}

.quote-band small {
  display: block;
  margin-top: 0.45rem;
  font-size: var(--small-size);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.footer {
  position: absolute;
  left: var(--slide-padding);
  right: var(--slide-padding);
  bottom: max(0.55rem, calc(var(--slide-padding) * 0.48));
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.7rem;
  font-size: var(--small-size);
  color: var(--text-soft);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  pointer-events: none;
}

.footer .slide-id {
  font-weight: 800;
  color: var(--text-main);
}

.progress-shell {
  position: fixed;
  right: clamp(0.8rem, 1.4vw, 1.4rem);
  bottom: clamp(0.8rem, 1.4vw, 1.4rem);
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 0.7rem;
  padding: 0.6rem 0.8rem;
  border-radius: 999px;
  background: rgba(246, 242, 236, 0.86);
  border: 1px solid rgba(14, 19, 24, 0.1);
  backdrop-filter: blur(16px);
  box-shadow: var(--shadow-soft);
}

.progress-count {
  font-family: 'Archivo', sans-serif;
  font-size: var(--small-size);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.progress-bar {
  width: min(24vw, 180px);
  height: 0.36rem;
  border-radius: 999px;
  background: rgba(14, 19, 24, 0.12);
  overflow: hidden;
}

.progress-bar span {
  display: block;
  height: 100%;
  width: 0;
  background: linear-gradient(90deg, var(--accent-main), rgba(241, 172, 95, 0.95));
}

.deck-collaboration .progress-bar span {
  background: linear-gradient(90deg, var(--accent-alt), rgba(98, 151, 147, 0.95));
}

.keyboard-hint {
  position: fixed;
  left: clamp(0.8rem, 1.4vw, 1.4rem);
  bottom: clamp(0.8rem, 1.4vw, 1.4rem);
  z-index: 20;
  padding: 0.52rem 0.72rem;
  border-radius: 999px;
  background: rgba(246, 242, 236, 0.84);
  border: 1px solid rgba(14, 19, 24, 0.1);
  font-size: var(--small-size);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.row-list {
  display: grid;
  gap: 0.55rem;
}

.row-item {
  display: grid;
  grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
  gap: 0.75rem;
  padding: 0.72rem 0.82rem;
  border-radius: 0.95rem;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid var(--line-soft);
}

.row-item strong {
  font-size: var(--small-size);
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.row-item p {
  margin: 0;
  font-size: var(--body-size);
  color: var(--text-soft);
  line-height: 1.38;
}

.phase-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
}

.phase-card {
  padding: 0.9rem 0.95rem;
  border-radius: 1rem;
  border: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.75);
  display: grid;
  gap: 0.42rem;
}

.phase-title {
  margin: 0;
  font-size: var(--h3-size);
  line-height: 1.08;
}

.phase-meta {
  font-size: var(--small-size);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-soft);
}

.warning-band {
  padding: 0.72rem 0.86rem;
  border-radius: 1rem;
  background: rgba(161, 25, 25, 0.08);
  border: 1px solid rgba(161, 25, 25, 0.14);
}

.deck-collaboration .warning-band {
  background: rgba(11, 106, 97, 0.08);
  border-color: rgba(11, 106, 97, 0.14);
}

.warning-band p {
  margin: 0;
  font-size: var(--body-size);
  line-height: 1.4;
}

.decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
}

.decision-card {
  padding: 0.95rem;
  border-radius: 1rem;
  border: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.78);
  display: grid;
  gap: 0.45rem;
}

.decision-card h3 {
  margin: 0;
  font-size: var(--h3-size);
  line-height: 1.04;
}

.decision-card p,
.decision-card li {
  margin: 0;
  font-size: var(--body-size);
  color: var(--text-soft);
  line-height: 1.38;
}

.decision-card ul {
  margin: 0;
  padding-left: 1rem;
  display: grid;
  gap: 0.38rem;
}

.slide.revealed .reveal {
  opacity: 1;
  transform: translateY(0);
}

.reveal {
  opacity: 0;
  transform: translateY(14px);
  transition: opacity 0.55s ease, transform 0.55s ease;
}

.delay-1 { transition-delay: 0.06s; }
.delay-2 { transition-delay: 0.12s; }
.delay-3 { transition-delay: 0.18s; }
.delay-4 { transition-delay: 0.24s; }

a {
  color: inherit;
}

@media (max-height: 760px) {
  :root {
    --slide-padding: clamp(0.8rem, 2.2vw, 2rem);
    --title-size: clamp(1.45rem, 4.1vw, 3rem);
    --h2-size: clamp(1.05rem, 2.3vw, 1.75rem);
    --body-size: clamp(0.72rem, 1vw, 0.94rem);
  }

  .slide-subtitle {
    display: none;
  }

  .quote-band,
  .warning-band,
  .lead-panel,
  .matrix,
  .card,
  .phase-card,
  .decision-card,
  .stat,
  .flow-node {
    padding: 0.72rem 0.8rem;
  }

  .card p,
  .lead-panel p,
  .matrix p,
  .matrix li,
  .decision-card p,
  .decision-card li,
  .flow-node p,
  .timeline-step p,
  .row-item p,
  .phase-card p,
  .stat p {
    line-height: 1.33;
  }

  .card-grid,
  .phase-grid,
  .decision-grid,
  .timeline,
  .flow,
  .matrix-table,
  .evidence-strip,
  .row-list {
    gap: 0.48rem;
  }

  .bullet-list,
  .compact-list {
    gap: 0.28rem;
  }

  .frame--wide { min-height: 34vh; }
  .frame--tall { min-height: 44vh; }
  .frame--compact { height: 28vh; }
  .evidence-shot { min-height: 3.8rem; }
}

@media (max-height: 620px) {
  :root {
    --slide-padding: clamp(0.6rem, 2vw, 1.3rem);
    --title-size: clamp(1.2rem, 3.6vw, 2rem);
  }

  .progress-shell,
  .keyboard-hint {
    display: none;
  }
}

@media (max-height: 720px) {
  .quote-band {
    display: none;
  }
}

@media (max-height: 680px) {
  .slide-subtitle,
  .eyebrow {
    display: none;
  }
}

@media (max-width: 980px) {
  .content-shell.split-2,
  .content-shell.split-3,
  .phase-grid,
  .decision-grid,
  .flow,
  .timeline {
    grid-template-columns: 1fr;
  }

  .slide-top,
  .footer {
    gap: 0.8rem;
  }

  .proof-row {
    justify-content: flex-start;
    max-width: 100%;
  }

  .slide-title {
    max-width: 100%;
  }

  .matrix-row,
  .row-item {
    grid-template-columns: 1fr;
  }

  .frame--wide { min-height: 30vh; }
  .frame--tall { min-height: 38vh; }
  .frame--compact { height: 14vh; }
  .evidence-shot { min-height: 3.6rem; }
}

@media (max-width: 640px) {
  :root {
    --title-size: clamp(1.05rem, 6vw, 1.55rem);
    --h2-size: clamp(0.82rem, 3.4vw, 1.1rem);
    --h3-size: clamp(0.72rem, 2.9vw, 0.92rem);
    --body-size: clamp(0.58rem, 2.25vw, 0.72rem);
    --small-size: clamp(0.5rem, 1.9vw, 0.62rem);
    --slide-padding: clamp(0.42rem, 2.8vw, 0.75rem);
    --content-gap: clamp(0.28rem, 1.45vw, 0.45rem);
    --element-gap: clamp(0.22rem, 1.1vw, 0.36rem);
  }

  .slide-subtitle {
    display: none;
  }

  .slide-content {
    padding-bottom: var(--slide-padding);
  }

  .footer,
  .progress-shell,
  .keyboard-hint,
  .frame-label {
    display: none;
  }

  .slide-title {
    line-height: 0.98;
  }

  .slide-top {
    align-items: flex-start;
  }

  .quote-band {
    display: none;
  }

  .warning-band,
  .lead-panel,
  .matrix,
  .card,
  .phase-card,
  .decision-card,
  .stat,
  .flow-node {
    padding: 0.48rem;
  }

  .card p,
  .card li,
  .lead-panel p,
  .matrix p,
  .matrix li,
  .bullet-list li,
  .compact-list li,
  .decision-card p,
  .decision-card li,
  .flow-node p,
  .timeline-step p,
  .row-item p,
  .phase-card p,
  .stat p {
    line-height: 1.22;
  }

  .frame--wide { min-height: 18vh; }
  .frame--tall { min-height: 22vh; }
  .frame--compact { height: 16vh; }
  .evidence-strip { display: none; }
  .evidence-shot figcaption { display: none; }
}

@media (max-width: 640px) and (max-height: 760px) {
  .quote-band,
  .slide-subtitle,
  .eyebrow {
    display: none;
  }

  .frame--wide,
  .frame--tall,
  .frame--compact {
    height: 16vh;
    min-height: 0;
  }

  .evidence-shot {
    min-height: 3.4rem;
  }
}

@media (max-width: 480px) {
  .eyebrow {
    display: none;
  }

  .proof-row {
    gap: 0.3rem;
  }

  .proof-chip {
    padding: 0.38rem 0.6rem;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.15s !important;
  }

  html {
    scroll-behavior: auto;
  }
}

@media print {
  @page { size: 13.333in 7.5in; margin: 0; }

  html, body {
    width: 13.333in;
    overflow: visible;
    background: white !important;
  }

  body::before,
  .progress-shell,
  .keyboard-hint {
    display: none !important;
  }

  .reveal {
    opacity: 1 !important;
    transform: none !important;
  }

  .slide {
    width: 13.333in;
    height: 7.5in;
    break-after: page;
    page-break-after: always;
  }

  .footer {
    position: absolute;
  }
}
`;

const sharedJs = String.raw`
class DeckController {
  constructor() {
    this.slides = Array.from(document.querySelectorAll('.slide'));
    this.index = 0;
    this.locked = false;
    this.touchStartY = 0;
    this.progressFill = document.querySelector('[data-progress-fill]');
    this.progressCount = document.querySelector('[data-progress-count]');
    this.bind();
    this.observe();
    this.update(0);
  }

  bind() {
    window.addEventListener('keydown', (event) => {
      if (['ArrowRight', 'ArrowDown', 'PageDown', ' '].includes(event.key)) {
        event.preventDefault();
        this.next();
      }
      if (['ArrowLeft', 'ArrowUp', 'PageUp'].includes(event.key)) {
        event.preventDefault();
        this.prev();
      }
      if (event.key === 'Home') {
        event.preventDefault();
        this.go(0);
      }
      if (event.key === 'End') {
        event.preventDefault();
        this.go(this.slides.length - 1);
      }
    }, { passive: false });

    window.addEventListener('wheel', (event) => {
      if (this.locked) return;
      if (Math.abs(event.deltaY) < 18) return;
      this.locked = true;
      if (event.deltaY > 0) this.next();
      else this.prev();
      window.setTimeout(() => { this.locked = false; }, 650);
    }, { passive: true });

    window.addEventListener('touchstart', (event) => {
      this.touchStartY = event.changedTouches[0].clientY;
    }, { passive: true });

    window.addEventListener('touchend', (event) => {
      const delta = this.touchStartY - event.changedTouches[0].clientY;
      if (Math.abs(delta) < 36) return;
      if (delta > 0) this.next();
      else this.prev();
    }, { passive: true });
  }

  observe() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const nextIndex = this.slides.indexOf(entry.target);
          if (nextIndex >= 0) this.update(nextIndex);
          entry.target.classList.add('revealed');
        }
      });
    }, { threshold: 0.65 });

    this.slides.forEach((slide) => observer.observe(slide));
  }

  go(index) {
    const next = Math.max(0, Math.min(index, this.slides.length - 1));
    this.slides[next].scrollIntoView({ behavior: 'smooth', block: 'start' });
    this.update(next);
  }

  next() { this.go(this.index + 1); }
  prev() { this.go(this.index - 1); }

  update(index) {
    this.index = index;
    const progress = ((index + 1) / this.slides.length) * 100;
    if (this.progressFill) this.progressFill.style.width = progress + '%';
    if (this.progressCount) this.progressCount.textContent = String(index + 1).padStart(2, '0') + ' / ' + String(this.slides.length).padStart(2, '0');
    window.location.hash = this.slides[index].id;
  }

  getIndex() {
    return this.index;
  }
}

window.addEventListener('DOMContentLoaded', () => {
  window.deckController = new DeckController();
});
`;

function proofChips(chips) {
  return `<div class="proof-row">${chips.map(({ label, kind }) => `<span class="proof-chip ${kind}">${label}</span>`).join('')}</div>`;
}

function frame(src, alt, classes, label) {
  return `
    <figure class="frame ${classes}">
      <img src="${src}" alt="${alt}">
      ${label ? `<figcaption class="frame-label">${label}</figcaption>` : ''}
    </figure>
  `;
}

function dashboardEvidence(items) {
  return `
    <div class="evidence-strip reveal delay-3">
      ${items.map(({ src, alt, label }) => `
        <figure class="evidence-shot">
          <img src="${src}" alt="${alt}">
          <figcaption>${label}</figcaption>
        </figure>
      `).join('')}
    </div>
  `;
}

function slideSection({ id, kicker, eyebrow, title, subtitle, proof, source, shellClass = 'split-2', content }) {
  return `
    <section class="slide" id="${id}">
      <div class="slide-content">
        <div class="slide-top reveal">
          <div class="kicker-stack">
            <div class="kicker">${kicker}</div>
            <div class="eyebrow">${eyebrow}</div>
            <h1 class="slide-title">${title}</h1>
            <p class="slide-subtitle">${subtitle}</p>
          </div>
          ${proofChips(proof)}
        </div>
        <div class="content-shell ${shellClass}">
          ${content}
        </div>
        <div class="footer">
          <span class="slide-id">${id.toUpperCase().replace('-', ' ')}</span>
          <span>${source}</span>
        </div>
      </div>
    </section>
  `;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function inlineMarkdownToHtml(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
}

function proofFromEvidenceLevel(evidenceLevel) {
  const proof = [];
  if (/Hosted production/i.test(evidenceLevel)) proof.push({ label: evidenceLabels.live, kind: 'live' });
  if (/Repo\/admin verified/i.test(evidenceLevel)) proof.push({ label: evidenceLabels.internal, kind: 'internal' });
  if (/Artifact\/doc proof only/i.test(evidenceLevel)) proof.push({ label: evidenceLabels.future, kind: 'future' });
  return proof.length ? proof : [{ label: evidenceLabels.internal, kind: 'internal' }];
}

function extractSection(block, startLabel, endLabel) {
  const start = block.indexOf(startLabel);
  if (start < 0) return '';
  const contentStart = start + startLabel.length;
  const end = endLabel ? block.indexOf(endLabel, contentStart) : -1;
  return block.slice(contentStart, end >= 0 ? end : undefined).trim();
}

function extractSectionUntilAny(block, startLabel, endLabels) {
  const start = block.indexOf(startLabel);
  if (start < 0) return '';
  const contentStart = start + startLabel.length;
  const ends = endLabels
    .map((label) => block.indexOf(label, contentStart))
    .filter((index) => index >= 0);
  const end = ends.length ? Math.min(...ends) : -1;
  return block.slice(contentStart, end >= 0 ? end : undefined).trim();
}

function renderMarkdownSlides(markdown, {
  idPrefix,
  kicker,
  eyebrow,
  defaultSource = 'MVP source pack',
}) {
  return markdown
    .split(/\n---\n/g)
    .filter((block) => /^## Slide \d+:/m.test(block))
    .map((block, index) => {
      const title = block.match(/^## Slide \d+:\s*(.+)$/m)?.[1]?.trim() ?? `Architecture Slide ${index + 1}`;
      const message = extractSection(block, '**Customer message:**', '**Current state and future strategy:**');
      const bulletsRaw = extractSection(block, '**Current state and future strategy:**', '**Evidence level:**');
      const evidenceLevel = extractSectionUntilAny(block, '**Evidence level:**', [
        '**Screenshot:**',
        '**Supporting source:**',
        '**Supporting sources:**',
      ]);
      const source = (block.match(/\*\*Supporting sources?:\*\*\s*(.+)$/m)?.[1] ?? 'Technical architecture source pack').trim();
      const screenshot = block.match(/\*\*Screenshot:\*\*\s*!\[([^\]]*)\]\(([^)]+)\)/);
      const bullets = bulletsRaw
        .split('\n')
        .map((line) => line.trim())
        .filter((line) => line.startsWith('- '))
        .map((line) => line.slice(2).trim());

      return slideSection({
        id: `${idPrefix}-${index + 1}`,
        kicker,
        eyebrow,
        title,
        subtitle: inlineMarkdownToHtml(message),
        proof: proofFromEvidenceLevel(evidenceLevel),
        source: inlineMarkdownToHtml(source || defaultSource),
        shellClass: screenshot ? 'split-2' : 'split-2',
        content: `
          <div class="stack reveal delay-1">
            <div class="lead-panel">
              <div class="section-label">Current state and future strategy</div>
              <ul class="bullet-list">
                ${bullets.map((bullet) => `<li>${inlineMarkdownToHtml(bullet)}</li>`).join('\n')}
              </ul>
            </div>
            <div class="warning-band">
              <p><strong>Evidence level:</strong> ${inlineMarkdownToHtml(evidenceLevel || 'Repo/admin verified')}</p>
            </div>
          </div>
          <div class="stack reveal delay-2">
            ${screenshot
              ? frame(screenshot[2], screenshot[1] || title, 'frame--wide frame--workspace', 'Hosted route proof')
              : `<div class="diagram-shell">
                  <div class="section-label">Interpretation</div>
                  <div class="phase-grid">
                    <article class="phase-card"><div class="phase-meta">Current state</div><h3 class="phase-title">Evidence now</h3><p>Use only hosted, admin, repo, and artifact proof that exists today.</p></article>
                    <article class="phase-card"><div class="phase-meta">Gated</div><h3 class="phase-title">Promotion rules</h3><p>MTS-LSTM, SAR, TreeSHAP refresh, and runout physics require explicit evidence before promotion.</p></article>
                    <article class="phase-card"><div class="phase-meta">Future strategy</div><h3 class="phase-title">Validation program</h3><p>Scientist review decides which technical paths become stronger operational claims.</p></article>
                  </div>
                </div>`}
          </div>
        `,
      });
    });
}

function renderTechnicalSlides(markdown) {
  return renderMarkdownSlides(markdown, {
    idPrefix: 't',
    kicker: 'Technical deck',
    eyebrow: 'Architecture addendum',
    defaultSource: 'Technical architecture source pack',
  });
}

const deck1Slides = [
  slideSection({
    id: 'd1-1',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Credibility arc • scientist-first contract',
    title: 'Avalanche Insight Hub',
    subtitle: 'MVP V2: a governed decision-support platform for avalanche forecasting, partner evidence intake, review, and scientific collaboration.',
    proof: [
      { label: evidenceLabels.internal, kind: 'internal' },
      { label: evidenceLabels.future, kind: 'future' },
    ],
    source: 'Discussion frame • platform brief',
    content: `
      <div class="stack loose reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Meeting objective</div>
          <ul class="bullet-list">
            <li>Show the live platform, the administration view, and the MVP V2 evidence-governance model.</li>
            <li>Distinguish hosted product proof from Swiss RAvaFcast research, Himalayan v3 partner intake, SAR shadow evidence, and future promotion gates.</li>
            <li>Close on whether the SASE/DGRE partner handoff and scientist-led validation program should begin next.</li>
          </ul>
        </div>
        <div class="card-grid">
          <article class="card">
            <div class="section-label">What this is</div>
            <h3>Governed decision support</h3>
            <p>Batch-first forecast publication, explicit uncertainty, auditable model-status surfaces, and partner evidence intake.</p>
          </article>
          <article class="card">
            <div class="section-label">What this is not</div>
            <h3>Autonomy-first launch</h3>
            <p>No active MTS-LSTM claim, no promoted SAR claim, no Himalayan accuracy claim, no authority-grade warning claim.</p>
          </article>
        </div>
      </div>
      <div class="stack loose reveal delay-2">
        <div class="phase-grid">
          <article class="phase-card">
            <div class="phase-meta">Discussion lane</div>
            <h3 class="phase-title">${evidenceLabels.live}</h3>
            <p>Public route screenshots plus hosted <code>/admin</code> route/auth smoke from May 8, 2026.</p>
          </article>
          <article class="phase-card">
            <div class="phase-meta">Discussion lane</div>
            <h3 class="phase-title">${evidenceLabels.internal}</h3>
            <p>Governance, benchmark, and candidate-model material available through technical artifacts and administration views.</p>
          </article>
          <article class="phase-card">
            <div class="phase-meta">Discussion lane</div>
            <h3 class="phase-title">${evidenceLabels.future}</h3>
            <p>Critical-layer validation, SAR qualification, Himalayan holdout evidence, and candidate-model advancement remain part of the next research program.</p>
          </article>
        </div>
        <div class="quote-band">
          <p>Use the deck to establish context first, then focus the discussion on the partner handoff and next scientific frontier.</p>
          <small>Keep the three discussion lanes visible throughout</small>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-2',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Why the problem is still hard',
    title: 'Avalanche Forecasting Remains Hard',
    subtitle: 'The discussion only matters if it starts from the real sparse-data and validation bottlenecks.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Top challenges • research synthesis',
    content: `
      <div class="stack reveal delay-1">
        <div class="card-grid">
          <article class="card">
            <div class="section-label">Observation scarcity</div>
            <h3>Sparse and discontinuous evidence</h3>
            <p>Storm windows create the worst blind spots exactly when human access becomes most constrained.</p>
          </article>
          <article class="card">
            <div class="section-label">Snow science</div>
            <h3>Weak layers carry memory</h3>
            <p>New snow totals alone do not capture persistent weak-layer structure or critical-layer failure risk.</p>
          </article>
          <article class="card">
            <div class="section-label">Statistics</div>
            <h3>Rare-event imbalance distorts trust</h3>
            <p>Naive accuracy can look good while still missing the avalanche days that matter operationally.</p>
          </article>
          <article class="card">
            <div class="section-label">Operations</div>
            <h3>Authority risk is real</h3>
            <p>Danger messaging, masking, and consequence framing matter as much as the raw score.</p>
          </article>
        </div>
        <div class="warning-band">
          <p><strong>What this means for the platform:</strong> batch-first delivery, reduced-confidence cues, masked terrain semantics, and governed claims are features of scientific discipline.</p>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="matrix">
          <h3 class="matrix-title">Operational pressure that is still live</h3>
          <div class="row-list">
            <div class="row-item">
              <strong>Manual snowpack work does not scale</strong>
              <p>Field pits remain expensive, dangerous, and geographically sparse.</p>
            </div>
            <div class="row-item">
              <strong>Micro-climate variability persists</strong>
              <p>Regional grids help, but local slope reality still resists broad generalization.</p>
            </div>
            <div class="row-item">
              <strong>Missing occurrence records weaken validation</strong>
              <p>That is why governed event capture and benchmark ownership matter in the next phase.</p>
            </div>
          </div>
        </div>
        <div class="quote-band">
          <p>“All relevant avalanche problems must be considered.”</p>
          <small>EAWS workflow • kept in the appendix and notes, not overstated on-product</small>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-3',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Research lineage',
    title: 'The Client’s Research Lineage',
    subtitle: 'This platform is building around a long avalanche-forecasting history, not pretending to have invented the science.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Research lineage synthesis',
    content: `
      <div class="timeline reveal delay-1">
        <div class="timeline-step">
          <strong>2008</strong>
          <p>ANN work in the Indian Himalaya established nonlinear modeling as part of the client’s lineage.</p>
        </div>
        <div class="timeline-step">
          <strong>2015</strong>
          <p>Calibration research surfaced weighting burden, multiple optima, and the need for disciplined tuning.</p>
        </div>
        <div class="timeline-step">
          <strong>2017</strong>
          <p>GPU acceleration showed the compute burden is real and belongs off the interactive user path.</p>
        </div>
        <div class="timeline-step">
          <strong>2020</strong>
          <p>HIM-STRAT reinforced that snowpack memory and stability indexing matter beyond simple snowfall totals.</p>
        </div>
        <div class="timeline-step">
          <strong>2025</strong>
          <p>Feature-selection and class-imbalance papers sharpened current benchmark and governance priorities.</p>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Why this matters in the room</div>
          <ul class="bullet-list">
            <li>The scientist team sees continuity with work they already respect.</li>
            <li>The product conversation starts from domain seriousness, not from shiny-tool novelty.</li>
            <li>The current platform is judged as an integration shell around real lineage and real limitations.</li>
          </ul>
        </div>
        <div class="card-grid">
          <article class="card">
            <div class="section-label">What not to claim</div>
            <h3>No “first-ever” rhetoric</h3>
            <p>The contribution is in how the stack is packaged, governed, and made discussable now.</p>
          </article>
          <article class="card">
            <div class="section-label">What to claim safely</div>
            <h3>Continuity with stronger packaging</h3>
            <p>The platform respects prior research while making evidence surfaces and user-facing semantics easier to inspect.</p>
          </article>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-4',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Discovery ledger',
    title: 'What Earlier Research Solved, And What It Did Not',
    subtitle: 'The slide that separates scientific precedent from current implementation and from what still needs scientist co-development.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Research precedent review',
    shellClass: 'split-3',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Established by prior research</div>
          <ul class="bullet-list">
            <li>Feature discipline matters more than feature sprawl.</li>
            <li>Rare-event metrics and class balancing are essential.</li>
            <li>Compute cost is part of the avalanche problem itself.</li>
            <li>Snowpack and weak-layer structure remain first-order science.</li>
          </ul>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Implemented in the current platform</div>
          <ul class="bullet-list">
            <li>Published-horizon batch forecast workspace.</li>
            <li>EAWS-style experimental bulletin framing with explicit uncertainty.</li>
            <li>Masked terrain semantics and share or export workflows.</li>
            <li>Governed model-status, provenance, and candidate-gate surfaces.</li>
          </ul>
        </div>
      </div>
      <div class="stack reveal delay-3">
        <div class="lead-panel">
          <div class="section-label">Still open for co-development</div>
          <ul class="bullet-list">
            <li>Scientist-owned critical-layer and weak-layer validation.</li>
            <li>Promotion-worthy candidate-model evidence.</li>
            <li>Operational SAR qualification per region and use case.</li>
            <li>Regional transfer limits and local heterogeneity maps.</li>
          </ul>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-5',
    kicker: 'Deck 1 of 5',
    eyebrow: 'First live-proof slide',
    title: 'What The Current Live Platform Proves Today',
    subtitle: 'This is the live proof surface: a forecast workspace, same-day full-grid technical publication, explicit uncertainty cues, and terrain-aware masking.',
    proof: [
      { label: 'Live platform', kind: 'live' },
    ],
    source: 'Live platform review',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Live route</div>
          <div class="link-list">
            <a class="link-chip" href="https://avalanche-insight-hub.netlify.app/">Live platform /</a>
            <a class="link-chip" href="https://avalanche-insight-hub.netlify.app/admin">Admin route /admin</a>
          </div>
        </div>
        <div class="card-grid">
          <article class="card">
            <div class="section-label">Forecast shell</div>
            <h3>Published artifact workspace</h3>
            <p>The user sees the latest published batch product rather than waiting on heavy science at click time.</p>
          </article>
          <article class="card">
            <div class="section-label">Hazard communication</div>
            <h3>Explicit uncertainty and masking</h3>
            <p>Reduced-confidence language and masked terrain prevent false precision.</p>
          </article>
        </div>
      </div>
      <div class="stack reveal delay-2">
        ${frame(screenshots.workspace, 'Live Avalanche Insight Hub workspace on May 8, 2026.', 'frame--wide frame--public', 'Live platform • 2026-05-08')}
      </div>
    `,
  }),
  slideSection({
    id: 'd1-6',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Operational shell',
    title: 'Forecast Workspace And Batch-First Delivery',
    subtitle: 'The platform is clear about compute: heavy work happens upstream, while the user sees the currently published horizon and freshness state on the hosted route.',
    proof: [
      { label: 'Live platform', kind: 'live' },
    ],
    source: 'Live platform workflow review',
    content: `
      <div class="stack reveal delay-1">
        ${frame(screenshots.workspace, 'Live workspace crop showing current published horizon and action bar.', 'frame--wide frame--workspace', 'Published horizon shown on route')}
      </div>
      <div class="stack reveal delay-2">
        <div class="stat-row">
          <article class="stat">
            <div class="stat-label">Current batch state</div>
            <div class="stat-number">Current</div>
            <p>May 8 proof uses a same-day <code>20x20</code> / <code>72h</code> full-grid technical publication for Colorado Rockies.</p>
          </article>
          <article class="stat">
            <div class="stat-label">Serving scorer</div>
            <div class="stat-number">RF baseline</div>
            <p>Current public route names <code>surrogate_rf_v1</code> as the active scorer.</p>
          </article>
        </div>
        <div class="lead-panel">
          <div class="section-label">Why batch-first matters</div>
          <ul class="bullet-list">
            <li>GPU or heavy candidate workflows stay off the public click path.</li>
            <li>Artifact hydration and lazy hour loading keep the surface responsive while preserving freshness state.</li>
          </ul>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-7',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Credibility wedge',
    title: 'Bulletin Structure, Uncertainty, And Masking',
    subtitle: 'This is where public trust posture becomes visible: structured danger framing, explicit reduced confidence, and terrain discipline.',
    proof: [
      { label: 'Live platform', kind: 'live' },
    ],
    source: 'Live bulletin review',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">What the user can read immediately</div>
          <ul class="bullet-list">
            <li>Danger level, avalanche problem framing, daypart, and elevation or aspect cues.</li>
            <li><code>EAWS-style experimental</code> wording kept visible rather than hidden in notes.</li>
            <li>High-uncertainty and reduced-confidence cues made public instead of buried in admin only.</li>
          </ul>
        </div>
        <div class="quote-band">
          <p>Danger communication stays useful only when snowpack stability, frequency, and size are not flattened into a single cosmetic badge.</p>
          <small>EAWS matrix framing • used as bounded structure, not authority equivalence</small>
        </div>
      </div>
      <div class="stack reveal delay-2">
        ${frame(screenshots.workspace, 'Live bulletin crop showing reduced confidence and masking cues.', 'frame--wide frame--bulletin', 'Live platform • bulletin and legend')}
      </div>
    `,
  }),
  slideSection({
    id: 'd1-8',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Workflow value',
    title: 'Share, Export, Report, And Expert Review',
    subtitle: 'The platform is not just a model display. It already supports team handoff, field reporting, and expert-facing review actions on the public route.',
    proof: [
      { label: 'Live platform', kind: 'live' },
    ],
    source: 'Live workflow review',
    content: `
      <div class="stack reveal delay-1">
        <div class="card-grid">
          <article class="card">
            <div class="section-label">State handoff</div>
            <h3>Shareable forecast links</h3>
            <p>Full-state sharing restores region, time, expert mode, and view state.</p>
          </article>
          <article class="card">
            <div class="section-label">Analysis export</div>
            <h3>CSV and JSON</h3>
            <p>Exports let scientists and operators pull forecast evidence out of the UI cleanly.</p>
          </article>
          <article class="card">
            <div class="section-label">Evidence intake</div>
            <h3>Report flow</h3>
            <p>Public report capture creates a path toward governed event enrichment rather than one-way display.</p>
          </article>
          <article class="card">
            <div class="section-label">Expert review</div>
            <h3>Events and overlays</h3>
            <p>The workflow already anticipates scientist or operator inspection beyond a simple heatmap.</p>
          </article>
        </div>
      </div>
      <div class="stack reveal delay-2">
        ${frame(screenshots.share, 'Live route showing share workflow confirmation.', 'frame--wide frame--workflow', 'Live platform • share state')}
      </div>
    `,
  }),
  slideSection({
    id: 'd1-9',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Operator lane',
    title: 'Admin Evidence Surfaces And Evidence Rules',
    subtitle: 'Hosted-authenticated review on May 8, 2026 allows a real admin observability view as validated internal evidence.',
    proof: [
      { label: 'Live platform', kind: 'live' },
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Platform observability review',
    content: `
      <div class="stack reveal delay-1">
        ${frame(screenshots.adminAuth, 'Hosted authenticated admin dashboard publication view.', 'frame--wide frame--admin', 'Validated internal evidence • 2026-05-08')}
      </div>
      <div class="stack reveal delay-2">
        <div class="matrix">
          <h3 class="matrix-title">Evidence rule now in effect</h3>
          <div class="matrix-table">
            <div class="matrix-row">
              <div><strong>Hosted /admin route</strong><p>Always proves route or gate availability when reachable.</p></div>
              <div><strong>Current smoke</strong><p>Fresh hosted-authenticated access succeeded, so the signed-in observability view can be discussed as validated internal evidence.</p></div>
            </div>
            <div class="matrix-row">
              <div><strong>What the admin lane adds</strong><p>Source health, provenance, model status, benchmark traces, stability, and publication state.</p></div>
              <div><strong>What it does not add</strong><p>Promotion proof by itself. It is richer observability, not a shortcut around validation.</p></div>
            </div>
          </div>
        </div>
        <div class="warning-band">
          <p><strong>Fallback rule:</strong> if hosted-auth access fails later, revert to the gate screenshot plus reconstructed governance tables.</p>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-10',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Current ML truth',
    title: 'RF Baseline, RAvaFcast Research, And Modal.com Split',
    subtitle: 'The live platform is anchored on the Random Forest baseline. Swiss RAvaFcast work is research-only, and the current active publication uses heuristic explanation fallback.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Platform ML and compute review',
    content: `
      <div class="stack reveal delay-1">
        <div class="matrix">
          <h3 class="matrix-title">What is active now</h3>
          <div class="matrix-table">
            <div class="matrix-row">
              <div><strong>Public scorer</strong><p><code>surrogate_rf_v1</code> is active; the current run reports <code>heuristic_fallback</code>, not active TreeSHAP proof.</p></div>
              <div><strong>Candidate lanes</strong><p><code>mts_lstm_v1</code>, SAR, and Modal-backed training/segmentation remain gated and off the public scoring path.</p></div>
            </div>
            <div class="matrix-row">
              <div><strong>Swiss research lane</strong><p>RAvaFcast is an initial research signal; GPxyz remains blocked until station coordinates exist.</p></div>
              <div><strong>Himalayan evidence lane</strong><p>The v3 partner contract validates package structure, provenance, and claim locks, not Himalayan accuracy.</p></div>
            </div>
          </div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="warning-band">
          <p><strong>Safe phrase:</strong> Modal.com supports bounded candidate compute; partner intake and synthetic checks do not authorize GPU, production scoring, or public claim changes.</p>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-11',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Governed autonomy reframing',
    title: 'Governed Evidence Fusion, Not Autonomous Truth Generation',
    subtitle: 'Weighting, corroboration, decay, and blocked-gate discipline are real. Scientist-grade truth generation is not yet proven and must stay framed that way.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Evidence-governance review',
    content: `
      <div class="stack reveal delay-1">
        <div class="diagram-shell">
          <div class="section-label">Current governed path</div>
          <div class="flow">
            <div class="flow-node"><strong>Ingest</strong><p>Field reports, news, and SAR paths enter with explicit source identity.</p></div>
            <div class="flow-node"><strong>Govern</strong><p><code>label_confidence</code>, weights, corroboration, decay, and audit-only rules shape trust.</p></div>
            <div class="flow-node"><strong>Summarize</strong><p>Admin surfaces persist evidence mix, candidate gates, runtime traces, and stability context.</p></div>
            <div class="flow-node"><strong>Block by default</strong><p>Candidate promotion stays blocked until release artifacts justify stronger claims.</p></div>
          </div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="matrix">
          <h3 class="matrix-title">What the current artifact does and does not prove</h3>
          <div class="matrix-table">
            <div class="matrix-row">
              <div><strong>Proves</strong><p><code>1000 / 1000</code> positives are autonomous today; <code>0</code> are manual positives.</p></div>
              <div><strong>Does not prove</strong><p>Any human-reviewed truth closure or field-certified autonomous event stream.</p></div>
            </div>
            <div class="matrix-row">
              <div><strong>Proves</strong><p>The governed summary spans <code>6</code> regions; newest positive source is <code>2023-12-24</code> and only <code>gee_sar</code> is positive in the sampled artifact.</p></div>
              <div><strong>Does not prove</strong><p>Fresh, diversified capture or robust regional transfer strong enough for autonomy-forward marketing language.</p></div>
            </div>
          </div>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-12',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Release-gate posture',
    title: 'Benchmark, Stability, And Release Gates',
    subtitle: 'This slide is about discipline, not theater. Current evidence should be read as governance metadata, partner-readiness infrastructure, and bounded observability, not broad robustness closure.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Benchmark and stability review',
    content: `
      <div class="stack reveal delay-1">
        <div class="stat-row">
          <article class="stat">
            <div class="stat-label">Latest benchmark</div>
            <div class="stat-number">inference_publication</div>
            <p>Status is <strong>ok</strong>; latest visible runtime trace is <code>4742.6s</code>.</p>
          </article>
          <article class="stat">
            <div class="stat-label">Stability classification</div>
            <div class="stat-number">unstable</div>
            <p>Current packaged stability evidence is explicitly conservative, not celebratory.</p>
          </article>
          <article class="stat">
            <div class="stat-label">Promotion rule</div>
            <div class="stat-number">Blocked until earned</div>
            <p>Candidate models and Himalayan claims stay gated until local evidence, holdout metrics, release artifacts, and scientist review justify stronger claims.</p>
          </article>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="matrix">
          <h3 class="matrix-title">Current bounded evidence</h3>
          <div class="matrix-table">
            <div class="matrix-row">
              <div><strong>Seed count</strong><p><code>3</code> seeds only. Read as bounded governance evidence.</p></div>
              <div><strong>Threshold drift</strong><p><code>0.157726</code> is visible and should remain visible in the scientist discussion.</p></div>
            </div>
            <div class="matrix-row">
              <div><strong>Source of truth</strong><p>Current admin surfaces, benchmark pack v0, validation protocol v0, v3 partner evidence contract, and the stability summary artifact.</p></div>
              <div><strong>What to say safely</strong><p>“We have explicit benchmark and stability traces, and they are conservative enough to keep stronger claims blocked.”</p></div>
            </div>
          </div>
        </div>
        <div class="warning-band">
          <p><strong>Do not say:</strong> “the shadow path is stable and ready for production.” The artifact only supports cautious governance language.</p>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-13',
    kicker: 'Deck 1 of 5',
    eyebrow: 'The real wedge',
    title: 'What Is Genuinely Unique Now',
    subtitle: 'The differentiation is not any single algorithm. It is the evidence-bounded integration of forecast UX, evidence governance, masking, and scientist-ready surfaces.',
    proof: [
      { label: 'Live platform', kind: 'live' },
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Differentiation analysis',
    content: `
      <div class="card-grid reveal delay-1">
        <article class="card">
          <div class="section-label">Operational UX</div>
          <h3>Published-horizon workspace</h3>
          <p>A usable forecast shell exists today, not just a model notebook or a static bulletin mockup.</p>
        </article>
        <article class="card">
          <div class="section-label">Semantic discipline</div>
          <h3>Masked terrain and reduced confidence</h3>
          <p>The UI refuses to translate missing support into cosmetic low risk.</p>
        </article>
        <article class="card">
          <div class="section-label">Inspectability</div>
          <h3>Explainability and provenance in context</h3>
          <p>Reasoning and lineage are inspectable at the point of use, not hidden in backend reports.</p>
        </article>
        <article class="card">
          <div class="section-label">Governance posture</div>
          <h3>Blocked until evidence is earned</h3>
          <p>The platform keeps candidate activation and evidence lanes explicit instead of flattening them into one story.</p>
        </article>
      </div>
      <div class="quote-band reveal delay-2">
        <p>The compelling story is integration under sparse-data discipline, not algorithm novelty by itself.</p>
        <small>Current strongest proposition for scientist trust</small>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-14',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Boundary slide',
    title: 'What Is Not Unique, And Must Not Be Overclaimed',
    subtitle: 'Trust increases when we draw the line before the scientist or partner agency has to do it for us.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Boundary and overclaim review',
    content: `
      <div class="stack reveal delay-1">
        <div class="matrix">
          <h3 class="matrix-title">Do not say</h3>
          <div class="matrix-table">
            <div class="matrix-row">
              <div><strong>Algorithm novelty</strong><p>ANNs, SHAP, SAR segmentation, LSTM-style modeling, and GPU workers are not unique by themselves.</p></div>
              <div><strong>Operational status</strong><p>No active public MTS-LSTM claim, no promoted SAR claim, no Himalayan accuracy claim, and no authority-grade warning status.</p></div>
            </div>
            <div class="matrix-row">
              <div><strong>Snow science closure</strong><p>No solved weak-layer or critical-layer validation story.</p></div>
              <div><strong>Autonomy closure</strong><p>No field-certified autonomous truth-generation claim and no <code>D_tidy</code>-equivalent Himalayan truth yet.</p></div>
            </div>
          </div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Safe substitute language</div>
          <ul class="bullet-list">
            <li>“Explainable baseline plus governed candidate pathways.”</li>
            <li>“Modal.com supports candidate compute, not the current public proof surface.”</li>
            <li>“SAR is promising but still qualification-bound.”</li>
            <li>“The SASE/DGRE packet is a partner-evidence handoff, not prediction success.”</li>
            <li>“The current value is disciplined integration under sparse-data constraints.”</li>
          </ul>
        </div>
        <div class="quote-band">
          <p>Use the available evidence to support bounded “second opinion” language, not expert-replacement rhetoric.</p>
          <small>Recent avalanche ML literature • used conservatively</small>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd1-15',
    kicker: 'Deck 1 of 5',
    eyebrow: 'Conditional close',
    title: 'Current Gaps, Blocked Claims, And The Real Question',
    subtitle: 'The right close is not certainty. It is whether the SASE/DGRE handoff and next scientist-owned validation step are worth doing now.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Validation decision frame',
    content: `
      <div class="stack reveal delay-1">
        <div class="decision-grid">
          <article class="decision-card">
            <div class="section-label">Blocked claim</div>
            <h3>No promoted next-gen scorer</h3>
            <p>MTS-LSTM remains candidate-only until gates and benchmark deltas are earned.</p>
          </article>
          <article class="decision-card">
            <div class="section-label">Blocked claim</div>
            <h3>No promoted SAR</h3>
            <p>Coverage signaling exists; scientist-grade qualification still does not.</p>
          </article>
          <article class="decision-card">
            <div class="section-label">Blocked claim</div>
            <h3>No Himalayan or weak-layer closure</h3>
            <p>V3 intake validates structure/provenance only; weak-layer and snowpack validation remain next-phase work.</p>
          </article>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Decision close</div>
          <ul class="bullet-list">
            <li>The platform already proves a serious decision-support shell and disciplined governance posture.</li>
            <li>The missing science is visible rather than hidden, which makes co-development discussable.</li>
            <li><strong>Meeting question:</strong> should the scientist team and SASE/DGRE partner contacts help own the benchmark, validation, and promotion frontier from here?</li>
          </ul>
        </div>
      </div>
    `,
  }),
];

const deck2Slides = [
  slideSection({
    id: 'd3-1',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Collaboration arc',
    title: 'Why Scientist And Partner Co-Development Is Necessary Now',
    subtitle: 'MVP V2 proves enough to justify SASE/DGRE partner handoff and scientist review. It does not prove enough to skip local Himalayan validation.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Collaboration framing',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Transition after Deck 1</div>
          <ul class="bullet-list">
            <li>The product proof is real: public route, admin observability, explainable baseline, and governance surfaces.</li>
            <li>The V2 infrastructure is real: Swiss RAvaFcast research, Himalayan v3 evidence templates, and one-command package triage.</li>
            <li>The science gap is also real: weak layers, regional transfer, quality-controlled labels, station coverage, and promotion evidence are unfinished.</li>
            <li>That gap is exactly where SASE/DGRE partners and the scientist team become central rather than decorative.</li>
          </ul>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="stat-row">
          <article class="stat">
            <div class="stat-label">Ready now</div>
            <div class="stat-number">Decision-support platform</div>
            <p>Public-facing product shell, operator evidence surfaces, and partner-intake templates already exist.</p>
          </article>
          <article class="stat">
            <div class="stat-label">Not ready now</div>
            <div class="stat-number">Scientific closure</div>
            <p>The next phase is about SASE/DGRE evidence handoff, benchmark ownership, and validation ownership, not declaring victory.</p>
          </article>
        </div>
        <div class="quote-band">
          <p>The strongest collaboration pitch is: “help us decide what should count as real Himalayan evidence here.”</p>
          <small>Scientist-first framing</small>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-2',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Attraction layer',
    title: 'Why This Is Worth The Scientist Team’s Time',
    subtitle: 'The program becomes attractive when scientists gain ownership, benchmark authority, and publishable pilot leverage instead of being asked to bless a black box.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Collaboration value analysis',
    content: `
      <div class="card-grid reveal delay-1">
        <article class="card">
          <div class="section-label">Ownership</div>
          <h3>Benchmark design authority</h3>
          <p>The scientist team can define slices, acceptance thresholds, and the cases that matter operationally.</p>
        </article>
        <article class="card">
          <div class="section-label">Control</div>
          <h3>Release-gate veto power</h3>
          <p>Promotion claims stay blocked until scientist-reviewed evidence says otherwise.</p>
        </article>
        <article class="card">
          <div class="section-label">Relevance</div>
          <h3>Field and weak-layer focus</h3>
          <p>The hardest real avalanche questions become the center of the roadmap, not an appendix afterthought.</p>
        </article>
        <article class="card">
          <div class="section-label">Output</div>
          <h3>Publication and pilot value</h3>
          <p>A co-owned validation pack can become the basis for publishable pilot evidence, not just demo polish.</p>
        </article>
      </div>
      <div class="warning-band reveal delay-2">
        <p><strong>What makes this scientifically interesting:</strong> the stack is inspectable, the claims are gated, and the next step is benchmark ownership rather than UI applause.</p>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-3',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Relationship contract',
    title: 'Ground Rules: Claim Discipline, Evidence Discipline, Validation Authority',
    subtitle: 'This collaboration only works if live-platform truth, validated internal evidence, and future ambition remain visibly separate throughout the program.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Claim and evidence discipline',
    content: `
      <div class="stack reveal delay-1">
        <div class="matrix">
          <h3 class="matrix-title">Three rules for the program</h3>
          <div class="matrix-table">
            <div class="matrix-row">
              <div><strong>Rule 1</strong><p>Claim state must map to evidence state: live platform, validated internal evidence, or research next phase.</p></div>
              <div><strong>Rule 2</strong><p>Validation authority stays with scientists and operators, not with product marketing language.</p></div>
            </div>
            <div class="matrix-row">
              <div><strong>Rule 3</strong><p>Data-governance and publication expectations should be explicit before deeper pilot work begins.</p></div>
              <div><strong>Consequence</strong><p>If a gate fails, the claim downgrades immediately instead of being explained away.</p></div>
            </div>
          </div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Why scientists should like this</div>
          <ul class="bullet-list">
            <li>The collaboration asks for challenge and review, not passive endorsement.</li>
            <li>The product team is committing to explicit downgrade rules when evidence is weak.</li>
            <li>The language discipline is part of the operating model, not a one-off deck exercise.</li>
          </ul>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-4',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Scientist role',
    title: 'Scientist Role In The Next Phase',
    subtitle: 'The scientist team should own real responsibilities: benchmark design, weak-layer taxonomy, event arbitration, and promotion review.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Validation role definition',
    content: `
      <div class="card-grid reveal delay-1">
        <article class="card">
          <div class="section-label">Benchmark ownership</div>
          <h3>Decide what counts</h3>
          <p>Choose regions, slices, weak-layer cases, and acceptable benchmark deltas.</p>
        </article>
        <article class="card">
          <div class="section-label">Evidence arbitration</div>
          <h3>Review difficult labels</h3>
          <p>Resolve ambiguous event records and define what counts as meaningful corroboration.</p>
        </article>
        <article class="card">
          <div class="section-label">Governance authority</div>
          <h3>Shape promotion criteria</h3>
          <p>Keep candidate-model promotion tied to scientist-reviewed gates rather than engineering enthusiasm.</p>
        </article>
        <article class="card">
          <div class="section-label">Publication role</div>
          <h3>Co-author methods if warranted</h3>
          <p>Use the pilot to generate defensible evidence, not just slideware.</p>
        </article>
      </div>
      <div class="quote-band reveal delay-2">
        <p>This role is operationally meaningful: not advisory theater, but responsibility over what becomes credible enough to claim.</p>
        <small>Scientist-in-the-loop model</small>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-5',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Immediate work surface',
    title: 'Himalayan v3 Partner Handoff Packet',
    subtitle: 'The immediate packet is machine-readable intake infrastructure. It is deliberately not a Himalayan accuracy result.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Scientist benchmark pack v0',
    content: `
      <div class="stack reveal delay-1">
        <div class="matrix">
          <h3 class="matrix-title">What partners receive (20+ artifacts, summarized here; full list in the handout)</h3>
          <div class="matrix-table">
            <div class="matrix-row">
              <div><strong>Start here</strong><p>README, field dictionary, checksum guide, package index, and source-manifest template.</p></div>
              <div><strong>Evidence to fill</strong><p>Ten blank v3 CSVs for stations, weather, snowpack, labels, polygons, events, sensing, terrain, reviews, and holdout.</p></div>
            </div>
            <div class="matrix-row">
              <div><strong>Validation and triage</strong><p>Preflight, evidence validation, source checks, quality score, acceptance checklist, manifest diff, summary, and ledger.</p></div>
              <div><strong>Holdout and claim locks</strong><p>Pre-registered holdout protocol, leakage audit, metric report, release attestation, and explicit claim gates.</p></div>
            </div>
          </div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="warning-band">
          <p><strong>Boundary:</strong> blank templates and instructions only. Synthetic fixtures are validator smoke-tests, never partner evidence. See <code>Scientist_Handout_OnePager.md</code> for the complete inventory.</p>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-6',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Review loop',
    title: 'Validation Protocol v0 And V3 Triage Loop',
    subtitle: 'The minimum scientist-in-the-loop protocol is now tied to partner package triage: source governance, evidence validation, leakage checks, and promotion review.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Scientist validation protocol v0',
    content: `
      <div class="timeline reveal delay-1">
        <div class="timeline-step">
          <strong>01</strong>
          <p>Validate source manifest coverage and reject rows with missing or stale <code>source_ref</code> evidence.</p>
        </div>
        <div class="timeline-step">
          <strong>02</strong>
          <p>Review <code>D_tidy</code>-equivalent label provenance, nowcast/observer refs, regime, and timing fields.</p>
        </div>
        <div class="timeline-step">
          <strong>03</strong>
          <p>Check station X/Y/Z coverage, GPxyz readiness, snowpack provenance, event truth, and remote-sensing scope.</p>
        </div>
        <div class="timeline-step">
          <strong>04</strong>
          <p>Run holdout leakage and metric reports only after package evidence is complete and independent.</p>
        </div>
        <div class="timeline-step">
          <strong>05</strong>
          <p>Carry scientist decisions back into release-gate attestations, deck language, docs, and claim state.</p>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Why this matters now</div>
          <ul class="bullet-list">
            <li>The protocol gives the scientist team and partner reviewers a real review surface from day one.</li>
            <li>It turns “validation” into explicit package, source, label, station, holdout, and release-gate checkpoints.</li>
            <li>It keeps blocked claims blocked until someone can point to the proving artifact and reviewed local evidence.</li>
          </ul>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-7',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Hardest science gap',
    title: 'Critical-Layer And Weak-Layer Program',
    subtitle: 'This is the hardest scientific question in the whole conversation, and the deck should say so plainly.',
    proof: [
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Research synthesis • Top challenges',
    content: `
      <div class="card-grid reveal delay-1">
        <article class="card">
          <div class="section-label">Known limitation</div>
          <h3>Proxy wording is not closure</h3>
          <p>Snowpack proxies and problem framing help, but they do not prove critical-layer fidelity.</p>
        </article>
        <article class="card">
          <div class="section-label">Scientist need</div>
          <h3>Weak-layer benchmark slices</h3>
          <p>The scientist team needs to define the cases that actually matter before promotion is even discussed.</p>
        </article>
        <article class="card">
          <div class="section-label">Why now</div>
          <h3>This is where trust is earned</h3>
          <p>Senior avalanche scientists will ask this early; answering it openly improves credibility.</p>
        </article>
      </div>
      <div class="quote-band reveal delay-2">
        <p>Persistent weak-layer periods are where stronger validation discipline becomes most valuable and most difficult.</p>
        <small>Recent avalanche literature • used as a bounded scientific caution</small>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-8',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Autonomy roadmap',
    title: 'Governed Autonomy Roadmap And Promotion Logic',
    subtitle: 'Autonomy should be framed as a gated progression: ingest, govern, benchmark, review, then promote only if evidence says so.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Governance and promotion logic',
    content: `
      <div class="stack reveal delay-1">
        <div class="diagram-shell">
          <div class="section-label">Promotion logic</div>
          <div class="flow">
            <div class="flow-node"><strong>Governed ingest</strong><p>Evidence enters with confidence, source, corroboration, and decay metadata.</p></div>
            <div class="flow-node"><strong>Benchmark review</strong><p>Scientists inspect narrow evidence mixes, failure slices, and drift signals.</p></div>
            <div class="flow-node"><strong>Gate review</strong><p><code>pss_gate_passed</code>, shadow quality, SAR gates, and readiness remain explicit.</p></div>
            <div class="flow-node"><strong>Promotion only if earned</strong><p>Activation follows artifacts and review, not model novelty alone.</p></div>
          </div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="warning-band">
          <p><strong>Safe phrase:</strong> governed candidate evidence fusion. <strong>Unsafe phrase:</strong> finished autonomous avalanche intelligence.</p>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-9',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Remote sensing path',
    title: 'SAR Qualification Path',
    subtitle: 'Remote sensing is attractive to scientists, but the qualification blockers must be stated before the excitement outruns the evidence.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'SAR qualification analysis',
    content: `
      <div class="card-grid reveal delay-1">
        <article class="card">
          <div class="section-label">Data access</div>
          <h3>Reliable scene access</h3>
          <p>Qualification needs predictable multi-region scene availability and artifact bookkeeping.</p>
        </article>
        <article class="card">
          <div class="section-label">Labels</div>
          <h3>Reference scarcity</h3>
          <p>Held-out avalanche labels remain too thin for strong regional promotion claims.</p>
        </article>
        <article class="card">
          <div class="section-label">Terrain physics</div>
          <h3>Shadow and layover</h3>
          <p>Radar geometry creates real blind spots that need explicit treatment, not optimistic assumptions.</p>
        </article>
        <article class="card">
          <div class="section-label">Weather regime</div>
          <h3>Dry-snow detectability limits</h3>
          <p>Some relevant avalanche signatures remain difficult or ambiguous in the current SAR path.</p>
        </article>
        <article class="card">
          <div class="section-label">Operations</div>
          <h3>Revisit timing</h3>
          <p>The workflow must respect timing gaps before stronger operational claims are earned.</p>
        </article>
        <article class="card">
          <div class="section-label">Qualification scope</div>
          <h3>Region by region</h3>
          <p>SAR should qualify per use case and region rather than via one global promotional statement.</p>
        </article>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-10',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Pilot design',
    title: 'Scientist-In-The-Loop Pilot Design',
    subtitle: 'A credible near-term pilot is structured around benchmark ownership, review cadence, and explicit go or no-go gates.',
    proof: [
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Pilot design',
    content: `
      <div class="timeline reveal delay-1">
        <div class="timeline-step">
          <strong>Weeks 1-3 · Activate</strong>
          <p>Partner handoff session (W1), source-manifest discipline + SHA-256 walkthrough (W2), station metadata + GPxyz readiness gate (W3). Acceptance: ≥1 priority region exits <code>blocked_station_coordinates_required</code>.</p>
        </div>
        <div class="timeline-step">
          <strong>Weeks 4-6 · Evidence</strong>
          <p><code>D_tidy</code> label provenance + weak-layer slice definitions (W4), full validator/leakage triage + 100-point score (W5), Stage-1 RF4 feasibility spike + SAR read-only review (W6). Acceptance: ≥1 region scores ≥50/100; SAR not promoted.</p>
        </div>
        <div class="timeline-step">
          <strong>Weeks 7-9 · Audit + protocol lock</strong>
          <p>Refined-discretization audit (W7), weak-layer evidence pack round 1 (W8), <strong>pre-registered</strong> local holdout protocol with scientist co-signature (W9). Acceptance: protocol SHA-256 captured, immutable thereafter.</p>
        </div>
        <div class="timeline-step">
          <strong>Weeks 10-12 · Review + attestation</strong>
          <p>Weak-layer round 2 + spike iteration (W10), failure-mode review + pre-decision memo (W11), <strong>release-gate attestation or claim_review_blocked ledger entry</strong> (W12). No silent failures.</p>
        </div>
        <div class="timeline-step">
          <strong>Week 13 · Decision</strong>
          <p>60-min session producing one of: <code>Phase_2_Scoping.md</code>, <code>Narrow_Pilot_Charter.md</code>, or <code>Pilot_Termination_Memo.md</code>. Scientist Lead can extend, narrow, block, or terminate at any prior weekly gate.</p>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Per-week handout</div>
          <p>The week-by-week plan with deliverables, owners, acceptance gates, risk triggers, and contingencies (Swiss-only sandbox, synthetic-pseudo-stations, re-submission cycle, scientist-led narrow pilot) lives in <code>MVP_V2_13_Week_Pilot_Plan.md</code>. Companion artifacts: <code>MVP_V2_Action_List.md</code> and <code>MVP_V2_Weekly_Progress_Template.md</code>.</p>
        </div>
      </div>
      <div class="warning-band reveal delay-3">
        <p>Success is not “the model looked good.” Success is a benchmark result the scientist team is willing to stand behind narrowly and carefully.</p>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-11',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Requirements',
    title: 'Data And Field Requirements',
    subtitle: 'The next phase needs concrete contributions: reviewed source packages, case definitions, field context, weak-layer interpretation, and evidence-quality review.',
    proof: [
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Field and data requirements',
    content: `
      <div class="card-grid reveal delay-1">
          <article class="card">
            <div class="section-label">Scientist input</div>
            <h3>D_tidy-quality danger labels</h3>
            <p>Separate raw bulletins from reviewed nowcast, observer, event, or reanalysis-backed truth.</p>
          </article>
          <article class="card">
            <div class="section-label">Field context</div>
            <h3>Station and terrain metadata</h3>
            <p>GPxyz needs latitude, longitude, elevation, density diagnostics, and region coverage before spatial claims.</p>
          </article>
          <article class="card">
            <div class="section-label">Event curation</div>
            <h3>Label arbitration and event truth</h3>
            <p>Ambiguous, duplicated, or thinly sourced avalanche events need shared review and source-manifest backing.</p>
          </article>
        <article class="card">
          <div class="section-label">Honest caveat</div>
          <h3>Offline report replay is not field reliability proof</h3>
            <p>The queue-and-replay mechanism and v3 intake validators exist, but neither proves field-device robustness or Himalayan accuracy.</p>
        </article>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-12',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Execution realism',
    title: 'Engineering And Partner Workstreams Are Already Structured',
    subtitle: 'The path forward is not abstract. The current program already breaks the next work into concrete, bounded streams.',
    proof: [
      { label: 'Validated internal evidence', kind: 'internal' },
    ],
    source: 'Execution workstreams',
    content: `
      <div class="card-grid reveal delay-1">
        <article class="card">
          <div class="section-label">Workstream</div>
          <h3>Claim-state hardening</h3>
          <p>Every sentence is now mapped to an allowed proof tier and blocked-claim rule.</p>
        </article>
          <article class="card">
            <div class="section-label">Workstream</div>
            <h3>Partner-package triage</h3>
            <p><code>run_himalayan_partner_package_triage</code> produces preflight, source, evidence, holdout, ledger, dashboard, manifest, and traceability outputs.</p>
          </article>
        <article class="card">
          <div class="section-label">Workstream</div>
          <h3>Governed autonomy reframing</h3>
          <p>The story has shifted from autonomy rhetoric to governed candidate evidence fusion.</p>
        </article>
        <article class="card">
          <div class="section-label">Workstream</div>
          <h3>Benchmark and protocol packaging</h3>
            <p>Benchmark pack v0, validation protocol v0, and the v3 handoff packet are ready as discussion starters.</p>
        </article>
      </div>
      <div class="warning-band reveal delay-2">
        <p>These workstreams improve the next conversation and pilot design. They do not by themselves convert future science into present proof.</p>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-13',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Team model',
    title: 'Team Shape And Collaboration Model',
    subtitle: 'The likely winning shape is an India-lean engineering core with selective scientist, geospatial, and MLOps depth added when the benchmark program demands it.',
    proof: [
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Team model',
    content: `
      <div class="card-grid reveal delay-1">
        <article class="card">
          <div class="section-label">Core</div>
          <h3>Full-stack and mapping engineers</h3>
          <p>Own the public product shell, admin surfaces, map interactions, and evidence display quality.</p>
        </article>
        <article class="card">
          <div class="section-label">Science and data</div>
          <h3>ML or data engineer plus scientist review</h3>
          <p>Own benchmark assembly, evaluation slices, governance logic, and failure analysis packaging.</p>
        </article>
        <article class="card">
          <div class="section-label">Remote sensing</div>
          <h3>Geospatial or SAR specialist as needed</h3>
          <p>Engage selectively when the qualification path moves from schema to held-out regional evidence.</p>
        </article>
        <article class="card">
          <div class="section-label">Authority center</div>
          <h3>Scientist team at the center</h3>
          <p>Owns benchmark authority, review cadence, and the final interpretation of what becomes credible enough to promote.</p>
        </article>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-14',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Decision-ready roadmap',
    title: 'Three-Phase Timeline, Budget, And Infrastructure',
    subtitle: 'This main-deck roadmap uses only the 3-phase scientist collaboration model. The 5-phase commercialization path stays out of the core meeting arc.',
    proof: [
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Three-phase roadmap',
    content: `
      <div class="phase-grid reveal delay-1">
        <article class="phase-card">
          <div class="phase-meta">Phase 1 • 0-3 months</div>
          <h3 class="phase-title">Platform hardening</h3>
          <p>Lock claim states, verify proof surfaces, and package benchmark intake.</p>
          <p><strong>Budget:</strong> INR 25-40 lakh</p>
        </article>
        <article class="phase-card">
          <div class="phase-meta">Phase 2 • 3-9 months</div>
          <h3 class="phase-title">Scientist-in-the-loop pilot</h3>
          <p>Scientists co-own benchmark design, acceptance thresholds, and review loops.</p>
          <p><strong>Budget:</strong> INR 40-90 lakh</p>
        </article>
        <article class="phase-card">
          <div class="phase-meta">Phase 3 • 9-18 months</div>
          <h3 class="phase-title">Validation expansion</h3>
          <p>Qualify SAR candidates, expand multi-region benchmarking, and publish pilot evidence if earned.</p>
          <p><strong>Budget:</strong> INR 1.2-3.0 crore</p>
        </article>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Infrastructure assumptions</div>
          <ul class="bullet-list">
            <li>Hosted web shell continues on the current React, Supabase, and Netlify baseline.</li>
            <li>Modal.com and GPU spend stay tightly bounded to candidate-model and SAR qualification work.</li>
            <li>Scientist time is budgeted as validation authority and benchmark ownership, not just occasional advisory review.</li>
          </ul>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd3-15',
    kicker: 'Deck 3 of 5',
    eyebrow: 'Specific ask',
    title: 'Concrete Ask, Decision Options, And Next Steps',
    subtitle: 'End the meeting with a choice, not with generic enthusiasm or prediction-success language.',
    proof: [
      { label: 'Research next phase', kind: 'future' },
    ],
    source: 'Decision options',
    content: `
      <div class="decision-grid reveal delay-1">
        <article class="decision-card">
          <div class="section-label">Option 1</div>
          <h3>SASE/DGRE handoff session</h3>
          <ul>
            <li>Walk through README, field dictionary, checksum guide, source manifest, and blank v3 CSVs.</li>
            <li>Low commitment, high clarity before data formatting begins.</li>
          </ul>
        </article>
        <article class="decision-card">
          <div class="section-label">Option 2</div>
          <h3>90-day evidence pilot</h3>
          <ul>
            <li>Partner package submission, triage, scientist review, and go or no-go gates.</li>
            <li>Turns curiosity into inspectable pilot evidence.</li>
          </ul>
        </article>
        <article class="decision-card">
          <div class="section-label">Option 3</div>
          <h3>Deeper co-development track</h3>
          <ul>
            <li>Commit to validation authority, publication intent, and a longer program arc.</li>
            <li>Best only if the scientist team wants to shape the roadmap materially.</li>
          </ul>
        </article>
      </div>
      <div class="quote-band reveal delay-2">
        <p>The ideal immediate ask is a partner handoff session followed by a scientist-led benchmark-design session with selected regional cases and explicit validation criteria.</p>
        <small>Close on a concrete next step, not on AI transformation language</small>
      </div>
    `,
  }),
];

const deck6Slides = [
  slideSection({
    id: 'd6-1',
    kicker: 'Deck 6 of 6',
    eyebrow: 'MVP V2 explanation deck',
    title: 'Database, ML Models, And Himalayan Accuracy Path',
    subtitle: 'A beginner-friendly guide to what the Understand Anything graphs show, how the current model stack works, and what evidence is still needed before Himalayan accuracy can be claimed.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'Understand Anything graph • MVP V2 repo review',
    shellClass: 'split-2',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Plain-English purpose</div>
          <p>This deck explains the system as three connected parts: a database that stores facts, machine-learning models that estimate risk, and evidence gates that decide what may be shown or claimed.</p>
        </div>
        <div class="card-grid">
          <article class="card">
            <h3>For beginners</h3>
            <p>No code reading required; every technical term is mapped to a simple operational meaning.</p>
          </article>
          <article class="card">
            <h3>For scientists</h3>
            <p>The deck keeps label quality, validation data, SAR limits, and local holdout gates visible.</p>
          </article>
        </div>
      </div>
      <div class="stack reveal delay-2">
        ${frame(screenshots.uaStructural, 'Understand Anything structural overview of the Avalanche Insight Hub ML/backend layers.', 'frame--wide frame--dashboard', 'Understand Anything • structural overview')}
      </div>
    `,
  }),
  slideSection({
    id: 'd6-2',
    kicker: 'Deck 6 of 6',
    eyebrow: 'One-minute mental model',
    title: 'Three Things To Remember',
    subtitle: 'The website is not just a map. It is a governed evidence system: store facts, run models, then publish only what passes the right gates.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
    ],
    source: 'Repo architecture synthesis',
    shellClass: 'split-3',
    content: `
      <article class="card reveal delay-1">
        <div class="section-label">1 · Database</div>
        <h3>Stores the facts</h3>
        <p>Supabase/Postgres stores forecast runs, grid cells, events, model status, evaluation records, scientist reviews, and daily verification records.</p>
      </article>
      <article class="card reveal delay-2">
        <div class="section-label">2 · Models</div>
        <h3>Estimate risk</h3>
        <p>Random Forest is the active structured scorer; MTS-LSTM, SAR segmentation, and Swiss RAvaFcast remain gated research or candidate lanes.</p>
      </article>
      <article class="card reveal delay-3">
        <div class="section-label">3 · Evidence gates</div>
        <h3>Control claims</h3>
        <p>Publication, SAR, Himalayan partner, and holdout gates stop unsupported claims even when a model or graph looks promising.</p>
      </article>
      ${dashboardEvidence([
        { src: screenshots.uaDomain, alt: 'Understand Anything domain overview for the avalanche system.', label: 'Domain overview' },
        { src: screenshots.uaActiveRf, alt: 'Active RF pipeline screenshot.', label: 'Active RF' },
        { src: screenshots.uaHimalayan, alt: 'Himalayan partner evidence screenshot.', label: 'Himalayan evidence' },
      ])}
    `,
  }),
  slideSection({
    id: 'd6-3',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Dashboard map',
    title: 'What The Graph Is Showing',
    subtitle: 'Understand Anything turned the repo into a visual map: 2,045 nodes, 4,015 edges, and 10 ML/backend layers for the structural view.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
    ],
    source: '.understand-anything/knowledge-graph.json',
    content: `
      <div class="stack reveal delay-1">
        ${frame(screenshots.uaStructural, 'Structural graph showing ten ML and backend layers.', 'frame--wide frame--dashboard', '10 structural layers')}
      </div>
      <div class="stack reveal delay-2">
        <div class="stat-row">
          <article class="stat">
            <div class="stat-label">Nodes</div>
            <div class="stat-number">2,045</div>
            <p>Files, functions, classes, pipelines, config, and docs.</p>
          </article>
          <article class="stat">
            <div class="stat-label">Edges</div>
            <div class="stat-number">4,015</div>
            <p>Relationships that show how code and evidence connect.</p>
          </article>
          <article class="stat">
            <div class="stat-label">Layers</div>
            <div class="stat-number">10</div>
            <p>Grouped ML/backend workstreams, not random file lists.</p>
          </article>
        </div>
        <div class="lead-panel">
          <p>The graph is a navigation aid. It does not prove scientific accuracy by itself; it helps reviewers see where the implemented evidence and remaining gates live.</p>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd6-4',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Database basics',
    title: 'The Database In Plain English',
    subtitle: 'The database is the system ledger: it records forecast products, event evidence, model state, evaluation runs, and scientist review decisions.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
    ],
    source: 'Supabase migrations • README architecture',
    shellClass: 'split-3',
    content: `
      <article class="card reveal delay-1">
        <div class="section-label">Forecast facts</div>
        <h3>Runs and grid cells</h3>
        <p><code>forecast_runs</code>, <code>forecast_run_hours</code>, <code>forecast_grids</code>, and publication events record what was generated and published.</p>
      </article>
      <article class="card reveal delay-2">
        <div class="section-label">Ground evidence</div>
        <h3>Events and reports</h3>
        <p><code>avalanche_events</code>, field reports, outcome labels, and feature logs form the evidence trail behind model evaluation.</p>
      </article>
      <article class="card reveal delay-3">
        <div class="section-label">Governance</div>
        <h3>Status and reviews</h3>
        <p><code>model_status</code>, <code>evaluation_runs</code>, <code>scientist_validation_reviews</code>, and daily verifications keep model state and human checks visible.</p>
      </article>
      ${dashboardEvidence([
        { src: screenshots.uaBackend, alt: 'Backend support and shared infrastructure layer screenshot.', label: 'Backend support' },
        { src: screenshots.uaEvaluation, alt: 'Evaluation and release governance layer screenshot.', label: 'Governance tables' },
      ])}
    `,
  }),
  slideSection({
    id: 'd6-5',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Database flow',
    title: 'Forecast Run To Public Map',
    subtitle: 'A beginner can read the data path as a chain: inputs become a model run, the run writes grid cells, the public map reads the published grid, and scientists review exceptions.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
    ],
    source: 'Forecast publication plane • scientist workbench migrations',
    shellClass: 'split-2',
    content: `
      <div class="diagram-shell reveal delay-1">
        <div class="section-label">Core flow</div>
        <div class="flow">
          <div class="flow-node"><strong>Inputs</strong><p>Weather, terrain, snowpack proxies, event history, and model status.</p></div>
          <div class="flow-node"><strong>Forecast run</strong><p>Backend scoring creates a dated run with lineage and metadata.</p></div>
          <div class="flow-node"><strong>Grid cells</strong><p>Cell-level risk values become the map surface and bulletin context.</p></div>
          <div class="flow-node"><strong>Review</strong><p>Scientists and operators inspect cases, actions, and daily verification records.</p></div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">What is not UI-complete today</div>
          <p>Himalayan partner evidence intake is still CSV, source-manifest, and CLI based. The current UI supports product and review concepts, but the full partner evidence package is not yet a web form workflow.</p>
        </div>
        ${dashboardEvidence([
          { src: screenshots.uaEvaluation, alt: 'Evaluation and publication governance layer screenshot.', label: 'Review/gates' },
          { src: screenshots.uaBackend, alt: 'Backend support layer screenshot.', label: 'Data flow support' },
        ])}
      </div>
    `,
  }),
  slideSection({
    id: 'd6-6',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Model ladder',
    title: 'Current ML Model Map',
    subtitle: 'The system deliberately separates active, candidate, shadow, research, and evidence lanes so one promising result does not become an unsupported public claim.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'Understand Anything structural graph • backend model scan',
    shellClass: 'split-2',
    content: `
      <div class="stack reveal delay-1">
        ${frame(screenshots.uaActiveRf, 'Understand Anything layer view for the active Random Forest forecast pipeline.', 'frame--compact frame--dashboard', 'Active RF layer')}
      </div>
      <div class="stack reveal delay-2">
        <div class="matrix">
          <h3 class="matrix-title">Five lanes</h3>
          <div class="matrix-table">
            <div class="matrix-row"><div><strong>Active</strong><p>Random Forest with terrain, weather, and snowpack features.</p></div><div><strong>Candidate</strong><p>MTS-LSTM for future temporal learning.</p></div></div>
            <div class="matrix-row"><div><strong>Shadow and research</strong><p>SAR shadow plus Swiss RAvaFcast RF4, GPxyz, and refined aggregation.</p></div><div><strong>Evidence and claim lock</strong><p>Himalayan partner evidence; <code>production_scoring_allowed=false</code>; <code>himalayan_accuracy_claim_allowed=false</code>.</p></div></div>
          </div>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd6-7',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Active model',
    title: 'How Random Forest Improves Prediction',
    subtitle: 'Random Forest is a practical baseline: it combines many simple decision trees so the final estimate is less fragile than one hand-written rule.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
    ],
    source: 'backend/models/surrogate_rf.py • backend/daily_inference.py',
    shellClass: 'split-3',
    content: `
      <article class="card reveal delay-1">
        <div class="section-label">Input features</div>
        <h3>More than one signal</h3>
        <p>Terrain, weather, snowpack proxies, historical context, and freshness cues become structured columns for the model.</p>
      </article>
      <article class="card reveal delay-2">
        <div class="section-label">Tree ensemble</div>
        <h3>Many small votes</h3>
        <p>Each tree learns a different split pattern; the ensemble combines them to reduce dependence on a single brittle rule.</p>
      </article>
      <article class="card reveal delay-3">
        <div class="section-label">Publication gate</div>
        <h3>Prediction is not enough</h3>
        <p>The score must still pass model-status, lineage, freshness, and confidence controls before it is safe to publish.</p>
      </article>
      ${dashboardEvidence([
        { src: screenshots.uaActiveRf, alt: 'Active Random Forest pipeline layer screenshot.', label: 'RF layer' },
        { src: screenshots.uaEvaluation, alt: 'Evaluation and release governance layer screenshot.', label: 'Publication gates' },
      ])}
    `,
  }),
  slideSection({
    id: 'd6-8',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Quality controls',
    title: 'Calibration And Explainability',
    subtitle: 'Good prediction is not only the top class. The system also needs probability quality, explanation traces, and publication proof.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
    ],
    source: 'Model status, evaluation, and methodology reports',
    shellClass: 'split-2',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Calibration</div>
          <p>Calibration checks whether a probability behaves like a probability. If the model says 70% risk often, roughly 7 out of 10 comparable cases should behave that way over a valid evaluation set.</p>
        </div>
        <div class="lead-panel">
          <div class="section-label">Explainability</div>
          <p>TreeSHAP-style explanations and feature summaries help reviewers see why a cell moved up or down, instead of treating the model as a black box.</p>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="warning-band">
          <p>The current deck keeps explanation and calibration as evidence controls, not as magic. If a run falls back to heuristic explanation, that must remain visible.</p>
        </div>
        ${dashboardEvidence([
          { src: screenshots.uaEvaluation, alt: 'Evaluation and release governance layer screenshot.', label: 'Evaluation layer' },
          { src: screenshots.uaTests, alt: 'Tests and CI gates layer screenshot.', label: 'Test gates' },
        ])}
      </div>
    `,
  }),
  slideSection({
    id: 'd6-9',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Candidate model',
    title: 'Why MTS-LSTM May Help Later',
    subtitle: 'Avalanche danger changes over time. A sequence model can learn recent weather and snowpack progression, but it needs enough reviewed local sequences before promotion can be discussed.',
    proof: [
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'backend/lstm_model.py • backend/models/mts_lstm.py',
    shellClass: 'split-2',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Beginner version</div>
          <p>Random Forest sees a structured snapshot. MTS-LSTM can learn a short story over time: wind loading, snowfall, warming, settling, and changing instability.</p>
        </div>
      </div>
      <div class="card-grid reveal delay-2">
        <article class="card">
          <h3>Potential benefit</h3>
          <p>Better use of multi-day weather and snowpack sequences.</p>
        </article>
        <article class="card">
          <h3>Current boundary</h3>
          <p>Candidate lane only; it needs reviewed data, benchmark gates, and drift checks before activation.</p>
        </article>
      </div>
      ${dashboardEvidence([
        { src: screenshots.uaMtsLstm, alt: 'MTS-LSTM candidate model layer screenshot.', label: 'MTS-LSTM layer' },
        { src: screenshots.uaTests, alt: 'Tests and CI gates layer screenshot.', label: 'Candidate gates' },
      ])}
    `,
  }),
  slideSection({
    id: 'd6-10',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Remote sensing',
    title: 'SAR Shadow Lane',
    subtitle: 'Satellite radar can reveal avalanche deposits in places with sparse ground reports, but this lane remains shadow-gated because transferability and false positives are real scientific risks.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'SAR qualification scripts • SnowSlide and AvalCD artifacts',
    content: `
      <div class="stack reveal delay-1">
        ${frame(screenshots.uaSarShadow, 'Understand Anything layer view for the SAR shadow lane.', 'frame--wide frame--dashboard', 'SAR shadow lane')}
      </div>
      <div class="stack reveal delay-2">
        <div class="card-grid">
          <article class="card"><h3>Why it helps</h3><p>Sentinel-1 can monitor large remote areas through cloud cover.</p></article>
          <article class="card"><h3>Why it is gated</h3><p>Wet snow, crevasses, shadow/layover, small events, and scene transfer can distort detections.</p></article>
          <article class="card"><h3>Current posture</h3><p>AvalCD and SnowSlide evidence are valuable, but SAR stays out of public scoring until held-out gates pass.</p></article>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd6-11',
    kicker: 'Deck 6 of 6',
    eyebrow: 'European evidence',
    title: 'What Europe Adds To The Method',
    subtitle: 'European datasets and papers improve the methodology: label discipline, common danger language, spatial interpolation, aggregation, and remote-sensing caution.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'EAWS • NHESS 2022 • GMD 2024 • The Cryosphere 2024 • AvalCD arXiv 2026',
    shellClass: 'split-2',
    content: `
      <div class="stack reveal delay-1">
        ${frame(screenshots.uaSwiss, 'Understand Anything Swiss RAvaFcast reproduction layer screenshot.', 'frame--compact frame--dashboard', 'Swiss RAvaFcast research lane')}
      </div>
      <div class="stack reveal delay-2">
        <div class="matrix">
          <h3 class="matrix-title">European method lessons</h3>
          <div class="matrix-table">
            <div class="matrix-row"><div><strong>EAWS scale</strong><p>Shared 1-5 danger language.</p></div><div><strong>NHESS 2022</strong><p><code>D_tidy</code> labels and Random Forest baseline discipline.</p></div></div>
            <div class="matrix-row"><div><strong>GMD 2024</strong><p>Swiss RAvaFcast RF, GPxyz, and refined aggregation.</p></div><div><strong>The Cryosphere 2024</strong><p>SAR transfer limits, wet-snow false positives, small misses, shadow/layover.</p></div></div>
            <div class="matrix-row"><div><strong>AvalCD</strong><p>SAR change-detection benchmark context.</p></div><div><strong>Claim discipline</strong><p>Method transfer only; Himalayan proof needs local reviewed data.</p></div></div>
          </div>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd6-12',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Himalayan transfer',
    title: 'Why This Helps Himalayas, But Is Not Enough',
    subtitle: 'The European work gives a strong blueprint. Himalayan readiness still needs local reviewed labels, station coverage, event truth, warning-region geometry, and an independent holdout.',
    proof: [
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'Himalayan v3 partner evidence contract',
    content: `
      <div class="stack reveal delay-1">
        ${frame(screenshots.uaHimalayan, 'Understand Anything layer view for the Himalayan partner evidence contract.', 'frame--wide frame--dashboard', 'Himalayan partner evidence')}
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Critical boundary</div>
          <p>Swiss and European evidence can improve the playbook, feature discipline, and validation gates. It cannot substitute for Himalayan station X/Y/Z metadata, D_tidy-grade local labels, event evidence, polygons, and a leakage-checked holdout.</p>
        </div>
      </div>
    `,
  }),
  slideSection({
    id: 'd6-13',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Partner checklist',
    title: 'Himalayan Data Checklist',
    subtitle: 'This is the practical input list partners and scientists must fill before local claims can advance.',
    proof: [
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'partner_evidence_templates/*.csv',
    shellClass: 'split-2',
    content: `
      <div class="stack reveal delay-1">
        <div class="matrix">
          <h3 class="matrix-title">Core files to fill</h3>
          <div class="matrix-table">
            <div class="matrix-row"><div><strong>Station X/Y/Z</strong><p><code>station_metadata.csv</code></p></div><div><strong>Weather</strong><p><code>weather_station_observations.csv</code></p></div></div>
            <div class="matrix-row"><div><strong>Snowpack</strong><p><code>snowpack_profile_features.csv</code></p></div><div><strong>D_tidy labels</strong><p><code>danger_labels_and_bulletins.csv</code></p></div></div>
            <div class="matrix-row"><div><strong>Events and terrain</strong><p><code>historical_avalanche_events.csv</code>, <code>terrain_ates_runout_validation.csv</code></p></div><div><strong>Regions and holdout</strong><p><code>warning_region_polygons.csv</code>, <code>independent_himalayan_holdout.csv</code></p></div></div>
          </div>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="lead-panel">
          <div class="section-label">Fields that matter most</div>
          <ul class="bullet-list">
            <li><code>source_ref</code>, <code>license_scope</code>, <code>review_status</code>, <code>reviewer_id</code>, and <code>reviewed_at</code>.</li>
            <li>Latitude, longitude, elevation, validity windows, avalanche regime, label source, and reviewer notes.</li>
          </ul>
        </div>
        ${dashboardEvidence([
          { src: screenshots.uaHimalayan, alt: 'Himalayan partner evidence contract screenshot.', label: 'Partner contract' },
          { src: screenshots.uaDomain, alt: 'Domain overview screenshot.', label: 'Evidence domains' },
        ])}
      </div>
    `,
  }),
  slideSection({
    id: 'd6-14',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Technology FAQ',
    title: 'Beginner FAQ',
    subtitle: 'The technology stack is easier to understand when each tool is tied to a simple job.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
    ],
    source: 'README • package and backend scan',
    shellClass: 'split-3',
    content: `
      <article class="card reveal delay-1"><h3>React + Vite</h3><p>Builds the website screens and packages the frontend quickly.</p></article>
      <article class="card reveal delay-2"><h3>Supabase + PostGIS</h3><p>Stores database tables, auth, storage, functions, and geospatial map facts.</p></article>
      <article class="card reveal delay-3"><h3>Python + scikit-learn</h3><p>Runs data preparation, Random Forest, calibration, evaluation, and reports.</p></article>
      <article class="card reveal delay-1"><h3>PyTorch</h3><p>Supports MTS-LSTM candidate models and SAR segmentation experiments.</p></article>
      <article class="card reveal delay-2"><h3>Modal</h3><p>Runs bounded heavier compute jobs outside the public click path when authorized.</p></article>
      <article class="card reveal delay-3"><h3>Understand Anything</h3><p>Creates visual codebase maps so reviewers can see how the system fits together.</p></article>
      ${dashboardEvidence([
        { src: screenshots.uaStructural, alt: 'Structural graph screenshot showing frameworks.', label: 'Code map' },
        { src: screenshots.uaModal, alt: 'Modal and remote compute layer screenshot.', label: 'Remote compute' },
        { src: screenshots.uaBackend, alt: 'Backend support layer screenshot.', label: 'Backend' },
      ])}
    `,
  }),
  slideSection({
    id: 'd6-15',
    kicker: 'Deck 6 of 6',
    eyebrow: 'Next actions',
    title: 'What To Do Next, And What Not To Say',
    subtitle: 'The path forward is practical: collect local evidence, run triage, validate with scientists, then decide whether a narrow Himalayan pilot is justified.',
    proof: [
      { label: 'Technical evidence', kind: 'internal' },
      { label: 'Research agenda', kind: 'future' },
    ],
    source: 'MVP V2 claim locks and partner handoff plan',
    shellClass: 'split-2',
    content: `
      <div class="stack reveal delay-1">
        <div class="lead-panel">
          <div class="section-label">Next actions</div>
          <ul class="bullet-list">
            <li>Send partner handoff packet and ask for reviewed Himalayan source packages.</li>
            <li>Run partner package triage and source-manifest validation.</li>
            <li>Have scientists adjudicate label quality, station coverage, event truth, and holdout validity.</li>
            <li>Advance only a narrow pilot if local gates pass.</li>
          </ul>
        </div>
      </div>
      <div class="stack reveal delay-2">
        <div class="warning-band">
          <p><strong>Do not say:</strong> Himalayan accuracy is established, SAR is activated for public scoring, or the platform replaces regional avalanche forecasters.</p>
        </div>
        <div class="lead-panel">
          <div class="section-label">Allowed current framing</div>
          <p>Evidence-governed MVP V2 with a live technical proof region, active Random Forest baseline, research-only Swiss and SAR lanes, and a Himalayan partner evidence path.</p>
        </div>
        ${dashboardEvidence([
          { src: screenshots.uaHimalayan, alt: 'Himalayan partner evidence contract screenshot.', label: 'Next evidence path' },
          { src: screenshots.uaEvaluation, alt: 'Evaluation and release governance screenshot.', label: 'Release gates' },
        ])}
      </div>
    `,
  }),
];

function renderHtml({ bodyClass, deckName, deckSubtitle, slides }) {
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
  <title>${deckName}</title>
  <meta name="description" content="${deckSubtitle}">
  <style>${sharedCss}</style>
</head>
<body class="${bodyClass}">
  <main>
    ${slides.join('\n')}
  </main>
  <div class="keyboard-hint">Arrow keys • wheel • swipe</div>
  <div class="progress-shell" aria-hidden="true">
    <span class="progress-count" data-progress-count>01 / ${String(slides.length).padStart(2, '0')}</span>
    <span class="progress-bar"><span data-progress-fill></span></span>
  </div>
  <script>${sharedJs}</script>
</body>
</html>`;
}

function applyReplacements(text, replacements) {
  return replacements.reduce((value, [from, to]) => value.split(from).join(to), text);
}

function sanitizeClientFacingHtml(html) {
  const replacements = [
    ['Validated internal evidence', evidenceLabels.internal],
    ['Research next phase', evidenceLabels.future],
    ['The slide that separates scientific precedent from current implementation and from what still needs scientist co-development.', 'The slide that separates scientific precedent from current implementation and from what still needs scientist-led research.'],
    ['Still open for co-development', 'Next research program'],
    ['Public route screenshots plus hosted <code>/admin</code> route/auth smoke from May 8, 2026.', 'Public route screenshots and hosted <code>/admin</code> access checks from May 8, 2026.'],
    ['First live-proof slide', 'Current platform view'],
    ['What The Current Live Platform Proves Today', 'What The Live Platform Shows Today'],
    ['This is the live proof surface: a forecast workspace, structured bulletin layer, explicit uncertainty cues, and terrain-aware masking.', 'This is the current live platform surface: a forecast workspace, structured bulletin, explicit uncertainty cues, and terrain-aware masking.'],
    ['The deck uses what the hosted screenshot proves, not a hard-coded horizon claim.', 'The deck uses what the hosted screenshot shows, not a fixed horizon claim.'],
    ['Live route showing share workflow confirmation.', 'Live route showing share workflow panel.'],
    ['Operator lane', 'Administration view'],
    ['Admin Evidence Surfaces And Evidence Rules', 'Administration Surfaces And Evidence Context'],
    ['Hosted-authenticated review on May 8, 2026 allows a real admin observability view as validated internal evidence.', 'Hosted-authenticated access on May 8, 2026 provides a current administration observability view for technical discussion.'],
    ['Evidence rule now in effect', 'Current access and interpretation'],
    ['Always proves route or gate availability when reachable.', 'Shows administration access and route availability when reachable.'],
    ['Current smoke', 'Current access check'],
    ['Fresh hosted-authenticated access succeeded, so the signed-in observability view can be discussed as validated internal evidence.', 'Fresh hosted-authenticated access succeeded, so the signed-in observability view can be discussed as technical evidence.'],
    ['What the admin lane adds', 'What the administration view adds'],
    ['What it does not add', 'What it does not settle'],
    ['Promotion proof by itself. It is richer observability, not a shortcut around validation.', 'Candidate advancement is not settled here. This is richer observability, not a shortcut around validation.'],
    ['if hosted-auth access fails later', 'if hosted-auth access is unavailable later'],
    ['SAR flows exist as candidate evidence paths, not as current public forecast proof.', 'SAR flows exist as candidate evidence paths, not as current public forecast support.'],
    ['<div class="section-label">Safe phrase</div>', '<div class="section-label">Current description</div>'],
    ['That is the safest current description of Modal.com in the platform story.', 'That is the most accurate current description of Modal.com in the platform story.'],
    ['Weighting, corroboration, decay, and blocked-gate discipline are real. Scientist-grade truth generation is not yet proven and must stay framed that way.', 'Weighting, corroboration, decay, and blocked-gate discipline are real. Scientist-grade truth generation has not been established and should remain framed that way.'],
    ['What the current artifact does and does not prove', 'What the current artifact shows and what remains open'],
    ['<strong>Proves</strong>', '<strong>Shows</strong>'],
    ['<strong>Does not prove</strong>', '<strong>Does not establish</strong>'],
    ['Fresh, diversified capture or robust regional transfer strong enough for autonomy-forward marketing language.', 'Fresh, diversified capture or robust regional transfer strong enough for autonomy-forward language.'],
    ['What to say safely', 'Current reading'],
    ['<strong>Do not say:</strong>', '<strong>Avoid saying:</strong>'],
    ['The artifact only supports cautious governance language.', 'The artifact supports only cautious governance language.'],
    ['“Modal.com supports candidate compute, not the current public proof surface.”', '“Modal.com supports candidate compute, not the current public platform surface.”'],
    ['The right close is not certainty. It is whether the next scientist-owned validation step is worth doing now.', 'The right close is not certainty. It is whether the next scientist-led validation step should begin now.'],
    ['The platform already proves a serious decision-support shell and disciplined governance posture.', 'The platform already provides a serious decision-support shell and disciplined governance posture.'],
    ['The missing science is visible rather than hidden, which makes co-development discussable.', 'The missing science is visible rather than hidden, which makes the next research step concrete.'],
    ['<strong>Meeting question:</strong> should the scientist team help own the benchmark, validation, and promotion frontier from here?', '<strong>Meeting question:</strong> should the scientist team help shape the benchmark, validation, and advancement program from here?'],
    ['The platform proves enough to justify a serious discussion. It does not prove enough to skip scientist-owned validation.', 'The platform is ready for a serious scientific discussion. It is not yet a finished validation story.'],
    ['The product proof is real: public route, admin observability, explainable baseline, and governance surfaces.', 'The current platform already includes a public route, administration observability, an explainable baseline, and governance surfaces.'],
    ['Public-facing product shell and operator evidence surfaces already exist.', 'Public-facing platform shell and operational evidence surfaces already exist.'],
    ['This collaboration only works if live-platform truth, validated internal evidence, and future ambition remain visibly separate throughout the program.', 'This collaboration only works if current platform behavior, technical evidence, and future research remain visibly separate throughout the program.'],
    ['Claim state must map to evidence state: live platform, validated internal evidence, or research next phase.', 'Every major statement should map to one of three lanes: live platform, technical evidence, or research agenda.'],
    ['Validation authority stays with scientists and operators, not with product marketing language.', 'Validation authority stays with scientists and operators, not with promotional language.'],
    ['A co-owned validation pack can become the basis for publishable pilot evidence, not just demo polish.', 'A co-owned validation pack can become the basis for publishable pilot evidence, not just interface polish.'],
    ['Public route proof, admin observability, inference manifest, stability summary, evaluation contracts, and governance contracts.', 'Public route evidence, administration observability, inference manifest, stability summary, evaluation contracts, and governance contracts.'],
    ['It keeps blocked claims blocked until someone can point to the proving artifact.', 'It keeps blocked claims blocked until someone can point to the supporting artifact.'],
    ['<strong>Safe phrase:</strong>', '<strong>Recommended framing:</strong>'],
    ['<strong>Unsafe phrase:</strong>', '<strong>Avoid:</strong>'],
    ['Offline report replay is not field reliability proof', 'Offline report replay is not the same as field reliability'],
    ['Every sentence is now mapped to an allowed proof tier and blocked-claim rule.', 'Every major statement is now mapped to a clear evidence lane and blocked-claim rule.'],
    ['These workstreams improve the next conversation and pilot design. They do not by themselves convert future science into present proof.', 'These workstreams improve the next conversation and pilot design. They do not by themselves convert future research into present-day operating readiness.'],
    ['Lock claim states, verify proof surfaces, and package benchmark intake.', 'Lock claim states, verify core evidence surfaces, and package benchmark intake.'],
    ['Scientist co-development model, benchmark path, and roadmap.', 'Scientist collaboration model, validation path, and roadmap.'],
  ];

  return applyReplacements(html, replacements);
}

function decodeEntities(text) {
  return text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

function stripHtmlForTranscript(html) {
  const raw = decodeEntities(
    html
      .replace(/<li>/g, '\n- ')
      .replace(/<\/(p|li|div|article|section|h1|h2|h3|h4|figcaption|small|ul|ol|strong)>/g, '\n')
      .replace(/<br\s*\/?>/g, '\n')
      .replace(/<code>/g, '`')
      .replace(/<\/code>/g, '`')
      .replace(/<[^>]+>/g, ''),
  );

  return raw
    .split('\n')
    .map((line) => line.replace(/\s+/g, ' ').trim())
    .reduce((lines, line) => {
      if (!line) {
        if (lines[lines.length - 1] !== '') lines.push('');
        return lines;
      }

      lines.push(line);
      return lines;
    }, [])
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function renderTranscriptMarkdown(deckTitle, html) {
  const sectionRegex = /<section class="slide" id="([^"]+)">([\s\S]*?)<\/section>/g;
  const slides = [];
  let match;

  while ((match = sectionRegex.exec(html)) !== null) {
    const [, slideId, slideHtml] = match;
    const eyebrow = slideHtml.match(/<div class="eyebrow">([\s\S]*?)<\/div>/)?.[1] ?? '';
    const title = slideHtml.match(/<h1 class="slide-title">([\s\S]*?)<\/h1>/)?.[1] ?? '';
    const subtitle = slideHtml.match(/<p class="slide-subtitle">([\s\S]*?)<\/p>/)?.[1] ?? '';
    const proofMatches = [...slideHtml.matchAll(/<span class="proof-chip [^"]+">([\s\S]*?)<\/span>/g)].map((item) => item[1].trim());
    const contentStart = slideHtml.indexOf('<div class="content-shell');
    const contentOpenEnd = contentStart >= 0 ? slideHtml.indexOf('>', contentStart) : -1;
    const footerStart = slideHtml.lastIndexOf('<div class="footer">');
    const contentHtml = contentOpenEnd >= 0 && footerStart >= 0 ? slideHtml.slice(contentOpenEnd + 1, footerStart) : '';
    const contentText = stripHtmlForTranscript(contentHtml);

    slides.push(
      `## ${slideId.toUpperCase()} — ${decodeEntities(title)}\n\n` +
      (eyebrow ? `_${decodeEntities(eyebrow)}_\n\n` : '') +
      (subtitle ? `${decodeEntities(subtitle)}\n\n` : '') +
      (proofMatches.length ? `Evidence lanes: ${proofMatches.join('; ')}\n\n` : '') +
      `${contentText}`.trim(),
    );
  }

  return `# ${deckTitle} Transcript\n\n${slides.join('\n\n---\n\n')}\n`;
}

async function writeDeck(fileName, html) {
  await fs.writeFile(path.join(__dirname, fileName), html.replace(/[ \t]+$/gm, ''), 'utf8');
}

async function writeTranscript(fileName, markdown) {
  await fs.writeFile(path.join(__dirname, fileName), markdown.replace(/[ \t]+$/gm, ''), 'utf8');
}

async function main() {
  const deck1Html = sanitizeClientFacingHtml(
    renderHtml({
      bodyClass: 'deck-credibility',
      deckName: 'Avalanche Insight Hub — Credibility Review',
      deckSubtitle: 'Current live platform, scientific context, and governance boundaries.',
      slides: deck1Slides,
    }),
  );
  await writeDeck(
    'avalanche-insight-hub-deck-1-credibility.html',
    deck1Html,
  );
  await writeTranscript(
    'avalanche-insight-hub-deck-1-credibility-transcript.md',
    renderTranscriptMarkdown('Avalanche Insight Hub — Credibility', deck1Html),
  );

  const deck2Html = sanitizeClientFacingHtml(
    renderHtml({
      bodyClass: 'deck-collaboration',
      deckName: 'Avalanche Insight Hub — Deck 3 Scientist Validation',
      deckSubtitle: 'Scientist collaboration model, validation path, and roadmap.',
      slides: deck2Slides,
    }),
  );
  await writeDeck(
    'avalanche-insight-hub-deck-3-scientist-validation.html',
    deck2Html,
  );
  const collaborationTranscript = renderTranscriptMarkdown('Avalanche Insight Hub — Collaboration', deck2Html);
  await writeTranscript(
    'avalanche-insight-hub-deck-3-scientist-validation-transcript.md',
    collaborationTranscript,
  );
  await writeTranscript(
    'avalanche-insight-hub-deck-2-collaboration-transcript.md',
    collaborationTranscript,
  );

  const techMarkdown = await fs.readFile(path.join(__dirname, 'Tech_deck_final.md'), 'utf8');
  const techHtml = sanitizeClientFacingHtml(
    renderHtml({
      bodyClass: 'deck-technical',
      deckName: 'Avalanche Insight Hub — Deck 4 Technical Architecture',
      deckSubtitle: 'Current platform architecture, proof boundaries, and future technical strategy.',
      slides: renderTechnicalSlides(techMarkdown),
    }),
  );
  await writeDeck(
    'avalanche-insight-hub-deck-4-technical-architecture.html',
    techHtml,
  );
  const technicalArchitectureTranscript = renderTranscriptMarkdown('Avalanche Insight Hub — Technical Architecture', techHtml);
  await writeTranscript(
    'avalanche-insight-hub-deck-4-technical-architecture-transcript.md',
    technicalArchitectureTranscript,
  );
  await writeTranscript(
    'avalanche-insight-hub-technical-architecture-transcript.md',
    technicalArchitectureTranscript,
  );

  const challengeMarkdown = await fs.readFile(path.join(__dirname, 'deck_challenge_alignment_final.md'), 'utf8');
  const challengeHtml = sanitizeClientFacingHtml(
    renderHtml({
      bodyClass: 'deck-challenges',
      deckName: 'Avalanche Insight Hub — Deck 2 Top 15 Challenge Alignment',
      deckSubtitle: 'Evidence-gated mapping of systemic avalanche forecasting challenges to current MVP response.',
      slides: renderMarkdownSlides(challengeMarkdown, {
        idPrefix: 'd2',
        kicker: 'Deck 2 of 5',
        eyebrow: 'Challenge alignment',
        defaultSource: 'Top challenges source pack',
      }),
    }),
  );
  await writeDeck(
    'avalanche-insight-hub-deck-2-challenge-alignment.html',
    challengeHtml,
  );
  await writeTranscript(
    'avalanche-insight-hub-deck-2-challenge-alignment-transcript.md',
    renderTranscriptMarkdown('Avalanche Insight Hub — Challenge Alignment', challengeHtml),
  );

  const termsMarkdown = await fs.readFile(path.join(__dirname, 'deck_technology_terms_final.md'), 'utf8');
  const termsHtml = sanitizeClientFacingHtml(
    renderHtml({
      bodyClass: 'deck-terms',
      deckName: 'Avalanche Insight Hub — Technology Glossary And Future Strategy',
      deckSubtitle: 'Plain-English technical glossary, release gates, and future strategy boundaries.',
      slides: renderMarkdownSlides(termsMarkdown, {
        idPrefix: 'd5',
        kicker: 'Deck 5 of 5',
        eyebrow: 'Technical field guide',
        defaultSource: 'Technical glossary source pack',
      }),
    }),
  );
  await writeDeck(
    'avalanche-insight-hub-deck-5-technology-glossary.html',
    termsHtml,
  );
  await writeTranscript(
    'avalanche-insight-hub-deck-5-technology-glossary-transcript.md',
    renderTranscriptMarkdown('Avalanche Insight Hub — Technology Glossary', termsHtml),
  );

  const mlUnderstandingHtml = sanitizeClientFacingHtml(
    renderHtml({
      bodyClass: 'deck-ml-understanding',
      deckName: 'Avalanche Insight Hub — Database, ML Models, And Himalayan Accuracy Path',
      deckSubtitle: 'Beginner-friendly MVP V2 guide to the Understand Anything graphs, database, model lanes, and validation gates.',
      slides: deck6Slides,
    }),
  );
  await writeDeck(
    'avalanche-insight-hub-deck-6-ml-understanding.html',
    mlUnderstandingHtml,
  );
  await writeTranscript(
    'avalanche-insight-hub-deck-6-ml-understanding-transcript.md',
    renderTranscriptMarkdown('Avalanche Insight Hub — Database, ML Models, And Himalayan Accuracy Path', mlUnderstandingHtml),
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
