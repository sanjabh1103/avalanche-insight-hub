import { useEffect, useMemo, useRef, useState } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import booleanIntersects from '@turf/boolean-intersects';
import { lineString, point, polygon } from '@turf/helpers';
import type { Feature, Polygon } from 'geojson';
import { fetchOverpassJson, OverpassDegraded } from '@/lib/overpassClient';

interface Props {
  bbox: [number, number, number, number];
  showRoads: boolean;
  showInfrastructure: boolean;
  runoutPolygons?: Array<Record<string, unknown>>;
}

interface OverlaySummary {
  affectedRoads: number;
  affectedAssets: number;
  affectedRoadNames: string[];
  affectedAssetNames: string[];
}

function buildQuery(bbox: [number, number, number, number], type: 'roads' | 'infra'): string {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const b = `${latMin},${lngMin},${latMax},${lngMax}`;
  if (type === 'roads') {
    return `[out:json][timeout:10];(way["highway"~"primary|secondary|trunk"](${b}););out geom;`;
  }
  return `[out:json][timeout:10];(node["aerialway"](${b});node["place"~"village|town"](${b}););out;`;
}

function buildRunoutFeatures(runoutPolygons: Array<Record<string, unknown>>): Array<Feature<Polygon>> {
  return runoutPolygons
    .map((item) => item.polygon)
    .filter((ringCoordinates): ringCoordinates is unknown[] => Array.isArray(ringCoordinates) && ringCoordinates.length >= 4)
    .map((ringCoordinates) =>
      polygon([
        ringCoordinates
          .filter((point): point is [number, number] => Array.isArray(point) && point.length >= 2)
          .map((point) => [Number(point[0]), Number(point[1])]),
      ]),
    )
    .filter((feature) => feature.geometry.coordinates[0].length >= 4);
}

function intersectsRoad(
  geometry: Array<{ lat: number; lon: number }>,
  runoutFeatures: Array<Feature<Polygon>>,
): boolean {
  if (runoutFeatures.length === 0 || geometry.length < 2) return false;
  const line = lineString(geometry.map((segmentPoint) => [segmentPoint.lon, segmentPoint.lat]));
  return runoutFeatures.some((feature) => booleanIntersects(feature, line));
}

function intersectsAsset(
  lat: number,
  lon: number,
  runoutFeatures: Array<Feature<Polygon>>,
): boolean {
  if (runoutFeatures.length === 0) return false;
  const assetPoint = point([lon, lat]);
  return runoutFeatures.some((feature) => booleanIntersects(feature, assetPoint));
}

const EMPTY_SUMMARY: OverlaySummary = {
  affectedRoads: 0,
  affectedAssets: 0,
  affectedRoadNames: [],
  affectedAssetNames: [],
};

