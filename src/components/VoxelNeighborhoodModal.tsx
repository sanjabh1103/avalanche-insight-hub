import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, RefreshCw, Loader2, Info } from 'lucide-react';
import { RISK_COLORS, RISK_LABELS, GRID_SIZE } from '@/lib/constants';
import {
  getCellMaskLabel,
  getCellMaskReasonDescriptions,
  getCellMaskSummary,
  hasRenderableCellGeometry,
  isCellMasked,
  isCellUnavailable,
  isHighUncertaintyCell,
  type GridCell,
} from '@/lib/gridUtils';
import { Canvas, ThreeEvent, useFrame } from '@react-three/fiber';
import { OrbitControls, Instances, Instance } from '@react-three/drei';
import { useTheme } from 'next-themes';
import * as THREE from 'three';
import { fetchOverpassJson } from '@/lib/overpassClient';

// ---- types ----
interface BaseBlock {
  type: 'building' | 'road' | 'forest' | 'lift' | 'ground';
  lat: number;
  lng: number;
  levelInfo?: number;
}

interface OSMGeometryPoint {
  lat: number;
  lon: number;
}

interface OSMElement {
  type?: 'way' | 'node';
  tags?: Record<string, string>;
  center?: OSMGeometryPoint;
  geometry?: OSMGeometryPoint[];
  lat?: number;
  lon?: number;
}

interface VoxelCoordinate {
  x: number;
  y: number;
  z: number;
  data: BaseBlock;
}

interface FetchedVoxelData {
  voxels: VoxelCoordinate[];
  degradedMessage: string | null;
  cacheable: boolean;
}

interface HoveredInfo {
  type: string;
  riskLabel: string;
  riskScore: number;
  lat: number;
  lng: number;
  color: string;
  unavailable?: boolean;
  masked?: boolean;
  availabilityReason?: string | null;
  maskLabel?: string;
  maskSummary?: string;
  maskReasons?: string[];
  problemType?: string;
  probability?: number;
  uncertaintyClass?: 'low' | 'medium' | 'high';
}

interface Props {
  open: boolean;
  onClose: () => void;
  bbox: [number, number, number, number];
  gridCells: GridCell[];
  hourlyGrids: Array<GridCell[] | null> | null;
  timeOffset: number;
}

const WORLD_SIZE = 60; // 60x60 strict grid
const OVERPASS_FETCH_TIMEOUT_MS = 10000;

// ---- In-memory session cache ----
const sessionCache = new Map<string, VoxelCoordinate[]>();

function bboxToQuery(bbox: [number, number, number, number]) {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const b = `${latMin},${lngMin},${latMax},${lngMax}`;
  return `[out:json][timeout:15];(
    way["building"](${b});
    way["highway"](${b});
    way["landuse"~"forest|grass|meadow"](${b});
    node["aerialway"](${b});
  );out center geom;`;
}

function geoToLocal(lat: number, lng: number, bbox: [number, number, number, number]): [number, number] {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const x = Math.floor(((lng - lngMin) / (lngMax - lngMin)) * WORLD_SIZE) - WORLD_SIZE / 2;
  const z = Math.floor(((lat - latMin) / (latMax - latMin)) * WORLD_SIZE) - WORLD_SIZE / 2;
  return [x, -z];
}

function localToGeo(x: number, z: number, bbox: [number, number, number, number]): [number, number] {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const lng = ((x + WORLD_SIZE / 2) / WORLD_SIZE) * (lngMax - lngMin) + lngMin;
  const lat = ((-z + WORLD_SIZE / 2) / WORLD_SIZE) * (latMax - latMin) + latMin;
  return [lat, lng];
}

function buildTerrainFallback(bbox: [number, number, number, number]): VoxelCoordinate[] {
  const voxels: VoxelCoordinate[] = [];

  for (let x = -WORLD_SIZE / 2; x < WORLD_SIZE / 2; x++) {
    for (let z = -WORLD_SIZE / 2; z < WORLD_SIZE / 2; z++) {
      const [lat, lng] = localToGeo(x, z, bbox);
      voxels.push({ x, y: 0, z, data: { type: 'ground', lat, lng } });
    }
  }

  return voxels;
}

