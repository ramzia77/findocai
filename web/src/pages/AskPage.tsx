import { Send } from "lucide-react";
import { useState } from "react";
import { askQuestion } from "../api/client";
import { DOC_TYPES, DocType, QueryResponse } from "../api/types";
import { AnswerText } from "../components/AnswerText";
import { CitationCard } from "../components/CitationCard";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Spinner } from "../components/ui/Spinner";
import { TextArea } from "../components/ui/TextArea";
import { useSettings } from "../context/SettingsContext";
import { useToast } from "../context/ToastContext";

export function AskPage() {
  const { apiBaseUrl, apiKey } = useSettings();
  const toast = useToast();

  const [question, setQuestion] = useState("");
  const [docTypeFilter, setDocTypeFilter] = useState<DocType | "">("");
  const [topK, setTopK] = useState(5);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [highlighted, setHighlighted] = useState<number | null>(null);

  function scrollToCitation(index: number) {
    setHighlighted(index);
    document.getElementById(`citation-${index}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(() => setHighlighted((current) => (current === index ? null : current)), 2000);
  }

  async function handleAsk() {
    if (!question.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const response = await askQuestion(
        { baseUrl: apiBaseUrl, apiKey },
        question.trim(),
        docTypeFilter || null,
        topK,
      );
      setResult(response);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-slate-900">Ask a question</h2>
          <p className="text-sm text-slate-500">Answers are grounded in ingested documents, with citations.</p>
        </CardHeader>
        <CardBody className="space-y-4">
          <TextArea
            rows={3}
            placeholder="e.g. What is the interest rate on the loan?"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Document type filter</label>
              <Select value={docTypeFilter} onChange={(e) => setDocTypeFilter(e.target.value as DocType | "")}>
                <option value="">All types</option>
                {DOC_TYPES.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">Top-K results</label>
              <Input
                type="number"
                min={1}
                max={20}
                value={topK}
                onChange={(e) => setTopK(Number(e.target.value) || 1)}
              />
            </div>
          </div>

          <Button onClick={handleAsk} disabled={!question.trim() || loading}>
            {loading ? <Spinner /> : <Send className="h-4 w-4" />}
            {loading ? "Thinking..." : "Ask"}
          </Button>
        </CardBody>
      </Card>

      {result && (
        <>
          <Card>
            <CardHeader>
              <h2 className="text-sm font-semibold text-slate-900">Answer</h2>
            </CardHeader>
            <CardBody>
              <AnswerText
                text={result.answer}
                citationCount={result.citations.length}
                onCitationClick={scrollToCitation}
              />
            </CardBody>
          </Card>

          <div>
            <h2 className="mb-3 text-sm font-semibold text-slate-900">
              Sources {result.citations.length > 0 && `(${result.citations.length})`}
            </h2>
            {result.citations.length === 0 ? (
              <p className="text-sm text-slate-400">No supporting chunks were retrieved for this question.</p>
            ) : (
              <div className="space-y-3">
                {result.citations.map((citation, index) => (
                  <CitationCard
                    key={citation.source.chunk_id}
                    citation={citation}
                    index={index}
                    highlighted={highlighted === index}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
