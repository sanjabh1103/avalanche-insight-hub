import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { AlertTriangle, RefreshCw, Loader2, Info } from 'lucide-react';
import { RISK_COLORS, RISK_LABELS, GRID_SIZE } from '@/lib/constants';
import type { GridCell } from '@/lib/gridUtils';
import { Canvas, ThreeEvent, useFrame } from '@react-three/fiber';
import { OrbitControls, Instances, Instance } from '@react-three/drei';
import { useTheme } from 'next-themes';
import * as THREE from 'three';

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

interface VoxelCoordinate {
  x: number;
  y: number;
  z: number;
  data: BaseBlock;
}

interface HoveredInfo {
  type: string;
  riskLabel: string;
  riskScore: number;
  lat: number;
  lng: number;
  color: string;
  problemType?: string;
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
const WORLD_SIZE = 60; // 60x60 strict grid

// ---- In-memory session cache ----
const sessionCache = new Map<string, VoxelCoordinate[]>();

// ---- Rate limiting state (module-level singleton) ----
let lastRequestTime = 0;
let consecutiveFailures = 0;
const MIN_REQUEST_INTERVAL = 5000; // 5 seconds minimum between requests
const MAX_RETRIES = 3;

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

function findRiskForPosition(lat: number, lng: number, cells: GridCell[]): GridCell | undefined {
  return cells.find(c => lat >= c.lat && lat < c.latEnd && lng >= c.lng && lng < c.lngEnd);
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

// Store the in-progress promise for deduplication
let pendingPromise: Promise<VoxelCoordinate[]> | null = null;

async function fetchOSMData(bbox: [number, number, number, number], retryCount = 0): Promise<VoxelCoordinate[]> {
  // Deduplication: if a fetch is already in progress, return that promise
  if (pendingPromise) {
    return pendingPromise;
  }
  
  // Create and store the promise IMMEDIATELY (synchronously)
  // This prevents race conditions where multiple calls slip through
  pendingPromise = (async (): Promise<VoxelCoordinate[]> => {
    try {
      // Circuit breaker: add extra delay if we've had recent failures
      const circuitBreakerDelay = Math.min(consecutiveFailures * 3000, 15000);
      
      // Rate limiting: ensure minimum interval between requests
      const now = Date.now();
      const timeSinceLastRequest = now - lastRequestTime;
      const requiredDelay = Math.max(MIN_REQUEST_INTERVAL, circuitBreakerDelay);
      
      if (timeSinceLastRequest < requiredDelay) {
        await new Promise(resolve => setTimeout(resolve, requiredDelay - timeSinceLastRequest));
      }
      
      const query = bboxToQuery(bbox);
      
      lastRequestTime = Date.now();
      const res = await fetch(OVERPASS_URL, {
        method: 'POST',
        body: `data=${encodeURIComponent(query)}`,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      });
      
      // Handle 429 (Rate Limit) and 504 (Gateway Timeout) with exponential backoff
      if ((res.status === 429 || res.status === 504) && retryCount < MAX_RETRIES) {
        consecutiveFailures++;
        // Longer delays with jitter: 3s, 6s, 12s
        const delay = Math.pow(2, retryCount) * 3000 + Math.random() * 1000;
        await new Promise(resolve => setTimeout(resolve, delay));
        return fetchOSMData(bbox, retryCount + 1);
      }
      
      // Track failures for circuit breaker
      if (res.status === 429 || res.status >= 500) {
        consecutiveFailures++;
      }
      
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      
      // Reset failure count on success
      consecutiveFailures = 0;
      
      const data = await res.json();
      
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
        // Base layer
        voxels.push({ x, y: 0, z, data: block });
        
        // Extrude buildings
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
    } catch (err) {
      consecutiveFailures++;
      throw err;
    } finally {
      pendingPromise = null;
    }
  })();
  
  return pendingPromise;
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
  }, [voxels, dummy]);

  // Update colors (reactively to cells changing via timeline scrub)
  useEffect(() => {
    if (!meshRef.current) return;
    try {
      voxels.forEach((v, i) => {
        const baseC = getBaseColor(v.data.type);
        const cell = findRiskForPosition(v.data.lat, v.data.lng, cells);
        if (cell) {
          const riskC = new THREE.Color(RISK_COLORS[Math.max(1, Math.min(5, Math.round(cell.riskScore)))]);
          // Tint the base color strongly with the risk color
          baseC.lerp(riskC, 0.7);
        }
        meshRef.current!.setColorAt(i, baseC);
      });
      if (meshRef.current.instanceColor) meshRef.current.instanceColor.needsUpdate = true;
      onRenderReady();
    } catch (error) {
      onRenderError(error instanceof Error ? error : new Error('Failed to color voxel instances'));
    }
  }, [voxels, cells]);

