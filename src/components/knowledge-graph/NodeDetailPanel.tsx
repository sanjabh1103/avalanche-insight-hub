import { useEffect, useState, useCallback } from 'react';
import { Loader2, FileText, ExternalLink, AlertCircle, Sparkles, Send } from 'lucide-react';

import type { GraphFreshness, GraphNode } from '@/lib/knowledge-graph/graphData';
import type { AudienceId, DepthId } from '@/lib/knowledge-graph/audienceModel';
import type { PerspectiveId } from '@/lib/knowledge-graph/perspectives';
import { getPerspective, perspectives } from '@/lib/knowledge-graph/perspectives';
import { AUDIENCE_IDS, DEPTH_IDS } from '@/lib/knowledge-graph/audienceModel';
import {
  generateExplanation,
  type NodeExplanation,
} from '@/lib/knowledge-graph/explainer';
import {
  fetchModelExplanation,
  isModelError,
  type ModelExplanationResponse,
} from '@/lib/knowledge-graph/explainerApi';

// G5: Module-level in-memory cache for AI responses.
// Key: `${nodeId}|${perspective}|${question}|${audience}|${depth}`
// Value: NodeExplanation. Cache persists across node selections and re-renders.
const aiResponseCache = new Map<string, NodeExplanation>();
const AI_CACHE_MAX_ENTRIES = 50;

interface NodeDetailPanelProps {
  node: GraphNode | null;
  perspective: PerspectiveId;
  audience?: AudienceId;
  depth?: DepthId;
  snapshotId?: string | null;
  graphHash?: string | null;
  graphFreshness?: GraphFreshness;
  onClose: () => void;
  // G6: aiMode is now controlled by parent for persistence across node selections
  aiMode?: boolean;
  onAiModeChange?: (mode: boolean) => void;
}

