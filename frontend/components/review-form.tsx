"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAuth } from "@/components/auth-provider";
import { Surface } from "@/components/ui";
import type { ReviewResponse } from "@/lib/types";

const reviewSchema = z.object({
  handler_user: z.string().min(2, "Enter the reviewer name."),
  handling_note: z.string().min(8, "Add a meaningful handling note."),
  review_result: z.enum(["Pending", "Approved", "Rejected", "NeedsReview"])
});

type ReviewValues = z.infer<typeof reviewSchema>;

export function ReviewForm({
  invoiceId,
  defaults,
  onSuccess
}: {
  invoiceId: number;
  defaults: ReviewValues;
  onSuccess?: () => void;
}) {
  const { authFetch } = useAuth();
  const [message, setMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const form = useForm<ReviewValues>({
    resolver: zodResolver(reviewSchema),
    defaultValues: defaults
  });

  return (
    <Surface className="dense-surface status-processing">
      <p className="mono-label text-brand">Decision form</p>
      <h3 className="mt-3 text-2xl font-semibold tracking-tight text-ink">Reviewer note and outcome</h3>
      <form
        className="mt-5 space-y-4"
        onSubmit={form.handleSubmit(async (values) => {
          setMessage("");
          setErrorMessage("");
          try {
            const idempotencyKey =
              typeof crypto !== "undefined" && "randomUUID" in crypto
                ? crypto.randomUUID()
                : `review-${invoiceId}-${Date.now()}`;
            const response = await authFetch(`/api/invoices/${invoiceId}/review`, {
              method: "POST",
              headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
              body: JSON.stringify(values)
            });
            const result = (await response.json()) as ReviewResponse;
            setMessage(result.message || (result.changed ? "Decision saved and audit trail updated." : "Decision already recorded."));
            onSuccess?.();
          } catch (error) {
            setErrorMessage(error instanceof Error ? error.message : "Unable to save this review decision.");
          }
        })}
      >
        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-ink">
            <span>Handler</span>
            <input className="w-full px-4 py-2.5 outline-none" {...form.register("handler_user")} />
            <span className="text-xs text-rose">{form.formState.errors.handler_user?.message}</span>
          </label>
          <label className="space-y-2 text-sm font-medium text-ink">
            <span>Review result</span>
            <select className="w-full px-4 py-2.5 outline-none" {...form.register("review_result")}>
              <option value="Pending">Pending</option>
              <option value="Approved">Approved</option>
              <option value="Rejected">Rejected</option>
              <option value="NeedsReview">Needs review</option>
            </select>
          </label>
        </div>

        <label className="block space-y-2 text-sm font-medium text-ink">
          <span>Handling note</span>
          <textarea className="min-h-40 w-full px-4 py-2.5 outline-none" {...form.register("handling_note")} />
          <span className="text-xs text-rose">{form.formState.errors.handling_note?.message}</span>
        </label>

        <button
          className="terminal-primary"
          disabled={form.formState.isSubmitting}
          type="submit"
        >
          {form.formState.isSubmitting ? "Saving..." : "Submit review decision"}
        </button>
        {errorMessage ? <p className="text-sm font-medium text-rose">{errorMessage}</p> : null}
        {message ? <p className="text-sm font-medium text-mint">{message}</p> : null}
      </form>
    </Surface>
  );
}
