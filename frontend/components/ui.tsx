import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";

export function Badge({
  tone = "neutral",
  children
}: {
  tone?: "neutral" | "ok" | "warn" | "danger";
  children: ReactNode;
}) {
  return <span className={cn("badge-pill", `badge-${tone}`)}>{children}</span>;
}

export function Surface({
  className,
  children
}: {
  className?: string;
  children: ReactNode;
}) {
  return <section className={cn("surface-card", className)}>{children}</section>;
}

export function StatCard({
  label,
  value,
  note,
  tone = "neutral"
}: {
  label: string;
  value: string;
  note: string;
  tone?: "neutral" | "ok" | "warn" | "danger";
}) {
  return (
    <Surface className={cn("relative overflow-hidden", `tone-${tone}`)}>
      <p className="mono-label text-slate">{label}</p>
      <div className="mt-4 text-3xl font-semibold text-ink">{value}</div>
      <p className="mt-3 text-sm text-slate">{note}</p>
    </Surface>
  );
}

export function SectionHeader({
  kicker,
  title,
  copy,
  action
}: {
  kicker?: string;
  title: string;
  copy: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
      <div className="max-w-2xl">
        {kicker ? <p className="mono-label text-brand">{kicker}</p> : null}
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-ink">{title}</h2>
        <p className="mt-2 text-sm leading-6 text-slate">{copy}</p>
      </div>
      {action}
    </div>
  );
}

export function LinkCard({
  href,
  kicker,
  title,
  copy
}: {
  href: string;
  kicker: string;
  title: string;
  copy: string;
}) {
  return (
    <Link className="block surface-card transition-transform hover:-translate-y-0.5" href={href}>
      <p className="mono-label text-brand">{kicker}</p>
      <div className="mt-3 flex items-center justify-between gap-3">
        <div>
          <div className="text-lg font-semibold text-ink">{title}</div>
          <p className="mt-2 text-sm leading-6 text-slate">{copy}</p>
        </div>
        <ArrowRight className="size-4 text-brand" />
      </div>
    </Link>
  );
}

export function EmptyState({
  title,
  copy
}: {
  title: string;
  copy: string;
}) {
  return (
    <Surface className="border-dashed">
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      <p className="mt-2 max-w-xl text-sm leading-6 text-slate">{copy}</p>
    </Surface>
  );
}
