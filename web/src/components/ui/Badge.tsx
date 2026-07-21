import { HTMLAttributes } from "react";

type Tone = "neutral" | "accent" | "success" | "warning" | "danger";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-zinc-100 text-zinc-700",
  accent: "bg-accent-50 text-accent-700",
  success: "bg-accent-50 text-accent-700",
  warning: "bg-amber-50 text-amber-700",
  danger: "bg-rose-50 text-rose-700",
};

export function Badge({ tone = "neutral", className = "", ...props }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]} ${className}`}
      {...props}
    />
  );
}