function buildVoxelGridFromOSM(data: { elements?: OSMElement[] }, bbox: [number, number, number, number]): VoxelCoordinate[] {
  // 2D grid to track what's at x,z
  const gridMap = new Map<string, BaseBlock>();

  // Ground plane
  for (let x = -WORLD_SIZE / 2; x < WORLD_SIZE / 2; x++) {
    for (let z = -WORLD_SIZE / 2; z < WORLD_SIZE / 2; z++) {
      const [lat, lng] = localToGeo(x, z, bbox);
      gridMap.set(`${x},${z}`, { type: 'ground', lat, lng });
    }
  }

  for (const el of (data.elements || [])) {
    const tags = (el.tags || {}) as Record<string, string>;

    if (el.type === 'way' && tags.building && (el.center || el.geometry)) {
      const levels = parseInt(tags['building:levels'] || '3', 10);
      const height = Math.max(2, Math.min(8, levels));
      const geom = el.geometry || [];
      const pts = el.center ? [el.center] : geom;
      pts.forEach((p: OSMGeometryPoint) => {
        const [x, z] = geoToLocal(p.lat, p.lon, bbox);
        gridMap.set(`${x},${z}`, { type: 'building', lat: p.lat, lng: p.lon, levelInfo: height });
      });
    } else if (el.type === 'way' && tags.highway && el.geometry) {
      el.geometry.forEach((p: OSMGeometryPoint) => {
        const [x, z] = geoToLocal(p.lat, p.lon, bbox);
        // Only overwrite ground, not buildings
        if (gridMap.get(`${x},${z}`)?.type === 'ground') {
          gridMap.set(`${x},${z}`, { type: 'road', lat: p.lat, lng: p.lon });
        }
      });
    } else if (el.type === 'way' && tags.landuse && (el.center || el.geometry)) {
      const pts = el.center ? [el.center] : (el.geometry || []);
      pts.forEach((p: OSMGeometryPoint) => {
        const [x, z] = geoToLocal(p.lat, p.lon, bbox);
        if (gridMap.get(`${x},${z}`)?.type === 'ground') {
          gridMap.set(`${x},${z}`, { type: 'forest', lat: p.lat, lng: p.lon });
        }
      });
    } else if (el.type === 'node' && tags.aerialway) {
      const [x, z] = geoToLocal(el.lat, el.lon, bbox);
      gridMap.set(`${x},${z}`, { type: 'lift', lat: el.lat, lng: el.lon });
    }
  }

  // Convert map to 3D voxel coordinates (extrude)
  const voxels: VoxelCoordinate[] = [];
  gridMap.forEach((block, key) => {
    const [x, z] = key.split(',').map(Number);
    voxels.push({ x, y: 0, z, data: block });

    if (block.type === 'building') {
      const h = block.levelInfo || 3;
      for (let y = 1; y < h; y++) {
        voxels.push({ x, y, z, data: block });
      }
    } else if (block.type === 'lift') {
      voxels.push({ x, y: 1, z, data: block });
      voxels.push({ x, y: 2, z, data: block });
    }
  });

  return voxels;
}

function findRiskForPosition(lat: number, lng: number, cells: GridCell[]): GridCell | undefined {
  return cells.find((cell) => (
    hasRenderableCellGeometry(cell)
    && lat >= cell.lat
    && lat < cell.latEnd
    && lng >= cell.lng
    && lng < cell.lngEnd
  ));
}

function typeName(type: BaseBlock['type']): string {
  return { building: 'Building', road: 'Road', forest: 'Forest / Meadow', lift: 'Ski Lift', ground: 'Terrain' }[type];
}

