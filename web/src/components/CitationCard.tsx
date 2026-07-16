import { FileText } from "lucide-react";
import { useState } from "react";
import type { Citation } from "../api/types";
import { Badge } from "./ui/Badge";
import { Card, CardBody } from "./ui/Card";

const SNIPPET_PREVIEW_LENGTH = 240;

interface CitationCardProps {
  citation: Citation;
  index: number;
  highlighted: boolean;
}

export function CitationCard({ citation, index, highlighted }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);
  const { source, snippet } = citation;
  const isLong = snippet.length > SNIPPET_PREVIEW_LENGTH;
  const shownSnippet = expanded || !isLong ? snippet : `${snippet.slice(0, SNIPPET_PREVIEW_LENGTH)}...`;

  return (
    <Card
      id={`citation-${index}`}
      className={`scroll-mt-24 transition-shadow ${highlighted ? "ring-2 ring-brand-400" : ""}`}
    >
      <CardBody>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700">
            {index + 1}
          </span>
          <span className="flex items-center gap-1 text-sm font-medium text-slate-800">
            <FileText className="h-3.5 w-3.5 text-slate-400" />
            {source.filename}
          </span>
          <Badge tone="neutral">page {source.page_number}</Badge>
          {source.section && <Badge tone="brand">{source.section}</Badge>}
        </div>

        <p className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-slate-600">
          {shownSnippet}
        </p>
        {isLong && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="mt-1 text-xs font-medium text-brand-600 hover:text-brand-700"
          >
            {expanded ? "Show less" : "Show more"}
          </button>
        )}

        <p className="mt-2 text-xs text-slate-400">{source.chunk_id}</p>
      </CardBody>
    </Card>
  );
}
