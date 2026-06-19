# Scientist Learning Guide: Top 20 Features To Verify

Status date: 2026-05-22

This guide is for scientist reviewers who need to check Avalanche Insight Hub from the beginning, without assuming strong IT familiarity. It translates the current web app into a practical verification checklist and a starter glossary for avalanche-science discussions.

## Purpose And Proof Boundary

| Point | Meaning for the reviewer |
|---|---|
| What this file is | A hand-holding guide for checking the website, scientist workspace, validation workflow, and learning terms. |
| What this file is not | It is not an official avalanche service bulletin, a field-safety instruction, or a claim that the model is already scientifically closed. |
| Main reviewer job | Check whether the website evidence, terminology, review fields, exports, and claim boundaries make sense to an avalanche scientist. |
| Main proof boundary | Scientist reviews can create evidence, downgrade claims, block claims, or request more data. They must not automatically retrain, promote, or change public forecast claims. |
| Standard language to use | Use EAWS danger levels, EAWS avalanche problems, model-vs-scientist paired verification, and impact-aware review language. |
| EAWS Matrix caution | The Matrix standardizes danger-level reasoning, but stability, frequency, and avalanche size are still expert-assessed inputs; wet-snow and gliding-snow situations need extra caution in review. |

## Top 20 Features Scientists Should Verify