export function NodeDetailPanel({
  node,
  perspective,
  audience = 'novice',
  depth = 'briefing',
  snapshotId = null,
  graphHash = null,
  graphFreshness = 'unknown',
  onClose,
  aiMode: externalAiMode,
  onAiModeChange,
}: NodeDetailPanelProps) {
  const [explanation, setExplanation] = useState<NodeExplanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  // G6: Use external state if provided, otherwise internal state
  const [internalAiMode, setInternalAiMode] = useState(false);
  const aiMode = externalAiMode ?? internalAiMode;
  const setAiMode = useCallback((mode: boolean | ((prev: boolean) => boolean)) => {
    const next = typeof mode === 'function' ? mode(aiMode) : mode;
    if (onAiModeChange) {
      onAiModeChange(next);
    } else {
      setInternalAiMode(next);
    }
  }, [aiMode, onAiModeChange]);
  const [question, setQuestion] = useState('');
  const [aiWarning, setAiWarning] = useState<string | null>(null);

  const loadDeterministic = useCallback(() => {
    if (!node) {
      setExplanation(null);
      return;
    }
    setLoading(true);
    setError(null);
    setAiWarning(null);
    generateExplanation(node, perspective, {
      audience,
      depth,
      snapshotId,
      graphHash,
      graphFreshness,
    })
      .then((result) => {
        setExplanation(result);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to generate explanation');
        setLoading(false);
      });
  }, [audience, depth, graphFreshness, graphHash, node, perspective, snapshotId]);

  const loadAiExplanation = useCallback(
    (q?: string) => {
      if (!node) {
        setExplanation(null);
        return;
      }
      // G5: Check client-side cache before making API call
      const cacheKey = `${node.id}|${perspective}|${q || ''}|${audience}|${depth}`;
      const cached = aiResponseCache.get(cacheKey);
      if (cached) {
        setExplanation(cached);
        setLoading(false);
        setAiWarning(null);
        return;
      }
      setLoading(true);
      setError(null);
      setAiWarning(null);
      fetchModelExplanation({
        nodeId: node.id,
        perspective,
        question: q || undefined,
        context: {
          audience,
          depth,
          includeSource: true,
          maxDepth: depth === 'deep' ? 3 : depth === 'working' ? 2 : 1,
        },
      })
        .then((result) => {
          if (isModelError(result)) {
            // Model endpoint returned an error — fall back to deterministic
            setAiWarning(
              result.retryAfter
                ? `AI mode unavailable (rate limited, retry in ${result.retryAfter}s). Showing rule-based explanation.`
                : `AI mode unavailable (${result.error}). Showing rule-based explanation.`,
            );
            setAiMode(false);
            loadDeterministic();
            return;
          }
          const mapped = mapModelResponse(result, node);
          // G5: Store in client-side cache with LRU eviction
          const cacheKey = `${node.id}|${perspective}|${q || ''}|${audience}|${depth}`;
          if (aiResponseCache.size >= AI_CACHE_MAX_ENTRIES) {
            // Evict oldest entry (first key in insertion order)
            const firstKey = aiResponseCache.keys().next().value;
            if (firstKey) aiResponseCache.delete(firstKey);
          }
          aiResponseCache.set(cacheKey, mapped);
          setExplanation(mapped);
          setLoading(false);
        })
        .catch((err) => {
          // Network or auth error — fall back to deterministic
          setAiWarning(
            `AI endpoint unreachable (${err instanceof Error ? err.message : 'unknown error'}). Showing rule-based explanation.`,
          );
          setAiMode(false);
          loadDeterministic();
        });
    },
    [audience, depth, node, perspective, loadDeterministic, setAiMode],
  );

  useEffect(() => {
    if (aiMode) {
      loadAiExplanation(question || undefined);
    } else {
      loadDeterministic();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audience, depth, graphFreshness, graphHash, node, perspective, snapshotId, aiMode]);

  if (!node) {
    return (
      <aside
        className="flex h-full w-full flex-col items-center justify-center gap-3 p-6 text-muted-foreground"
        aria-label="Node detail panel"
      >
        <FileText className="h-8 w-8 opacity-40" aria-hidden="true" />
        <p className="text-center text-sm">
          Click any node in the graph to see a dynamic explanation.
          <br />
          Switch perspectives above to change how nodes are interpreted.
        </p>
      </aside>
    );
  }

  const perspectiveMeta = getPerspective(perspective);

  return (
    <aside
      className="flex h-full w-full flex-col overflow-hidden border-l border-border bg-card/50"
      aria-label={`Detail panel for ${node.name}`}
      role="complementary"
    >
      <header className="flex items-start justify-between gap-2 border-b border-border p-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-primary">
              {node.type}
            </span>
            {node.filePath && (
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard?.writeText(node.filePath || '').then(() => setCopied(true));
                }}
                className="max-w-[240px] truncate rounded px-1 text-left text-[10px] text-muted-foreground underline-offset-2 hover:bg-muted hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
                title="Copy source path"
                aria-label={`Copy source path ${node.filePath}`}
              >
                {copied ? 'Copied' : node.filePath}
              </button>
            )}
          </div>
          <h2 className="mt-1 truncate text-lg font-semibold text-foreground">{node.name}</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Explained via {perspectiveMeta.label} perspective
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Close detail panel"
        >
          ✕
        </button>
      </header>

      <div className="border-b border-border bg-muted/30 px-4 py-2.5">
        <div className="flex items-center justify-between gap-2">
          <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer select-none">
            <button
              type="button"
              role="switch"
              aria-checked={aiMode}
              onClick={() => setAiMode((prev) => !prev)}
              onKeyDown={(e) => {
                if (e.key === ' ' || e.key === 'Enter') {
                  e.preventDefault();
                  setAiMode((prev) => !prev);
                }
              }}
              className={`relative inline-flex h-4 w-7 flex-shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 ${
                aiMode ? 'bg-primary' : 'bg-muted-foreground/30'
              }`}
              aria-label="Toggle AI explanations"
            >
              <span
                className={`inline-block h-3 w-3 transform rounded-full bg-background shadow transition-transform ${
                  aiMode ? 'translate-x-3.5' : 'translate-x-0.5'
                }`}
              />
            </button>
            <span className="flex items-center gap-1">
              <Sparkles className="h-3 w-3" aria-hidden="true" />
              Use AI explanations
            </span>
          </label>
          <span className="text-[10px] text-muted-foreground">
            {aiMode ? 'Gemini-powered' : 'Rule-based'}
          </span>
        </div>

        {aiMode && (
          <form
            className="mt-2 flex gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              loadAiExplanation(question || undefined);
            }}
          >
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about this node (optional)..."
              className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/70"
              aria-label="Question for AI explanation"
              maxLength={2000}
            />
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-xs text-primary-foreground hover:bg-primary/90 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70"
              aria-label="Send question to AI"
            >
              <Send className="h-3 w-3" aria-hidden="true" />
              Ask
            </button>
          </form>
        )}

        {aiWarning && (
          <div className="mt-2 flex items-start gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-[10px] text-amber-600 dark:text-amber-400">
            <AlertCircle className="h-3 w-3 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <span>{aiWarning}</span>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {loading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span>{aiMode ? 'Asking Gemini...' : 'Generating explanation...'}</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        {explanation && !loading && !error && (
          <div className="space-y-5">
            {explanation.sections.map((section, i) => (
              <section key={i} className="space-y-1.5">
                <h3 className="text-sm font-semibold text-foreground">{section.heading}</h3>
                <div
                  className="prose prose-sm prose-invert max-w-none text-sm leading-relaxed text-muted-foreground
                             prose-code:rounded prose-code:bg-muted prose-code:px-1 prose-code:py-0.5 prose-code:text-xs
                             prose-pre:overflow-x-auto prose-pre:rounded-lg prose-pre:bg-muted/50 prose-pre:p-3
                             prose-strong:text-foreground prose-a:text-primary"
                >
                  <MarkdownLite text={section.body} />
                </div>
                {section.sourceRefs && section.sourceRefs.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1">
                    {section.sourceRefs.map((ref) => (
                      <span
                        key={ref}
                        className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
                      >
                        <ExternalLink className="h-2.5 w-2.5" aria-hidden="true" />
                        {ref}
                      </span>
                    ))}
                  </div>
                )}
              </section>
            ))}
            <div className="rounded-md border border-border/70 bg-muted/30 px-2 py-1.5 text-[10px] text-muted-foreground" role="status">
              Audience: {explanation.audience} · Depth: {explanation.depth} · Evidence: {explanation.evidenceSummary.proofLevel}
            </div>
            <footer className="border-t border-border pt-3 text-[10px] text-muted-foreground">
              Generated at {new Date(explanation.generatedAt).toLocaleTimeString()} ·{' '}
              {aiMode ? (
                <span className="inline-flex items-center gap-0.5">
                  <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
                  Gemini-powered
                </span>
              ) : (
                'Rule-based, no LLM'
              )}
            </footer>
          </div>
        )}
      </div>
    </aside>
  );
}

