import { RISK_COLORS, RISK_LABELS } from '@/lib/constants';

export default function RiskLegend() {
  return (
    <div className="glass-panel rounded-2xl p-3 space-y-1.5">
      <div className="text-[10px] text-muted-foreground uppercase tracking-[0.24em] mb-2">
        Avalanche Danger
      </div>
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
    </div>
  );
}
