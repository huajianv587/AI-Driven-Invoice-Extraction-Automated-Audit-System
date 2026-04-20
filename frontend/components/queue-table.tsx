"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  type RowSelectionState,
  useReactTable,
  type VisibilityState
} from "@tanstack/react-table";

import { useAuth } from "@/components/auth-provider";
import { Badge, Surface } from "@/components/ui";
import type { InvoiceListItem } from "@/lib/types";
import { formatDate, formatMoney } from "@/lib/utils";

const columnHelper = createColumnHelper<InvoiceListItem>();

export function QueueTable({ items, onChanged }: { items: InvoiceListItem[]; onChanged?: () => void }) {
  const { authFetch, user } = useAuth();
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [batchMessage, setBatchMessage] = useState("");
  const canReview = !user?.is_public_demo && (user?.role === "admin" || user?.role === "reviewer");
  const columns = useMemo(
    () => [
      columnHelper.display({
        id: "select",
        header: ({ table }) => (
          <input
            aria-label="Select all invoices"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            type="checkbox"
          />
        ),
        cell: ({ row }) => (
          <input
            aria-label={`Select invoice ${row.original.id}`}
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            type="checkbox"
          />
        ),
        enableHiding: false
      }),
      columnHelper.accessor("id", {
        header: "Invoice",
        cell: (info) => <span className="font-semibold text-ink">#{info.getValue()}</span>
      }),
      columnHelper.accessor("seller_name", {
        header: "Seller",
        cell: (info) => (
          <div>
            <div className="font-medium text-ink">{info.getValue() || "Unknown seller"}</div>
            <div className="text-xs text-slate">{info.row.original.purchase_order_no || "No PO"}</div>
          </div>
        )
      }),
      columnHelper.accessor("invoice_date", {
        header: "Date",
        cell: (info) => <span className="text-sm text-slate">{formatDate(info.getValue())}</span>
      }),
      columnHelper.accessor("total_amount_with_tax", {
        header: "Amount",
        cell: (info) => <span className="font-medium text-ink">{formatMoney(info.getValue())}</span>
      }),
      columnHelper.accessor("amount_diff", {
        header: "Delta",
        cell: (info) => (
          <span className={info.getValue() > 0 ? "font-medium text-rose" : "font-medium text-ink"}>
            {formatMoney(info.getValue())}
          </span>
        )
      }),
      columnHelper.accessor("invoice_status", {
        header: "Status",
        cell: (info) => (
          <Badge tone={info.getValue() === "Approved" ? "ok" : info.getValue() === "Rejected" ? "danger" : "warn"}>
            {info.getValue() || "Pending"}
          </Badge>
        )
      }),
      columnHelper.accessor("sync_label", {
        header: "Sync",
        cell: (info) => <Badge tone={info.row.original.sync_tone as "neutral" | "ok" | "warn" | "danger"}>{info.getValue()}</Badge>
      }),
      columnHelper.display({
        id: "actions",
        header: "Action",
        enableHiding: false,
        cell: (info) => (
          <div className="flex gap-3 text-sm font-medium text-brand">
            <Link href={`/app/invoices/${info.row.original.id}`}>Details</Link>
            {canReview ? <Link href={`/app/review/${info.row.original.id}`}>Review</Link> : null}
          </div>
        )
      })
    ],
    [canReview]
  );

  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => String(row.id),
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    state: { columnVisibility, rowSelection }
  });
  const selectedRows = table.getSelectedRowModel().rows.map((row) => row.original);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("invoice-queue-column-visibility");
      if (saved) {
        setColumnVisibility(JSON.parse(saved) as VisibilityState);
      }
    } catch {
      setColumnVisibility({});
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("invoice-queue-column-visibility", JSON.stringify(columnVisibility));
    } catch {
      return;
    }
  }, [columnVisibility]);

  const bulkMarkNeedsReview = async () => {
    if (!canReview || !selectedRows.length) {
      return;
    }
    setBatchMessage("");
    const results = await Promise.allSettled(
      selectedRows.map((item) =>
        authFetch(`/api/invoices/${item.id}/review`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": `queue-bulk-needs-review-${item.id}` },
          body: JSON.stringify({
            handler_user: user?.full_name || "Queue reviewer",
            handling_note: "Bulk queue action: marked for manual review so finance can resolve evidence gaps.",
            review_result: "NeedsReview"
          })
        })
      )
    );
    const failed = results.filter((result) => result.status === "rejected");
    if (failed.length === 0) {
      setRowSelection({});
      setBatchMessage(`Bulk action complete: ${selectedRows.length} invoice(s) marked NeedsReview.`);
      onChanged?.();
    } else {
      const firstError = failed[0] as PromiseRejectedResult;
      setBatchMessage(
        `Bulk action partially failed: ${selectedRows.length - failed.length} saved, ${failed.length} need retry. ${
          firstError.reason instanceof Error ? firstError.reason.message : ""
        }`
      );
      onChanged?.();
    }
  };

  return (
    <Surface className="overflow-hidden p-0">
      <div className="flex flex-col gap-3 border-b border-line bg-white/5 px-4 py-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-sm font-semibold text-ink">{selectedRows.length} selected</div>
          <p className="text-xs text-slate">
            {canReview ? "Customize columns and use safe bulk handling for triage work." : "Public demo is read-only; sign in to submit review actions."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {table
            .getAllLeafColumns()
            .filter((column) => column.getCanHide())
            .map((column) => (
              <label key={column.id} className="rounded-[8px] border border-line bg-white/5 px-3 py-2 text-xs font-semibold text-slate">
                <input
                  checked={column.getIsVisible()}
                  className="mr-2"
                  onChange={column.getToggleVisibilityHandler()}
                  type="checkbox"
                />
                {column.columnDef.header?.toString() || column.id}
              </label>
            ))}
          {canReview ? (
            <button
              className="terminal-primary min-h-0 px-4 py-2 text-xs"
              disabled={!selectedRows.length}
              onClick={() => void bulkMarkNeedsReview()}
              type="button"
            >
              Mark NeedsReview
            </button>
          ) : null}
        </div>
        {batchMessage ? <p className="text-sm font-medium text-slate">{batchMessage}</p> : null}
      </div>

      <div className="md:hidden">
        {table.getRowModel().rows.length ? (
          <div className="space-y-3 p-4">
            {table.getRowModel().rows.map((row) => {
              const item = row.original;
              return (
                <article key={row.id} className="terminal-row queue-mobile-card">
                  <div className="flex items-start justify-between gap-3">
                    <label className="flex items-center gap-3 text-sm font-semibold text-ink">
                      <input
                        aria-label={`Select invoice ${item.id}`}
                        checked={row.getIsSelected()}
                        onChange={row.getToggleSelectedHandler()}
                        type="checkbox"
                      />
                      <span>#{item.id}</span>
                    </label>
                    <Badge tone={item.invoice_status === "Approved" ? "ok" : item.invoice_status === "Rejected" ? "danger" : "warn"}>
                      {item.invoice_status || "Pending"}
                    </Badge>
                  </div>
                  <div className="mt-3">
                    <div className="text-base font-semibold text-ink">{item.seller_name || "Unknown seller"}</div>
                    <p className="mt-1 text-xs text-slate">{item.purchase_order_no || "No PO linked"}</p>
                  </div>
                  <div className="queue-metric-grid mt-4 text-sm">
                    <div className="queue-metric-tile">
                      <div className="text-xs text-slate">Amount</div>
                      <div className="mt-1 font-semibold text-ink">{formatMoney(item.total_amount_with_tax)}</div>
                    </div>
                    <div className="queue-metric-tile">
                      <div className="text-xs text-slate">Delta</div>
                      <div className={`mt-1 font-semibold ${item.amount_diff > 0 ? "text-rose" : "text-ink"}`}>{formatMoney(item.amount_diff)}</div>
                    </div>
                    <div className="queue-metric-tile">
                      <div className="text-xs text-slate">Date</div>
                      <div className="mt-1 font-semibold text-ink">{formatDate(item.invoice_date)}</div>
                    </div>
                    <div className="queue-metric-tile">
                      <div className="text-xs text-slate">Sync</div>
                      <div className="mt-1">
                        <Badge tone={item.sync_tone as "neutral" | "ok" | "warn" | "danger"}>{item.sync_label}</Badge>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 rounded-[8px] border border-line bg-white/5 px-3 py-2.5">
                    <div className="text-xs uppercase tracking-[0.12em] text-slate">Risk summary</div>
                    <p className="mt-1.5 text-sm leading-6 text-slate">{item.risk_reason_summary || "No risk summary captured."}</p>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Link className="terminal-secondary min-h-0 px-3 py-2 text-xs" href={`/app/invoices/${item.id}`}>
                      Details
                    </Link>
                    {canReview ? (
                      <Link className="terminal-primary min-h-0 px-3 py-2 text-xs" href={`/app/review/${item.id}`}>
                        Review
                      </Link>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="px-6 py-12 text-center">
            <div className="mx-auto max-w-md">
              <div className="text-lg font-semibold text-ink">No invoices match this view</div>
              <p className="mt-2 text-sm leading-6 text-slate">
                Try clearing the search term, changing status, or turning off risk-only mode.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="hidden overflow-x-auto md:block">
        <table className="terminal-table min-w-full">
          <thead className="bg-white/5">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="text-left">
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="align-top">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td className="px-6 py-12 text-center" colSpan={columns.length}>
                  <div className="mx-auto max-w-md">
                    <div className="text-lg font-semibold text-ink">No invoices match this view</div>
                    <p className="mt-2 text-sm leading-6 text-slate">
                      Try clearing the search term, changing status, or turning off risk-only mode.
                    </p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Surface>
  );
}
