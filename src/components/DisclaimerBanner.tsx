import { AlertTriangle, X } from 'lucide-react';
import { useState } from 'react';

export default function DisclaimerBanner() {
  const [visible, setVisible] = useState(true);
  if (!visible) return null;

  return (
    <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 flex items-center justify-between gap-3 z-50">
      <div className="flex items-center gap-2 text-amber-400 text-[11px] leading-tight">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
        <span>
          <strong>Experimental AI system</strong> — Not for life-critical decisions. Use official avalanche centers where available.
        </span>
      </div>
      <button onClick={() => setVisible(false)} className="text-amber-400/60 hover:text-amber-400 shrink-0">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