function getBaseColor(type: BaseBlock['type']): THREE.Color {
  if (type === 'road') return new THREE.Color('#9ca3af');
  if (type === 'lift') return new THREE.Color('#c084fc');
  if (type === 'forest') return new THREE.Color('#22c55e');
  if (type === 'building') return new THREE.Color('#f3f4f6');
  return new THREE.Color('#d1d5db'); // ground
}

function getTerrainHeight(cell: GridCell | undefined): number {
  const hazard = cell?.hazard ?? 0.2;
  return Math.max(1, Math.min(5, Math.round(1 + hazard * 4)));
}

function buildRenderedVoxels(voxels: VoxelCoordinate[], cells: GridCell[]): VoxelCoordinate[] {
  const rendered: VoxelCoordinate[] = [];
  const terrainHeights = new Map<string, number>();

  for (const voxel of voxels) {
    const key = `${voxel.x},${voxel.z}`;
    let terrainHeight = terrainHeights.get(key);

    if (terrainHeight === undefined) {
      const cell = findRiskForPosition(voxel.data.lat, voxel.data.lng, cells);
      terrainHeight = getTerrainHeight(cell);
      terrainHeights.set(key, terrainHeight);
    }

    if (voxel.data.type === 'ground') {
      for (let y = 0; y < terrainHeight; y++) {
        rendered.push({ ...voxel, y, data: voxel.data });
      }
      continue;
    }

    rendered.push({ ...voxel, y: voxel.y + terrainHeight, data: voxel.data });
  }

  return rendered;
}

// Story 16: strict PRD rule delegated to canonical helper (span > 0.30 overrides EAWS).
function isHighUncertainty(cell: GridCell | undefined) {
  return isHighUncertaintyCell(cell);
}

async function fetchOSMData(bbox: [number, number, number, number]): Promise<FetchedVoxelData> {
  const result = await fetchOverpassJson<{ elements?: OSMElement[] }>({
    cacheKey: `overpass:voxel:${bbox.join(',')}`,
    query: bboxToQuery(bbox),
    ttlMs: 60_000,
    timeoutMs: OVERPASS_FETCH_TIMEOUT_MS,
  });

  if (!result.ok) {
    console.warn('Failed to load OSM voxel data, using terrain fallback', result.message);
    return {
      voxels: buildTerrainFallback(bbox),
      degradedMessage: result.message,
      cacheable: false,
    };
  }

  return {
    voxels: buildVoxelGridFromOSM(result.data, bbox),
    degradedMessage: null,
    cacheable: true,
  };
}

