"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { QueueTable } from "@/components/queue-table";
import { SectionHeader, StatCard, Surface } from "@/components/ui";
import { useAuth } from "@/components/auth-provider";
import type { InvoiceListResponse } from "@/lib/types";
import { formatMoney } from "@/lib/utils";

export default function QueuePage() {
  const { authFetch } = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All");
  const [riskOnly, setRiskOnly] = useState(false);
  const [sort, setSort] = useState("newest");

  const query = useQuery({
    queryKey: ["queue", search, status, riskOnly, sort],
    queryFn: async () => {
      const params = new URLSearchParams({
        search,
        status,
        sort,
        risk_only: String(riskOnly),
        limit: "80"
      });
      return (await (await authFetch(`/api/invoices?${params.toString()}`)).json()) as InvoiceListResponse;
    }
  });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setSearch(params.get("search") ?? "");
  }, []);

  return (
    <AppShell
      title="Review Queue"
      subtitle="Search, narrow, and prioritize the working slice without losing the premium app shell or deep links into case detail."
    >
      <Surface>
        <SectionHeader
          kicker="Controls"
          title="Search, filter, and order"
          copy="Keep the queue precise enough for execution and broad enough for operational awareness."
        />
        <div className="mt-6 grid gap-4 md:grid-cols-[1.45fr_0.75fr_0.75fr_0.85fr]">
          <input
            className="rounded-2xl border border-line bg-white px-4 py-3 outline-none"
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Seller, buyer, invoice, or PO"
            value={search}
          />
          <select className="rounded-2xl border border-line bg-white px-4 py-3 outline-none" onChange={(event) => setStatus(event.target.value)} value={status}>
            <option>All</option>
            <option>Pending</option>
            <option>Approved</option>
            <option>Rejected</option>
            <option>NeedsReview</option>
          </select>
          <select className="rounded-2xl border border-line bg-white px-4 py-3 outline-none" onChange={(event) => setSort(event.target.value)} value={sort}>
            <option value="newest">Newest first</option>
            <option value="risk">Risk first</option>
            <option value="largest_delta">Largest delta</option>
          </select>
          <label className="flex items-center justify-center gap-3 rounded-2xl border border-line bg-[#f8fbff] px-4 py-3 text-sm font-medium text-ink">
            <input checked={riskOnly} onChange={(event) => setRiskOnly(event.target.checked)} type="checkbox" />
            Risk only
          </label>
        </div>
      </Surface>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="Matched" value={String(query.data?.total_count ?? 0)} note="Rows in the current working slice." />
        <StatCard label="Risk rows" tone="danger" value={String(query.data?.matched_risk_count ?? 0)} note="Flagged records in scope." />
        <StatCard label="Pending" tone="warn" value={String(query.data?.matched_pending_count ?? 0)} note="Open decisions still waiting." />
        <StatCard label="Matched value" tone="ok" value={formatMoney(query.data?.matched_total_amount ?? 0)} note="Aggregate invoice value in scope." />
      </div>

      {query.isError ? (
        <Surface>
          <div className="text-lg font-semibold text-rose">Queue data is unavailable</div>
          <p className="mt-2 text-sm leading-6 text-slate">
            The API could not load this working slice. Check the backend health and retry the filter.
          </p>
        </Surface>
      ) : query.isLoading ? (
        <Surface>
          <div className="text-lg font-semibold text-ink">Loading queue...</div>
          <p className="mt-2 text-sm leading-6 text-slate">Restoring the latest invoice state from the API.</p>
        </Surface>
      ) : (
        <QueueTable items={query.data?.items ?? []} onChanged={() => void query.refetch()} />
      )}
    </AppShell>
  );
}
