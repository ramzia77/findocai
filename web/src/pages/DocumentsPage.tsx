import { Copy, FileCheck2, Trash2, UploadCloud } from "lucide-react";
import { useEffect, useState } from "react";
import { deleteDocument, ingestDocument, listDocuments } from "../api/client";
import { DOC_TYPES, DocType, DocumentSummary } from "../api/types";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Select } from "../components/ui/Select";
import { Spinner } from "../components/ui/Spinner";
import { useSettings } from "../context/SettingsContext";
import { useToast } from "../context/ToastContext";

export function DocumentsPage() {
  const { apiBaseUrl, apiKey } = useSettings();
  const toast = useToast();

  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<DocType>("loan_agreement");
  const [uploading, setUploading] = useState(false);
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  function refreshDocuments() {
    setLoadingDocs(true);
    listDocuments({ baseUrl: apiBaseUrl, apiKey })
      .then((res) => setDocuments(res.documents))
      .catch(() => setDocuments(null))
      .finally(() => setLoadingDocs(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refreshDocuments, [apiBaseUrl, apiKey]);

  async function handleUpload() {
    if (!file) return;
    setUploading(true);
    try {
      const result = await ingestDocument({ baseUrl: apiBaseUrl, apiKey }, file, docType);
      toast.success(`Ingested "${file.name}" -- ${result.num_chunks} chunks indexed`);
      setFile(null);
      refreshDocuments();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(doc: DocumentSummary) {
    if (!window.confirm(`Permanently delete "${doc.filename}" (${doc.doc_id})? This cannot be undone.`)) {
      return;
    }
    setDeletingId(doc.doc_id);
    try {
      await deleteDocument({ baseUrl: apiBaseUrl, apiKey }, doc.doc_id);
      toast.success(`Deleted "${doc.filename}"`);
      refreshDocuments();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-zinc-900">Ingest a document</h2>
          <p className="text-sm text-zinc-500">Upload a .txt or .pdf document to index it for Q&amp;A.</p>
        </CardHeader>
        <CardBody className="space-y-4">
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-zinc-300 px-6 py-10 text-center hover:border-zinc-400 hover:bg-zinc-50">
            <input
              type="file"
              accept=".txt,.pdf"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <>
                <FileCheck2 className="h-8 w-8 text-zinc-700" />
                <span className="text-sm font-medium text-zinc-800">{file.name}</span>
                <span className="text-xs text-zinc-500">Click to choose a different file</span>
              </>
            ) : (
              <>
                <UploadCloud className="h-8 w-8 text-zinc-400" />
                <span className="text-sm font-medium text-zinc-700">Click to upload or drag and drop</span>
                <span className="text-xs text-zinc-500">.txt or .pdf</span>
              </>
            )}
          </label>

          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-600">Document type</label>
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
          <h2 className="text-sm font-semibold text-zinc-900">Indexed documents</h2>
          <p className="text-sm text-zinc-500">Everything currently searchable, straight from the vector index.</p>
        </CardHeader>
        <CardBody>
          {loadingDocs ? (
            <div className="flex items-center gap-2 text-sm text-zinc-500">
              <Spinner /> Loading...
            </div>
          ) : !documents || documents.length === 0 ? (
            <p className="text-sm text-zinc-400">Nothing ingested yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="label-caps">
                    <th className="pb-2 pr-4 font-semibold">Document</th>
                    <th className="pb-2 pr-4 font-semibold">Type</th>
                    <th className="pb-2 pr-4 font-semibold">Chunks</th>
                    <th className="pb-2 pr-4 font-semibold">PII redacted</th>
                    <th className="pb-2 pr-4 font-semibold">Doc ID</th>
                    <th className="pb-2 pr-4 font-semibold" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-100">
                  {documents.map((d) => (
                    <tr key={d.doc_id}>
                      <td className="py-2 pr-4 font-medium text-zinc-800">{d.filename}</td>
                      <td className="py-2 pr-4">
                        <Badge tone="accent">{DOC_TYPES.find((t) => t.value === d.doc_type)?.label}</Badge>
                      </td>
                      <td className="py-2 pr-4 tabular-nums text-zinc-600">{d.num_chunks}</td>
                      <td className="py-2 pr-4">
                        {d.pii_chunks > 0 ? (
                          <Badge tone="warning">{d.pii_chunks} redacted</Badge>
                        ) : (
                          <Badge tone="neutral">none</Badge>
                        )}
                      </td>
                      <td className="py-2 pr-4">
                        <button
                          onClick={() => navigator.clipboard.writeText(d.doc_id)}
                          className="inline-flex items-center gap-1 font-mono text-xs text-zinc-500 hover:text-zinc-900"
                          title="Copy doc_id"
                        >
                          {d.doc_id.slice(0, 10)}...
                          <Copy className="h-3 w-3" />
                        </button>
                      </td>
                      <td className="py-2 pr-4">
                        <button
                          onClick={() => handleDelete(d)}
                          disabled={deletingId === d.doc_id}
                          className="inline-flex items-center gap-1 text-xs font-medium text-rose-600 hover:text-rose-700 disabled:opacity-50"
                          title="Delete document (requires admin scope)"
                        >
                          {deletingId === d.doc_id ? <Spinner className="h-3 w-3" /> : <Trash2 className="h-3 w-3" />}
                          Delete
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
