import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { MapContainer, TileLayer, Rectangle, CircleMarker, Pane, Popup, Polygon, Tooltip, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import 'leaflet/dist/leaflet.css';
import {
  getCellMaskLabel,
  getCellMaskReasonDescriptions,
  getCellMaskSummary,
  hasRenderableCellGeometry,
  getRiskColor,
  isCellMasked,
  isCellUnavailable,
  isHighUncertaintyCell,
  type GridCell,
} from '@/lib/gridUtils';
import {
  getAvalancheEventGovernanceLabel,
  getAvalancheEventGovernanceState,
  getAvalancheEventMarkerAppearance,
  type AvalancheEvent,
} from '@/lib/avalancheEvents';
import { useTheme } from 'next-themes';

const LazyActivityHeatmap = lazy(() => import('@/components/ActivityHeatmap'));
const LazyImpactOverlays = lazy(() => import('@/components/ImpactOverlays'));

interface Props {
  cells: GridCell[];
  selectedCell: GridCell | null;
  onCellClick: (cell: GridCell) => void;
  center: [number, number];
  zoom: number;
  historicalEvents?: AvalancheEvent[];
  heatmapEvents?: AvalancheEvent[];
  showHeatmap?: boolean;
  showRoads?: boolean;
  showInfra?: boolean;
  showVectorPolygons?: boolean;
  runoutPolygons?: Array<Record<string, unknown>>;
  sarEventGeometries?: Array<Record<string, unknown>>;
  bbox?: [number, number, number, number];
}

function OverlayLoadingNotice({ label }: { label: string }) {
  return (
    <div className="absolute top-20 left-1/2 z-[1000] max-w-[22rem] -translate-x-1/2 rounded-full border border-border/70 bg-card/80 px-4 py-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground shadow-xl backdrop-blur-xl">
      {label}
    </div>
  );
}

function MapUpdater({ center, zoom }: { center: [number, number]; zoom: number }) {
  const map = useMap();
  const prevCenter = useRef(center);
  useEffect(() => {
    if (prevCenter.current[0] !== center[0] || prevCenter.current[1] !== center[1]) {
      map.flyTo(center, zoom, { duration: 1.5 });
      prevCenter.current = center;
    }
    setTimeout(() => map.invalidateSize(), 100);
  }, [map, center, zoom]);
  return null;
}

export default function AvalancheMap({
  cells, selectedCell, onCellClick, center, zoom,
  historicalEvents = [], heatmapEvents = historicalEvents, showHeatmap = false, showRoads = false, showInfra = false,
  showVectorPolygons = false, runoutPolygons = [], sarEventGeometries = [], bbox,
}: Props) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';
  const tileUrl = isDark
    ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';

  // Render persisted batch overlays when vector mode is on.
  const [vectorPolygons, setVectorPolygons] = useState<{key: string; positions: [number, number][][]}[]>([]);
  const renderableCells = useMemo(
    () => cells.filter((cell) => hasRenderableCellGeometry(cell)),
    [cells],
  );

  useEffect(() => {
    if (!showVectorPolygons) {
      setVectorPolygons([]);
      return;
    }

    const persistedRunout = runoutPolygons
      .filter((item) => Array.isArray(item.polygon) && item.polygon.length > 0)
      .map((item, index) => ({
        key: `runout-${index}`,
        positions: [
          (item.polygon as unknown[]).map((coord) => {
            const point = coord as [number, number];
            return [Number(point[1]), Number(point[0])] as [number, number];
          }),
        ],
      }));

    if (persistedRunout.length > 0) {
      setVectorPolygons(persistedRunout);
      return;
    }

    const sarPolygons = sarEventGeometries
      .map((item, index) => {
        const geometry = item.geometry as GeoJSON.Geometry | undefined;
        if (!geometry) return null;
        if (geometry.type === 'Polygon') {
          return {
            key: `sar-${index}`,
            positions: [geometry.coordinates[0].map((coord) => [coord[1], coord[0]] as [number, number])],
          };
        }
        if (geometry.type === 'MultiPolygon') {
          return {
            key: `sar-${index}`,
            positions: geometry.coordinates.map((polygon) => polygon[0].map((coord) => [coord[1], coord[0]] as [number, number])),
          };
        }
        return null;
      })
      .filter((item): item is {key: string; positions: [number, number][][]} => item !== null);

    setVectorPolygons(sarPolygons);
  }, [runoutPolygons, sarEventGeometries, showVectorPolygons]);

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    const skippedCellCount = cells.length - renderableCells.length;
    if (skippedCellCount <= 0) return;
    console.warn(`[AvalancheMap] skipped ${skippedCellCount} cells with invalid rectangle bounds`);
  }, [cells.length, renderableCells.length]);

  return (
    <MapContainer center={center} zoom={zoom} className="h-full w-full z-0 theme-aware-map" zoomControl={true} touchZoom={true} dragging={true}>
      <MapUpdater center={center} zoom={zoom} />
      <TileLayer attribution='&copy; <a href="https://carto.com/">CARTO</a>' url={tileUrl} />

      {/* Risk grid cells */}
      {renderableCells.map((cell) => {
        const bounds: LatLngBoundsExpression = [[cell.lat, cell.lng], [cell.latEnd, cell.lngEnd]];
        const isSelected = selectedCell?.row === cell.row && selectedCell?.col === cell.col;
        const isHighUncertainty = isHighUncertaintyCell(cell);
        const isUnavailable = isCellUnavailable(cell);
        const isMasked = isCellMasked(cell) && !isUnavailable;
        const maskLabel = getCellMaskLabel(cell);
        const maskSummary = getCellMaskSummary(cell);
        const maskReasonDescriptions = getCellMaskReasonDescriptions(cell);
        return (
          <Rectangle
            key={`${cell.row}-${cell.col}`}
            bounds={bounds}
            pathOptions={{
              color: isSelected ? '#ffffff' : 'transparent',
              weight: isSelected ? 2 : 0,
              fillColor: isUnavailable || isMasked ? '#6b7280' : isHighUncertainty ? '#9ca3af' : getRiskColor(cell.riskScore),
              fillOpacity: isUnavailable ? 0.3 : isMasked ? 0.38 : isHighUncertainty ? 0.42 : 0.45 + cell.riskScore * 0.06,
            }}
            eventHandlers={{ click: () => { if (!isUnavailable) onCellClick(cell); } }}
          >
            <Tooltip direction="top" opacity={0.9} className="bg-card border-border">
              <div className="text-xs space-y-1 p-1">
                {isUnavailable ? (
                  <>
                    <div className="font-semibold text-slate-200">Terrain unavailable</div>
                    <div className="text-muted-foreground">Grid [{cell.row},{cell.col}] is disabled in the batch artifact.</div>
                    <div className="text-muted-foreground">Reason: {cell.availabilityReason ?? cell.status ?? 'unavailable_terrain'}</div>
                  </>
                ) : (
                  <>
                    <div className="font-semibold">{isMasked ? maskLabel : `Risk: ${cell.riskScore}/5`}</div>
                    <div className="text-muted-foreground">
                      Elev: {cell.terrainInputs?.elevation_m?.toFixed(0) ?? 'N/A'}m
                    </div>
                    <div className="text-muted-foreground">
                      Slope: {cell.terrainInputs?.slope_angle_deg?.toFixed(1) ?? 'N/A'}°
                    </div>
                    <div className="text-muted-foreground">
                      Prob: {isMasked
                        ? 'masked'
                        : typeof cell.probability === 'number' && Number.isFinite(cell.probability)
                          ? `${(cell.probability * 100).toFixed(1)}%`
                          : Number.isFinite(cell.riskScore)
                            ? `${((cell.riskScore / 5) * 100).toFixed(1)}%`
                            : 'N/A'}
                    </div>
                    {isMasked && (
                      <>
                        <div className="text-muted-foreground">{maskSummary}</div>
                        {maskReasonDescriptions.length > 1 && maskReasonDescriptions.map((reason) => (
                          <div key={reason} className="text-muted-foreground">
                            Reason: {reason}
                          </div>
                        ))}
                        {cell.aptEligible === false && (
                          <div className="text-muted-foreground">
                            Profile: {cell.aptProfile ?? 'apt_30_50_v1'}
                          </div>
                        )}
                      </>
                    )}
                    {cell.dominantDriverFeature && (
                      <div className="text-emerald-400">Driver: {cell.dominantDriverFeature}</div>
                    )}
                  </>
                )}
              </div>
            </Tooltip>
          </Rectangle>
        );
      })}

      {/* Vector polygons overlay */}
      {vectorPolygons.map((vp) => (
        <Polygon
          key={vp.key}
          positions={vp.positions}
          pathOptions={{ color: '#ef4444', fillColor: '#ef4444', fillOpacity: 0.25, weight: 2, dashArray: '4 4' }}
        />
      ))}

      <Pane name="events-pane" style={{ zIndex: 650 }}>
        {historicalEvents
          .filter((event) => Number.isFinite(event.lat) && Number.isFinite(event.lng))
          .map((evt) => {
            const markerAppearance = getAvalancheEventMarkerAppearance(evt);
            const governanceLabel = getAvalancheEventGovernanceLabel(evt);
            const governanceState = getAvalancheEventGovernanceState(evt);
            return (
              <CircleMarker
                key={evt.id}
                center={[evt.lat, evt.lng]}
                radius={governanceState === 'pending_corroboration' ? 7 : 8}
                pathOptions={markerAppearance}
              >
              <Popup>
                <div className="text-xs space-y-1" style={{ color: isDark ? '#ddd' : '#111' }}>
                  <div className="font-bold">{evt.event_type.toUpperCase()}</div>
                  <div className={isDark ? 'text-blue-300' : 'text-blue-700'}>
                    📍 {evt.location_name || `${evt.lat.toFixed(3)}°, ${evt.lng.toFixed(3)}°`}
                  </div>
                  <div>{evt.description}</div>
                  <div className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                    Source: {evt.fusionSource || evt.source} • Confidence: {(evt.confidence * 100).toFixed(0)}%
                  </div>
                  <div className={isDark ? 'text-amber-300' : 'text-amber-700'}>
                    Status: {governanceLabel}
                  </div>
                  {governanceState === 'pending_corroboration' && (
                    <div className={isDark ? 'text-gray-400' : 'text-gray-600'}>
                      Received from the field-report loop and awaiting corroboration or review.
                    </div>
                  )}
                  {evt.timestamp && (
                    <div className={isDark ? 'text-gray-500' : 'text-gray-500'}>
                      🕐 {new Date(evt.timestamp).toLocaleString()}
                    </div>
                  )}
                </div>
              </Popup>
              </CircleMarker>
            );
          })}
      </Pane>

      {/* Activity Heatmap layer */}
      {showHeatmap ? (
        <Suspense fallback={<OverlayLoadingNotice label="Loading activity heatmap" />}>
          <LazyActivityHeatmap events={heatmapEvents} visible={showHeatmap} />
        </Suspense>
      ) : null}

      {/* Impact overlays */}
      {bbox && (showRoads || showInfra) ? (
        <Suspense fallback={<OverlayLoadingNotice label="Loading impact overlays" />}>
          <LazyImpactOverlays
            bbox={bbox}
            showRoads={showRoads}
            showInfrastructure={showInfra}
            runoutPolygons={runoutPolygons}
          />
        </Suspense>
      ) : null}
    </MapContainer>
  );
}