| # | Feature | Where to open it | What to check | Expected result | Proof boundary | Scientist sign-off question |
|---:|---|---|---|---|---|---|
| 1 | Published batch forecast workspace | `/` | Confirm the public page loads a prepared forecast instead of asking the user to run heavy compute. | The map, sidebar, and controls load from a published artifact or show a clear unavailable state. | Batch delivery proves product usability, not field accuracy. | Is the forecast workspace understandable as a review surface? |
| 2 | Region selector and forecast loading state | `/`, region control | Change or inspect the selected region and observe ready, partial, stale, or unavailable messaging. | The user can see which region is being reviewed and whether the forecast data is ready. | Region availability depends on published artifacts and source data. | Is the region state clear enough for a non-technical reviewer? |
| 3 | 72-hour time slider / daypart review | `/`, time slider | Move through forecast hours and compare the map with bulletin dayparts. | Hourly or daypart changes are visible without re-running a model in the browser. | Time navigation is only as good as the published forecast package. | Does the time flow match how forecasters discuss changing avalanche danger? |
| 4 | EAWS-style experimental bulletin | `/`, bulletin panel | Check danger level, avalanche problem, elevations, aspects, peak window, and caveats. | The bulletin uses structured danger/problem language instead of raw model scores only. | This is experimental EAWS-style framing, not an authorized avalanche-warning product. | Are the danger and problem terms scientifically appropriate and not overstated? |
| 5 | Forecast grid cell risk inspection | `/`, click a map cell | Select a cell and review risk score, probability, problem type, and terrain context. | The sidebar updates to the selected cell and shows interpretable values. | A cell is a model output for review, not a slope-specific safety decision. | Can a scientist understand what the cell is claiming and what it is not claiming? |
| 6 | Masked / unavailable terrain behavior | `/`, inspect masked cells | Look for cells withheld because terrain or snow relevance is not suitable for public interpretation. | Masked or unavailable cells are visibly different from normal low-risk cells. | Masking prevents misleading low-risk presentation; it does not prove all terrain filtering is perfect. | Are withheld cells visually and textually clear enough? |
| 7 | Risk drivers and explanation fields | `/`, selected cell sidebar | Review dominant driver, explanation mode, SHAP/heuristic fallback labels, and feature wording. | The app explains the model signal or clearly labels fallback explanation. | Explanation fields help review but do not prove causality. | Are the explanations useful, honest, and scientifically reviewable? |
| 8 | Uncertainty and reduced-confidence signaling | `/`, selected cell and bulletin | Check uncertainty span, uncertainty class, reduced-confidence text, and evidence coverage warnings. | Weak evidence or high uncertainty is flagged rather than hidden. | Uncertainty labels need scientist calibration before strong public claims. | Are uncertainty warnings strong enough for risky conditions? |
| 9 | SAR coverage and residual-shadow warning display | `/`, selected cell sidebar | Check SAR coverage state, residual-shadow flags, and SAR limitation language. | SAR appears as coverage/evidence context, not as a promoted production scorer. | SAR remains shadow-gated unless benchmark and scientist gates pass. | Does the SAR wording avoid overclaiming remote-sensing capability? |
| 10 | Weather and snowpack proxy context | `/`, sidebar and cell evidence | Check weather summary, weak-layer proxy, shear/settlement proxy, and snowpack caveat text. | Snowpack proxy appears as review context with clear limits. | Proxy evidence is not completed weak-layer validation. | Which proxy fields are useful, and which need field/snowpit data? |
| 11 | Historical events / field evidence overlay | `/`, historical events toggle | Turn on or inspect historical event markers and linked evidence. | Past events and field evidence appear as context around the forecast. | Historical records may be incomplete, duplicated, or uncertain. | Are event markers useful for review, and what source quality is missing? |
| 12 | Field report submission and offline queue concept | `/`, report action | Check whether a reviewer can submit or understand field observation capture. | Field reports can be captured and queued for later governance. | Raw field reports need verification before model or training use. | Are the requested field-report details sufficient for scientific review? |
| 13 | Shareable forecast links | `/`, Share button | Copy a link after selecting region, time, and optionally a cell. | The link should preserve enough state for another reviewer to inspect the same context. | A shared link is a review convenience, not a certified record by itself. | Is the shared-link workflow adequate for scientist meetings? |
| 14 | CSV / JSON forecast export | `/`, export buttons | Export data and inspect whether metadata, cells, uncertainty, and events are included. | CSV and JSON exports support offline analysis and audit. | Export quality depends on the loaded artifact and available fields. | Does the export include the fields scientists need for review? |
| 15 | Expert overlays and runout / asset review | `/`, expert controls | Check roads, infrastructure, runout polygons, and consequence context where available. | Expert overlays help connect hazard signals to exposed assets. | Runout and asset overlays are review context, not final impact certification. | Are the overlays relevant for road, settlement, or rescue planning discussions? |
| 16 | 3D voxel neighborhood inspection | `/`, 3D control after selecting a cell | Open the 3D view and inspect terrain, selected cell context, and masked/unavailable states. | The 3D view gives spatial intuition beyond the 2D grid. | 3D visualization improves review, but it does not replace DEM/field validation. | Does 3D help scientists explain terrain context to non-technical stakeholders? |
| 17 | Scientist-safe `/scientist` route | `/scientist` | Sign in as scientist and confirm the user sees validation tools without admin-only controls. | Scientist users can review cases without getting broad admin access. | Role separation is a security/control feature, not scientific proof. | Is the scientist route limited to the right tasks? |
| 18 | Scientist validation case queue and structured review | `/scientist` | Open a case and complete structured fields: avalanche problem, label quality, model error, terrain/SAR ambiguity, evidence needed, rationale. | Priority cases require structured review before sign-off. | Reviews create governed evidence and actions; they do not automatically promote the model. | Are the structured fields enough to capture real scientist judgment? |
| 19 | Daily paired scientist-vs-model verification | `/scientist/daily-verification` | Enter scientist danger/problem, model danger/problem, observed outcome, and notes. | The page stores paired comparison rows and exports analytics. | Paired comparison supports Techel-style review, not immediate public claim changes. | Is this daily process realistic for a pilot team? |
| 20 | Modal.com / European shadow evidence as off-path validation compute | Docs: `docs/Modal_GPU_Scientist_Coworking_Operating_Note.md` and `docs/superpowers/plans/Euro_plans/README.md` | Review how Modal.com, SAR, SnowSlide, AvalCD, and European data are described. | Heavy compute and European SAR work are framed as shadow validation and candidate evidence. | European data does not prove Himalayan accuracy; Modal runs do not authorize public promotion. | Is the off-path compute role clear and scientifically safe? |

## Scientist Reviewer Score Sheet

Use this one-page score sheet after walking through the Top 20 feature table. Rating scale: 1 = not acceptable, 2 = major change needed, 3 = usable with changes, 4 = acceptable for pilot, 5 = strong and ready for repeated use.

