import { FileText, ScrollText } from "lucide-react";
import { useState } from "react";
import type { Citation } from "../api/types";
import { Badge } from "./ui/Badge";
import { Card, CardBody } from "./ui/Card";

const SNIPPET_PREVIEW_LENGTH = 240;

interface CitationCardProps {
  citation: Citation;
  index: number;
  highlighted: boolean;
  onViewInAudit?: () => void;
}

export function CitationCard({ citation, index, highlighted, onViewInAudit }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { source, snippet } = citation;
  const isLong = snippet.length > SNIPPET_PREVIEW_LENGTH;
  const shownSnippet = expanded || !isLong ? snippet : `${snippet.slice(0, SNIPPET_PREVIEW_LENGTH)}...`;

  return (
    <Card
      id={`citation-${index}`}
      className={`scroll-mt-24 transition-shadow ${highlighted ? "ring-2 ring-accent-400" : ""}`}
    >
      <CardBody>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-zinc-900 text-xs font-semibold text-white">
            {index + 1}
          </span>
          <span className="flex items-center gap-1 text-sm font-medium text-zinc-800">
            <FileText className="h-3.5 w-3.5 text-zinc-400" />
            {source.filename}
          </span>
          <Badge tone="neutral">page {source.page_number}</Badge>
          {source.section && <Badge tone="accent">{source.section}</Badge>}
        </div>

        <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-zinc-600">
          {shownSnippet}
        </p>

        <div className="mt-2 flex items-center gap-3">
          {isLong && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="text-xs font-medium text-zinc-500 hover:text-zinc-900"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
          {onViewInAudit && (
            <button
              onClick={onViewInAudit}
              className="flex items-center gap-1 text-xs font-medium text-zinc-400 hover:text-zinc-900"
            >
              <ScrollText className="h-3 w-3" />
              View in Audit Trail
            </button>
          )}
        </div>
      </CardBody>
    </Card>
  );
}
