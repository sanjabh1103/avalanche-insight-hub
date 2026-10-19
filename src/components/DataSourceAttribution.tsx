import { ExternalLink } from 'lucide-react';

interface DataSource {
  name: string;
  url: string;
}

interface DataSourceAttributionProps {
  sources: DataSource[];
  className?: string;
}

export default function DataSourceAttribution({ sources, className }: DataSourceAttributionProps) {
  return (
    <div className={`flex flex-wrap gap-2 ${className ?? ''}`}>
      {sources.map((source) => (
        <a
          key={source.name}
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-lg border border-border/50 bg-secondary/30 px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-emerald-500/30 hover:text-foreground"
        >
          <ExternalLink className="h-3 w-3 shrink-0" />
          {source.name}
        </a>
      ))}
    </div>
  );
}
