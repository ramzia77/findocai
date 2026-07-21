import { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-zinc-900 text-white hover:bg-zinc-800 disabled:bg-zinc-300",
  secondary:
    "border border-zinc-300 bg-white text-zinc-700 hover:border-zinc-400 hover:bg-zinc-50 disabled:text-zinc-400",
  ghost: "text-zinc-600 hover:bg-zinc-100 disabled:text-zinc-300",
};

export function Button({ variant = "primary", className = "", ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    />
  );
}
