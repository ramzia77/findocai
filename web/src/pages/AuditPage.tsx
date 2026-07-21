import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { listAudit } from "../api/client";
import { AuditRecord } from "../api/types";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody } from "../components/ui/Card";
import { Spinner } from "../components/ui/Spinner";
import { useSettings } from "../context/SettingsContext";
import { useToast } from "../context/ToastContext";

export function AuditPage() {
  const { apiBaseUrl, apiKey } = useSettings();
  const toast = useToast();
  const [records, setRecords] = useState<AuditRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  function load() {
    setLoading(true);
    listAudit({ baseUrl: apiBaseUrl, apiKey }, 100)
      .then((res) => setRecords(res.records))
      .catch((err) => toast.error(err instanceof Error ? err.message : "Failed to load audit trail"))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [apiBaseUrl, apiKey]);

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-900">Audit trail</h2>
          <p className="text-sm text-zinc-500">
            Every query and extraction, independent of application logs -- compliance-ready.
          </p>
        </div>
        <Button variant="secondary" onClick={load} disabled={loading}>
          {loading ? <Spinner /> : <RefreshCw className="h-4 w-4" />}
          Refresh
        </Button>
      </div>

      <Card>
        <CardBody className="p-0">
          {!records || records.length === 0 ? (
            <p className="p-5 text-sm text-zinc-400">No audit records yet.</p>
          ) : (
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="label-caps border-b border-zinc-100">
                  <th className="w-8" />
                  <th className="py-3 pr-4 font-semibold">Time</th>
                  <th className="py-3 pr-4 font-semibold">Endpoint</th>
                  <th className="py-3 pr-4 font-semibold">Doc type</th>
                  <th className="py-3 pr-4 font-semibold">Question</th>
                  <th className="py-3 pr-4 font-semibold">Latency</th>
                  <th className="py-3 pr-4 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-100">
                {records.map((r) => {
                  const isOpen = expanded === r.request_id;
                  return (
                    <Fragment key={r.request_id}>
                      <tr
                        onClick={() => setExpanded(isOpen ? null : r.request_id)}
                        className="cursor-pointer hover:bg-zinc-50"
                      >
                        <td className="pl-4">
                          {isOpen ? (
                            <ChevronDown className="h-3.5 w-3.5 text-zinc-400" />
                          ) : (
                            <ChevronRight className="h-3.5 w-3.5 text-zinc-400" />
                          )}
                        </td>
                        <td className="py-3 pr-4 text-zinc-500">{new Date(r.timestamp).toLocaleString()}</td>
                        <td className="py-3 pr-4">
                          <Badge tone={r.endpoint === "/extract" ? "accent" : "neutral"}>{r.endpoint}</Badge>
                        </td>
                        <td className="py-3 pr-4 text-zinc-500">{r.doc_type ?? "--"}</td>
                        <td className="max-w-sm truncate py-3 pr-4 text-zinc-800">{r.question}</td>
                        <td className="py-3 pr-4 tabular-nums text-zinc-500">{r.latency_ms.toFixed(0)} ms</td>
                        <td className="py-3 pr-4">
                          <Badge tone={r.status_code < 300 ? "accent" : "danger"}>{r.status_code}</Badge>
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="bg-zinc-50">
                          <td colSpan={7} className="px-5 py-4">
                            <div className="grid gap-4 sm:grid-cols-2">
                              <div>
                                <p className="label-caps mb-1">Answer</p>
                                <p className="whitespace-pre-wrap text-sm text-zinc-700">{r.answer}</p>
                              </div>
                              <div>
                                <p className="label-caps mb-1">Retrieved chunks ({r.retrieved_chunk_ids.length})</p>
                                <ul className="space-y-1 font-mono text-xs text-zinc-500">
                                  {r.retrieved_chunk_ids.map((id) => (
                                    <li key={id}>{id}</li>
                                  ))}
                                </ul>
                                <p className="label-caps mb-1 mt-3">Request</p>
                                <p className="font-mono text-xs text-zinc-500">
                                  {r.request_id} &middot; key {r.api_key_id}
                                </p>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
