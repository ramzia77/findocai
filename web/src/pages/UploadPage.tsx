import { Copy, FileCheck2, UploadCloud } from "lucide-react";
import { useEffect, useState } from "react";
import { ingestDocument } from "../api/client";
import { DOC_TYPES, DocType, IngestResponse } from "../api/types";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import { Spinner } from "../components/ui/Spinner";
import { useSettings } from "../context/SettingsContext";
import { useToast } from "../context/ToastContext";

const HISTORY_STORAGE_KEY = "findocai.uploadHistory";

interface HistoryEntry extends IngestResponse {
  filename: string;
  ingestedAt: string;
}

function loadHistory(): HistoryEntry[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_STORAGE_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export function UploadPage() {
  const { apiBaseUrl, apiKey } = useSettings();
  const toast = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<DocType>("loan_agreement");
  const [uploading, setUploading] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>(loadHistory);

  useEffect(() => {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
  }, [history]);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    try {
      const result = await ingestDocument({ baseUrl: apiBaseUrl, apiKey }, file, docType);
      setHistory((prev) => [
        { ...result, filename: file.name, ingestedAt: new Date().toLocaleString() },
        ...prev,
      ]);
      toast.success(`Ingested "${file.name}" -- ${result.num_chunks} chunks indexed`);
      setFile(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-slate-900">Ingest a document</h2>
          <p className="text-sm text-slate-500">Upload a .txt or .pdf document to index it for Q&amp;A.</p>
        </CardHeader>
        <CardBody className="space-y-4">
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-slate-300 px-6 py-10 text-center hover:border-brand-400 hover:bg-brand-50/30">
            <input
              type="file"
              accept=".txt,.pdf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <>
                <FileCheck2 className="h-8 w-8 text-brand-600" />
                <span className="text-sm font-medium text-slate-800">{file.name}</span>
                <span className="text-xs text-slate-500">Click to choose a different file</span>
              </>
            ) : (
              <>
                <UploadCloud className="h-8 w-8 text-slate-400" />
                <span className="text-sm font-medium text-slate-700">Click to upload or drag and drop</span>
                <span className="text-xs text-slate-500">.txt or .pdf</span>
              </>
            )}
          </label>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">Document type</label>
            <Select value={docType} onChange={(e) => setDocType(e.target.value as DocType)}>
              {DOC_TYPES.map((d) => (
                <option key={d.value} value={d.value}>
                  {d.label}
                </option>
              ))}
            </Select>
          </div>

          <Button onClick={handleUpload} disabled={!file || uploading}>
            {uploading && <Spinner />}
            {uploading ? "Ingesting..." : "Upload & Ingest"}
          </Button>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-slate-900">Recently ingested (this browser)</h2>
          <p className="text-sm text-slate-500">
            There's no server-side document list yet -- this table is a local convenience only.
          </p>
        </CardHeader>
        <CardBody>
          {history.length === 0 ? (
            <p className="text-sm text-slate-400">Nothing ingested yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-xs uppercase text-slate-400">
                    <th className="pb-2 pr-4">Document</th>
                    <th className="pb-2 pr-4">Type</th>
                    <th className="pb-2 pr-4">Pages</th>
                    <th className="pb-2 pr-4">Chunks</th>
                    <th className="pb-2 pr-4">PII redacted</th>
                    <th className="pb-2 pr-4">Doc ID</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {history.map((h) => (
                    <tr key={`${h.doc_id}-${h.ingestedAt}`}>
                      <td className="py-2 pr-4 font-medium text-slate-800">{h.filename}</td>
                      <td className="py-2 pr-4">
                        <Badge tone="brand">{DOC_TYPES.find((d) => d.value === h.doc_type)?.label}</Badge>
                      </td>
                      <td className="py-2 pr-4 text-slate-600">{h.num_pages}</td>
                      <td className="py-2 pr-4 text-slate-600">{h.num_chunks}</td>
                      <td className="py-2 pr-4">
                        {h.pii_chunks_redacted > 0 ? (
                          <Badge tone="warning">{h.pii_chunks_redacted} redacted</Badge>
                        ) : (
                          <Badge tone="neutral">none</Badge>
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        <button
                          onClick={() => navigator.clipboard.writeText(h.doc_id)}
                          className="inline-flex items-center gap-1 font-mono text-xs text-slate-500 hover:text-brand-600"
                          title="Copy doc_id"
                        >
                          {h.doc_id.slice(0, 10)}...
                          <Copy className="h-3 w-3" />
                        </button>
                      </td>
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
