import { useEffect, useState, useRef } from 'react';
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { toast } from 'sonner';

interface Props {
  bbox: [number, number, number, number];
  showRoads: boolean;
  showInfrastructure: boolean;
}

const OVERPASS_URL = 'https://overpass-api.de/api/interpreter';

function buildQuery(bbox: [number, number, number, number], type: 'roads' | 'infra'): string {
  const [latMin, lngMin, latMax, lngMax] = bbox;
  const b = `${latMin},${lngMin},${latMax},${lngMax}`;
  if (type === 'roads') {
    return `[out:json][timeout:10];(way["highway"~"primary|secondary|trunk"](${b}););out geom;`;
  }
  return `[out:json][timeout:10];(node["aerialway"](${b});node["place"~"village|town"](${b}););out;`;
}

export default function ImpactOverlays({ bbox, showRoads, showInfrastructure }: Props) {
  const map = useMap();
  const layersRef = useRef<L.Layer[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Cleanup previous layers
    layersRef.current.forEach(l => map.removeLayer(l));
    layersRef.current = [];

    if (!showRoads && !showInfrastructure) return;

    let cancelled = false;
    setLoading(true);

    const queries: Promise<void>[] = [];

    if (showRoads) {
      queries.push(
        fetch(OVERPASS_URL, {
          method: 'POST',
          body: `data=${encodeURIComponent(buildQuery(bbox, 'roads'))}`,
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
          .then(r => r.json())
          .then(data => {
            if (cancelled) return;
            const elements = data.elements || [];
            let added = 0;
            elements.forEach((el: Record<string, unknown>) => {
              if (el.type === 'way' && Array.isArray(el.geometry)) {
                const coords = (el.geometry as { lat: number; lon: number }[]).map(
                  p => [p.lat, p.lon] as [number, number]
                );
                const line = L.polyline(coords, { color: '#f97316', weight: 2, opacity: 0.7 });
                const tags = (el.tags || {}) as Record<string, string>;
                line.bindPopup(`<b>${tags.name || 'Road'}</b><br/>Type: ${tags.highway || 'unknown'}`);
                line.addTo(map);
                layersRef.current.push(line);
                added++;
              }
            });
            // B7 fix: inform the user if overlay returns zero results (silent failure → visible feedback)
            if (added === 0 && !cancelled) {
              toast.info('No major roads found in this region for overlay');
            }
          })
          .catch(() => {
            if (!cancelled) toast.error('Roads overlay failed — Overpass API unavailable');
          })
      );
    }

    if (showInfrastructure) {
      queries.push(
        fetch(OVERPASS_URL, {
          method: 'POST',
          body: `data=${encodeURIComponent(buildQuery(bbox, 'infra'))}`,
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        })
          .then(r => r.json())
          .then(data => {
            if (cancelled) return;
            const elements = data.elements || [];
            let added = 0;
            elements.forEach((el: Record<string, unknown>) => {
              if (el.type === 'node' && typeof el.lat === 'number' && typeof el.lon === 'number') {
                const tags = (el.tags || {}) as Record<string, string>;
                const isLift = !!tags.aerialway;
                const marker = L.circleMarker([el.lat as number, el.lon as number], {
                  radius: 6,
                  color: isLift ? '#a78bfa' : '#67e8f9',
                  fillColor: isLift ? '#a78bfa' : '#67e8f9',
                  fillOpacity: 0.8,
                  weight: 1,
                });
                marker.bindPopup(
                  `<b>${tags.name || (isLift ? 'Ski Lift' : 'Village')}</b><br/>Type: ${tags.aerialway || tags.place || 'unknown'}`
                );
                marker.addTo(map);
                layersRef.current.push(marker);
                added++;
              }
            });
            if (added === 0 && !cancelled) {
              toast.info('No villages or ski lifts found in this region');
            }
          })
          .catch(() => {
            if (!cancelled) toast.error('Villages/Lifts overlay failed — Overpass API unavailable');
          })
      );
    }

    Promise.all(queries).finally(() => { if (!cancelled) setLoading(false); });

    return () => {
      cancelled = true;
      layersRef.current.forEach(l => map.removeLayer(l));
      layersRef.current = [];
    };
  }, [map, bbox, showRoads, showInfrastructure]);

  return loading ? (
    <div className="absolute top-20 left-1/2 -translate-x-1/2 z-[1000] glass-panel rounded-full px-4 py-2 text-xs text-muted-foreground">
      Fetching impact data…
    </div>
  ) : null;
}