| Feature # | Feature | Rating 1-5 | Decision | Notes / required change |
|---:|---|---:|---|---|
| 1 | Published batch forecast workspace |  | accepted / needs wording / needs data / blocked |  |
| 2 | Region selector and forecast loading state |  | accepted / needs wording / needs data / blocked |  |
| 3 | 72-hour time slider / daypart review |  | accepted / needs wording / needs data / blocked |  |
| 4 | EAWS-style experimental bulletin |  | accepted / needs wording / needs data / blocked |  |
| 5 | Forecast grid cell risk inspection |  | accepted / needs wording / needs data / blocked |  |
| 6 | Masked / unavailable terrain behavior |  | accepted / needs wording / needs data / blocked |  |
| 7 | Risk drivers and explanation fields |  | accepted / needs wording / needs data / blocked |  |
| 8 | Uncertainty and reduced-confidence signaling |  | accepted / needs wording / needs data / blocked |  |
| 9 | SAR coverage and residual-shadow warning display |  | accepted / needs wording / needs data / blocked |  |
| 10 | Weather and snowpack proxy context |  | accepted / needs wording / needs data / blocked |  |
| 11 | Historical events / field evidence overlay |  | accepted / needs wording / needs data / blocked |  |
| 12 | Field report submission and offline queue concept |  | accepted / needs wording / needs data / blocked |  |
| 13 | Shareable forecast links |  | accepted / needs wording / needs data / blocked |  |
| 14 | CSV / JSON forecast export |  | accepted / needs wording / needs data / blocked |  |
| 15 | Expert overlays and runout / asset review |  | accepted / needs wording / needs data / blocked |  |
| 16 | 3D voxel neighborhood inspection |  | accepted / needs wording / needs data / blocked |  |
| 17 | Scientist-safe `/scientist` route |  | accepted / needs wording / needs data / blocked |  |
| 18 | Scientist validation case queue and structured review |  | accepted / needs wording / needs data / blocked |  |
| 19 | Daily paired scientist-vs-model verification |  | accepted / needs wording / needs data / blocked |  |
| 20 | Modal.com / European shadow evidence as off-path validation compute |  | accepted / needs wording / needs data / blocked |  |

## Step-By-Step Verification Process

| Step | What the scientist should do | How to do it slowly | What to observe | Record this |
|---:|---|---|---|---|
| 1 | Open the public website | Open the browser, type the website address, and wait for the main map page to load. | Does the public forecast workspace load, or does it show a clear unavailable message? | Record this: date, time, URL, selected region, and whether the page loaded. |
| 2 | Identify the selected region | Look for the region selector or region label on the public page. | Is the region name understandable and correct for the review session? | Record this: region name and any confusion about region boundaries. |
| 3 | Wait for forecast readiness | Do not click many controls immediately; first read any ready, partial, stale, or unavailable message. | Does the app explain whether data is current and usable? | Record this: readiness status and any warning text. |
| 4 | Read the bulletin first | Find the bulletin or danger summary before inspecting individual cells. | Does the bulletin mention danger level, avalanche problem, elevation/aspect, daypart, and uncertainty? | Record this: danger level, problem type, and whether the wording is acceptable. |
| 5 | Move through time | Use the time slider slowly from early hours to later hours. | Does danger or daypart framing change in a reasonable way? | Record this: any hour where the forecast looks inconsistent or unclear. |
| 6 | Click a normal grid cell | Select one cell that appears eligible for review. | Does the sidebar show risk score, probability, problem type, and evidence details? | Record this: cell row/column, score, problem type, and first scientific concern. |
| 7 | Click a masked or unavailable cell | Select a cell that appears greyed, withheld, or unavailable. | Does the page clearly explain why it is not a normal forecast cell? | Record this: mask reason and whether it prevents misreading as low danger. |
| 8 | Check explanation fields | In the selected cell, look for dominant driver, explanation mode, and feature contributions. | Is the explanation scientifically meaningful or only a technical placeholder? | Record this: useful driver fields and any misleading wording. |
| 9 | Check uncertainty fields | Look for uncertainty class, uncertainty span, reduced confidence, or evidence warning labels. | Does the app warn strongly enough when evidence is thin? | Record this: uncertainty label and whether it should be stronger or weaker. |
| 10 | Check weather and snowpack proxy context | Review weather summary and weak-layer proxy details where shown. | Are proxy values useful for review, or do they need partner snowpack data? | Record this: which fields are useful, missing, or scientifically questionable. |
| 11 | Turn on historical or field evidence | Use the historical events or evidence overlay control if available. | Do past events or field reports appear in useful relation to the selected region/cell? | Record this: visible evidence count, missing evidence, and source-quality concerns. |
| 12 | Try share link | Click Share after selecting a region, hour, and cell. | Does the copied link preserve the review context when reopened? | Record this: whether the link restored region, hour, and selected cell. |
| 13 | Export forecast data | Click CSV or JSON export after a forecast is loaded. | Does the downloaded file include useful scientific fields and metadata? | Record this: export format checked and any missing columns. |
| 14 | Inspect expert overlays | Turn on roads, assets, runout, or expert overlays if available. | Do overlays help judge possible impact or consequence? | Record this: which overlays are useful and which data layers are missing. |
| 15 | Open 3D inspection | Select a cell and open the 3D or voxel neighborhood view if available. | Does the 3D view help explain terrain shape and cell context? | Record this: whether 3D is useful, confusing, or unnecessary for the scientist workflow. |
| 16 | Open scientist workspace | Go to `/scientist` and sign in with the scientist account. | Does the scientist see validation tools and not broad admin controls? | Record this: login success, visible panels, and any access concern. |
| 17 | Review one validation case | Open a queued case and inspect evidence, linked field reports/outcomes, references, gates, claim boundary, and whether the row is synthetic, candidate-only, training-eligible, or production-eligible. | Is there enough evidence to make a structured judgment, and is the claim boundary clearly visible? | Record this: case id, claim boundary, synthetic/candidate/grounded status, evidence sufficiency, and next evidence needed. |
| 18 | Complete structured review fields | Fill avalanche problem, label quality, model error, terrain/SAR ambiguity, evidence needed, rationale, and verdict. | Does the form force enough structure for priority cases? | Record this: verdict, rationale quality, and any missing review option. |
| 19 | Export scientist sign-off | Use sign-off Markdown or JSON export. | Does the export include cases, reviews, actions, references, reviewer count, disagreement count, and boundaries? | Record this: export filename and whether it is adequate for meeting records. |
| 20 | Enter daily paired verification | Go to `/scientist/daily-verification` and enter scientist-vs-model danger/problem comparison. | Does analytics show agreement, confusion matrix, and unknown outcomes? | Record this: date, region, scientist danger/problem, model danger/problem, observed outcome. |
| 21 | Review European and Modal evidence | Open the Euro Plans README and Modal operating note. | Are SAR and European evidence clearly framed as shadow/candidate validation? | Record this: any wording that sounds too strong or unsafe. |
| 22 | Decide meeting actions | Summarize all observations into accepted, rejected, needs-info, blocked, and data-request items. | Does the review produce concrete next actions instead of general comments? | Record this: final action list, owner, priority, and deadline. |

