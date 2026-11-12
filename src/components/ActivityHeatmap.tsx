import { useEffect } from 'react';
import { useMap } from 'react-leaflet';
import type { AvalancheEvent } from '@/lib/avalancheEvents';
import L from 'leaflet';
import 'leaflet.heat';

interface Props {
  events: AvalancheEvent[];
  visible: boolean;
}

export default function ActivityHeatmap({ events, visible }: Props) {
  const map = useMap();

  useEffect(() => {
    if (!visible || events.length === 0) return;

    const now = Date.now();
    const points: [number, number, number][] = events
      .filter(e => e.lat !== 0 && e.lng !== 0)
      .map(e => {
        const age = (now - new Date(e.timestamp).getTime()) / (1000 * 60 * 60 * 24);
        const recency = Math.max(0.2, 1 - age / 365);
        return [e.lat, e.lng, recency * (e.severity || 3) / 5] as [number, number, number];
      });

    const heat = (L as unknown as { heatLayer: (pts: [number, number, number][], opts: Record<string, unknown>) => L.Layer }).heatLayer(points, {
      radius: 25,
      blur: 15,
      maxZoom: 12,
      max: 1,
      gradient: { 0.2: '#22c55e', 0.4: '#84cc16', 0.6: '#eab308', 0.8: '#f97316', 1.0: '#ef4444' },
    });

    heat.addTo(map);
    return () => { map.removeLayer(heat); };
  }, [map, events, visible]);

  return null;
}
