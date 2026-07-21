import { CircleAlert, CircleCheck } from "lucide-react";
import { useState } from "react";
import { getHealth } from "../api/client";
import { Button } from "../components/ui/Button";
import { Card, CardBody, CardHeader } from "../components/ui/Card";
import { Input } from "../components/ui/Input";
import { Spinner } from "../components/ui/Spinner";
import { useSettings } from "../context/SettingsContext";

type TestResult =
  | { status: "idle" }
  | { status: "testing" }
  | { status: "ok"; message: string }
  | { status: "error"; message: string };

export function SettingsPage() {
  const { apiBaseUrl, apiKey, setApiBaseUrl, setApiKey } = useSettings();
  const [result, setResult] = useState<TestResult>({ status: "idle" });

  async function handleTest() {
    setResult({ status: "testing" });
    try {
      const health = await getHealth({ baseUrl: apiBaseUrl, apiKey });
      setResult({
        status: "ok",
        message: `Connected -- vectorstore: ${health.vectorstore_backend}, LLM: ${health.llm_provider}, embeddings: ${health.embedding_provider}`,
      });
    } catch (err) {
      setResult({ status: "error", message: err instanceof Error ? err.message : "Connection failed" });
    }
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Card>
        <CardHeader>
          <h2 className="text-sm font-semibold text-zinc-900">API connection</h2>
          <p className="text-sm text-zinc-500">
            Stored in this browser only (localStorage) -- never sent anywhere except the API base URL below.
          </p>
        </CardHeader>
        <CardBody className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-600">API base URL</label>
            <Input
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value)}
              placeholder="http://localhost:8000"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-zinc-600">API key</label>
            <Input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="dev-local-key"
            />
            <p className="mt-1 text-xs text-zinc-400">
              Matches an entry in <code>FINDOCAI_API_KEYS</code> / <code>config.yaml</code> on the backend.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={handleTest} disabled={result.status === "testing"}>
              {result.status === "testing" && <Spinner />}
              Test connection
            </Button>

            {result.status === "ok" && (
              <span className="flex items-center gap-1.5 text-sm text-emerald-700">
                <CircleCheck className="h-4 w-4" /> {result.message}
              </span>
            )}
            {result.status === "error" && (
              <span className="flex items-center gap-1.5 text-sm text-rose-700">
                <CircleAlert className="h-4 w-4" /> {result.message}
              </span>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
