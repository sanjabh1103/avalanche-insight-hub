import {
  Brain,
  FileCheck,
  FlaskConical,
  GitBranch,
  Network,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';

import type { PerspectiveId } from '@/lib/knowledge-graph/perspectives';
import { perspectives } from '@/lib/knowledge-graph/perspectives';

const ICONS: Record<string, LucideIcon> = {
  Network,
  Brain,
  GitBranch,
  ShieldCheck,
  FlaskConical,
  FileCheck,
};

interface PerspectiveSwitcherProps {
  activeId: PerspectiveId;
  onChange: (id: PerspectiveId) => void;
  nodeCounts: Record<PerspectiveId, number>;
}

export function PerspectiveSwitcher({ activeId, onChange, nodeCounts }: PerspectiveSwitcherProps) {
  const activeIndex = Math.max(0, perspectives.findIndex((perspective) => perspective.id === activeId));

  const moveFocus = (index: number) => {
    const nextIndex = (index + perspectives.length) % perspectives.length;
    const next = perspectives[nextIndex];
    onChange(next.id);
    window.requestAnimationFrame(() => {
      document.getElementById(`knowledge-perspective-${next.id}`)?.focus();
    });
  };

  return (
    <nav
      className="flex flex-wrap gap-2"
      aria-label="Graph perspective selector"
      role="tablist"
      onKeyDown={(event) => {
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
          event.preventDefault();
          moveFocus(activeIndex + 1);
        } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
          event.preventDefault();
          moveFocus(activeIndex - 1);
        } else if (event.key === 'Home') {
          event.preventDefault();
          moveFocus(0);
        } else if (event.key === 'End') {
          event.preventDefault();
          moveFocus(perspectives.length - 1);
        }
      }}
    >
      {perspectives.map((perspective) => {
        const Icon = ICONS[perspective.icon] || Network;
        const isActive = perspective.id === activeId;
        const count = nodeCounts[perspective.id] ?? 0;
        return (
          <button
            key={perspective.id}
            id={`knowledge-perspective-${perspective.id}`}
            type="button"
            role="tab"
            tabIndex={isActive ? 0 : -1}
            aria-selected={isActive}
            aria-controls="knowledge-graph-panel"
            aria-label={`${perspective.label}: ${count} nodes`}
            onClick={() => onChange(perspective.id)}
            className={`group flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/70 ${
              isActive
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border bg-card/50 text-muted-foreground hover:border-primary/50 hover:text-foreground'
            }`}
          >
            <Icon className="h-4 w-4" aria-hidden="true" />
            <span className="font-medium">{perspective.label}</span>
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] tabular-nums ${
                isActive ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
              }`}
            >
              {count}
            </span>
          </button>
        );
      })}
    </nav>
  );
}
