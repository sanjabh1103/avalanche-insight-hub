import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Share2, Check } from 'lucide-react';
import { toast } from 'sonner';
import type { GridCell } from '@/lib/gridUtils';
import type { Region } from '@/components/RegionSelector';
import { cn } from '@/lib/utils';

interface Props {
  forecastId?: string;
  region?: Region;
  hour?: number;
  selectedCell?: GridCell | null;
  expertMode?: boolean;
  show3D?: boolean;
  className?: string;
}

export default function ShareForecast({ forecastId, region, hour = 0, selectedCell, expertMode, show3D, className }: Props) {
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
    // B10 fix: Include expert mode and 3D view state in URL
    if (expertMode) params.set('expert', '1');
    if (show3D) params.set('3d', '1');

    const url = `${window.location.origin}?${params.toString()}`;

    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast.success('Full-state forecast link copied - restores region, hour, expert mode, and 3D view');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // B10 fix: clipboard API blocked (e.g. non-HTTPS or permissions denied) -
      // show error toast with manual copy option
      toast.error('Could not auto-copy link. Please copy manually.', { duration: 5000 });
      // Also show the URL in a toast so the user can copy it manually
      toast.info(`Copy this link: ${url}`, { duration: 15000 });
    }

  };

  return (
    <Button
      variant="outline"
      className={cn('h-10 text-xs font-semibold gap-2 glass-panel border-0 rounded-2xl px-3 sm:px-4', className)}
      onClick={handleShare}
    >
      {copied ? <Check className="h-4 w-4 text-green-400" /> : <Share2 className="h-4 w-4" />}
      SHARE
    </Button>
  );
}
