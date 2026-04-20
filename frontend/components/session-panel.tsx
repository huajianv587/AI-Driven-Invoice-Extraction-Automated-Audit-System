"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "@/components/auth-provider";
import type { AuthSessionDevice } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export function SessionPanel() {
  const { authFetch } = useAuth();
  const [message, setMessage] = useState("");
  const [expanded, setExpanded] = useState(false);
  const sessionsQuery = useQuery({
    queryKey: ["auth-sessions"],
    queryFn: async () => (await (await authFetch("/api/auth/sessions")).json()) as AuthSessionDevice[],
    enabled: expanded
  });

  const revoke = async (sessionId: number) => {
    setMessage("");
    try {
      await authFetch(`/api/auth/sessions/${sessionId}`, { method: "DELETE" });
      await sessionsQuery.refetch();
      setMessage("Session revoked. That device must sign in again.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to revoke this session.");
    }
  };

  const sessions = sessionsQuery.data ?? [];
  const activeSessions = sessions.filter((session) => !session.revoked_at).slice(0, 3);

  return (
    <div className="mt-4 border border-line bg-white/5 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-ink">Session devices</div>
          <p className="mt-1 text-xs leading-5 text-slate">Review active refresh sessions and revoke stale devices.</p>
        </div>
        <button
          className="terminal-button min-h-0 px-3 py-1.5 text-xs"
          onClick={() => {
            setExpanded((value) => !value);
            if (expanded) {
              setMessage("");
            }
          }}
          type="button"
        >
          {expanded ? "Hide" : "Manage"}
        </button>
      </div>

      {expanded ? (
        <div className="mt-3 space-y-2">
          <button className="terminal-button min-h-0 px-3 py-1.5 text-xs" disabled={sessionsQuery.isFetching} onClick={() => void sessionsQuery.refetch()} type="button">
            {sessionsQuery.isFetching ? "Refreshing" : "Refresh sessions"}
          </button>
          {sessionsQuery.isError ? (
            <div className="border border-rose/20 bg-white/5 p-3 text-xs text-rose">
              Session devices are unavailable. Try signing in again if this continues.
            </div>
          ) : null}
          {!sessionsQuery.isLoading && activeSessions.length === 0 ? (
            <div className="border border-line bg-white/5 p-3 text-xs text-slate">No active sessions found.</div>
          ) : null}
          {activeSessions.map((session) => (
            <div key={session.id} className="border border-line bg-white/5 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-semibold text-ink">
                  {session.device_label}
                  {session.is_current ? <span className="ml-2 text-brand">Current</span> : null}
                </div>
                <button
                  className="text-xs font-semibold text-rose disabled:cursor-not-allowed disabled:opacity-40"
                  disabled={session.is_current}
                  onClick={() => void revoke(session.id)}
                  type="button"
                >
                  Revoke
                </button>
              </div>
              <p className="mt-1 text-xs leading-5 text-slate">
                Last seen {formatDate(session.last_seen_at)} / expires {formatDate(session.expires_at)}
              </p>
            </div>
          ))}
        </div>
      ) : null}
      {message ? <p className="mt-3 text-xs font-medium text-slate">{message}</p> : null}
    </div>
  );
}
