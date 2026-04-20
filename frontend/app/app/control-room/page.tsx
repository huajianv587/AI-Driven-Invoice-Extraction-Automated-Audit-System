"use client";

import Link from "next/link";
import { type DragEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FolderOpen,
  Mail,
  RefreshCcw,
  UploadCloud,
  XCircle
} from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { Badge, LinkCard, SectionHeader, StatCard, Surface } from "@/components/ui";
import type {
  ControlRoomSummary,
  IntakePipelineCounts,
  IntakeUploadItem,
  IntakeUploadStatus,
  IntakeUploadsResponse,
  UploadInvoiceResponse
} from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";

const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
const ACCEPTED_UPLOAD_TYPES = [".pdf", ".png", ".jpg", ".jpeg", ".webp"];
const EMPTY_PIPELINE_COUNTS: IntakePipelineCounts = {
  queued: 0,
  processing: 0,
  ingested: 0,
  failed: 0,
  total: 0
};

type LocalUploadStatus = "validating" | "uploading" | IntakeUploadStatus;

type LocalUploadItem = {
  localId: string;
  uploadId?: number;
  name: string;
  extension: string;
  sizeBytes: number;
  status: LocalUploadStatus;
  message: string;
};

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(2)} MB`;
}

function statusTone(status: LocalUploadStatus): "neutral" | "ok" | "warn" | "danger" {
  if (status === "ingested") return "ok";
  if (status === "failed") return "danger";
  if (status === "queued" || status === "processing" || status === "uploading" || status === "validating") return "warn";
  return "neutral";
}

function statusLabel(status: LocalUploadStatus) {
  if (status === "validating") return "Validating";
  if (status === "uploading") return "Uploading";
  return status;
}

function statusIcon(status: LocalUploadStatus) {
  if (status === "ingested") return CheckCircle2;
  if (status === "failed") return XCircle;
  if (status === "processing") return Activity;
  return Clock3;
}

function uploadStatusGroups(items: IntakeUploadItem[]) {
  return [
    { key: "queued" as const, title: "Queued", description: "Accepted uploads waiting for worker pickup." },
    { key: "processing" as const, title: "Processing", description: "Worker has started OCR and extraction." },
    { key: "ingested" as const, title: "Ingested", description: "Attached to an invoice record and audit trail." },
    { key: "failed" as const, title: "Failed", description: "Needs operator attention before retry." }
  ].map((group) => ({
    ...group,
    items: items.filter((item) => item.status === group.key)
  }));
}

export default function ControlRoomPage() {
  const { authFetch, user } = useAuth();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadTone, setUploadTone] = useState<"ok" | "danger" | "neutral">("neutral");
  const [localUploads, setLocalUploads] = useState<LocalUploadItem[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const canUseOps = user?.role === "admin" || user?.role === "ops";
  const canWriteOps = canUseOps && !user?.is_public_demo;

  const summaryQuery = useQuery({
    queryKey: ["ops-control-room"],
    queryFn: async () => (await (await authFetch("/api/ops/control-room")).json()) as ControlRoomSummary,
    enabled: Boolean(canUseOps)
  });

  const uploadsQuery = useQuery({
    queryKey: ["ops-intake-uploads"],
    queryFn: async () => (await (await authFetch("/api/ops/intake/uploads?limit=24")).json()) as IntakeUploadsResponse,
    enabled: Boolean(canUseOps)
  });

  const control = summaryQuery.data;
  const readinessChecks = Object.entries(control?.readiness.checks ?? {});
  const history = uploadsQuery.data?.items ?? control?.intake.recent_uploads ?? [];
  const pipelineCounts = control?.intake.pipeline_counts ?? EMPTY_PIPELINE_COUNTS;
  const hasActivePipeline =
    history.some((item) => item.status === "queued" || item.status === "processing") ||
    localUploads.some((item) => ["validating", "uploading", "queued", "processing"].includes(item.status));

  useEffect(() => {
    if (!history.length) {
      return;
    }
    setLocalUploads((current) =>
      current.map((item) => {
        const match = history.find((upload) => upload.id === item.uploadId);
        if (!match) {
          return item;
        }
        return {
          ...item,
          status: match.status,
          message:
            match.status === "failed"
              ? match.error_message || "Worker reported an ingestion failure."
              : match.status === "ingested"
                ? `Linked to invoice #${match.invoice_id || "-"}`
                : match.status === "processing"
                  ? "Worker picked up this upload."
                  : "Queued in the intake pipeline."
        };
      })
    );
  }, [history]);

  useEffect(() => {
    if (!hasActivePipeline) {
      return;
    }
    const timer = window.setInterval(() => {
      void Promise.all([summaryQuery.refetch(), uploadsQuery.refetch()]);
    }, 3500);
    return () => window.clearInterval(timer);
  }, [hasActivePipeline, summaryQuery, uploadsQuery]);

  const refreshPanels = async () => {
    await Promise.all([summaryQuery.refetch(), uploadsQuery.refetch()]);
  };

  const queueFiles = async (fileList: FileList | File[] | null) => {
    const files = fileList ? Array.from(fileList) : [];
    if (!files.length || !canWriteOps) {
      return;
    }
    setUploadMessage("");
    setUploadTone("neutral");
    setIsUploading(true);

    for (const file of files) {
      const localId =
        typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `upload-${Date.now()}-${file.name}`;
      const extension = file.name.includes(".") ? file.name.slice(file.name.lastIndexOf(".")).toLowerCase() : "";
      setLocalUploads((current) => [
        {
          localId,
          name: file.name,
          extension: extension || "-",
          sizeBytes: file.size,
          status: "validating" as const,
          message: "Checking file extension and intake size limit."
        },
        ...current
      ].slice(0, 10));

      if (!ACCEPTED_UPLOAD_TYPES.includes(extension)) {
        setLocalUploads((current) =>
          current.map((item) =>
            item.localId === localId
              ? { ...item, status: "failed" as const, message: `Unsupported type ${extension || "unknown"}.` }
              : item
          )
        );
        setUploadTone("danger");
        setUploadMessage(`Skipped ${file.name}: unsupported type.`);
        continue;
      }

      if (file.size > MAX_UPLOAD_BYTES) {
        setLocalUploads((current) =>
          current.map((item) =>
            item.localId === localId
              ? { ...item, status: "failed" as const, message: "File exceeds the 15 MB intake limit." }
              : item
          )
        );
        setUploadTone("danger");
        setUploadMessage(`Skipped ${file.name}: file is too large.`);
        continue;
      }

      setLocalUploads((current) =>
        current.map((item) =>
          item.localId === localId ? { ...item, status: "uploading" as const, message: "Posting file to the intake API." } : item
        )
      );

      try {
        const formData = new FormData();
        formData.append("file", file);
        const response = await authFetch("/api/ops/intake/upload", {
          method: "POST",
          body: formData
        });
        const payload = (await response.json()) as UploadInvoiceResponse;
        setLocalUploads((current) =>
          current.map((item) =>
            item.localId === localId
              ? {
                  ...item,
                  uploadId: payload.upload.id,
                  status: payload.upload.status,
                  message:
                    payload.upload.status === "queued"
                      ? "Queued in the watched intake directory."
                      : payload.message
                }
              : item
          )
        );
        setUploadTone("ok");
        setUploadMessage(payload.message);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Upload staging failed.";
        setLocalUploads((current) =>
          current.map((item) => (item.localId === localId ? { ...item, status: "failed" as const, message } : item))
        );
        setUploadTone("danger");
        setUploadMessage(message);
      }

      await refreshPanels();
    }

    setIsUploading(false);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  };

  const onDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    await queueFiles(event.dataTransfer.files);
  };

  return (
    <AppShell
      allowedRoles={["admin", "ops"]}
      title="Control Room"
      subtitle="Run the intake lane like a real operator surface: watch readiness, stage multiple invoices, track pipeline state, and pivot into alerts or recovery without exposing developer scripts."
    >
      <div className="grid gap-3 md:grid-cols-4">
        <StatCard label="Queued" tone="warn" value={String(pipelineCounts.queued)} note="Accepted uploads waiting for worker pickup." />
        <StatCard label="Processing" tone="warn" value={String(pipelineCounts.processing)} note="OCR or extraction is active right now." />
        <StatCard label="Ingested" tone="ok" value={String(pipelineCounts.ingested)} note="Uploads already linked to invoice records." />
        <StatCard label="Failed" tone="danger" value={String(pipelineCounts.failed)} note="Uploads that still need intervention." />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.08fr_0.92fr]">
        <div className="space-y-4">
          <Surface className="stagger-in dense-surface">
            <SectionHeader
              kicker="Intake console"
              title="Dropzone, queue, and folder visibility"
              copy="Multiple files can be staged from here while the current intake queue and watched directory stay visible in one tighter operator panel."
              action={
                <div className="flex flex-wrap gap-2">
                  <button className="terminal-secondary min-h-0 px-4 py-2 text-sm" onClick={() => void refreshPanels()} type="button">
                    <RefreshCcw className="mr-2 size-3.5" />
                    Refresh
                  </button>
                  {canWriteOps ? (
                    <button
                      className="terminal-primary min-h-0 px-4 py-2 text-sm"
                      disabled={isUploading || !control?.intake.upload_enabled}
                      onClick={() => inputRef.current?.click()}
                      type="button"
                    >
                      <UploadCloud className="mr-2 size-4" />
                      {isUploading ? "Uploading..." : "Choose files"}
                    </button>
                  ) : null}
                </div>
              }
            />

            <div
              className={`upload-dropzone mt-5 ${dragActive ? "is-dragover" : ""} ${canWriteOps ? "" : "is-disabled"}`}
              onDragEnter={(event) => {
                event.preventDefault();
                if (canWriteOps) {
                  setDragActive(true);
                }
              }}
              onDragLeave={(event) => {
                event.preventDefault();
                setDragActive(false);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => void onDrop(event)}
              role="presentation"
            >
              <div className="flex size-12 items-center justify-center rounded-[8px] border border-line bg-brandSoft text-brand">
                <UploadCloud className="size-5" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-base font-semibold text-ink">
                  {canWriteOps ? "Drop invoice files here or choose them manually." : "Read-only intake visibility is active."}
                </div>
                <p className="mt-2 text-sm leading-6 text-slate">
                  {canWriteOps
                    ? "Each file is posted through the single-file intake API, logged in the database, then picked up by the existing worker."
                    : "Public demo can inspect queue state, readiness, and alerts, but only admin or ops users can stage new invoice files."}
                </p>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge tone="neutral">{control?.intake.directory || "No intake directory configured"}</Badge>
                  <Badge tone="neutral">{(control?.intake.accepted_extensions ?? ACCEPTED_UPLOAD_TYPES).join(", ")}</Badge>
                  <Badge tone={control?.intake.upload_enabled ? "ok" : "danger"}>
                    {control?.intake.upload_enabled ? "Upload enabled" : "Upload blocked"}
                  </Badge>
                </div>
              </div>
              <input
                accept={ACCEPTED_UPLOAD_TYPES.join(",")}
                className="hidden"
                disabled={isUploading || !canWriteOps || !control?.intake.upload_enabled}
                multiple
                onChange={(event) => void queueFiles(event.target.files)}
                ref={inputRef}
                type="file"
              />
            </div>

            {uploadMessage ? (
              <p className={`mt-4 text-sm font-medium ${uploadTone === "danger" ? "text-rose" : uploadTone === "ok" ? "text-mint" : "text-slate"}`}>
                {uploadMessage}
              </p>
            ) : null}

            <div className="mt-5 grid gap-3 md:grid-cols-3">
              <div className="terminal-row dense-row">
                <div className="text-sm text-slate">Watched files</div>
                <div className="mt-2 text-xl font-semibold text-ink">{control?.intake.total_files ?? 0}</div>
                <p className="mt-2 text-xs text-slate">{formatBytes(control?.intake.total_bytes ?? 0)} across the intake folder.</p>
              </div>
              <div className="terminal-row dense-row">
                <div className="text-sm text-slate">Recent file types</div>
                <div className="mt-2 text-xl font-semibold text-ink">
                  {Object.keys(control?.intake.extension_breakdown ?? {}).length || 0}
                </div>
                <p className="mt-2 text-xs text-slate">
                  {Object.entries(control?.intake.extension_breakdown ?? {})
                    .map(([extension, count]) => `${extension} ${count}`)
                    .join(" / ") || "No staged files yet."}
                </p>
              </div>
              <div className="terminal-row dense-row">
                <div className="text-sm text-slate">Pipeline total</div>
                <div className="mt-2 text-xl font-semibold text-ink">{pipelineCounts.total}</div>
                <p className="mt-2 text-xs text-slate">Queued, processing, ingested, and failed upload logs combined.</p>
              </div>
            </div>

            <div className="mt-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="mono-label text-brand">Current intake queue</p>
                  <p className="mt-2 text-sm text-slate">Immediate per-file feedback before the persistent history refreshes.</p>
                </div>
                <Badge tone={localUploads.length ? "warn" : "neutral"}>{localUploads.length} local items</Badge>
              </div>
              <div className="mt-4 space-y-3">
                {localUploads.length ? (
                  localUploads.map((item) => {
                    const Icon = statusIcon(item.status);
                    return (
                      <div key={item.localId} className={`upload-queue-item status-${item.status}`}>
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="truncate font-semibold text-ink">{item.name}</div>
                            <p className="mt-1 text-xs text-slate">
                              {item.extension} / {formatBytes(item.sizeBytes)}
                            </p>
                          </div>
                          <Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
                        </div>
                        <div className="mt-3 flex items-start gap-2 text-sm text-slate">
                          <Icon className="mt-0.5 size-4 shrink-0 text-brand" />
                          <span>{item.message}</span>
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div className="terminal-row dense-row text-sm text-slate">
                    Drop files or choose them from disk to start the next intake sequence.
                  </div>
                )}
              </div>
            </div>
          </Surface>

          <Surface className="stagger-in dense-surface">
            <SectionHeader
              kicker="History"
              title="Recent intake history"
              copy="Persistent upload logs survive page refreshes so operators can tell what is still queued, what is already ingested, and which files need a retry."
            />
            <div className="status-group-grid mt-5">
              {uploadStatusGroups(history).map((group) => (
                <div key={group.key} className="history-column">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-ink">{group.title}</div>
                      <p className="mt-1 text-xs leading-5 text-slate">{group.description}</p>
                    </div>
                    <Badge tone={statusTone(group.key)}>{group.items.length}</Badge>
                  </div>
                  <div className="history-list mt-4">
                    {group.items.length ? (
                      group.items.map((item) => (
                        <div key={item.id} className={`upload-history-card status-${item.status}`}>
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <div className="truncate font-semibold text-ink">{item.original_name}</div>
                              <p className="mt-1 truncate text-xs text-slate">{item.staged_name}</p>
                            </div>
                            <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                          </div>
                          <div className="mt-3 text-xs leading-5 text-slate">
                            {formatBytes(item.size_bytes)} / {formatDate(item.updated_at || item.created_at)}
                          </div>
                          {item.invoice_id ? (
                            <div className="mt-3">
                              <Link className="text-xs font-semibold text-brand" href={`/app/invoices/${item.invoice_id}`}>
                                Open invoice #{item.invoice_id}
                              </Link>
                            </div>
                          ) : null}
                          {item.error_message ? <p className="mt-3 text-xs leading-5 text-rose">{item.error_message}</p> : null}
                        </div>
                      ))
                    ) : (
                      <div className="terminal-row dense-row text-sm text-slate">No {group.title.toLowerCase()} uploads yet.</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Surface>
        </div>

        <div className="space-y-4">
          <Surface className="stagger-in dense-surface">
            <SectionHeader
              kicker="Preflight"
              title="Readiness wall"
              copy="Configuration, database reachability, and schema tracking stay explicit here so operators can spot blocked environments before assuming the stack is healthy."
            />
            <div className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-1">
              {readinessChecks.map(([name, check]) => (
                <div key={name} className={`terminal-row dense-row ${check.ok ? "status-ingested" : "status-failed"}`}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold uppercase tracking-[0.08em] text-ink">{name}</div>
                    <Badge tone={check.ok ? "ok" : "danger"}>{check.ok ? "Ready" : "Check"}</Badge>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate">{check.detail}</p>
                  {check.latest_file ? (
                    <p className="mt-3 text-xs text-slate">
                      Latest schema file {check.latest_file}
                      {check.applied_at ? ` / ${formatDate(check.applied_at)}` : ""}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </Surface>

          <Surface className="stagger-in dense-surface">
            <SectionHeader
              kicker="Operator shortcuts"
              title="Recovery, mail, and queue pivots"
              copy="Move from intake monitoring to replay or review without leaving the website."
            />
            <div className="mt-5 grid gap-3">
              <LinkCard
                copy="Open connector posture, replay failed Feishu syncs, and run live health checks from the dedicated recovery surface."
                href="/app/ops"
                kicker="Recovery"
                title="Ops Center"
              />
              <LinkCard
                copy="Jump into the working slice when a new upload or risk alert needs immediate manual review."
                href="/app/queue"
                kicker="Execution"
                title="Review Queue"
              />
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {control?.mailpit_url ? (
                <a className="terminal-secondary min-h-0 px-4 py-2 text-sm" href={control.mailpit_url}>
                  <Mail className="mr-2 size-4" />
                  Open Mailpit
                </a>
              ) : null}
              <button className="terminal-button min-h-0 px-4 py-2 text-sm" onClick={() => void refreshPanels()} type="button">
                <FolderOpen className="mr-2 size-4" />
                Refresh control room
              </button>
            </div>
          </Surface>

          <Surface className="stagger-in dense-surface">
            <SectionHeader
              kicker="Alert summary"
              title="Risk delivery posture"
              copy="Risk notification counts and recent alert rows remain visible so operators can tell whether a queue problem is upstream, downstream, or both."
            />
            <div className="mt-5 grid gap-3 md:grid-cols-3 xl:grid-cols-3">
              <div className="terminal-row dense-row">
                <div className="text-sm text-slate">Queued alerts</div>
                <div className="mt-2 text-xl font-semibold text-ink">{control?.alerts.queued_count ?? 0}</div>
              </div>
              <div className="terminal-row dense-row">
                <div className="text-sm text-slate">Personal sent</div>
                <div className="mt-2 text-xl font-semibold text-ink">{control?.alerts.personal_sent_count ?? 0}</div>
              </div>
              <div className="terminal-row dense-row">
                <div className="text-sm text-slate">Leader sent</div>
                <div className="mt-2 text-xl font-semibold text-ink">{control?.alerts.leader_sent_count ?? 0}</div>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {(control?.alerts.recent_items ?? []).map((item) => (
                <div key={`${item.invoice_id}-${item.alert_at}`} className="terminal-row dense-row status-failed">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-ink">
                        #{item.invoice_id} {item.seller_name || "Unknown seller"}
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate">{item.risk_reason_summary}</p>
                    </div>
                    <AlertTriangle className="size-4 shrink-0 text-rose" />
                  </div>
                  <p className="mt-3 text-xs leading-5 text-slate">
                    PO {item.purchase_order_no || "-"} / delta {formatMoney(item.amount_diff)} / personal {item.notify_personal_status || "-"} / leader {item.notify_leader_status || "-"}
                  </p>
                </div>
              ))}
            </div>
          </Surface>
        </div>
      </div>
    </AppShell>
  );
}
