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
  const canReview = user?.role === "admin" || user?.role === "reviewer";
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
    try {
      await Promise.all(
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
      setRowSelection({});
      setBatchMessage(`Bulk action complete: ${selectedRows.length} invoice(s) marked NeedsReview.`);
      onChanged?.();
    } catch (error) {
      setBatchMessage(error instanceof Error ? `Bulk action failed: ${error.message}` : "Bulk action failed.");
    }
  };

  return (
    <Surface className="overflow-hidden p-0">
      <div className="flex flex-col gap-3 border-b border-line bg-[#f8fbff] p-4 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="text-sm font-semibold text-ink">{selectedRows.length} selected</div>
          <p className="text-xs text-slate">Customize columns and use safe bulk handling for triage work.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {table
            .getAllLeafColumns()
            .filter((column) => column.getCanHide())
            .map((column) => (
              <label key={column.id} className="rounded-full border border-line bg-white px-3 py-2 text-xs font-semibold text-slate">
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
              className="rounded-full bg-brand px-4 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
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
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse">
          <thead className="bg-[#f8fbff]">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="border-b border-line px-4 py-4 text-left text-xs font-semibold uppercase tracking-[0.12em] text-slate"
                  >
                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length ? (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-b border-line/70 last:border-b-0 hover:bg-[#fcfdff]">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-4 align-top">
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
