import { useState, useEffect } from 'react';
import { Badge } from '@/components/ui/badge';
import { BrainCircuit } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';
import { useRealtimeSubscription } from '@/hooks/useRealtimeSubscription';

interface ModelInfo {
  version: string;
  f1_score: number;
  last_inference: string | null;
  data_freshness_hours: number;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return 'never';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function ModelStatusBadge() {
  const [status, setStatus] = useState<ModelInfo | null>(null);

  const loadStatus = async () => {
    const { data } = await supabase
      .from('model_status')
      .select('version, f1_score, last_inference, data_freshness_hours')
      .limit(1)
      .single();
    if (data) setStatus(data as unknown as ModelInfo);
  };

  useEffect(() => { loadStatus(); }, []);

  // Realtime sync with model_status table (BUG-11 fix)
  useRealtimeSubscription('model_status', () => { loadStatus(); });

  if (!status) return null;

  return (
    <div className="flex flex-col gap-1">
      <Badge variant="outline" className="gap-1.5 border-green-500/30 text-green-400 text-xs font-mono w-fit">
        <BrainCircuit className="h-3 w-3" />
        {status.version} • F1 {status.f1_score?.toFixed(2) ?? '—'}
      </Badge>
      <span className="text-[9px] text-muted-foreground font-mono pl-0.5">
        Last inference: {timeAgo(status.last_inference)} • Freshness: {status.data_freshness_hours < 999 ? `${status.data_freshness_hours.toFixed(0)}h` : 'sim'}
      </span>
    </div>
  );
}
