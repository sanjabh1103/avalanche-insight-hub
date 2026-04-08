import { useState, useEffect } from 'react';
import { Badge } from '@/components/ui/badge';
import { BrainCircuit } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';

export default function ModelStatusBadge() {
  const [status, setStatus] = useState<{ version: string; f1_score: number } | null>(null);

  useEffect(() => {
    supabase
      .from('model_status')
      .select('version, f1_score')
      .limit(1)
      .single()
      .then(({ data }) => {
        if (data) setStatus(data as unknown as { version: string; f1_score: number });
      });
  }, []);

  if (!status) return null;

  return (
    <Badge variant="outline" className="gap-1.5 border-green-500/30 text-green-400 text-xs font-mono">
      <BrainCircuit className="h-3 w-3" />
      {status.version} • F1 {status.f1_score.toFixed(2)}
    </Badge>
  );
}
