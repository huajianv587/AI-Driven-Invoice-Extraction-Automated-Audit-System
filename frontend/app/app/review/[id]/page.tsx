"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import { ReviewForm } from "@/components/review-form";
import { Badge, SectionHeader, Surface } from "@/components/ui";
import type { InvoiceDetail } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";

function evidencePreview(detail: InvoiceDetail) {
  const raw =
    typeof detail.invoice.raw_ocr_json === "string"
      ? detail.invoice.raw_ocr_json
      : JSON.stringify(detail.invoice.raw_ocr_json ?? {}, null, 2);
  return raw.length > 420 ? `${raw.slice(0, 420)}...` : raw;
}

export default function ReviewPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const { authFetch, user } = useAuth();
  const invoiceId = Number(params.id);
  const query = useQuery({
    queryKey: ["review-detail", invoiceId],
    queryFn: async () => (await (await authFetch(`/api/invoices/${invoiceId}`)).json()) as InvoiceDetail
  });
  const detail = query.data;

  const decisionPanel = detail ? (
    <div className="space-y-4">
      <Surface className="stagger-in dense-surface status-processing">
        <p className="mono-label text-brand">Decision diff</p>
        <h3 className="mt-2 text-xl font-semibold text-ink">Invoice vs purchase order</h3>
        <div className="mt-4 grid gap-3">
          <div className="flex items-center justify-between rounded-[8px] border border-line bg-white/5 px-3 py-2.5 text-sm">
            <span className="text-slate">Supplier</span>
            <span className="font-semibold text-ink">
              {detail.invoice.seller_name || "-"} / {detail.purchase_order?.supplier_name || "-"}
            </span>
          </div>
          <div className="flex items-center justify-between rounded-[8px] border border-line bg-white/5 px-3 py-2.5 text-sm">
            <span className="text-slate">Amount gap</span>
            <span className={Math.abs(detail.invoice.amount_diff) > 0 ? "font-semibold text-rose" : "font-semibold text-mint"}>
              {formatMoney(detail.invoice.amount_diff)}
            </span>
          </div>
          <div className="flex items-center justify-between rounded-[8px] border border-line bg-white/5 px-3 py-2.5 text-sm">
            <span className="text-slate">Risk signal</span>
            <span className="font-semibold text-ink">
              {detail.invoice.risk_flag ? detail.invoice.risk_reason_summary : "No active risk flag"}
            </span>
          </div>
        </div>
      </Surface>

      <Surface className="stagger-in dense-surface status-processing">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="mono-label text-brand">Current workflow state</p>
            <h3 className="mt-2 text-xl font-semibold text-ink">Case routing status</h3>
          </div>
          <Badge tone={detail.sync.sync_tone as "neutral" | "ok" | "warn" | "danger"}>{detail.sync.sync_label}</Badge>
        </div>
        <p className="mt-4 text-sm text-slate">{detail.sync.sync_error || "No sync error is blocking the current writeback path."}</p>
      </Surface>

      {!user?.is_public_demo && (user?.role === "admin" || user?.role === "reviewer") ? (
        <ReviewForm
          defaults={{
            handler_user: detail.invoice.handler_user || user?.full_name || "",
            handling_note: detail.invoice.handler_reason || "",
            review_result:
              (detail.invoice.invoice_status as "Pending" | "Approved" | "Rejected" | "NeedsReview") || "Pending"
          }}
          invoiceId={invoiceId}
          onSuccess={() => {
            void query.refetch();
            router.refresh();
          }}
        />
      ) : (
        <Surface className="stagger-in dense-surface">
          <p className="mono-label text-brand">Role policy</p>
          <h3 className="mt-3 text-2xl font-semibold tracking-tight text-ink">Read-only review access</h3>
          <p className="mt-3 text-sm leading-7 text-slate">
            Public demo and ops users can inspect case context but cannot commit review outcomes. Use an admin or reviewer account for writeback.
          </p>
        </Surface>
      )}
    </div>
  ) : null;

  return (
    <AppShell
      title={`Review Desk #${invoiceId}`}
      subtitle="Resolve the exception with a dual-column workflow that keeps evidence, queue context, and writeback aligned."
    >
      {query.isError ? (
        <Surface>
          <p className="mono-label text-brand">Case lookup</p>
          <h3 className="mt-3 text-2xl font-semibold tracking-tight text-ink">Invoice unavailable</h3>
          <p className="mt-3 text-sm leading-7 text-slate">
            This invoice could not be loaded. It may have been removed from the demo reset or your session may need to be restored.
          </p>
        </Surface>
      ) : !detail ? (
        <Surface>
          <div className="text-lg font-semibold text-ink">Loading review desk...</div>
          <p className="mt-2 text-sm text-slate">Collecting facts, audit history, and review state.</p>
        </Surface>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1.02fr_0.98fr]">
          <div className="space-y-4">
            <Surface className="stagger-in dense-surface">
              <SectionHeader
                kicker="Case brief"
                title={detail.invoice.seller_name || "Unknown seller"}
                copy={detail.invoice.risk_reason_summary || "Review the case before sign-off."}
              />
              <div className="mt-6 grid gap-3 md:grid-cols-2">
                <div className="terminal-row dense-row">
                  <div className="text-sm text-slate">Invoice amount</div>
                  <div className="mt-2 text-xl font-semibold text-ink">{formatMoney(detail.invoice.total_amount_with_tax)}</div>
                </div>
                <div className="terminal-row dense-row">
                  <div className="text-sm text-slate">Expected amount</div>
                  <div className="mt-2 text-xl font-semibold text-ink">{formatMoney(detail.invoice.expected_amount)}</div>
                </div>
                <div className="terminal-row dense-row">
                  <div className="text-sm text-slate">Delta</div>
                  <div className="mt-2 text-xl font-semibold text-rose">{formatMoney(detail.invoice.amount_diff)}</div>
                </div>
                <div className="terminal-row dense-row">
                  <div className="text-sm text-slate">Invoice date</div>
                  <div className="mt-2 text-xl font-semibold text-ink">{formatDate(detail.invoice.invoice_date)}</div>
                </div>
              </div>
              <div className="terminal-row dense-row mt-4">
                <div className="text-sm font-semibold text-ink">Evidence preview</div>
                <p className="mt-2 text-sm leading-6 text-slate">
                  Source: {detail.invoice.source_file_path || "No source file path captured."}
                </p>
                <pre className="mt-3 max-h-44 overflow-auto border border-line bg-black/30 p-4 text-xs leading-5 text-white/85">
                  {evidencePreview(detail)}
                </pre>
              </div>
            </Surface>

            <div className="xl:hidden">{decisionPanel}</div>

            <Surface className="stagger-in dense-surface">
              <SectionHeader
                kicker="Approval checklist"
                title="Before you commit a decision"
                copy="Confirm identity, amount outcome, and downstream communication so the audit story stays coherent."
              />
              <div className="mt-6 space-y-3">
                {[
                  "Validate the supplier, buyer, tax IDs, and purchase order alignment.",
                  "Explain whether the delta is accepted, rejected, or escalated in finance language.",
                  "Make sure queue status, event history, and Feishu sync tell the same story."
                ].map((item, index) => (
                  <div key={item} className="terminal-row dense-row">
                    <div className="flex items-start gap-3">
                      <div className="flex size-8 items-center justify-center rounded-full bg-brandSoft font-semibold text-brand">
                        {index + 1}
                      </div>
                      <p className="text-sm leading-6 text-slate">{item}</p>
                    </div>
                  </div>
                ))}
              </div>
            </Surface>

            <Surface className="stagger-in dense-surface">
              <SectionHeader
                kicker="Audit timeline"
                title="What changed before this decision"
                copy="State transitions, review tasks, and system events stay visible beside the approval action."
              />
              <div className="mt-6 space-y-3">
                {detail.state_transitions.slice(0, 4).map((transition) => (
                  <div key={`transition-${transition.id}`} className="terminal-row dense-row">
                    <div className="font-semibold text-ink">
                      {transition.from_status || "New"} {"->"} {transition.to_status}
                    </div>
                    <p className="mt-2 text-sm text-slate">{transition.reason || "No transition reason recorded."}</p>
                  </div>
                ))}
                {detail.events.slice(0, 4).map((event) => (
                  <div key={`event-${event.id}`} className="terminal-row dense-row">
                    <div className="font-semibold text-ink">{event.event_type}</div>
                    <p className="mt-2 text-sm text-slate">
                      {event.event_status} / {formatDate(event.created_at)}
                    </p>
                  </div>
                ))}
              </div>
            </Surface>
          </div>

          <div className="hidden space-y-4 xl:sticky xl:top-5 xl:block">{decisionPanel}</div>
        </div>
      )}
    </AppShell>
  );
}