## Top 30 Avalanche And Platform Terms

| # | Term | Brief definition | Why scientists use it | Real-life example |
|---:|---|---|---|---|
| 1 | Avalanche bulletin | A structured forecast product describing avalanche danger, problems, terrain, and timing. | It is the normal way avalanche services communicate regional hazard. | "Today the bulletin says danger is 3-Considerable on north aspects above 2,800 m." |
| 2 | Danger level | A five-level summary of avalanche danger, commonly 1-Low to 5-Very High in EAWS language. | It gives a compact regional hazard level for a time period. | "The model predicts 3, but the scientist thinks 2 is more defensible." |
| 3 | EAWS Matrix | A decision-support matrix using stability, frequency of instability, and avalanche size to determine danger level. | It makes danger-level reasoning more standardized and reviewable, while still depending on expert-assessed inputs. | "If poor stability is frequent and size 3 avalanches are likely, the danger may move toward High; wet-snow or gliding-snow cases may still need extra expert discussion." |
| 4 | Avalanche problem | The main type or cause of instability, such as wind slab or wet snow. | It explains what kind of avalanche situation exists, not only how dangerous it is. | "Danger level is 3, and the primary problem is wind slab near ridgelines." |
| 5 | New snow | Instability related to recent snowfall loading the old snow surface. | New snow can rapidly increase avalanche likelihood during and after storms. | "A 40 cm storm overnight creates a new snow problem." |
| 6 | Wind slab | A cohesive slab formed when wind transports and deposits snow. | Wind slabs often form on lee slopes and near ridges. | "Strong west wind loads east-facing slopes and creates wind slab." |
| 7 | Persistent weak layer | A buried weak layer that can remain unstable for long periods. | Persistent layers are hard to manage because they may be spatially variable and long-lived. | "Buried faceted crystals remain reactive two weeks after the storm." |
| 8 | Wet snow | Instability caused by liquid water weakening the snowpack. | Wet snow problems often increase with warming, sun, or rain on snow. | "Afternoon warming creates wet loose avalanches on solar aspects." |
| 9 | Gliding snow | Full-depth snowpack movement over smooth ground, sometimes producing glide cracks. | It can release unpredictably and is often difficult to forecast precisely. | "A glide crack opens above a road after several warm days." |
| 10 | No distinct avalanche problem | A condition where no specific avalanche problem dominates the bulletin. | It prevents forcing a false problem label when evidence is weak or hazard is low. | "Danger is Low with no distinct avalanche problem." |
| 11 | Weak layer | A fragile snow layer that can fail and allow a slab to release. | Weak layers are central to slab avalanche formation. | "Surface hoar buried under storm snow becomes the weak layer." |
| 12 | Snowpack stability | The ability of the snowpack to resist failure under natural or human loading. | Stability is one of the core inputs for danger assessment. | "Compression tests and recent avalanches suggest poor stability." |
| 13 | Snowpack frequency distribution | How widespread a stability class is across terrain, such as few, some, or many slopes. | It helps distinguish isolated danger from widespread danger. | "Poor stability exists on many north-facing slopes, not just one test pit." |
| 14 | Avalanche size | A class describing destructive potential and runout size, often size 1 to size 5. | Size changes the consequence of a release. | "A size 2 can bury a person; a size 3 can damage a vehicle." |
| 15 | Aspect | The compass direction a slope faces. | Aspect controls sun exposure, wind loading, and snow preservation. | "North aspects keep cold snow and may preserve weak layers." |
| 16 | Elevation band | A height range such as below treeline, treeline, alpine, or a meter band. | Avalanche problems often vary strongly by elevation. | "Wind slab exists above 3,000 m, but lower slopes are wet." |
| 17 | Starting zone | The slope area where an avalanche begins. | Forecasts and runout models need to identify where release is plausible. | "A 38-degree lee slope below a ridge is a likely starting zone." |
| 18 | Track | The path an avalanche follows after release. | It connects the starting zone to the runout zone. | "The track channels snow through a gully toward the valley." |
| 19 | Runout zone | The area where avalanche debris slows and stops. | It is critical for roads, settlements, and rescue planning. | "The runout zone reaches the road during large events." |
| 20 | Avalanche-prone terrain | Terrain where slope, snow, and path geometry make avalanches possible or relevant. | It helps avoid treating non-avalanche terrain as normal forecast terrain. | "A flat valley floor may be masked unless exposed to overhead hazard." |
| 21 | Masked terrain | A website state where the app withholds normal risk coloring because the cell is outside valid interpretation. | It prevents users from confusing out-of-scope terrain with low danger. | "A warm, low-elevation cell is shown as withheld rather than green." |
| 22 | Field report | A human observation from the field, such as avalanche activity, cracking, or snow condition. | It provides reality evidence that models and remote data may miss. | "A guide reports recent natural avalanches on east aspects." |
| 23 | Forecast outcome | A later observation used to check whether a forecast matched reality. | It supports model verification and calibration. | "The forecast predicted High danger and several natural avalanches occurred." |
| 24 | False positive | A case where the model warns or predicts an event but the event is not observed. | It measures over-warning and can affect trust. | "The model flagged high risk but no avalanches were observed in the target area." |
| 25 | False negative | A case where the model misses a hazard or event that occurs. | It is often the most safety-critical failure type. | "The model predicted Moderate, but a large natural avalanche occurred." |
| 26 | Calibration | How well predicted probabilities match real-world frequencies. | A calibrated model's confidence is more trustworthy. | "Cells predicted at 70% should be correct about 70% of the time over many cases." |
| 27 | Brier Score | A probability-forecast error metric where lower is better. | It checks whether probability forecasts are numerically useful. | "A lower Brier Score means the model probabilities match outcomes better." |
| 28 | Peirce Skill Score | A rare-event skill metric comparing hit rate and false-alarm rate. | It is more useful than simple accuracy when avalanche events are uncommon. | "A model can be 99% accurate by saying no avalanche everywhere; PSS exposes that weakness." |
| 29 | SHAP / TreeSHAP | Explanation methods that estimate which features contributed to a model output. | They help scientists review whether the model used sensible signals. | "The model score increased because wind speed and slope angle were strong contributors." |
| 30 | SAR | Synthetic Aperture Radar, a satellite radar method that can observe surface structure through cloud and darkness. | It may help detect avalanche debris or snow-surface change, but needs strict validation. | "Sentinel-1 SAR may provide shadow evidence for avalanche debris mapping." |

