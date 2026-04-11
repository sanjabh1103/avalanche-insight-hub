import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { History } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';

export interface AvalancheEvent {
  id: string;
  lat: number;
  lng: number;
  severity: number;
  confidence: number;
  description: string;
  source: string;
  event_type: string;
  timestamp: string;
}

interface Props {
  visible: boolean;
  onToggle: () => void;
  onEventsLoaded: (events: AvalancheEvent[]) => void;
  bbox: [number, number, number, number];
}

export default function HistoricalEventsToggle({ visible, onToggle, onEventsLoaded, bbox }: Props) {
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!visible) {
      onEventsLoaded([]);
      return;
    }
    setLoading(true);
    supabase
      .from('avalanche_events')
      .select('*')
      .order('timestamp', { ascending: false })
      .limit(50)
      .then(({ data }) => {
        if (data) {
          const events: AvalancheEvent[] = data.map((e: unknown) => {
            const event = e as Record<string, unknown>;
            // Parse PostGIS POINT
            let lat = 0, lng = 0;
            const location = event.location;
            if (typeof location === 'string') {
              const m = location.match(/POINT\(([-\d.]+)\s+([-\d.]+)\)/);
              if (m) { lng = parseFloat(m[1]); lat = parseFloat(m[2]); }
            } else if (location && typeof location === 'object') {
              // GeoJSON
              const coords = (location as { coordinates?: number[] }).coordinates;
              if (coords) { lng = coords[0]; lat = coords[1]; }
            }
            return {
              id: String(event.id || ''),
              lat, lng,
              severity: Number(event.severity) || 3,
              confidence: Number(event.confidence) || 0.5,
              description: String(event.description || ''),
              source: String(event.source || 'unknown'),
              event_type: String(event.event_type || 'unknown'),
              timestamp: String(event.timestamp || ''),
            };
          });
          onEventsLoaded(events);
        }
        setLoading(false);
      });
  }, [visible, bbox]);

  return (
    <Button
      variant="outline"
      size="sm"
      className={`h-9 text-xs font-semibold gap-2 glass-panel border-0 ${visible ? 'text-amber-400' : ''}`}
      onClick={onToggle}
      disabled={loading}
    >
      <History className="h-4 w-4" />
      {visible ? 'HIDE' : 'SHOW'} EVENTS
    </Button>
  );
}
