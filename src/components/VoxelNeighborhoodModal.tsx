import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, RefreshCw, Loader2, Info } from 'lucide-react';
import { RISK_COLORS, RISK_LABELS, GRID_SIZE } from '@/lib/constants';
import type { GridCell } from '@/lib/gridUtils';
import { Canvas, ThreeEvent } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useTheme } from 'next-themes';

// ---- types ----
interface VoxelBlock {
  x: number;
  y: number;
  z: number;
  h: number;
  type: 'building' | 'road' | 'forest' | 'lift' | 'ground';
  lat: number;
  lng: number;
}

interface HoveredInfo {
  type: string;
  riskLabel: string;
  riskScore: number;
  lat: number;
  lng: number;
  color: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  bbox: [number, number, number, number];
  gridCells: GridCell[];
  hourlyGrids: GridCell[][] | null;
  timeOffset: number;
}

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';
const WORLD_SIZE = 80;

// ---- In-memory session cache (survives re-opens within same browser session) ----
const sessionCache = new Map<string, VoxelBlock[]>();

function bboxToQuery(bbox: [number, number, number, number]) {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const b = `${latMin},${lngMin},${latMax},${lngMax}`;
  return `[out:json][timeout:15];(
    way["building"](${b});
    way["highway"](${b});
    way["landuse"~"forest|grass|meadow"](${b});
    node["aerialway"](${b});
  );out body geom;`;
}

function geoToLocal(lat: number, lng: number, bbox: [number, number, number, number]): [number, number] {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const x = ((lng - lngMin) / (lngMax - lngMin)) * WORLD_SIZE - WORLD_SIZE / 2;
  const z = ((lat - latMin) / (latMax - latMin)) * WORLD_SIZE - WORLD_SIZE / 2;
  return [x, -z];
}

function findRiskForPosition(lat: number, lng: number, cells: GridCell[]): GridCell | undefined {
  return cells.find(c => lat >= c.lat && lat < c.latEnd && lng >= c.lng && lng < c.lngEnd);
}

function riskToColor(score: number): string {
  return RISK_COLORS[Math.max(1, Math.min(5, Math.round(score)))] || RISK_COLORS[1];
}

function typeName(type: VoxelBlock['type']): string {
  return { building: 'Building', road: 'Road', forest: 'Forest / Meadow', lift: 'Ski Lift', ground: 'Terrain' }[type];
}