## Director Letter Areas To Include Next

| Area | What to include in the letter | Required evidence or attachment |
|---|---|---|
| Opening purpose | Request a structured scientist verification pilot for Avalanche Insight Hub. | Attach this Top20 guide. |
| Why the platform is ready for verification | Explain public forecast workspace, scientist route, validation queue, daily verification, and export workflow. | `docs/Scientist_Onboarding.md`, `/scientist` workflow summary. |
| What has been implemented for co-working | Role-separated scientist access, structured review fields, two-reviewer governance, action ledger, and sign-off export. | `docs/Scientist_Coworking_Completion_Tracker.md`. |
| What scientists are requested to verify | Feature usability, EAWS terminology, danger/problem review, masked terrain, evidence sufficiency, false positives, false negatives, and claim boundaries. | Top 20 feature table in this file. |
| Requested pilot region and data package | Ask for one pilot region, one winter season, 20-30 historical cases, bulletin archive, station/weather rows, field reports, and snowpack/HIM-STRAT data if available. | `docs/SASE_DGRE_Outreach_Kit.md`, `docs/SNOWPACK_HIMSTRAT_Partner_Data_Adapter.md`. |
| Governance promise | State that reviews can open actions, request data, block claims, or downgrade claims; they will not automatically retrain or promote the model. | `docs/Scientist_Coworking_SLA.md`. |
| Meeting workflow and outputs | Propose demo of one synthetic case, review of 3-5 candidate real cases, questionnaire answers, and exported sign-off packet. | `docs/MVP/source/Scientist_pre_meeting_questionnaire.md`. |
| Partnership ask | Request named technical contacts, data-sharing path, review cadence, and permission boundaries for benchmark-only vs training-eligible data. | `docs/SASE_DGRE_Partnership_Brief.md`. |
| Reply-by date and next agenda | Ask for reply within 14 days and propose a 60-90 minute technical review meeting. | Include editable date placeholder in the letter. |
| Attachments list | Include Top20 guide, onboarding, outreach kit, questionnaire, SLA, SASE/DGRE brief, and data adapter. | Attach or link the listed documents. |

