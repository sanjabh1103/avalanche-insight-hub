he Complete Unified PRD (v2.0)
Avalanche Insight Hub – Product Requirements Document (v2.0) Vision: The world’s first open-source, Groundsource-style AI avalanche early-warning system. By synthesizing real-time citizen science, Sentinel-1 SAR, Gemini-extracted news, and Physics-Informed Machine Learning (MTS-LSTM/Random Forest), it delivers localized, explainable 24-hour forecasts in the world's most data-sparse terrains.
1. Core Objectives
Provide 24-hour ahead, region-aware avalanche risk forecasts using real weather, terrain, and cumulative Class-II snowpack proxies.
Create a self-improving closed-loop system resolving the Himalayan data deficit via Gemini news extraction and Google Earth Engine (GEE) SAR pipelines.
Deliver Flood Hub-level UX (interactive map grid, 3D Voxels, timeline playback, SHAP plain-text explanations, shareable public links).
Address severe algorithmic biases using KMeansSMOTE oversampling and Cost-Sensitive Learning (4:1 ratio)
.
Run heavy spatial ML safely via asynchronous offline CI/CD batch jobs (GitHub Actions), eliminating costly real-time GPU inference.
2. The 21 Master User Stories (For Implementation Tracking)
UI / UX Foundation Stories (1-15)
Region Selection: Backcountry user selects a preset/bbox; map flies to center.
24h Risk Grid: 20x20 grid colored by EAWS 1-5 scale remains visible on zoom.
Timeline Scrubber: 24h playback scrubber updates colors/SHAP live from forecast_grids JSONB.
SHAP Explanations: Bar chart shows top features driving risk per cell.
Field Report Submission: User submits report; Gemini classifies; PostGIS dedups.
Events Layer: Toggles historical/recent avalanches with confidence-colored markers.
Admin Job Triggers: One-click UI buttons to trigger backend workflows with active job toasts.
Model Status Badge: Shows version, last inference time, data freshness, and PSS score.
Export Data: Export current forecast + events as CSV/JSON.
Shareable Links: URL params capture region, hour, selected cell, and 3D view state for exact recreation.
Global Open-Meteo: App utilizes real Open-Meteo feeds globally for unmonitored regions.
Mobile-Responsive: Touch-friendly targets, hamburger menu, scrubbers work on mobile.
Safety Disclaimer: Permanent red banner referencing EAWS/official centers.
Daily Groundsource: Midnight pg_cron runs Gemini + NewsData.io.
Admin Analytics: Real-time job status, compute logs, and API usage tracking.
Advanced Scientific Architecture Stories (16-21) 16. True Epistemic Uncertainty: RF variance extraction before Isotonic Calibration; Grey Voxels for low confidence (>30% variance). 17. Offline-First PWA: Google Workbox Service Worker caches reports via IndexedDB when offline; syncs when online. 18. Alpha-Beta Runout Overlays: WhiteboxTools calculates flow paths on dynamically rasterio-cropped 5km DEMs to prevent OOM crashes; Turf.js flags road intersections. 19. Feature-Optimized SHAP: Backend SVM-RFE trims to 15 features
; frontend limits to Top 5 absolute contributors translated to plain text. 20. Class-II Proxy Visibility: snowpack_proxy.py calculates HIM-STRAT proxies using seasonal cumulative inputs (from Nov 1); displayed in Expert Mode. 21. Climate Concept Drift & Data Integrity: GitHub Actions retrains weekly using TimeSeriesSplit; rejects deposit-zone Gemini news (training_eligible=false) and masked SAR shadows; requires PSS > 0.45.
