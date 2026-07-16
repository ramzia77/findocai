import { CircleAlert, CircleCheck } from "lucide-react";
import { useHealth } from "../hooks/useHealth";
import { Badge } from "./ui/Badge";
import { Spinner } from "./ui/Spinner";

interface TopBarProps {
  title: string;
  subtitle?: string;
}

export function TopBar({ title, subtitle }: TopBarProps) {
  const { health, error, loading } = useHealth();

  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-8 py-5">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
      </div>

      <div>
        {loading ? (
          <Badge tone="neutral">
            <Spinner className="h-3 w-3" /> Checking connection
          </Badge>
        ) : health ? (
          <Badge tone="success">
            <CircleCheck className="h-3.5 w-3.5" />
            Connected &middot; {health.llm_provider} / {health.vectorstore_backend}
          </Badge>
        ) : (
          <Badge tone="danger" title={error ?? undefined}>
            <CircleAlert className="h-3.5 w-3.5" />
            Disconnected &mdash; check Settings
          </Badge>
        )}
      </div>
    </header>
  );
}