## Source Anchors

| Source | Why it matters |
|---|---|
| [EAWS Avalanche Problems](https://www.avalanches.org/standards/avalanche-problems/) | Official EAWS problem taxonomy: new snow, wind slab, persistent weak layers, wet snow, gliding snow, plus optional categories. |
| [EAWS Matrix](https://www.avalanches.org/standards/eaws-matrix/) | Standardized danger-level reasoning using snowpack stability, frequency distribution, and avalanche size. |
| [EAWS Matrix operational testing and use, NHESS 2026](https://nhess.copernicus.org/articles/26/1161/2026/nhess-26-1161-2026.html) | Latest operational-testing evidence; useful caution that Matrix consistency improves review, but input factors remain expert-assessed and wet/gliding cases need careful handling. |
| [EAWS Avalanche Danger Scale](https://www.avalanches.org/standards/avalanche-danger-scale/) | Five-level danger scale used in the guide's danger-language review. |
| [EAWS Glossary](https://www.avalanches.org/glossary/) | Avalanche bulletin, avalanche size, avalanche terrain, weak layer, and stability definitions. |
| [Avalanche Canada Glossary](https://avalanche.ca/glossary) | Practical public-forecast explanations for danger, problems, terrain, and avalanche size. |
| [WMO Impact-Based Forecast and Warning Services](https://wmo.int/impact-based-forecast-and-warning-services) | Keeps review focused on what hazard information helps people and institutions do. |
| [Techel et al. 2025](https://nhess.copernicus.org/articles/25/3333/2025/) | Supports model-vs-human forecast comparison framing. |
| [Pérez-Guillén et al. 2025](https://nhess.copernicus.org/articles/25/1331/2025.html) | Supports explainable model output as transparent second-opinion evidence. |
| [Modal.com Docs](https://modal.com/docs) and [Modal GPU Reference](https://modal.com/docs/reference/modal.gpu) | Supports Modal.com as serverless off-path compute for heavy candidate training and validation jobs. |
| `docs/MVP/source/Top20_features.md` | Existing broad MVP feature map; this new file does not replace it. |
| `docs/Scientist_Onboarding.md` | Current scientist route and review workflow onboarding. |
| `docs/Modal_GPU_Scientist_Coworking_Operating_Note.md` | Current Modal.com role and claim boundaries. |
| `docs/superpowers/plans/Euro_plans/README.md` | Current European shadow evidence pack boundary. |
