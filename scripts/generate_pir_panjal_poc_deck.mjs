#!/usr/bin/env node

/**
 * Generate the Pir Panjal customer-review deck from the editable Markdown
 * script. The Markdown remains the source of truth; this renderer intentionally
 * keeps the visual system simple so a source edit can be regenerated without
 * hand-editing a binary deck.
 */
import fs from 'node:fs';
import path from 'node:path';
import pptxgen from 'pptxgenjs';

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
const sourcePath = path.join(root, 'docs/MVP4/01_customer_review/PIR_PANJAL_POC_READINESS_15_SLIDE_SCRIPT.md');
const outputPath = path.join(root, 'docs/MVP4/05_generated_assets/PIR_PANJAL_POC_READINESS_15_SLIDE_DECK.pptx');

const source = fs.readFileSync(sourcePath, 'utf8');
const sections = [...`${source}\n## Appendix`.matchAll(/^## Slide (\d+) — (.+?)\n([\s\S]*?)(?=^## Slide \d+ —|^## Appendix)/gm)]
  .map((match) => ({ number: Number(match[1]), title: match[2].trim(), body: match[3].trim() }))
  .sort((a, b) => a.number - b.number);

if (sections.length !== 15 || sections.some((section, index) => section.number !== index + 1)) {
  throw new Error(`Expected exactly 15 sequential slide sections, found ${sections.length}`);
}

function markdownToPlainText(markdown) {
  return markdown
    .replace(/```[\s\S]*?```/g, (block) => block.replace(/```[^\n]*\n?/g, '').trim())
    .replace(/^\|\s*-+.*\|$/gm, '')
    .replace(/^\|\s*/gm, '')
    .replace(/\s*\|\s*/g, ' — ')
    .replace(/^\s*[-*]\s+/gm, '• ')
    .replace(/^\s*\d+\.\s+/gm, '• ')
    .replace(/^#+\s+/gm, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/^>\s?/gm, '“')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function addFooter(slide, number) {
  slide.addText('PIR PANJAL SNOWPACK POC · INTERNAL / CONTROLLED USE', {
    x: 0.45, y: 7.08, w: 8.5, h: 0.18,
    fontFace: 'Aptos', fontSize: 7.5, color: '8FA3B8',
    margin: 0,
  });
  slide.addText(`${String(number).padStart(2, '0')} / 15`, {
    x: 11.75, y: 7.02, w: 1.1, h: 0.25,
    fontFace: 'Aptos Mono', fontSize: 8, color: '8FA3B8',
    align: 'right', margin: 0,
  });
}

const pptx = new pptxgen();
pptx.layout = 'LAYOUT_WIDE';
pptx.author = 'Avalanche Insight Hub';
pptx.company = 'Avalanche Insight Hub';
pptx.subject = 'Pir Panjal local SNOWPACK candidate review';
pptx.title = 'Pir Panjal POC Readiness';
pptx.lang = 'en-US';
pptx.theme = {
  headFontFace: 'Aptos Display',
  bodyFontFace: 'Aptos',
  lang: 'en-US',
};

const colors = {
  background: '08111D',
  panel: '102235',
  panelAlt: '0D1B2A',
  text: 'F1F5F9',
  muted: 'A7B7C8',
  sky: '67D5FF',
  amber: 'F6C453',
  green: '70E1B5',
  violet: 'B59BFF',
};

for (const section of sections) {
  const slide = pptx.addSlide();
  slide.background = { color: colors.background };

  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: 13.333, h: 0.12,
    fill: { color: colors.sky }, line: { color: colors.sky, transparency: 100 },
  });
  slide.addText('CURRENT VERIFIED CANDIDATE · PIPELINE PROOF ONLY', {
    x: 0.55, y: 0.38, w: 5.2, h: 0.22,
    fontFace: 'Aptos Mono', fontSize: 9, bold: true, color: colors.amber,
    margin: 0,
  });
  slide.addText(section.title, {
    x: 0.55, y: 0.78, w: 12.1, h: 0.55,
    fontFace: 'Aptos Display', fontSize: 25, bold: true, color: colors.text,
    margin: 0, breakLine: false,
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 0.55, y: 1.5, w: 12.2, h: 0,
    line: { color: '2D4B62', width: 1 },
  });

  const body = markdownToPlainText(section.body);
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.55, y: 1.78, w: 12.2, h: 4.95,
    rectRadius: 0.08,
    fill: { color: colors.panelAlt, transparency: 4 },
    line: { color: '2A4B63', width: 0.8 },
  });
  slide.addText(body, {
    x: 0.88, y: 2.04, w: 11.55, h: 4.42,
    fontFace: 'Aptos', fontSize: 14, color: colors.text,
    breakLine: false, fit: 'shrink', valign: 'top',
    margin: 0.03, paraSpaceAfterPt: 7,
    bullet: { type: 'ul' },
  });
  slide.addText('Derived candidate geometry · hourly GFS forcing · no 3 km skill claim · scientific validation separate', {
    x: 0.88, y: 6.42, w: 11.55, h: 0.2,
    fontFace: 'Aptos Mono', fontSize: 8.5, color: colors.green,
    margin: 0,
  });
  addFooter(slide, section.number);
}

await pptx.writeFile({ fileName: outputPath });
console.log(`Generated ${sections.length} slides from ${path.relative(root, sourcePath)}`);
console.log(`Output: ${path.relative(root, outputPath)}`);
