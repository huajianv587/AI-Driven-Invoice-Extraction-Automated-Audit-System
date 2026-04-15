"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { Badge, SectionHeader, Surface } from "@/components/ui";
import { useAuth } from "@/components/auth-provider";
import type { InvoiceDetail } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";

function jsonPreview(value: unknown) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2);
  return text.length > 520 ? `${text.slice(0, 520)}...` : text;
}

export default function InvoiceDetailPage() {
  const params = useParams<{ id: string }>();
  const { authFetch } = useAuth();
  const invoiceId = Number(params.id);
  const query = useQuery({
    queryKey: ["invoice-detail", invoiceId],
    queryFn: async () => (await (await authFetch(`/api/invoices/${invoiceId}`)).json()) as InvoiceDetail
  });

  const detail = query.data;

  return (
    <AppShell
      title={`Invoice #${invoiceId}`}
      subtitle="Inspect captured document facts, purchase order alignment, line items, machine payloads, and audit history in one premium detail surface."
    >
      {query.isError ? (
        <Surface>
          <p className="mono-label text-brand">Case lookup</p>
          <h3 className="mt-3 text-2xl font-semibold tracking-tight text-ink">Invoice unavailable</h3>
          <p className="mt-3 text-sm leading-7 text-slate">
            This invoice could not be loaded. Use the review queue to reopen an active case.
          </p>
        </Surface>
      ) : !detail ? (
        <Surface>
          <div className="text-lg font-semibold text-ink">Loading invoice detail...</div>
          <p className="mt-2 text-sm text-slate">Restoring document facts, line items, and audit history.</p>
        </Surface>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Surface><p className="mono-label text-brand">Invoice amount</p><div className="mt-3 text-3xl font-semibold text-ink">{formatMoney(detail.invoice.total_amount_with_tax)}</div></Surface>
            <Surface><p className="mono-label text-brand">Expected amount</p><div className="mt-3 text-3xl font-semibold text-ink">{formatMoney(detail.invoice.expected_amount)}</div></Surface>
            <Surface><p className="mono-label text-brand">Delta</p><div className="mt-3 text-3xl font-semibold text-rose">{formatMoney(detail.invoice.amount_diff)}</div></Surface>
            <Surface><p className="mono-label text-brand">Current status</p><div className="mt-3"><Badge tone="warn">{detail.invoice.invoice_status || "Pending"}</Badge></div></Surface>
          </div>

          <div className="grid gap-4 md:grid-cols-[1.05fr_0.95fr]">
            <Surface>
              <SectionHeader kicker="Case facts" title="Document summary" copy={detail.invoice.risk_reason_summary || "Review invoice and PO alignment."} />
              <div className="mt-6 grid gap-3 md:grid-cols-2">
                <div className="rounded-[20px] border border-line bg-[#f8fbff] p-4"><div className="text-sm text-slate">Seller</div><div className="mt-2 font-semibold text-ink">{detail.invoice.seller_name || "-"}</div></div>
                <div className="rounded-[20px] border border-line bg-[#f8fbff] p-4"><div className="text-sm text-slate">Buyer</div><div className="mt-2 font-semibold text-ink">{detail.invoice.buyer_name || "-"}</div></div>
                <div className="rounded-[20px] border border-line bg-[#f8fbff] p-4"><div className="text-sm text-slate">Invoice date</div><div className="mt-2 font-semibold text-ink">{formatDate(detail.invoice.invoice_date)}</div></div>
                <div className="rounded-[20px] border border-line bg-[#f8fbff] p-4"><div className="text-sm text-slate">PO number</div><div className="mt-2 font-semibold text-ink">{detail.invoice.purchase_order_no || "-"}</div></div>
              </div>
              <div className="mt-6 rounded-[22px] border border-line bg-white p-4">
                <div className="text-sm font-semibold text-ink">Evidence preview</div>
                <p className="mt-2 text-sm leading-6 text-slate">
                  Source file: {detail.invoice.source_file_path || "No source file path captured."}
                </p>
                <pre className="mt-3 max-h-48 overflow-auto rounded-2xl bg-[#0f172a] p-4 text-xs leading-5 text-white/85">
                  {jsonPreview(detail.invoice.raw_ocr_json)}
                </pre>
              </div>
              <div className="mt-6">
                <Link className="text-sm font-semibold text-brand" href={`/app/review/${invoiceId}`}>Open Review Desk</Link>
              </div>
            </Surface>

            <Surface>
              <SectionHeader kicker="Cloud mirror" title="Sync posture" copy="See whether the document already reached Feishu and whether replay is required." />
              <div className="mt-6 rounded-[20px] border border-line bg-[#f8fbff] p-4">
                <Badge tone={detail.sync.sync_tone as "neutral" | "ok" | "warn" | "danger"}>{detail.sync.sync_label}</Badge>
                <p className="mt-4 text-sm text-slate">{detail.sync.sync_error || "No sync error is currently recorded for this invoice."}</p>
              </div>
              <div className="mt-6 rounded-[20px] border border-line bg-[#f8fbff] p-4">
                <div className="text-sm text-slate">Purchase order owner</div>
                <div className="mt-2 font-semibold text-ink">{detail.purchase_order?.purchaser_name || "-"}</div>
                <div className="mt-3 text-sm text-slate">{detail.purchase_order?.purchaser_email || "No purchaser email on file."}</div>
              </div>
              <div className="mt-6 rounded-[20px] border border-line bg-[#f8fbff] p-4">
                <div className="text-sm text-slate">Invoice vs PO difference</div>
                <div className={Math.abs(detail.invoice.amount_diff) > 0 ? "mt-2 text-2xl font-semibold text-rose" : "mt-2 text-2xl font-semibold text-mint"}>
                  {formatMoney(detail.invoice.amount_diff)}
                </div>
                <p className="mt-3 text-sm leading-6 text-slate">
                  {detail.invoice.risk_flag ? detail.invoice.risk_reason_summary : "No active risk flag; values match the current purchase order."}
                </p>
              </div>
            </Surface>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Surface>
              <SectionHeader kicker="Line items" title="Extracted invoice rows" copy="Review parsed units, quantities, and tax amounts before sign-off." />
              <div className="mt-6 space-y-3">
                {detail.items.map((item, index) => (
                  <div key={`${item.id}-${index}`} className="rounded-[20px] border border-line bg-[#f8fbff] p-4">
                    <div className="font-semibold text-ink">{item.item_name || `Line ${index + 1}`}</div>
                    <p className="mt-2 text-sm text-slate">
                      Qty {item.item_quantity ?? "-"} | Unit {item.item_unit || "-"} | Amount {formatMoney(item.item_amount ?? 0)}
                    </p>
                  </div>
                ))}
              </div>
            </Surface>

            <Surface>
              <SectionHeader kicker="Audit trail" title="Events and manual decisions" copy="System events and reviewer actions remain visible for downstream traceability." />
              <div className="mt-6 space-y-3">
                {detail.state_transitions.map((transition) => (
                  <div key={`transition-${transition.id}`} className="rounded-[20px] border border-line bg-[#f8fbff] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-semibold text-ink">{transition.from_status || "New"}{" -> "}{transition.to_status}</div>
                      <div className="text-xs uppercase tracking-[0.12em] text-slate">{transition.actor_role || "system"}</div>
                    </div>
                    <p className="mt-2 text-sm text-slate">{transition.reason || "No transition reason recorded."}</p>
                  </div>
                ))}
                {detail.review_tasks.slice(0, 3).map((task) => (
                  <div key={`review-${task.id}`} className="rounded-[20px] border border-line bg-[#f8fbff] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-semibold text-ink">Review: {task.review_result}</div>
                      <div className="text-xs uppercase tracking-[0.12em] text-slate">{task.source_channel || "web_app"}</div>
                    </div>
                    <p className="mt-2 text-sm text-slate">{task.handling_note || "No reviewer note recorded."}</p>
                  </div>
                ))}
                {detail.events.map((event) => (
                  <div key={event.id} className="rounded-[20px] border border-line bg-[#f8fbff] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="font-semibold text-ink">{event.event_type}</div>
                      <div className="text-xs uppercase tracking-[0.12em] text-slate">{event.event_status}</div>
                    </div>
                    <p className="mt-2 text-sm text-slate">{formatDate(event.created_at)}</p>
                  </div>
                ))}
              </div>
            </Surface>
          </div>
        </>
      )}
    </AppShell>
  );
}