export default function ImpactOverlays({ bbox, showRoads, showInfrastructure, runoutPolygons = [] }: Props) {
  const map = useMap();
  const layersRef = useRef<L.Layer[]>([]);
  const [loading, setLoading] = useState(false);
  const [summary, setSummary] = useState<OverlaySummary>(EMPTY_SUMMARY);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const runoutFeatures = useMemo(() => buildRunoutFeatures(runoutPolygons), [runoutPolygons]);

  useEffect(() => {
    layersRef.current.forEach((layer) => map.removeLayer(layer));
    layersRef.current = [];
    setSummary(EMPTY_SUMMARY);
    setStatusMessage(null);

    if (!showRoads && !showInfrastructure) return;

    let cancelled = false;
    const nextSummary: OverlaySummary = {
      affectedRoads: 0,
      affectedAssets: 0,
      affectedRoadNames: [],
      affectedAssetNames: [],
    };
    setLoading(true);

    const fetchPromises: Promise<void>[] = [];

    if (showRoads) {
      fetchPromises.push(
        fetchOverpassJson<{ elements?: Record<string, unknown>[] }>({
          cacheKey: `overpass:roads:${bbox.join(',')}`,
          query: buildQuery(bbox, 'roads'),
          ttlMs: 60_000,
        })
          .then((result) => {
            if (cancelled) return;
            if (!result.ok) {
              setStatusMessage((result as OverpassDegraded).message);
              return;
            }
            const data = result.data;
            const elements = data.elements || [];
            let added = 0;
            elements.forEach((element: Record<string, unknown>) => {
              if (element.type !== 'way' || !Array.isArray(element.geometry)) return;
              const geometry = element.geometry as Array<{ lat: number; lon: number }>;
              const affected = intersectsRoad(geometry, runoutFeatures);
              const coords = geometry.map((point) => [point.lat, point.lon] as [number, number]);
              const tags = (element.tags || {}) as Record<string, string>;
              const roadName = tags.name || `${tags.highway || 'road'} ${Number(element.id ?? 0)}`;
              const line = L.polyline(coords, {
                color: affected ? '#ef4444' : '#f97316',
                weight: affected ? 3 : 2,
                opacity: affected ? 0.92 : 0.7,
              });
              line.bindPopup(
                `<b>${roadName}</b><br/>Type: ${tags.highway || 'unknown'}${
                  affected ? '<br/><span style="color:#ef4444">Runout intersection detected</span>' : ''
                }`,
              );
              line.addTo(map);
              layersRef.current.push(line);
              added++;
              if (affected) {
                nextSummary.affectedRoads += 1;
                nextSummary.affectedRoadNames.push(roadName);
              }
            });
          }),
      );
    }

    if (showInfrastructure) {
      fetchPromises.push(
        fetchOverpassJson<{ elements?: Record<string, unknown>[] }>({
          cacheKey: `overpass:infra:${bbox.join(',')}`,
          query: buildQuery(bbox, 'infra'),
          ttlMs: 60_000,
        })
          .then((result) => {
            if (cancelled) return;
            if (!result.ok) {
              setStatusMessage((result as OverpassDegraded).message);
              return;
            }
            const data = result.data;
            const elements = data.elements || [];
            let added = 0;
            elements.forEach((element: Record<string, unknown>) => {
              if (element.type !== 'node' || typeof element.lat !== 'number' || typeof element.lon !== 'number') return;
              const tags = (element.tags || {}) as Record<string, string>;
              const isLift = !!tags.aerialway;
              const affected = intersectsAsset(element.lat as number, element.lon as number, runoutFeatures);
              const assetName = tags.name || (isLift ? 'Ski Lift' : 'Village');
              const marker = L.circleMarker([element.lat as number, element.lon as number], {
                radius: affected ? 7 : 6,
                color: affected ? '#ef4444' : isLift ? '#a78bfa' : '#67e8f9',
                fillColor: affected ? '#ef4444' : isLift ? '#a78bfa' : '#67e8f9',
                fillOpacity: 0.85,
                weight: 1,
              });
              marker.bindPopup(
                `<b>${assetName}</b><br/>Type: ${tags.aerialway || tags.place || 'unknown'}${
                  affected ? '<br/><span style="color:#ef4444">Inside predicted runout zone</span>' : ''
                }`,
              );
              marker.addTo(map);
              layersRef.current.push(marker);
              added++;
              if (affected) {
                nextSummary.affectedAssets += 1;
                nextSummary.affectedAssetNames.push(assetName);
              }
            });
          }),
      );
    }

    Promise.all(fetchPromises).finally(() => {
      if (!cancelled) {
        setSummary(nextSummary);
        setLoading(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [bbox, map, runoutFeatures, showInfrastructure, showRoads]);

  if (loading) {
    return (
      <div className="absolute top-20 left-1/2 -translate-x-1/2 z-[1000] glass-panel rounded-full px-4 py-2 text-xs text-muted-foreground">
        Fetching impact data…
      </div>
    );
  }

  if (statusMessage) {
    return (
      <div className="absolute top-20 left-1/2 z-[1000] max-w-[32rem] -translate-x-1/2 rounded-2xl border border-amber-500/30 bg-black/80 px-4 py-2.5 text-xs text-amber-100 shadow-xl">
        {statusMessage}
      </div>
    );
  }

  if ((showRoads || showInfrastructure) && runoutFeatures.length > 0) {
    const summaryText = summary.affectedRoads > 0 || summary.affectedAssets > 0
      ? `Runout warnings: ${summary.affectedRoads} roads and ${summary.affectedAssets} assets intersect persisted runout polygons.`
      : 'No fetched roads or mapped assets intersect the persisted runout polygons.';
    const detailNames = [...summary.affectedRoadNames, ...summary.affectedAssetNames].slice(0, 3);
    return (
      <div className="absolute top-20 left-1/2 -translate-x-1/2 z-[1000] max-w-[32rem] glass-panel rounded-2xl px-4 py-2.5 text-xs text-foreground shadow-xl">
        <div className="font-medium">{summaryText}</div>
        {detailNames.length > 0 && (
          <div className="mt-1 text-muted-foreground">
            Affected: {detailNames.join(', ')}
            {(summary.affectedRoadNames.length + summary.affectedAssetNames.length) > detailNames.length ? '…' : ''}
          </div>
        )}
      </div>
    );
  }

  return null;
}
