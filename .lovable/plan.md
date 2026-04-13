

# 3D Neighborhood View (Arnis-style Voxel Map) Plan

## Overview

Add an optional "3D Neighborhood View" modal triggered from Expert Mode. Uses `@react-three/fiber@^8.18` + `@react-three/drei@^9.122.0` + `three` to render a lightweight Minecraft-style block map from OSM data, colored by the current risk grid.

## Files

### New: `src/components/VoxelNeighborhoodModal.tsx`
- Full-screen responsive modal (Dialog) with Three.js canvas
- On open: fetch OSM data via Overpass API (buildings, roads, landuse, aerialway) for current bbox
- Convert OSM features to voxel blocks:
  - Buildings → tall blocks (height 3-8 based on `building:levels` tag or default 4), colored by risk cell
  - Roads → flat gray blocks (height 1)
  - Ski lifts → blue/purple blocks (height 2)
  - Forest/landuse → green low blocks (height 1-2)
- Map each block's lat/lng to the corresponding 20x20 grid cell → apply EAWS risk color
- OrbitControls for rotation/zoom, ambient + directional light
- Hover tooltip showing risk level, problem type, 72h probability
- Loading state: "Generating voxel map from OpenStreetMap… (est. 4–8s)"
- Cache rendered voxel data in localStorage keyed by `bbox`
- "Refresh 3D Map" button to re-fetch
- Footer: disclaimer + "3D view inspired by Arnis (github.com/louis-e/arnis)" + "Experimental 3D visualization — for illustration only"
- Dark theme support (darker ambient light in dark mode)
- ARIA labels, Esc to close

### Update: `src/components/ExpertModePanel.tsx`
- Add new ToggleRow: "3D Neighborhood View" with tooltip
- Add prop `onToggle3D` and call it when toggled on (parent manages modal state)

### Update: `src/pages/Index.tsx`
- Add `show3DModal` state
- Pass `onToggle3D` callback to ExpertModePanel
- Render `VoxelNeighborhoodModal` with current grid cells, timeOffset, hourlyGrids, bbox, region

### Update: `package.json`
- Add `three`, `@react-three/fiber@^8.18`, `@react-three/drei@^9.122.0`, `@types/three`

## Technical Details

- Voxel generation: convert bbox to a local coordinate system (meters), place blocks on a flat plane
- Risk coloring: for each block, determine which grid cell (row, col) it falls in, use `RISK_COLORS[riskScore]`
- Timeline sync: when `timeOffset` changes and `hourlyGrids` is available, re-color blocks from the corresponding hour's grid
- Performance: use Three.js `InstancedMesh` for all blocks of the same type to minimize draw calls
- Bundle impact: three.js ~150KB gzip, fiber+drei ~50KB — within budget given lazy loading via `React.lazy`
- Lazy-load the modal component so Three.js is only loaded when user opens it

## No Changes To
- Edge functions, database, core forecast logic, or any existing component behavior

