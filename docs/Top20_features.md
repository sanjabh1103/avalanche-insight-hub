"Avalanche Insight Hub is the world's first open-source, self-improving AI avalanche early-warning system. It combines LLM-powered Groundsource event mining, real 24h/72h ensemble forecasts with SHAP explainability, a 3D voxel neighborhood view synced to risk timeline, realtime field reports, and expert impact overlays — all in one beautiful, shareable web app that works globally, even in regions with zero traditional monitoring."

**Top 20 Features to Highlight for Avalanche Insight Hub (Avalanche Compass)**

This list is synthesized from the full conversation history, PRD v1.1, all QA reports, and the latest implementation state. It positions the app as **the world's first truly self-improving, open-source, Groundsource-style avalanche early-warning platform** — a direct analogue to Google Flood Hub but specialized for avalanches, with unique elements no existing tool (Swiss SLF, Colorado Avalanche Center, OpenSnow PEAKS Avy, or Open Avalanche Project) offers in a single, accessible web app.

### Unique Differentiators (What Makes This Implementation Stand Out)
No other public avalanche prediction tool combines **all** of these in one open-source, global, self-improving system:
- LLM-powered Groundsource event mining + field reports + daily pg_cron automation.
- Real-time, explainable ensemble forecasts with SHAP for every cell.
- 3D voxel (Minecraft-style) neighborhood view synced to risk timeline.
- Full-state shareable links + export + realtime collaboration.
- Evaluation harness with labeling, metrics, and lineage tracking.
- Multi-hazard foundation already wired (avalanche as default, ready for volcano/flood/thunderstorm).

### Top 20 Features to Project (Ranked by Impact & Uniqueness)

| Rank | Feature | Why It Is Unique / Highlight | Customer Value |
|------|---------|------------------------------|----------------|
| 1 | **Self-Improving Groundsource Loop** | Gemini extracts events from global news + user field reports → pg_cron daily enrichment → realtime Events layer → ensemble fine-tune. No other tool has automated, continuous dataset growth from both news and citizen reports. | The app gets smarter every day without manual effort — truly "self-improving" for sparse regions. |
| 2 | **24h/72h Dynamic Risk Grid with Real Open-Meteo Ensemble** | 20×20 grid colored by EAWS 1–5 scale, powered by real weather + terrain + snowpack proxies for every region (not just monitored Alps/US). | Accurate forecasts even in data-sparse Himalayas, Andes, or remote areas where no official bulletins exist. |
| 3 | **3D Neighborhood Voxel View (Arnis-inspired OSM block map)** | Generates Minecraft-style 3D block map of your exact area (buildings tall, roads flat, risk-colored voxels). Timeline-synced colors. First avalanche tool with playable, immersive 3D risk visualization. | Users literally "see" risk on their neighborhood/slope in 3D — far more intuitive than 2D grids. |
| 4 | **SHAP Explainability per Cell** | Every grid cell shows why it is risky (real snowfall, wind, slope, recent activity, etc.). | Builds trust: users understand the "why" behind the risk level, not just a color. |
| 5 | **Realtime Field Reports → Events Layer** | Submit a report → AI classifies → marker appears on map within seconds for everyone. | Citizen science loop: every report improves the dataset instantly for all users. |
| 6 | **Full-State Shareable Links** | One link restores exact region, hour, selected cell, Expert Mode, and 3D view. | Perfect for guides, rescue teams, or sharing with friends ("this is the exact risk right now"). |
| 7 | **Export CSV/JSON** | Full forecast grid + events + weather + SHAP data downloadable. | Guides, researchers, and agencies can analyze or archive data offline. |
| 8 | **Expert Mode with Impact Overlays** | Toggle roads, villages, ski lifts, population heatmaps, historical activity, vector polygons. | Professional users see real-world consequences (roads/villages in runout zones). |
| 9 | **Evaluation Harness & Model Lineage** | Forecast outcomes, labeling, F1/ECE metrics, calibration profiles, version tracking all visible in Admin. | Transparency and continuous improvement — rare in public avalanche tools. |
| 10 | **Multi-Hazard Foundation (Ready for Expansion)** | `hazard_type` infrastructure already wired; easy to add volcano, flood, thunderstorm modules. | One app becomes a unified natural-hazards platform (future-proof). |
| 11 | **Daily Automated Enrichment (pg_cron)** | Midnight UTC job pulls news via NewsData.io + Gemini → new events added automatically. | No manual maintenance needed — dataset grows 24/7. |
| 12 | **Permanent Safety Disclaimer** | Red banner on every screen, non-dismissible. | Strong ethical stance — users always know it's experimental. |
| 13 | **Mobile-Responsive + PWA** | Full functionality on phone, installable as app. | Backcountry users can check risk on the mountain. |
| 14 | **Admin Panel with Job Triggers & Analytics** | One-click enrichment, fine-tune, snow-cover, evaluation, realtime job status, Gemini usage counter. | Maintainers can monitor and control the system easily. |
| 15 | **Historical Activity Heatmap** | Past events rendered as heatmap with recency weighting. | Shows avalanche-prone zones at a glance. |
| 16 | **Keyboard Shortcuts** | R=Run Forecast, Space=Play/Pause, arrows=scrub. | Power users get faster interaction. |
| 17 | **Dark/Light Theme Toggle with Proper Map Tiles** | Seamless switching with matching basemap. | Better usability in different lighting conditions. |
| 18 | **Real-Time Job & Model Status Badge** | Live updates for jobs, version, F1, freshness. | Users always know how current the model is. |
| 19 | **Field Report Quality Fields** | `review_status`, `training_eligible` automatically populated. | Enables active learning and quality control. |
| 20 | **Open-Source & Self-Hostable** | Full GitHub repo with Supabase + Edge Functions. | Anyone can run their own instance or contribute improvements. |

These 20 points make Avalanche Insight Hub **stand out globally**:
- No competitor combines **LLM Groundsource automation + real-time field reports + 3D voxel visualization + evaluation harness + full-state sharing** in one open-source web app.
- It is the first tool that truly scales to **sparse, data-poor regions** while remaining transparent and explainable.

 


 