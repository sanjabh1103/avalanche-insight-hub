import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Share2, Check } from 'lucide-react';
import { toast } from 'sonner';

interface Props {
  forecastId?: string;
}

export default function ShareForecast({ forecastId }: Props) {
  const [copied, setCopied] = useState(false);

  const handleShare = async () => {
    const url = forecastId
      ? `${window.location.origin}?forecast=${forecastId}`
      : window.location.href;
    
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast.success('Forecast link copied to clipboard');
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
