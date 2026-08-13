import {
  AUDIENCE_IDS,
  DEPTH_IDS,
  getAudienceProfile,
  getDepthProfile,
  normalizeAudience,
  normalizeDepth,
  type AudienceId,
  type DepthId,
} from '@/lib/knowledge-graph/audienceModel';

interface AudienceDepthControlsProps {
  audience: AudienceId;
  depth: DepthId;
  onAudienceChange: (value: AudienceId) => void;
  onDepthChange: (value: DepthId) => void;
}

export function AudienceDepthControls({
  audience,
  depth,
  onAudienceChange,
  onDepthChange,
}: AudienceDepthControlsProps) {
  return (
    <section
      className="mt-3 flex flex-wrap items-end gap-3 rounded-lg border border-border/70 bg-card/40 p-3"
      aria-label="Explanation audience and depth"
    >
      <div className="min-w-[180px] flex-1">
        <label htmlFor="knowledge-audience" className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Audience
        </label>
        <select
          id="knowledge-audience"
          value={audience}
          onChange={(event) => onAudienceChange(normalizeAudience(event.target.value))}
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
          aria-describedby="knowledge-audience-help"
        >
          {AUDIENCE_IDS.map((id) => (
            <option key={id} value={id}>
              {getAudienceProfile(id).label}
            </option>
          ))}
        </select>
      </div>

      <div className="min-w-[160px] flex-1">
        <label htmlFor="knowledge-depth" className="mb-1 block text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          Depth
        </label>
        <select
          id="knowledge-depth"
          value={depth}
          onChange={(event) => onDepthChange(normalizeDepth(event.target.value))}
          className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
          aria-describedby="knowledge-depth-help"
        >
          {DEPTH_IDS.map((id) => (
            <option key={id} value={id}>
              {getDepthProfile(id).label}
            </option>
          ))}
        </select>
      </div>

      <p id="knowledge-audience-help" className="sr-only">
        Audience changes the explanation emphasis. Depth changes how much deterministic evidence and caveat detail is shown.
      </p>
      <p id="knowledge-depth-help" className="sr-only">
        These controls affect only local deterministic explanations; they do not invoke a model or provide forecast advice.
      </p>
    </section>
  );
}
