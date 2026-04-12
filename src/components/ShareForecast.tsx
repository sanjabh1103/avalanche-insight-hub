import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Share2, Check } from 'lucide-react';
import { toast } from 'sonner';
import type { GridCell } from '@/lib/gridUtils';
import type { Region } from '@/components/RegionSelector';

interface Props {
  forecastId?: string;
  region?: Region;
  hour?: number;
  selectedCell?: GridCell | null;
  expertMode?: boolean;
}

export default function ShareForecast({ forecastId, region, hour = 0, selectedCell, expertMode }: Props) {
  const [copied, setCopied] = useState(false);

  const handleShare = async () => {
    const params = new URLSearchParams();
    
    // Always include region
    if (region) {
      params.set('region', region.name);
      params.set('bbox', region.bbox.join(','));
    }
    
    // Include hour
    params.set('hour', String(hour));
    
    // Include forecast ID if available
    if (forecastId) {
      params.set('forecast', forecastId);
    }
    
    // Include selected cell if available
    if (selectedCell) {
      params.set('cell', `${selectedCell.row},${selectedCell.col}`);
    }
    if (expertMode) params.set('expert', '1');
    
    const url = `${window.location.origin}?${params.toString()}`;
    
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast.success('Full-state forecast link copied — restores region, hour, and selected cell');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.info(url);
    }
  };

  return (
    <Button
      variant="outline"
      className="h-9 text-xs font-semibold gap-2 glass-panel border-0"
      onClick={handleShare}
    >
      {copied ? <Check className="h-4 w-4 text-green-400" /> : <Share2 className="h-4 w-4" />}
      SHARE
    </Button>
  );
}
