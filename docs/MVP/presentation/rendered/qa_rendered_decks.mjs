import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const baseUrl = process.env.DECK_BASE_URL || 'http://127.0.0.1:4380';
const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const today = '2026-05-28';

const decks = [
  {
    slug: 'deck-1',
    label: 'Deck 1 — Credibility',
    html: 'avalanche-insight-hub-deck-1-credibility.html',
    pdf: 'avalanche-insight-hub-deck-1-credibility.pdf',
    slideCount: 15,
    requiredProofSlides: ['d1-9', 'd1-10', 'd1-11', 'd1-12'],
  },
  {
    slug: 'deck-2',
    label: 'Deck 2 — Challenge Alignment',
    html: 'avalanche-insight-hub-deck-2-challenge-alignment.html',
    pdf: 'avalanche-insight-hub-deck-2-challenge-alignment.pdf',
    slideCount: 15,
    requiredProofSlides: ['d2-6', 'd2-8', 'd2-13'],
  },
  {
    slug: 'deck-3',
    label: 'Deck 3 — Collaboration',
    html: 'avalanche-insight-hub-deck-3-scientist-validation.html',
    pdf: 'avalanche-insight-hub-deck-3-scientist-validation.pdf',
    slideCount: 15,
    requiredProofSlides: ['d3-8', 'd3-9', 'd3-14'],
  },
  {
    slug: 'tech',
    label: 'Deck 4 — Technical Architecture',
    html: 'avalanche-insight-hub-deck-4-technical-architecture.html',
    pdf: 'avalanche-insight-hub-deck-4-technical-architecture.pdf',
    slideCount: 15,
    requiredProofSlides: ['t-1', 't-5', 't-8'],
  },
  {
    slug: 'technology-glossary',
    label: 'Deck 5 — Technology Glossary',
    html: 'avalanche-insight-hub-deck-5-technology-glossary.html',
    pdf: 'avalanche-insight-hub-deck-5-technology-glossary.pdf',
    slideCount: 15,
    requiredProofSlides: ['d5-2', 'd5-6', 'd5-11'],
  },
  {
    slug: 'ml-understanding',
    label: 'Deck 6 — ML Understanding',
    html: 'avalanche-insight-hub-deck-6-ml-understanding.html',
    pdf: 'avalanche-insight-hub-deck-6-ml-understanding.pdf',
    slideCount: 15,
    requiredProofSlides: ['d6-3', 'd6-4', 'd6-6', 'd6-11', 'd6-15'],
  },
];

const viewports = [
  { width: 1920, height: 1080 },
  { width: 1280, height: 720 },
  { width: 768, height: 1024 },
  { width: 390, height: 844 },
];

const overflowTolerance = 15;

async function loadDeck(page, deck) {
  await page.goto(`${baseUrl}/${deck.html}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(1800);
}

async function collectStructure(page) {
  return page.evaluate(() => {
    const slides = Array.from(document.querySelectorAll('.slide')).map((slide) => ({
      id: slide.id,
      chipCount: slide.querySelectorAll('.proof-chip').length,
      contentOverflow: (() => {
        const content = slide.querySelector('.slide-content');
        return content ? content.scrollHeight - content.clientHeight : 0;
      })(),
      slideOverflow: slide.scrollHeight - slide.clientHeight,
      horizontalOverflow: (() => {
        const rect = slide.getBoundingClientRect();
        return rect.right > window.innerWidth + 1 || rect.left < -1;
      })(),
    }));

    return {
      slideIds: slides.map((slide) => slide.id),
      slides,
      deckIndex: window.deckController?.getIndex?.() ?? null,
      documentTitle: document.title,
    };
  });
}

async function runViewportChecks(page, deck) {
  const results = [];

  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.waitForTimeout(250);
    await page.goto(`${baseUrl}/${deck.html}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
    await page.waitForTimeout(1800);

    const startIndex = await page.evaluate(() => window.deckController?.getIndex?.() ?? null);
    await page.keyboard.press('ArrowDown');
    await page.waitForTimeout(700);
    const afterOne = await page.evaluate(() => window.deckController?.getIndex?.() ?? null);
    await page.keyboard.press('End');
    await page.waitForTimeout(900);
    const atEnd = await page.evaluate(() => window.deckController?.getIndex?.() ?? null);

    const structure = await collectStructure(page);
    const badSlides = structure.slides.filter((slide) =>
      slide.contentOverflow > overflowTolerance ||
      slide.slideOverflow > overflowTolerance ||
      slide.horizontalOverflow,
    );
    const missingProofChips = deck.requiredProofSlides.filter((id) => {
      const target = structure.slides.find((slide) => slide.id === id);
      return !target || target.chipCount < 1;
    });

    results.push({
      viewport: `${viewport.width}x${viewport.height}`,
      pass: badSlides.length === 0 && missingProofChips.length === 0 && startIndex === 0 && afterOne === 1 && atEnd === deck.slideCount - 1,
      startIndex,
      afterOne,
      atEnd,
      overflowSlides: badSlides.map((slide) => ({
        id: slide.id,
        contentOverflow: slide.contentOverflow,
        slideOverflow: slide.slideOverflow,
        horizontalOverflow: slide.horizontalOverflow,
      })),
      missingProofChips,
    });
  }

  return results;
}

