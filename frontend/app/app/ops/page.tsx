"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { SectionHeader, StatCard, Surface } from "@/components/ui";
import { useAuth } from "@/components/auth-provider";
import type { ConnectorHealth, FeishuFailureItem, FeishuSyncStatusResponse } from "@/lib/types";

export default function OpsPage() {
  const { authFetch, user } = useAuth();
  const [actionMessage, setActionMessage] = useState("");
  const canUseOps = user?.role === "admin" || user?.role === "ops";
  const connectorsQuery = useQuery({
    queryKey: ["ops-connectors"],
    queryFn: async () => (await (await authFetch("/api/ops/connectors")).json()) as ConnectorHealth[],
    enabled: Boolean(canUseOps)
  });
  const syncQuery = useQuery({
    queryKey: ["ops-feishu-sync"],
    queryFn: async () => (await (await authFetch("/api/ops/feishu-sync")).json()) as FeishuSyncStatusResponse,
    enabled: Boolean(canUseOps)
  });
  const failuresQuery = useQuery({
    queryKey: ["ops-feishu-failures"],
    queryFn: async () => (await (await authFetch("/api/ops/feishu-sync/failures")).json()) as FeishuFailureItem[],
    enabled: Boolean(canUseOps)
  });

  const retry = async (mode: "failed" | "pending") => {
    setActionMessage("");
    try {
      const response = await authFetch("/api/ops/feishu-sync/retry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, limit: 20 })
      });
      const result = await response.json() as { ok_count?: number; fail_count?: number };
      await Promise.all([syncQuery.refetch(), failuresQuery.refetch()]);
      setActionMessage(`Replay finished: ${result.ok_count ?? 0} synced, ${result.fail_count ?? 0} failed.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? `Replay failed: ${error.message}` : "Replay failed: connector unavailable.");
    }
  };

  return (
    <AppShell
      allowedRoles={["admin", "ops"]}
      title="Operations Center"
      subtitle="Monitor connector posture, manage Feishu replay, and keep the data plane stable from one operator-grade control deck."
    >
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Synced" tone="ok" value={String(syncQuery.data?.summary.synced_count ?? 0)} note="Rows already mirrored to Feishu." />
        <StatCard label="Pending" tone="warn" value={String(syncQuery.data?.summary.pending_count ?? 0)} note="Rows that have not reached Feishu yet." />
        <StatCard label="Failed" tone="danger" value={String(syncQuery.data?.summary.failed_count ?? 0)} note="Rows currently waiting for replay." />
      </div>

      <div className="grid gap-4 md:grid-cols-[0.95fr_1.05fr]">
        <Surface>
          <SectionHeader kicker="Connector mesh" title="Runtime posture" copy="Each dependency surface is visible here so recovery work happens with context." />
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              className="rounded-2xl border border-line bg-white px-4 py-2 text-sm font-semibold text-ink"
              disabled={connectorsQuery.isFetching}
              onClick={() => {
                void connectorsQuery.refetch({ throwOnError: false });
              }}
              type="button"
            >
              {connectorsQuery.isFetching ? "Refreshing..." : "Refresh cached health"}
            </button>
            <button
              className="rounded-2xl bg-brand px-4 py-2 text-sm font-semibold text-white shadow-focus"
              disabled={connectorsQuery.isFetching}
              onClick={async () => {
                await authFetch("/api/ops/connectors?refresh=true");
                await connectorsQuery.refetch();
              }}
              type="button"
            >
              Run live check
            </button>
          </div>
          <div className="mt-6 space-y-3">
            {connectorsQuery.isError ? (
              <div className="rounded-[20px] border border-rose/20 bg-[#fff7fa] p-4 text-sm text-rose">
                Connector health is unavailable. Check API and integration credentials, then retry.
              </div>
            ) : null}
            {(connectorsQuery.data ?? []).map((connector) => (
              <div key={connector.name} className="rounded-[20px] border border-line bg-[#f8fbff] p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-base font-semibold text-ink">{connector.name}</div>
                  <div className="text-xs uppercase tracking-[0.12em] text-slate">{connector.status}</div>
                </div>
                <p className="mt-2 text-sm text-slate">{connector.message}</p>
                {connector.detail ? <p className="mt-2 text-xs text-slate">{connector.detail}</p> : null}
                <p className="mt-3 text-xs text-slate">
                  {connector.stale ? "Stale snapshot" : "Fresh snapshot"} · {connector.latency_ms ?? 0}ms
                  {connector.cached_at ? ` · ${connector.cached_at.slice(0, 19)}` : ""}
                </p>
              </div>
            ))}
          </div>
        </Surface>

        <div className="space-y-4">
          <Surface>
            <SectionHeader kicker="Replay actions" title="Feishu recovery controls" copy="Use manual replay when operations cannot wait for the background worker." />
            <div className="mt-6 flex flex-wrap gap-3">
              <button className="rounded-2xl bg-brand px-5 py-3 text-sm font-semibold text-white shadow-focus" onClick={() => void retry("failed")} type="button">
                Retry failed syncs
              </button>
              <button className="rounded-2xl border border-line bg-white px-5 py-3 text-sm font-semibold text-ink" onClick={() => void retry("pending")} type="button">
                Sync pending rows
              </button>
            </div>
            <p className="mt-4 text-sm leading-6 text-slate">
              Worker mode {syncQuery.data?.retry_mode || "failed"} every {syncQuery.data?.retry_interval_sec || 300}s with batch size {syncQuery.data?.retry_batch_limit || 20}.
            </p>
            {actionMessage ? <p className="mt-4 text-sm font-medium text-mint">{actionMessage}</p> : null}
            <div className="mt-5 rounded-[20px] border border-line bg-[#f8fbff] p-4">
              <div className="font-semibold text-ink">Recovery tips</div>
              <p className="mt-2 text-sm leading-6 text-slate">
                If replay keeps failing, run a live connector check, confirm Feishu credentials, then retry a smaller batch.
                Failed rows remain in the exception queue for a safe second attempt.
              </p>
            </div>
          </Surface>

          <Surface>
            <SectionHeader kicker="Exception queue" title="Recent failed syncs" copy="Review the newest failures and replay them without leaving the ops page." />
            <div className="mt-6 space-y-3">
              {failuresQuery.isError ? (
                <div className="rounded-[20px] border border-rose/20 bg-[#fff7fa] p-4 text-sm text-rose">
                  Failed sync queue is unavailable. The retry controls will recover when the API returns.
                </div>
              ) : null}
              {(failuresQuery.data ?? []).map((item) => (
                <div key={`${item.invoice_id}-${item.updated_at}`} className="rounded-[20px] border border-line bg-[#f8fbff] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-ink">#{item.invoice_id} {item.seller_name || "Unknown seller"}</div>
                    <div className="text-xs uppercase tracking-[0.12em] text-slate">{item.updated_at?.slice(0, 10) || "-"}</div>
                  </div>
                  <p className="mt-2 text-sm text-slate">{item.sync_error || "No error message available."}</p>
                </div>
              ))}
              {!failuresQuery.isLoading && !failuresQuery.isError && (failuresQuery.data ?? []).length === 0 ? (
                <div className="rounded-[20px] border border-line bg-[#f8fbff] p-4 text-sm text-slate">
                  No failed Feishu syncs are waiting for replay.
                </div>
              ) : null}
            </div>
          </Surface>
        </div>
      </div>
    </AppShell>
  );
}
