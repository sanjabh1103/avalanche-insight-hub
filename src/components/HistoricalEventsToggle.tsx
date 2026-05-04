import { Button } from '@/components/ui/button';
import { History, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface Props {
  visible: boolean;
  onToggle: () => void;
  loading?: boolean;
  className?: string;
}

export default function HistoricalEventsToggle({ visible, onToggle, loading = false, className }: Props) {
  return (
    <Button
      variant="outline"
      size="sm"
      className={cn('h-10 text-xs font-semibold gap-2 glass-panel border-0 rounded-2xl px-3 sm:px-4', visible ? 'text-amber-400' : '', className)}
      onClick={onToggle}
      disabled={loading && !visible}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <History className="h-4 w-4" />}
      {visible ? 'HIDE' : 'SHOW'} EVENTS
    </Button>
  );
}
