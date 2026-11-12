import { AlertTriangle } from 'lucide-react';

export default function DisclaimerBanner() {
  return (
    <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 flex items-center gap-2 z-50 backdrop-blur-sm">
      <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-400" />
      <span className="text-amber-400 text-[11px] leading-tight">
        <strong>Experimental AI system</strong> — Not for life-critical decisions. Use official avalanche centers where available.
      </span>
    </div>
  );
}
