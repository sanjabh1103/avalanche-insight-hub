import { LockKeyhole } from 'lucide-react';

export default function KnowledgeGraphUnavailable() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center px-6 py-16">
      <section
        className="max-w-xl rounded-3xl border border-border/70 bg-card/70 p-8 text-center shadow-2xl shadow-black/20 backdrop-blur-2xl"
        aria-labelledby="knowledge-graph-unavailable-title"
      >
        <LockKeyhole className="mx-auto h-10 w-10 text-amber-400" aria-hidden="true" />
        <h1 id="knowledge-graph-unavailable-title" className="mt-4 text-2xl font-semibold text-foreground">
          Local Knowledge Workspace
        </h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">
          This internal code knowledge graph is available only from the local development server.
          It is intentionally not bundled into the public build until the private snapshot,
          role, security, and customer-claim review gates are complete.
        </p>
        <p className="mt-4 rounded-xl bg-muted/50 px-4 py-3 text-xs text-muted-foreground">
          Start the app with <code className="rounded bg-background px-1.5 py-0.5 text-foreground">npm run dev</code>{' '}
          and open it from <code className="rounded bg-background px-1.5 py-0.5 text-foreground">localhost</code>.
          You also need <code className="rounded bg-background px-1.5 py-0.5 text-foreground">.env.local</code> —
          copy it from <code className="rounded bg-background px-1.5 py-0.5 text-foreground">.env.local.example</code>.
        </p>
      </section>
    </div>
  );
}
