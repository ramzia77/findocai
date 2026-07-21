import { AlertTriangle, FileStack, Layers, MessageSquareText } from "lucide-react";
import { useEffect, useState } from "react";
import { listAudit, listDocuments } from "../api/client";
import { AuditRecord, DocumentSummary } from "../api/types";
import { Badge } from "../components/ui/Badge";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { StatTile } from "../components/ui/StatTile";
import { useSettings } from "../context/SettingsContext";

export function OverviewPage() {
  const { apiBaseUrl, apiKey } = useSettings();
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [audit, setAudit] = useState<AuditRecord[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const config = { baseUrl: apiBaseUrl, apiKey };

    Promise.all([listDocuments(config), listAudit(config, 200)])
      .then(([docsRes, auditRes]) => {
        if (cancelled) return;
        setDocuments(docsRes.documents);
        setAudit(auditRes.records);
      })
      .catch(() => {
        if (cancelled) return;
        setDocuments(null);
        setAudit(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl, apiKey]);

  const totalChunks = documents?.reduce((sum, d) => sum + d.num_chunks, 0) ?? 0;
  const totalPii = documents?.reduce((sum, d) => sum + d.pii_chunks, 0) ?? 0;
  const totalQuestions = audit?.filter((r) => r.endpoint === "/query").length ?? 0;

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-zinc-500">
        <Spinner /> Loading overview...
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Documents" value={documents?.length ?? 0} icon={FileStack} />
        <StatTile label="Chunks Indexed" value={totalChunks} icon={Layers} />
        <StatTile label="Questions Asked" value={totalQuestions} icon={MessageSquareText} tone="accent" />
        <StatTile label="PII Redactions" value={totalPii} icon={AlertTriangle} tone="warning" />
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-zinc-900">Recent activity</h2>
          <p className="text-sm text-zinc-500">Latest queries and extractions from the audit trail.</p>
        </CardHeader>
        <CardBody>
          {!audit || audit.length === 0 ? (
            <p className="text-sm text-zinc-400">No activity yet -- ingest a document and ask a question.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="label-caps">
                    <th className="pb-2 pr-4 font-semibold">Time</th>
                    <th className="pb-2 pr-4 font-semibold">Endpoint</th>
                    <th className="pb-2 pr-4 font-semibold">Question</th>
                    <th className="pb-2 pr-4 font-semibold">Latency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {audit.slice(0, 8).map((r) => (
                    <tr key={r.request_id}>
                      <td className="py-2 pr-4 text-zinc-500">{new Date(r.timestamp).toLocaleString()}</td>
                      <td className="py-2 pr-4">
                        <Badge tone={r.endpoint === "/extract" ? "accent" : "neutral"}>{r.endpoint}</Badge>
                      </td>
                      <td className="max-w-xs truncate py-2 pr-4 text-zinc-800">{r.question}</td>
                      <td className="py-2 pr-4 tabular-nums text-zinc-500">{r.latency_ms.toFixed(0)} ms</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