/**
 * Maps a ModelExplanationResponse from the edge function to the NodeExplanation
 * shape that the UI expects. The model endpoint returns sections with a slightly
 * different structure (no StructuredClaim objects), so we adapt them here.
 */
// G10: Runtime validators for API response fields — safe fallbacks for invalid values.
const VALID_PERSPECTIVE_IDS = perspectives.map((p) => p.id);
function validatePerspective(value: string): PerspectiveId {
  return (VALID_PERSPECTIVE_IDS as readonly string[]).includes(value) ? value as PerspectiveId : 'architecture';
}
function validateAudience(value: string): AudienceId {
  return (AUDIENCE_IDS as readonly string[]).includes(value) ? value as AudienceId : 'novice';
}
function validateDepth(value: string): DepthId {
  return (DEPTH_IDS as readonly string[]).includes(value) ? value as DepthId : 'briefing';
}

function mapModelResponse(
  response: ModelExplanationResponse,
  node: GraphNode,
): NodeExplanation {
  const graphHash = response.provenance.graphHash;
  const proofLevel: 'snapshot-linked' | 'unverified' = graphHash ? 'snapshot-linked' : 'unverified';
  const evidenceRefs = graphHash
    ? [graphHash]
    : node.filePath
      ? [node.filePath]
      : [`graph:${node.id}`];

  return {
    nodeId: response.explanation.nodeId || node.id,
    nodeName: node.name,
    nodeType: node.type,
    perspective: validatePerspective(response.explanation.perspective),
    audience: validateAudience(response.explanation.audience),
    depth: validateDepth(response.explanation.depth),
    audienceLens: {
      audience: response.explanation.audience as AudienceId,
      depth: response.explanation.depth as DepthId,
      perspective: response.explanation.perspective,
      requiredSections: [],
      claims: [],
      snapshotId: null,
      graphHash,
      proofLevel,
    },
    evidenceSummary: {
      proofLevel,
      snapshotId: null,
      graphHash,
      evidenceRefs,
    },
    sections: response.explanation.sections.map((section) => ({
      heading: section.heading,
      body: section.body,
      sourceRefs: evidenceRefs,
      claimCategory: section.claimCategory,
      claim: {
        text: section.body,
        category: section.claimCategory,
        evidenceRefs,
        snapshotId: null,
        graphHash,
        proofLevel,
      },
      claims: [],
    })),
    generatedAt: response.timestamp,
  };
}

/**
 * Lightweight markdown renderer for the explainer output.
 * Supports: bold, code blocks, inline code, bullet lists, paragraphs.
 * Avoids a full markdown dependency for the graph page bundle.
 */
function MarkdownLite({ text }: { text: string }) {
  const blocks = text.split(/```/);
  return (
    <>
      {blocks.map((block, i) => {
        if (i % 2 === 1) {
          const lines = block.split('\n');
          const lang = lines[0].trim();
          const code = lines.slice(1).join('\n').trim();
          return (
            <pre key={i} className="overflow-x-auto rounded-lg bg-muted/50 p-3 text-xs">
              <code className={`language-${lang}`}>{code}</code>
            </pre>
          );
        }
        return <InlineMarkdown key={i} text={block} />;
      })}
    </>
  );
}

function InlineMarkdown({ text }: { text: string }) {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let listItems: string[] = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="ml-4 list-disc space-y-0.5">
          {listItems.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(item) }} />
          ))}
        </ul>,
      );
      listItems = [];
    }
  };

  for (const line of lines) {
    if (line.trim().startsWith('- ')) {
      listItems.push(line.trim().slice(2));
    } else if (line.trim() === '') {
      flushList();
    } else {
      flushList();
      elements.push(
        <p key={`p-${elements.length}`} dangerouslySetInnerHTML={{ __html: inlineFormat(line) }} />,
      );
    }
  }
  flushList();

  return <>{elements}</>;
}

function inlineFormat(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>');
}
