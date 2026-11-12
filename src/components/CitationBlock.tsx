import { useState } from 'react';
import { Copy, Check, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface CitationBlockProps {
  citation: string;
  bibtex?: string;
  doi?: string;
}

export default function CitationBlock({ citation, bibtex, doi }: CitationBlockProps) {
  const [copied, setCopied] = useState(false);

  const copyBibtex = async () => {
    if (!bibtex) return;
    try {
      await navigator.clipboard.writeText(bibtex);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available
    }
  };

  return (
    <div className="rounded-xl border border-border/60 bg-secondary/20 px-4 py-3">
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="text-sm leading-relaxed text-foreground">{citation}</p>
          {doi && (
            <a
              href={`https://doi.org/${doi}`}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-1 inline-block text-xs text-emerald-400/80 hover:text-emerald-400 underline"
            >
              DOI: {doi}
            </a>
          )}
          {bibtex && (
            <div className="mt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={copyBibtex}
                className="h-7 gap-1.5 rounded-lg px-2 text-xs text-muted-foreground hover:text-foreground"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-emerald-400" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    Copy BibTeX
                  </>
                )}
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
