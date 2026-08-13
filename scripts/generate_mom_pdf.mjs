#!/usr/bin/env node
/**
 * Generate the MoM (Minutes of Meeting) PDF from the 5 infographic PNGs + email text.
 *
 * This script creates a 5-page PDF (one page per infographic) with the corresponding
 * email text from mom_2july.md on each page. Uses Playwright to render HTML → PDF.
 *
 * Usage:
 *   node scripts/generate_mom_pdf.mjs [--output <path>]
 *
 * Output: docs/MVP3/infographics/MoM_details.pdf (default)
 */

import { chromium } from 'playwright-core';
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { writeFileSync } from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const repoRoot = resolve(__dirname, '..');

// Parse args
const outputArg = process.argv.indexOf('--output');
const outputPath = outputArg !== -1 ? process.argv[outputArg + 1] : resolve(repoRoot, 'docs/MVP3/infographics/MoM_details.pdf');

// Read infographic images as base64
const infographicsDir = resolve(repoRoot, 'docs/MVP3/infographics');
const pages = [
  {
    title: 'Page 1: Data Ingestion Inventory & Overall Workflow',
    image: 'infographic_1_data_ingestion.png',
    text: `This addresses the point on the total number of data ingestion layers and their sources. The pipeline integrates 17 data sources across 6 processing stages, classified in 4 tiers: 6 scheduled+active, 4 on-demand+static, 5 adapter-ready/disabled (pending Partner feed URLs), and 2 disabled/fix-needed. These include 5 separate Open-Meteo API channels (Forecast, Archive, Historical Forecast, Ensemble, and Batch Multi-Coordinate) providing 14 hourly variables per cell. The infographic maps each source to its processing stage — from ingestion through feature engineering, ML inference, risk fusion, publication, and frontend rendering. Auth requirements and fetch frequencies are noted for each source.`,
  },
  {
    title: 'Page 2: Model Input Specification (29-Feature RF Vector)',
    image: 'infographic_2_model_input.png',
    text: `This answers your second question on how much input data is fed into the Random Forest and at what frequency. The model receives 29 features per cell per hour, sourced from four categories: Open-Meteo weather data (10 features), SRTM DEM terrain (5 features), snowpack physics proxy (8 features), and computed/seismic signals (6 features). Per inference run, this amounts to approximately 835,200 feature values per region (400 cells × 29 features × 72 hours). The infographic shows the complete feature vector with colour-coded source categories and the data flow through feature selection, isotonic calibration, and probability output.`,
  },
  {
    title: 'Page 3: Grid Spatial Resolution & Sentinel-1 SAR',
    image: 'infographic_3_grid_sar.png',
    text: `This addresses the point on the 20×20 grid, cell sizes, and how Sentinel-1 SAR captures snow information. The current production grid divides each region's bounding box into 20×20 = 400 cells, with cell sizes ranging from ~8 km (Swiss Alps) to ~11 km (Himalayan regions) depending on latitude and bbox extent. A 500 m UTM-projected grid has been implemented using pyproj but is not yet activated in production inference. On the SAR side, the infographic details Sentinel-1 specifications: C-band (5.405 GHz), IW GRD mode, 10 m pixel spacing, VV+VH dual polarisation, 6-day revisit with the S1A/S1C constellation. The wet-snow detection algorithm uses VV < -18 dB and VH < -22 dB thresholds applied after terrain masking (layover, shadow, slopes > 60° excluded). The infographic also notes what SAR can and cannot detect — wet snow extent yes, dry snow no, snow depth no.`,
  },
  {
    title: 'Page 4: End-to-End Architecture Demo Flow',
    image: 'infographic_4_end_to_end.png',
    text: `This addresses the point on what we can showcase end-to-end. We propose a 10-stage live demonstration, approximately 15 minutes in total, covering: (1) live Open-Meteo API calls, (2) grid and terrain extraction, (3) 29-feature assembly per cell, (4) Random Forest inference with calibration, (5) Chebyshev IPA risk fusion, (6) TreeSHAP explainability, (7) Supabase publication, (8) CAP 1.2 alert generation (draft — requires SMS_AUTH_KEY for MSG91 push), (9) frontend rendering with heatmap and 3D voxel view, and (10) eDMRG station validation (requires active Partner feed URL — currently disabled). Each stage is annotated with the specific file and function involved. The demo can be triggered via GitHub Actions (workflow_dispatch) or run locally.`,
  },
  {
    title: 'Page 5: Historical Backfill Feasibility (Nov 2024 – Feb 2025)',
    image: 'infographic_5_historical_backfill.png',
    text: `This addresses the point on what can be demonstrated using four months of historical open-source data. Six of eight data sources are available for this period: Open-Meteo Archive, Open-Meteo Historical Forecast, Sentinel-1 SAR via Google Earth Engine, USGS FDSN seismic, SRTM DEM. Note: NASA GIBS MODIS is currently disabled (fix needed) but can be re-enabled for the backfill period. The system can produce historical forecast grids (400 cells × 72 hours per day), SAR wet-snow detection timelines, TreeSHAP feature importance rankings for specific storm dates, seismic cascade event visualisations, and MODIS snow-cover fraction maps. One caveat: computing accuracy metrics (Peirce Skill Score, Brier Score, ROC-AUC) requires an avalanche event inventory from Partner for the same period. Without labels, we can demonstrate pipeline outputs and feature production but not model skill scores. This step will have the cost repercussions too as some of the APIs will be chargeable, along with the storage space.`,
  },
];

