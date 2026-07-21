import { LucideIcon } from "lucide-react";
import { Card, CardBody } from "./Card";

type Tone = "neutral" | "accent" | "warning";

interface StatTileProps {
  label: string;
  value: string | number;
  icon?: LucideIcon;
  tone?: Tone;
}

const ICON_TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-zinc-100 text-zinc-500",
  accent: "bg-accent-50 text-accent-600",
  warning: "bg-amber-50 text-amber-600",
};

export function StatTile({ label, value, icon: Icon, tone = "neutral" }: StatTileProps) {
  return (
    <Card>
      <CardBody className="flex items-start justify-between">
        <div>
          <p className="label-caps">{label}</p>
          <p className="mt-2 text-3xl font-semibold tabular-nums text-zinc-900">{value}</p>
        </div>
        {Icon && (
          <div className={`rounded-lg p-2 ${ICON_TONE_CLASSES[tone]}`}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </CardBody>
    </Card>
  );
}