async function fetchOSMData(bbox: [number, number, number, number]): Promise<VoxelBlock[]> {
  const query = bboxToQuery(bbox);
  const res = await fetch(OVERPASS_URL, {
    method: 'POST',
    body: `data=${encodeURIComponent(query)}`,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  const data = await res.json();
  const blocks: VoxelBlock[] = [];

  // Ground plane always generated
  for (let gx = -WORLD_SIZE / 2; gx < WORLD_SIZE / 2; gx += 2) {
    for (let gz = -WORLD_SIZE / 2; gz < WORLD_SIZE / 2; gz += 2) {
      const lat = bbox[0] + (((-gz) + WORLD_SIZE / 2) / WORLD_SIZE) * (bbox[2] - bbox[0]);
      const lng = bbox[1] + ((gx + WORLD_SIZE / 2) / WORLD_SIZE) * (bbox[3] - bbox[1]);
      blocks.push({ x: gx, y: 0, z: gz, h: 0.3, type: 'ground', lat, lng });
    }
  }

  for (const el of (data.elements || [])) {
    const tags = (el.tags || {}) as Record<string, string>;

    if (el.type === 'way' && tags.building && el.geometry) {
      const levels = parseInt(tags['building:levels'] || '3', 10);
      const height = Math.max(2, Math.min(8, levels));
      const geom = el.geometry as { lat: number; lon: number }[];
      const centerLat = geom.reduce((s: number, p: { lat: number }) => s + p.lat, 0) / geom.length;
      const centerLng = geom.reduce((s: number, p: { lon: number }) => s + p.lon, 0) / geom.length;
      const [x, z] = geoToLocal(centerLat, centerLng, bbox);
      blocks.push({ x: Math.round(x), y: height / 2, z: Math.round(z), h: height, type: 'building', lat: centerLat, lng: centerLng });
    } else if (el.type === 'way' && tags.highway && el.geometry) {
      const geom = el.geometry as { lat: number; lon: number }[];
      for (let i = 0; i < geom.length; i += 3) {
        const [x, z] = geoToLocal(geom[i].lat, geom[i].lon, bbox);
        blocks.push({ x: Math.round(x), y: 0.15, z: Math.round(z), h: 0.3, type: 'road', lat: geom[i].lat, lng: geom[i].lon });
      }
    } else if (el.type === 'way' && tags.landuse && el.geometry) {
      const geom = el.geometry as { lat: number; lon: number }[];
      const centerLat = geom.reduce((s: number, p: { lat: number }) => s + p.lat, 0) / geom.length;
      const centerLng = geom.reduce((s: number, p: { lon: number }) => s + p.lon, 0) / geom.length;
      const [x, z] = geoToLocal(centerLat, centerLng, bbox);
      blocks.push({ x: Math.round(x), y: 0.5, z: Math.round(z), h: 1, type: 'forest', lat: centerLat, lng: centerLng });
    } else if (el.type === 'node' && tags.aerialway) {
      const [x, z] = geoToLocal(el.lat, el.lon, bbox);
      blocks.push({ x: Math.round(x), y: 1, z: Math.round(z), h: 2, type: 'lift', lat: el.lat, lng: el.lon });
    }
  }

  return blocks;
}

function dedupeBlocks(blocks: VoxelBlock[]): VoxelBlock[] {
  const seen = new Set<string>();
  return blocks.filter(b => {
    const key = `${Math.round(b.x)},${Math.round(b.z)},${b.type}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ---- Three.js scene ----
function VoxelScene({
  blocks,
  cells,
  onHover,
  onHoverEnd,
}: {
  blocks: VoxelBlock[];
  cells: GridCell[];
  onHover: (info: HoveredInfo) => void;
  onHoverEnd: () => void;
}) {
  const coloredBlocks = useMemo(() => {
    return blocks.map(b => {
      let color: string;
      let riskScore = 1;
      if (b.type === 'road') color = '#6b7280';
      else if (b.type === 'lift') color = '#a78bfa';
      else if (b.type === 'forest') color = '#166534';
      else {
        const cell = findRiskForPosition(b.lat, b.lng, cells);
        riskScore = cell?.riskScore ?? 1;
        color = cell ? riskToColor(cell.riskScore) : '#374151';
      }
      return { ...b, color, riskScore };
    });
  }, [blocks, cells]);

  return (
    <>
      <color attach="background" args={['transparent']} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[30, 50, 20]} intensity={0.8} />
      <OrbitControls
        enablePan
        enableZoom
        enableRotate
        maxPolarAngle={Math.PI / 2.2}
        minDistance={10}
        maxDistance={120}
      />
      {coloredBlocks.map((b, i) => (
        <mesh
          key={i}
          position={[b.x, b.y, b.z]}
          onClick={(e: ThreeEvent<MouseEvent>) => {
            e.stopPropagation();
            const score = Math.max(1, Math.min(5, Math.round(b.riskScore)));
            onHover({
              type: typeName(b.type),
              riskLabel: RISK_LABELS[score] ?? 'Unknown',
              riskScore: score,
              lat: b.lat,
              lng: b.lng,
              color: b.color,
            });
          }}
          onPointerMissed={() => onHoverEnd()}
        >
          <boxGeometry args={[
            b.type === 'road' ? 1.5 : 1,
            b.h,
            b.type === 'road' ? 1.5 : 1,
          ]} />
          <meshStandardMaterial color={b.color} />
        </mesh>
      ))}
    </>
  );
}

// ---- Main modal ----
export default function VoxelNeighborhoodModal({ open, onClose, bbox, gridCells, hourlyGrids, timeOffset }: Props) {
  // B2 fix: distinct states — null=never fetched, []=fetch error, [...]=data
  const [blocks, setBlocks] = useState<VoxelBlock[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [sparseRegion, setSparseRegion] = useState(false);

  // B3 fix: tooltip state
  const [hovered, setHovered] = useState<HoveredInfo | null>(null);

  // B5 fix: theme-aware canvas background
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';
  const canvasBg = isDark ? '#0a0a0a' : '#f1f5f9';

  const currentCells = useMemo(() => {
    if (hourlyGrids && hourlyGrids[timeOffset]) return hourlyGrids[timeOffset];
    return gridCells;
  }, [hourlyGrids, timeOffset, gridCells]);

  const cacheKey = useMemo(() => `voxel_${bbox.join(',')}`, [bbox]);

  const fetchBlocks = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    setSparseRegion(false);
    setHovered(null);
    try {
      const raw = await fetchOSMData(bbox);
      const deduped = dedupeBlocks(raw);

      // B4/B13 fix: detect sparse regions (fewer than 5 non-ground elements)
      const structureCount = deduped.filter(b => b.type !== 'ground').length;
      if (structureCount < 5) {
        setSparseRegion(true);
      }

      setBlocks(deduped);

      // B12 fix: write to both in-memory session cache and localStorage
      sessionCache.set(cacheKey, deduped);
      try { localStorage.setItem(cacheKey, JSON.stringify(deduped)); } catch {}
    } catch (err) {
      setFetchError('Could not fetch OSM data — check your connection and try again.');
      setBlocks([]);
    } finally {
      setLoading(false);
    }
  }, [bbox, cacheKey]);

  useEffect(() => {
    if (!open) return;
    setHovered(null);

    // B12 fix: check in-memory session cache first (instant), then localStorage, then fetch
    const memCached = sessionCache.get(cacheKey);
    if (memCached) {
      setBlocks(memCached);
      const sc = memCached.filter(b => b.type !== 'ground').length < 5;
      setSparseRegion(sc);
      return;
    }
    try {
      const cached = localStorage.getItem(cacheKey);
      if (cached) {
        const parsed = JSON.parse(cached) as VoxelBlock[];
        sessionCache.set(cacheKey, parsed); // promote to memory cache
        setBlocks(parsed);
        const sc = parsed.filter(b => b.type !== 'ground').length < 5;
        setSparseRegion(sc);
        return;
      }
    } catch {}
    fetchBlocks();
  }, [open, cacheKey, fetchBlocks]);

  if (!open) return null;

  const hasRealData = blocks !== null && blocks.length > 0;

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      {/* B6 fix: prevent ANY outside pointer event from closing the modal.
          This means timeline scrubber, play button, toolbar, region selector
          — none of them will dismiss the 3D modal. Only X button or Escape closes it. */}
      <DialogContent
        className="max-w-[95vw] w-[95vw] h-[90vh] max-h-[90vh] p-0 bg-card border-border flex flex-col"
        aria-label="3D Neighborhood Risk Map"
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader className="p-4 pb-2 border-b border-border shrink-0">
          <DialogTitle className="flex items-center gap-2 text-foreground text-base">
            <span className="text-lg">🧊</span> 3D Neighborhood Risk Map
          </DialogTitle>
        </DialogHeader>

        {/* B1 fix: RED disclaimer banner (was amber) */}
        <div className="bg-red-500/15 px-4 py-1.5 flex items-center gap-2 shrink-0 border-b border-red-500/30">
          <AlertTriangle className="h-3 w-3 shrink-0 text-red-400" />
          <span className="text-red-400 text-[10px]"><strong>Experimental 3D visualization</strong> — for illustration only</span>
        </div>

        {/* B4/B13 fix: sparse region banner */}
        {sparseRegion && !loading && hasRealData && (
          <div className="bg-blue-500/10 px-4 py-1 flex items-center gap-2 shrink-0 border-b border-blue-500/20">
            <Info className="h-3 w-3 shrink-0 text-blue-400" />
            <span className="text-blue-400 text-[10px]">Limited OSM building data for this region — showing terrain risk grid only</span>
          </div>
        )}

        {/* B5 fix: canvas background now theme-aware via style prop */}
        <div className="flex-1 relative min-h-0" style={{ background: canvasBg }}>
          {loading ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <span className="text-sm text-muted-foreground">Generating voxel map from OpenStreetMap… (est. 4–8s)</span>
            </div>
          ) : fetchError ? (
            // B13 fix: differentiated error for network failure
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-muted-foreground text-sm px-8 text-center">
              <AlertTriangle className="h-8 w-8 text-red-400" />
              <span>{fetchError}</span>
            </div>
          ) : hasRealData ? (
            <Canvas
              camera={{ position: [40, 40, 40], fov: 50 }}
              style={{ width: '100%', height: '100%', background: canvasBg }}
            >
              <VoxelScene
                blocks={blocks!}
                cells={currentCells}
                onHover={setHovered}
                onHoverEnd={() => setHovered(null)}
              />
            </Canvas>
          ) : (
            // B2 fix: only shown when blocks=[] (fetch returned empty, not null=pre-fetch)
            <div className="absolute inset-0 flex items-center justify-center text-muted-foreground text-sm">
              No voxel data available for this region
            </div>
          )}

          {/* B3 fix: click tooltip overlay */}
          {hovered && (
            <div className="absolute top-3 left-3 z-20 glass-panel rounded-lg p-3 space-y-1.5 min-w-[160px] pointer-events-none">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: hovered.color }} />
                <span className="text-xs font-semibold text-foreground">{hovered.riskLabel} Risk</span>
              </div>
              <div className="text-[10px] text-muted-foreground space-y-0.5">
                <div>Type: {hovered.type}</div>
                <div>Lat: {hovered.lat.toFixed(4)}°</div>
                <div>Lng: {hovered.lng.toFixed(4)}°</div>
              </div>
              <div className="text-[9px] text-muted-foreground/60">Click elsewhere to dismiss</div>
            </div>
          )}

          <Button
            variant="outline"
            size="sm"
            className="absolute top-3 right-3 z-10 glass-panel border-0 gap-1.5 text-xs"
            onClick={fetchBlocks}
            disabled={loading}
          >
            <RefreshCw className="h-3 w-3" /> Refresh 3D Map
          </Button>

          <div className="absolute bottom-3 left-3 z-10 glass-panel rounded-lg p-2 space-y-1">
            {[1, 2, 3, 4, 5].map(level => (
              <div key={level} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: RISK_COLORS[level] }} />
                <span className="text-[10px] text-muted-foreground">{RISK_LABELS[level]}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="p-3 border-t border-border text-[10px] text-muted-foreground flex items-center justify-between shrink-0">
          <span>3D view inspired by <a href="https://github.com/louis-e/arnis" target="_blank" rel="noopener noreferrer" className="underline text-primary/70 hover:text-primary">Arnis</a> (github.com/louis-e/arnis)</span>
          <span>Hour {timeOffset} • {currentCells.length} cells</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
