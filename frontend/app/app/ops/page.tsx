"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { SectionHeader, StatCard, Surface } from "@/components/ui";
import type { ConnectorHealth, FeishuFailureItem, FeishuReplayResult, FeishuSyncStatusResponse } from "@/lib/types";

export default function OpsPage() {
  const { authFetch, user } = useAuth();
  const [actionMessage, setActionMessage] = useState("");
  const [actionTone, setActionTone] = useState<"ok" | "danger" | "neutral">("neutral");
  const [isRetrying, setIsRetrying] = useState(false);
  const canUseOps = user?.role === "admin" || user?.role === "ops";
  const canWriteOps = canUseOps && !user?.is_public_demo;
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
    if (isRetrying) {
      setActionTone("danger");
      setActionMessage("Replay is already running in this browser. Wait for it to finish before retrying.");
      return;
    }
    setActionMessage("");
    setActionTone("neutral");
    setIsRetrying(true);
    try {
      const response = await authFetch("/api/ops/feishu-sync/retry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, limit: 20 })
      });
      const result = (await response.json()) as FeishuReplayResult;
      await Promise.all([syncQuery.refetch(), failuresQuery.refetch()]);
      setActionTone(result.fail_count ? "danger" : "ok");
      setActionMessage(
        `Replay finished: ${result.ok_count ?? 0} synced, ${result.fail_count ?? 0} failed / run ${result.run_id?.slice(0, 8) || "-"} / ${Math.round(result.latency_ms ?? 0)}ms.`
      );
    } catch (error) {
      setActionTone("danger");
      setActionMessage(error instanceof Error ? `Replay failed: ${error.message}` : "Replay failed: connector unavailable.");
    } finally {
      setIsRetrying(false);
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

      <div className="grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
        <Surface className="stagger-in dense-surface">
          <SectionHeader kicker="Connector mesh" title="Runtime posture" copy="Each dependency surface is visible here so recovery work happens with context." />
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              className="terminal-secondary min-h-0 px-4 py-2 text-sm"
              disabled={connectorsQuery.isFetching}
              onClick={() => {
                void connectorsQuery.refetch({ throwOnError: false });
              }}
              type="button"
            >
              {connectorsQuery.isFetching ? "Refreshing..." : "Refresh cached health"}
            </button>
            {canWriteOps ? (
              <button
                className="terminal-primary min-h-0 px-4 py-2 text-sm"
                disabled={connectorsQuery.isFetching}
                onClick={async () => {
                  await authFetch("/api/ops/connectors?refresh=true");
                  await connectorsQuery.refetch();
                }}
                type="button"
              >
                Run live check
              </button>
            ) : (
              <span className="mono-label text-slate">Live checks require admin login</span>
            )}
            <Link className="terminal-button min-h-0 px-4 py-2 text-sm" href="/app/control-room">
              Control Room
            </Link>
          </div>
          <div className="mt-6 space-y-3">
            {connectorsQuery.isError ? (
              <div className="terminal-row border-rose/20 text-sm text-rose">
                Connector health is unavailable. Check API and integration credentials, then retry.
              </div>
            ) : null}
            {(connectorsQuery.data ?? []).map((connector) => (
              <div key={connector.name} className="terminal-row dense-row">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-base font-semibold text-ink">{connector.name}</div>
                  <div className="text-xs uppercase tracking-[0.12em] text-slate">{connector.status}</div>
                </div>
                <p className="mt-2 text-sm text-slate">{connector.message}</p>
                {connector.detail ? <p className="mt-2 text-xs text-slate">{connector.detail}</p> : null}
                <p className="mt-3 text-xs text-slate">
                  {connector.stale ? "Stale snapshot" : "Fresh snapshot"} / {connector.latency_ms ?? 0}ms
                  {connector.cached_at ? ` / ${connector.cached_at.slice(0, 19)}` : ""}
                </p>
              </div>
            ))}
          </div>
        </Surface>

        <div className="space-y-4">
          <Surface className="stagger-in dense-surface status-processing">
            <SectionHeader kicker="Replay actions" title="Feishu recovery controls" copy="Use manual replay when operations cannot wait for the background worker." />
            {canWriteOps ? (
              <div className="mt-5 flex flex-wrap gap-3">
                <button className="terminal-primary" disabled={isRetrying} onClick={() => void retry("failed")} type="button">
                  {isRetrying ? "Replay running..." : "Retry failed syncs"}
                </button>
                <button className="terminal-secondary" disabled={isRetrying} onClick={() => void retry("pending")} type="button">
                  Sync pending rows
                </button>
              </div>
            ) : (
              <div className="terminal-row mt-6">
                <div className="mono-label text-brand">Read-only demo</div>
                <p className="mt-2 text-sm leading-6 text-slate">
                  Feishu replay and live connector checks are disabled until an admin or ops user signs in.
                </p>
              </div>
            )}
            <p className="mt-4 text-sm leading-6 text-slate">
              Worker mode {syncQuery.data?.retry_mode || "failed"} every {syncQuery.data?.retry_interval_sec || 300}s with batch size {syncQuery.data?.retry_batch_limit || 20}.
            </p>
            {actionMessage ? (
              <p className={`mt-4 text-sm font-medium ${actionTone === "danger" ? "text-rose" : actionTone === "ok" ? "text-mint" : "text-slate"}`}>
                {actionMessage}
              </p>
            ) : null}
            <div className="terminal-row dense-row mt-4">
              <div className="font-semibold text-ink">Recovery tips</div>
              <p className="mt-2 text-sm leading-6 text-slate">
                If replay keeps failing, run a live connector check, confirm Feishu credentials, then retry a smaller batch.
                Failed rows remain in the exception queue for a safe second attempt.
              </p>
            </div>
          </Surface>

          <Surface className="stagger-in dense-surface">
            <SectionHeader kicker="Exception queue" title="Recent failed syncs" copy="Review the newest failures and replay them without leaving the ops page." />
            <div className="mt-6 space-y-3">
              {failuresQuery.isError ? (
                <div className="terminal-row border-rose/20 text-sm text-rose">
                  Failed sync queue is unavailable. The retry controls will recover when the API returns.
                </div>
              ) : null}
              {(failuresQuery.data ?? []).map((item) => (
                <div key={`${item.invoice_id}-${item.updated_at}`} className="terminal-row dense-row">
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-ink">
                      #{item.invoice_id} {item.seller_name || "Unknown seller"}
                    </div>
                    <div className="text-xs uppercase tracking-[0.12em] text-slate">{item.updated_at?.slice(0, 10) || "-"}</div>
                  </div>
                  <p className="mt-2 text-sm text-slate">{item.sync_error || "No error message available."}</p>
                </div>
              ))}
              {!failuresQuery.isLoading && !failuresQuery.isError && (failuresQuery.data ?? []).length === 0 ? (
                <div className="terminal-row text-sm text-slate">No failed Feishu syncs are waiting for replay.</div>
              ) : null}
            </div>
          </Surface>
        </div>
      </div>
    </AppShell>
  );
}
