import { RISK_COLORS, RISK_LABELS } from '@/lib/constants';
import { cn } from '@/lib/utils';

export default function RiskLegend({ compact = false, className }: { compact?: boolean; className?: string }) {
  return (
    <div className={cn('glass-panel rounded-2xl p-3', compact ? 'space-y-2' : 'space-y-1.5', className)}>
      <div className="mb-2 text-[10px] text-muted-foreground uppercase tracking-[0.24em]">
        Avalanche Danger
      </div>
      <div className={cn(compact ? 'grid grid-cols-2 gap-2 sm:grid-cols-3' : 'space-y-1.5')}>
        {[1, 2, 3, 4, 5].map((level) => (
          <div key={level} className="flex items-center gap-2">
            <div
              className="h-3 w-6 rounded-sm"
              style={{ backgroundColor: RISK_COLORS[level] }}
            />
            <span className="text-[11px] text-foreground font-mono">
              {level} — {RISK_LABELS[level]}
            </span>
          </div>
        ))}
        <div className="flex items-center gap-2">
          <div
            className="h-3 w-6 rounded-sm bg-slate-500"
          />
          <span className="text-[11px] text-foreground font-mono">
            Masked terrain
          </span>
        </div>
      </div>
    </div>
  );
}
