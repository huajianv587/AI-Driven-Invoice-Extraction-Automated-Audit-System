"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { ActivityStrip } from "@/components/activity-strip";
import { AppShell } from "@/components/app-shell";
import { EmptyState, LinkCard, SectionHeader, StatCard, Surface } from "@/components/ui";
import { useAuth } from "@/components/auth-provider";
import type { DashboardSummary, DailyActivityPoint, InvoiceListResponse } from "@/lib/types";
import { formatMoney, formatPercent } from "@/lib/utils";

export default function DashboardPage() {
  const { authFetch } = useAuth();
  const summaryQuery = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: async () => (await (await authFetch("/api/dashboard/summary")).json()) as DashboardSummary
  });
  const activityQuery = useQuery({
    queryKey: ["dashboard-activity"],
    queryFn: async () => (await (await authFetch("/api/dashboard/activity")).json()) as DailyActivityPoint[]
  });
  const queueQuery = useQuery({
    queryKey: ["queue-preview"],
    queryFn: async () =>
      (await (await authFetch("/api/invoices?sort=risk&limit=6")).json()) as InvoiceListResponse
  });

  const summary = summaryQuery.data;
  const activity = activityQuery.data ?? [];
  const queue = queueQuery.data;

  return (
    <AppShell
      title="Mission Control"
      subtitle="Track risk posture, queue pressure, cloud sync integrity, and connector readiness from one flagship control surface."
    >
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="Invoices" value={String(summary?.totals.total_count ?? 0)} note="Total records in the workspace." />
        <StatCard
          label="High risk"
          tone="danger"
          value={String(summary?.totals.risk_count ?? 0)}
          note={`Risk ratio ${formatPercent(summary?.ratios.risk_ratio ?? 0)}.`}
        />
        <StatCard
          label="Pending"
          tone="warn"
          value={String(summary?.totals.pending_count ?? 0)}
          note="Cases waiting for a reviewer decision."
        />
        <StatCard
          label="Volume"
          tone="ok"
          value={formatMoney(summary?.totals.total_amount ?? 0)}
          note={`Risk delta ${formatMoney(summary?.totals.risk_amount ?? 0)}.`}
        />
      </div>

      <section className="space-y-4">
        <SectionHeader
          kicker="Seven-day signal"
          title="Operational activity"
          copy="A compact view of throughput and risk formation across the last seven days."
        />
        {activity.length ? <ActivityStrip items={activity} /> : <EmptyState title="No activity yet" copy="Run sample ingestion to populate the new dashboard." />}
      </section>

      <section className="grid gap-4 md:grid-cols-[1.1fr_0.9fr]">
        <Surface>
          <SectionHeader
            kicker="Priority risk"
            title="Top review candidates"
            copy="Escalate the largest deltas first, then move into the full queue."
            action={<Link className="text-sm font-semibold text-brand" href="/app/queue">Open queue</Link>}
          />
          <div className="mt-6 space-y-3">
            {summary?.top_risk.length ? (
              summary.top_risk.map((item) => (
                <div key={item.id} className="rounded-[22px] border border-line bg-[#f8fbff] p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <div className="text-lg font-semibold text-ink">{item.seller_name || "Unknown seller"}</div>
                      <p className="mt-2 text-sm text-slate">{item.risk_reason_summary}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-lg font-semibold text-rose">{formatMoney(item.amount_diff)}</div>
                      <div className="mt-2 text-xs uppercase tracking-[0.12em] text-slate">#{item.id}</div>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <EmptyState title="No flagged invoices" copy="Once risk records exist, this spotlight will surface the most urgent cases." />
            )}
          </div>
        </Surface>

        <div className="space-y-4">
          <LinkCard
            href="/app/queue"
            kicker="Working slice"
            title="Review Queue"
            copy={`Browse ${queue?.total_count ?? 0} matched invoices with search, status filters, and direct review routes.`}
          />
          <LinkCard
            href="/app/ops"
            kicker="Recovery"
            title="Operations Center"
            copy={`Connector mesh ${summary?.connectors.ready_count ?? 0}/${summary?.connectors.total_count ?? 0} ready with replay controls nearby.`}
          />
          <Surface>
            <p className="mono-label text-brand">Connector posture</p>
            <div className="mt-4 rounded-[20px] border border-line bg-[#f8fbff] p-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-base font-semibold text-ink">
                    {summary?.connectors.ready_count ?? 0}/{summary?.connectors.total_count ?? 4} ready
                  </div>
                  <p className="mt-2 text-sm leading-6 text-slate">
                    Dashboard uses the latest cached connector snapshot so slow external checks never block mission control.
                  </p>
                </div>
                <Link className="text-sm font-semibold text-brand" href="/app/ops">Refresh in Ops</Link>
              </div>
            </div>
          </Surface>
        </div>
      </section>
    </AppShell>
  );
}
