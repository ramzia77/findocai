interface AnswerTextProps {
  text: string;
  citationCount: number;
  onCitationClick: (index: number) => void;
}

const MARKER_PATTERN = /(\[\d+\])/g;
const MARKER_CAPTURE = /^\[(\d+)\]$/;

// The backend guarantees bracket number n in the answer maps to
// citations[n-1] by construction (rag/chain.py numbers context in the same
// order citations are built), so this only needs to parse the marker text,
// not infer any meaning from it.
export function AnswerText({ text, citationCount, onCitationClick }: AnswerTextProps) {
  const parts = text.split(MARKER_PATTERN);

  return (
    <p className="whitespace-pre-wrap text-base leading-relaxed text-slate-800">
      {parts.map((part, i) => {
        const match = part.match(MARKER_CAPTURE);
        if (!match) return <span key={i}>{part}</span>;

        const index = parseInt(match[1], 10) - 1;
        const valid = index >= 0 && index < citationCount;
        return (
          <button
            key={i}
            disabled={!valid}
            onClick={() => onCitationClick(index)}
            className="mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-100 px-1 align-middle text-xs font-semibold text-brand-700 hover:bg-brand-200 disabled:cursor-default disabled:opacity-60"
          >
            {match[1]}
          </button>
        );
      })}
    </p>
  );
}