  const handlePointerMove = useCallback((e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    if (e.instanceId !== undefined && e.instanceId !== null) {
      const v = voxels[e.instanceId];
      if (v) {
        const cell = findRiskForPosition(v.data.lat, v.data.lng, cells);
        const score = Math.max(1, Math.min(5, Math.round(cell?.riskScore || 1)));
        onHover({
          type: typeName(v.data.type),
          riskLabel: RISK_LABELS[score] ?? 'Unknown',
          riskScore: score,
          lat: v.data.lat,
          lng: v.data.lng,
          color: RISK_COLORS[score] || '#333',
          problemType: cell?.problemType,
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
      ctx.fillStyle = RISK_COLORS[riskScore] || '#334155';
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
    if (hourlyGrids && hourlyGrids[timeOffset]) return hourlyGrids[timeOffset];
    return gridCells;
  }, [hourlyGrids, timeOffset, gridCells]);

  const cacheKey = useMemo(() => `voxel_grid_${bbox.join(',')}`, [bbox]);

  const fetchBlocks = useCallback(async () => {
    setLoading(true);
    setFetchError(null);
    setRenderError(null);
    setRenderReady(false);
    setSparseRegion(false);
    setHovered(null);
    try {
      const raw = await fetchOSMData(bbox);
      
      const structureCount = raw.filter(b => b.data.type !== 'ground').length;
      if (structureCount < 5) {
        setSparseRegion(true);
      }

      setBlocks(raw);
      sessionCache.set(cacheKey, raw);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      if (msg.includes('504') || msg.includes('timeout') || msg.includes('Gateway')) {
        setFetchError('Overpass API server is overloaded (504). Please wait 30 seconds and try again.');
      } else if (msg.includes('429')) {
        setFetchError('Rate limit exceeded. Please wait a moment before retrying.');
      } else {
        setFetchError('Could not fetch OSM data — check your connection and try again.');
      }
      setBlocks([]);
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
  const hasRealData = blocks !== null && blocks.length > 0;
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

        <div className="flex-1 relative min-h-0" style={{ background: canvasBg }}>
          {loading ? (
            <div 
              className="absolute inset-0 flex flex-col items-center justify-center gap-3"
              style={{ background: canvasBg }}
            >
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <span className="text-sm text-muted-foreground">Generating true voxel map… (est. 4–8s)</span>
            </div>
          ) : fetchError ? (
            <div 
              className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-foreground text-sm px-8 text-center"
              style={{ background: canvasBg }}
            >
              <AlertTriangle className="h-8 w-8 text-red-400" />
              <span className="max-w-md">{fetchError}</span>
            </div>
          ) : hasRealData && !renderError ? (
            <Canvas
              camera={{ position: [40, 40, 40], fov: 50 }}
              style={{ width: '100%', height: '100%', background: canvasBg }}
            >
              <VoxelScene
                voxels={blocks!}
                cells={currentCells}
                onHover={setHovered}
                onHoverEnd={() => setHovered(null)}
                onRenderReady={handleRenderReady}
                onRenderError={handleRenderError}
              />
            </Canvas>
          ) : hasRealData ? (
            <VoxelFallbackCanvas voxels={blocks!} cells={currentCells} canvasBg={canvasBg} />
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
                <span className="text-xs font-semibold text-foreground">{hovered.riskLabel} Risk</span>
              </div>
              <div className="text-[10px] text-muted-foreground space-y-0.5 mt-2">
                <div><strong>Type:</strong> {hovered.type}</div>
                {hovered.problemType && <div><strong>Problem:</strong> {hovered.problemType}</div>}
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
          </div>
        </div>

        <div className="p-3 border-t border-border text-[10px] text-muted-foreground flex items-center justify-between shrink-0">
          <span>3D view inspired by <a href="https://github.com/louis-e/arnis" target="_blank" rel="noopener noreferrer" className="underline text-primary/70 hover:text-primary">Arnis</a> (github.com/louis-e/arnis)</span>
          <span>Hour {timeOffset} • {currentCells.length} cells • {blocks?.length || 0} voxels</span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