// ---- Three.js scene ----
function VoxelScene({
  voxels,
  cells,
  onHover,
  onHoverEnd,
  onRenderReady,
  onRenderError,
}: {
  voxels: VoxelCoordinate[];
  cells: GridCell[];
  onHover: (info: HoveredInfo) => void;
  onHoverEnd: () => void;
  onRenderReady: () => void;
  onRenderError: (error: Error) => void;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const colorObj = useMemo(() => new THREE.Color(), []);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  // Update instanced mesh positions only once
  useEffect(() => {
    if (!meshRef.current) return;
    try {
      voxels.forEach((v, i) => {
        dummy.position.set(v.x, v.y, v.z);
        dummy.updateMatrix();
        meshRef.current!.setMatrixAt(i, dummy.matrix);
      });
      meshRef.current.instanceMatrix.needsUpdate = true;
      onRenderReady();
    } catch (error) {
      onRenderError(error instanceof Error ? error : new Error('Failed to prepare voxel matrices'));
    }
  }, [dummy, onRenderError, onRenderReady, voxels]);

  // Update colors (reactively to cells changing via timeline scrub)
  useEffect(() => {
    if (!meshRef.current) return;
    try {
      voxels.forEach((v, i) => {
        const baseC = getBaseColor(v.data.type);
        const cell = findRiskForPosition(v.data.lat, v.data.lng, cells);
        if (cell) {
          if (isCellUnavailable(cell)) {
            baseC.lerp(new THREE.Color('#6b7280'), 0.78);
          } else if (isCellMasked(cell)) {
            baseC.lerp(new THREE.Color('#6b7280'), 0.72);
          } else if (isHighUncertainty(cell)) {
            baseC.lerp(new THREE.Color('#9ca3af'), 0.72);
          } else {
            const riskC = new THREE.Color(RISK_COLORS[Math.max(1, Math.min(5, Math.round(cell.riskScore)))]);
            // Tint the base color strongly with the risk color
            baseC.lerp(riskC, 0.7);
          }
        }
        meshRef.current!.setColorAt(i, baseC);
      });
      if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true;
      onRenderReady();
    } catch (error) {
      onRenderError(error instanceof Error ? error : new Error('Failed to color voxel instances'));
    }
  }, [cells, onRenderError, onRenderReady, voxels]);

  const handlePointerMove = useCallback((e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    if (e.instanceId !== undefined && e.instanceId !== null) {
      const v = voxels[e.instanceId];
      if (v) {
        const cell = findRiskForPosition(v.data.lat, v.data.lng, cells);
        const unavailable = isCellUnavailable(cell);
        const masked = isCellMasked(cell) && !unavailable;
        const maskLabel = getCellMaskLabel(cell);
        const maskSummary = getCellMaskSummary(cell);
        const maskReasons = getCellMaskReasonDescriptions(cell);
        const score = masked ? 0 : Math.max(1, Math.min(5, Math.round(cell?.riskScore || 1)));
        onHover({
          type: typeName(v.data.type),
          riskLabel: unavailable ? 'Unavailable' : masked ? maskLabel : (RISK_LABELS[score] ?? 'Unknown'),
          riskScore: score,
          lat: v.data.lat,
          lng: v.data.lng,
          color: unavailable || masked ? '#6b7280' : isHighUncertainty(cell) ? '#9ca3af' : (RISK_COLORS[score] || '#333'),
          unavailable,
          masked,
          availabilityReason: cell?.availabilityReason ?? null,
          maskLabel,
          maskSummary,
          maskReasons,
          problemType: cell?.problemType,
          probability: cell?.probability,
          uncertaintyClass: cell?.uncertaintyClass,
        });
      }
    }
  }, [voxels, cells, onHover]);

  return (
    <>
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
      {voxels.length > 0 && (
        <instancedMesh
          ref={meshRef}
          args={[undefined, undefined, voxels.length]}
          onPointerMove={handlePointerMove}
          onPointerOut={() => onHoverEnd()}
        >
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial />
        </instancedMesh>
      )}
    </>
  );
}

function VoxelFallbackCanvas({
  voxels,
  cells,
  canvasBg,
}: {
  voxels: VoxelCoordinate[];
  cells: GridCell[];
  canvasBg: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = canvasBg;
    ctx.fillRect(0, 0, width, height);

    const scaleX = width / WORLD_SIZE;
    const scaleY = height / WORLD_SIZE;

    for (const voxel of voxels.slice(0, 2500)) {
      const cell = findRiskForPosition(voxel.data.lat, voxel.data.lng, cells);
      const riskScore = Math.max(1, Math.min(5, Math.round(cell?.riskScore || 1)));
      ctx.fillStyle = isCellUnavailable(cell) || isCellMasked(cell) ? '#6b7280' : isHighUncertainty(cell) ? '#9ca3af' : (RISK_COLORS[riskScore] || '#334155');
      const x = Math.round((voxel.x + WORLD_SIZE / 2) * scaleX);
      const y = Math.round((voxel.z + WORLD_SIZE / 2) * scaleY);
      const size = voxel.data.type === 'building' ? 3 : voxel.data.type === 'road' ? 2 : 1.5;
      ctx.fillRect(x, y, size, size);
    }
  }, [voxels, cells, canvasBg]);

  return <canvas ref={canvasRef} width={900} height={700} className="w-full h-full" />;
}

