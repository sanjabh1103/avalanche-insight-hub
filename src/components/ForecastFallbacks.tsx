import { Loader2 } from 'lucide-react';

export function ShellLoadingNotice({
  label,
  className = '',
}: {
  label: string;
  className?: string;
}) {
  return (
    <div className={`rounded-[1.35rem] border border-border/70 bg-card/70 px-4 py-3 shadow-2xl shadow-black/20 backdrop-blur-2xl ${className}`}>
      <div className="flex items-center gap-3 text-xs uppercase tracking-[0.2em] text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin text-emerald-400" />
        <span>{label}</span>
      </div>
    </div>
  );
}

export function MapSurfaceFallback() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-[radial-gradient(circle_at_top_left,_hsl(156_74%_45%_/_0.14),_transparent_28%),linear-gradient(180deg,hsl(224_28%_8%),hsl(224_24%_6%))] px-4">
      <ShellLoadingNotice label="Loading map surface" className="w-full max-w-sm text-center" />
    </div>
  );
}

export function ExpertPanelFallback() {
  return (
    <div className="fixed right-0 top-0 bottom-0 z-40 flex h-full w-[min(23rem,calc(100vw-0.75rem))] flex-col border-l border-border/80 bg-card/95 p-4 shadow-2xl shadow-black/40 backdrop-blur-2xl md:absolute">
      <ShellLoadingNotice label="Loading expert panel" />
    </div>
  );
}

export function ModalFallback({ label }: { label: string }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
      <ShellLoadingNotice label={label} className="w-full max-w-md" />
    </div>
  );
}