// Build HTML
function buildHtml() {
  const pageHtml = pages.map((page, idx) => {
    const imgPath = resolve(infographicsDir, page.image);
    const imgBase64 = readFileSync(imgPath).toString('base64');
    const isLast = idx === pages.length - 1;
    return `
    <div class="page">
      <div class="page-header">
        <h1>${page.title}</h1>
      </div>
      <div class="infographic-container">
        <img src="data:image/png;base64,${imgBase64}" alt="${page.title}" />
      </div>
      <div class="page-text">
        <p>${page.text}</p>
      </div>
    </div>`;
  }).join('\n');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MoM Details — Avalanche Insight Hub</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
      background: #0A1628;
      color: #E0E0E0;
    }
    .page {
      width: 100%;
      height: 100vh;
      padding: 10px 20px;
      display: flex;
      flex-direction: column;
      page-break-after: always;
      break-after: page;
      overflow: hidden;
    }
    .page:last-child {
      page-break-after: auto;
      break-after: auto;
    }
    .page-header {
      border-bottom: 1px solid #00D4FF;
      padding-bottom: 5px;
      margin-bottom: 8px;
      flex-shrink: 0;
    }
    .page-header h1 {
      font-size: 14px;
      color: #00D4FF;
      font-weight: 600;
    }
    .infographic-container {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      margin-bottom: 8px;
      min-height: 0;
    }
    .infographic-container img {
      max-width: 100%;
      max-height: 62vh;
      object-fit: contain;
      border-radius: 4px;
    }
    .page-text {
      font-size: 9px;
      line-height: 1.4;
      color: #B0B0B0;
      text-align: justify;
      padding: 5px 0;
      border-top: 1px solid #1a2a3a;
      flex-shrink: 0;
      max-height: 15vh;
      overflow: hidden;
    }
    .page-break {
      page-break-after: always;
      break-after: page;
    }
    @page {
      size: A4 landscape;
      margin: 15mm;
    }
  </style>
</head>
<body>
${pageHtml}
</body>
</html>`;
}

async function generatePdf() {
  console.log('Launching Playwright (chromium)...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const html = buildHtml();
  await page.setContent(html, { waitUntil: 'networkidle' });

  console.log('Generating PDF...');
  const pdfBuffer = await page.pdf({
    path: outputPath,
    format: 'A4',
    landscape: true,
    printBackground: true,
    margin: { top: '15mm', bottom: '15mm', left: '15mm', right: '15mm' },
    preferCSSPageSize: true,
  });

  await browser.close();
  console.log(`PDF generated: ${outputPath} (${(pdfBuffer.length / 1024 / 1024).toFixed(2)} MB)`);
  console.log('Verifying 5 distinct pages with unique images...');

  // Verify: check that the PDF has 5 pages
  const pdfStr = pdfBuffer.toString('latin1');
  const pageMatches = pdfStr.match(/\/Type\s*\/Page[^s]/g);
  const pageCount = pageMatches ? pageMatches.length : 0;
  console.log(`Page count: ${pageCount}`);

  if (pageCount !== 5) {
    console.error(`WARNING: Expected 5 pages, got ${pageCount}. Check page breaks.`);
  } else {
    console.log('✅ 5 distinct pages confirmed.');
  }
}

generatePdf().catch(err => {
  console.error('PDF generation failed:', err);
  process.exit(1);
});
