/**
 * Vendored primitives (shadcn/ui-derived approach: copy-in, zero runtime CDN deps — §3.4).
 * Logical properties ONLY (the ms-, me-, ps-, pe-, text-start families) — CI greps for
 * physical ones.
 */
import { type VariantProps, cva } from "class-variance-authority";
import { clsx } from "clsx";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

const button = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors " +
    "duration-150 focus-visible:outline-2 disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        primary: "bg-verdigris-400 text-ink-950 hover:bg-verdigris-400/90",
        ghost: "text-sand-400 hover:text-sand-100 hover:bg-ink-700/40",
        outline: "border border-ink-700 text-sand-100 hover:border-verdigris-400/60",
        danger: "bg-cinnabar-400 text-sand-100 hover:bg-cinnabar-400/90",
      },
      size: {
        sm: "h-8 ps-3 pe-3 text-sm",
        md: "h-10 ps-4 pe-4 text-sm",
        lg: "h-12 ps-6 pe-6 text-base",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {}

export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={clsx(button({ variant, size }), className)} {...props} />;
}

export function Panel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("panel p-4", className)} {...props} />;
}

const badge = cva(
  "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border ps-2.5 pe-2.5 py-0.5 " +
    "text-xs font-medium",
  {
    variants: {
      tone: {
        live: "border-verdigris-400/40 text-verdigris-400",
        sand: "border-ink-700 text-sand-400",
        alarm: "border-cinnabar-400/50 text-cinnabar-400",
      },
    },
    defaultVariants: { tone: "sand" },
  },
);

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badge> {}

export function Badge({ className, tone, ...props }: BadgeProps) {
  return <span className={clsx(badge({ tone }), className)} {...props} />;
}

export function Metric({
  label,
  value,
  unit,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-xs text-sand-400">{label}</span>
      <span className="metric text-lg" aria-live="polite">
        {value}
        {unit ? <span className="text-xs text-sand-400 ms-1">{unit}</span> : null}
      </span>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-ink-700/50", className)} aria-hidden />;
}