function getPdfPageCount(pdfPath) {
  try {
    const bytes = fs.readFile(pdfPath, { encoding: 'binary' });
    return bytes.then((raw) => {
      const matches = Array.from(String(raw).matchAll(/\/Type\s*\/Pages[\s\S]{0,200}?\/Count\s+(\d+)/g)).map((match) => Number(match[1]));
      return matches.length ? Math.max(...matches) : null;
    });
  } catch {
    return null;
  }
}

async function exportPdf(page, deck) {
  await page.goto(`${baseUrl}/${deck.html}`, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForTimeout(1800);
  await page.evaluate(() => {
    document.querySelectorAll('.slide').forEach((slide) => slide.classList.add('revealed'));
  });
  const pdfPath = path.join(__dirname, deck.pdf);
  await page.pdf({
    path: pdfPath,
    printBackground: true,
    width: '13.333in',
    height: '7.5in',
    margin: { top: '0in', right: '0in', bottom: '0in', left: '0in' },
    preferCSSPageSize: true,
  });
  return {
    path: deck.pdf,
    pageCount: await getPdfPageCount(pdfPath),
  };
}

function inventoryRows() {
  return [
    ['2026-05-08_hosted-public_cell-full-grid-after-refresh.png', 'Live platform', 'D1-5 hero and D1-6 full-grid publication proof'],
    ['2026-05-08_hosted-public_mobile-cell-full-grid-after-refresh.png', 'Live platform', 'Mobile full-grid proof for the MVP readiness record'],
    ['2026-05-08_hosted-admin-auth-full-grid-run.png', 'Live platform', 'D1-9 and Technical Deck hosted-auth admin full run-id proof'],
    ['2026-05-07_hosted-public_workspace.png', 'Live platform', 'Full-workspace context and bulletin visual reference'],
    ['2026-05-07_hosted-public_share-workflow.png', 'Live platform', 'D1-8 workflow state'],
    ['2026-05-07_hosted-public_events-workflow.png', 'Live platform', 'Optional alternate workflow crop if needed'],
    ['2026-05-07_hosted-admin-gate.png', 'Live platform', 'Fallback gate view if hosted-auth screenshots are unavailable'],
    ['ua-structural-overview.png', 'Technical evidence', 'D6 structural graph overview: 10 ML/backend layers'],
    ['ua-domain-overview.png', 'Technical evidence', 'D6 domain graph overview: domains, flows, and steps'],
    ['ua-active-rf-layer.png', 'Technical evidence', 'D6 active Random Forest forecast pipeline layer'],
    ['ua-mts-lstm-layer.png', 'Technical evidence', 'D6 MTS-LSTM candidate model layer'],
    ['ua-sar-shadow-layer.png', 'Technical evidence', 'D6 SAR shadow segmentation lane'],
    ['ua-swiss-ravafcast-layer.png', 'Technical evidence', 'D6 Swiss RAvaFcast research lane'],
    ['ua-himalayan-evidence-layer.png', 'Technical evidence', 'D6 Himalayan partner evidence contract lane'],
    ['ua-evaluation-governance-layer.png', 'Technical evidence', 'D6 evaluation, publication, and release governance layer'],
    ['ua-modal-compute-layer.png', 'Technical evidence', 'D6 Modal and remote compute orchestration layer'],
    ['ua-tests-ci-layer.png', 'Technical evidence', 'D6 tests and CI gates layer'],
    ['ua-backend-support-layer.png', 'Technical evidence', 'D6 backend support and shared infrastructure layer'],
  ];
}

function markdownSummary(results) {
  const lines = [];
  lines.push('# Deck QA Summary');
  lines.push('');
  lines.push(`Updated: ${today}`);
  lines.push('');
  lines.push('## Outputs');
  lines.push('');
  for (const result of results) {
    lines.push(`- ${result.label}: \`${result.html}\` and \`${result.pdf.path}\``);
    lines.push(`  - slide count: \`${result.slideCount}\``);
    lines.push(`  - pdf pages: \`${result.pdf.pageCount ?? 'unknown'}\``);
  }
  lines.push('');
  lines.push('## Screenshot Inventory');
  lines.push('');
  lines.push('| File | Evidence label | Use |');
  lines.push('|---|---|---|');
  for (const [file, bucket, use] of inventoryRows()) {
    lines.push(`| \`${file}\` | \`${bucket}\` | ${use} |`);
  }
  lines.push('');
  lines.push('## Hosted Authenticated Admin Proof');
  lines.push('');
  lines.push('- Fresh hosted-authenticated admin smoke succeeded on May 8, 2026.');
  lines.push('- D1-9 and Technical Deck slide 8 use hosted authenticated admin observability, so no local fallback label is required on those slides for this build.');
  lines.push('');
  lines.push('## Viewport Results');
  lines.push('');
  lines.push('| Deck | Viewport | Pass | Notes |');
  lines.push('|---|---|---|---|');
  for (const result of results) {
    for (const viewport of result.viewports) {
      const issues = [];
      if (viewport.missingProofChips.length) issues.push(`missing proof chips: ${viewport.missingProofChips.join(', ')}`);
      if (viewport.overflowSlides.length) issues.push(`overflow: ${viewport.overflowSlides.map((slide) => slide.id).join(', ')}`);
      if (viewport.startIndex !== 0 || viewport.afterOne !== 1 || viewport.atEnd !== result.slideCount - 1) {
        issues.push(`nav indices ${viewport.startIndex}/${viewport.afterOne}/${viewport.atEnd}`);
      }
      lines.push(`| ${result.label} | \`${viewport.viewport}\` | ${viewport.pass ? 'pass' : 'fail'} | ${issues.length ? issues.join('; ') : 'no overflow; navigation ok; proof chips visible'} |`);
    }
  }
  lines.push('');
  lines.push('## Fallback Decisions Used');
  lines.push('');
  lines.push('- D1-10 through D1-12 use reconstructed tables and diagrams only, never raw admin/doc screenshots.');
  lines.push('- D3 uses reconstructed roadmap, validation, and qualification visuals rather than screenshot-heavy slides.');
  lines.push('- D2 uses the strict challenge ratings from `Top_challanges.md`, not the inflated Gemini draft ratings.');
  lines.push('- D5 uses proof-bucket labels for current, repo/admin verified, candidate/gated, and future-strategy terms.');
  lines.push('- The hosted admin gate screenshot remains in the bundle as a fallback, but the current deck build uses hosted authenticated admin proof for D1-9 and Technical Deck slide 8.');
  lines.push('');
  lines.push('## Manual QA Follow-Up');
  lines.push('');
  lines.push('- Open all six decks in Google Chrome at `http://127.0.0.1:4380/` and verify first, mid, and final slides with native keyboard navigation.');
  lines.push('- If meeting-day hosted auth fails in a later rerun, replace D1-9 authenticated imagery with the gate screenshot or a reconstructed evidence table.');
  lines.push('');
  return lines.join('\n');
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromePath,
  });

  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  const results = [];

  for (const deck of decks) {
    await loadDeck(page, deck);
    const structure = await collectStructure(page);
    const pdf = await exportPdf(page, deck);
    const viewportsResult = await runViewportChecks(page, deck);

    results.push({
      label: deck.label,
      html: deck.html,
      slideCount: structure.slideIds.length,
      pdf,
      viewports: viewportsResult,
    });
  }

  await browser.close();

  await fs.writeFile(path.join(__dirname, 'QA_SUMMARY.md'), markdownSummary(results), 'utf8');

  console.log(JSON.stringify(results, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
