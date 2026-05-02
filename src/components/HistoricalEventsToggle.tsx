import { Button } from '@/components/ui/button';
import { History, Loader2 } from 'lucide-react';

interface Props {
  visible: boolean;
  onToggle: () => void;
  loading?: boolean;
}

export default function HistoricalEventsToggle({ visible, onToggle, loading = false }: Props) {
  return (
    <Button
      variant="outline"
      size="sm"
      className={`h-9 text-xs font-semibold gap-2 glass-panel border-0 ${visible ? 'text-amber-400' : ''}`}
      onClick={onToggle}
      disabled={loading && !visible}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <History className="h-4 w-4" />}
      {visible ? 'HIDE' : 'SHOW'} EVENTS
    </Button>
  );
}