// ---- Main modal ----
export default function VoxelNeighborhoodModal({ open, onClose, bbox, gridCells, hourlyGrids, timeOffset }: Props) {
  const [blocks, setBlocks] = useState<VoxelCoordinate[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [renderReady, setRenderReady] = useState(false);
  const [sparseRegion, setSparseRegion] = useState(false);
  const [hovered, setHovered] = useState<HoveredInfo | null>(null);

  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';
  const canvasBg = isDark ? '#0a0a0a' : '#f1f5f9';

  const currentCells = useMemo(() => {
    const sourceCells = hourlyGrids && Array.isArray(hourlyGrids[timeOffset]) ? hourlyGrids[timeOffset] : gridCells;
    return sourceCells.filter((cell) => hasRenderableCellGeometry(cell));
  }, [hourlyGrids, timeOffset, gridCells]);

  const renderedBlocks = useMemo(() => {
    if (!blocks) return null;
    return buildRenderedVoxels(blocks, currentCells);
  }, [blocks, currentCells]);

  const cacheKey = useMemo(() => `voxel_grid_${bbox.join(',')}`, [bbox]);

  const fetchBlocks = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    setRenderError(null);
    setRenderReady(false);
    setSparseRegion(false);
    setHovered(null);
    try {
      const result = await fetchOSMData(bbox);
      const raw = result.voxels;
      setFetchError(result.degradedMessage);
      
      const structureCount = raw.filter(b => b.data.type !== 'ground').length;
      if (structureCount < 5) {
        setSparseRegion(true);
      }

      setBlocks(raw);
      if (result.cacheable) {
        sessionCache.set(cacheKey, raw);
      }
    } catch {
      setFetchError('Could not fetch OSM data — using terrain fallback for this view.');
      setBlocks(buildTerrainFallback(bbox));
    } finally {
      setLoading(false);
    }
  }, [bbox, cacheKey]);

  const handleRenderReady = useCallback(() => {
    setRenderReady(true);
    setLoading(false);
    setRenderError(null);
  }, []);

  const handleRenderError = useCallback((error: Error) => {
    console.error('Voxel render failed:', error);
    setRenderError(error.message || '3D rendering failed');
    setLoading(false);
  }, []);

  useEffect(() => {
    if (!open) {
      // Reset state when modal closes to prevent stale data on reopen
      setHovered(null);
      setLoading(false);
      return;
    }
    setHovered(null);

    const memCached = sessionCache.get(cacheKey);
    if (memCached) {
      setBlocks(memCached);
      const sc = memCached.filter(b => b.data.type !== 'ground').length < 5;
      setSparseRegion(sc);
      return;
    }
    // B4 fix: Ensure fetch is called with proper loading state
    fetchBlocks();
  }, [open, cacheKey, fetchBlocks]);

  if (!open) return null;

  // hasRealData: blocks has been loaded (null = loading, [] or [..] = loaded)
  // We always get ground voxels from OSM so blocks.length > 0 is always true after a successful fetch
  const hasRealData = renderedBlocks !== null && renderedBlocks.length > 0;
  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
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
          <DialogDescription className="sr-only">
            Explore a 3D neighborhood risk view generated from OpenStreetMap structures and the current avalanche risk grid.
          </DialogDescription>
        </DialogHeader>

        <div className="bg-red-500/15 px-4 py-1.5 flex items-center gap-2 shrink-0 border-b border-red-500/30">
          <AlertTriangle className="h-3 w-3 shrink-0 text-red-400" />
          <span className="text-red-400 text-[10px]"><strong>Experimental 3D visualization</strong> — for illustration only</span>
        </div>

        {sparseRegion && !loading && hasRealData && (
          <div className="bg-blue-500/10 px-4 py-1 flex items-center gap-2 shrink-0 border-b border-blue-500/20">
            <Info className="h-3 w-3 shrink-0 text-blue-400" />
            <span className="text-blue-400 text-[10px]">Limited OSM building data for this region — showing terrain risk map</span>
          </div>
        )}

        {fetchError && !loading && hasRealData && (
          <div className="bg-amber-500/10 px-4 py-1 flex items-center gap-2 shrink-0 border-b border-amber-500/20">
            <Info className="h-3 w-3 shrink-0 text-amber-300" />
            <span className="text-amber-100 text-[10px]">{fetchError}</span>
          </div>
        )}

        <div className="flex-1 relative min-h-0" style={{ background: canvasBg }}>
          {loading ? (
            <div 
              className="absolute inset-0 flex flex-col items-center justify-center gap-3"
              style={{ background: canvasBg }}
            >
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <span className="text-sm text-muted-foreground">Generating true voxel map… (est. 4–8s)</span>
            </div>
          ) : hasRealData && !renderError ? (
            <Canvas
              camera={{ position: [40, 40, 40], fov: 50 }}
              style={{ width: '100%', height: '100%', background: canvasBg }}
            >
              <VoxelScene
                voxels={renderedBlocks!}
                cells={currentCells}
                onHover={setHovered}
                onHoverEnd={() => setHovered(null)}
                onRenderReady={handleRenderReady}
                onRenderError={handleRenderError}
              />
            </Canvas>
          ) : hasRealData ? (
            <VoxelFallbackCanvas voxels={renderedBlocks!} cells={currentCells} canvasBg={canvasBg} />
          ) : (
            <div 
              className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground text-sm px-8 text-center"
              style={{ background: canvasBg }}
            >
              {renderError ? (
                <>
                  <span className="text-red-400 font-medium">3D render fallback active</span>
                  <span>{renderError}</span>
                </>
              ) : (
                <>
                  <span className="font-medium">3D canvas is unavailable right now</span>
                  <span>Rendering the voxel dataset in fallback mode.</span>
                </>
              )}
            </div>
          )}

          {hovered && (
            <div className="absolute top-3 left-3 z-20 glass-panel rounded-lg p-3 space-y-1.5 min-w-[200px] pointer-events-none">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-sm shrink-0" style={{ backgroundColor: hovered.color }} />
                <span className="text-xs font-semibold text-foreground">
                  {hovered.unavailable ? 'Unavailable Cell' : hovered.masked ? hovered.maskLabel : `${hovered.riskLabel} Risk`}
                </span>
              </div>
              <div className="text-[10px] text-muted-foreground space-y-0.5 mt-2">
                <div><strong>Type:</strong> {hovered.type}</div>
                {hovered.unavailable && <div><strong>Reason:</strong> {hovered.availabilityReason ?? 'unavailable_terrain'}</div>}
                {hovered.masked && hovered.maskSummary && <div><strong>State:</strong> {hovered.maskSummary}</div>}
                {hovered.masked && hovered.maskReasons?.map((reason) => (
                  <div key={reason}><strong>Reason:</strong> {reason}</div>
                ))}
                {hovered.problemType && <div><strong>Problem:</strong> {hovered.problemType}</div>}
                {hovered.probability !== undefined && <div><strong>Prob:</strong> {hovered.probability.toFixed(2)}</div>}
                {hovered.uncertaintyClass && <div><strong>Uncertainty:</strong> {hovered.uncertaintyClass}</div>}
                <div><strong>Coords:</strong> {hovered.lat.toFixed(4)}°, {hovered.lng.toFixed(4)}°</div>
              </div>
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
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-sm bg-slate-500" />
              <span className="text-[10px] text-muted-foreground">Masked terrain</span>
            </div>
          </div>
        </div>

        <div className="p-3 border-t border-border text-[10px] text-muted-foreground flex items-center justify-between shrink-0">
          <span>3D view inspired by <a href="https://github.com/louis-e/arnis" target="_blank" rel="noopener noreferrer" className="underline text-primary/70 hover:text-primary">Arnis</a> (github.com/louis-e/arnis)</span>
          <span>Hour {timeOffset} • {currentCells.length} cells • {renderedBlocks?.length || 0} voxels</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
