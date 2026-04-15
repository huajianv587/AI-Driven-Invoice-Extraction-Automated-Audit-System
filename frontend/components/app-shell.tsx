"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Building2,
  ChartNoAxesCombined,
  type LucideIcon,
  ListFilter,
  LogOut,
  Search,
  ShieldCheck,
  Sparkles
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Badge, Surface } from "@/components/ui";
import type { UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

const navigation: Array<{ href: string; label: string; icon: LucideIcon; roles: UserRole[] }> = [
  { href: "/app/dashboard", label: "Mission Control", icon: ChartNoAxesCombined, roles: ["admin", "reviewer", "ops"] },
  { href: "/app/queue", label: "Review Queue", icon: ListFilter, roles: ["admin", "reviewer", "ops"] },
  { href: "/app/ops", label: "Ops Center", icon: ShieldCheck, roles: ["admin", "ops"] }
];

export function AppShell({
  title,
  subtitle,
  children,
  aside,
  allowedRoles
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  aside?: ReactNode;
  allowedRoles?: UserRole[];
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, ready, logout } = useAuth();
  const [command, setCommand] = useState("");

  useEffect(() => {
    if (ready && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [pathname, ready, router, user]);

  if (!ready || !user) {
    return (
      <main className="mx-auto max-w-[1520px] px-6 py-8">
        <Surface>
          <div className="text-lg font-semibold text-ink">Loading workspace...</div>
          <p className="mt-2 text-sm text-slate">Authenticating and restoring your finance session.</p>
        </Surface>
      </main>
    );
  }

  const allowed = !allowedRoles?.length || allowedRoles.includes(user.role);

  return (
    <main className="mx-auto max-w-[1520px] px-6 py-6">
      <div className="app-shell-grid">
        <aside className="space-y-4">
          <Surface className="sticky top-6">
            <div className="rounded-[24px] border border-white/80 bg-gradient-to-br from-white to-[#f3f7ff] p-5">
              <p className="mono-label text-brand">Finance platform</p>
              <h1 className="mt-3 text-3xl font-semibold leading-none tracking-tight text-ink">
                Invoice Operations Suite
              </h1>
              <p className="mt-4 text-sm leading-6 text-slate">
                Premium control center for intake, review routing, cloud sync, and audit traceability.
              </p>
            </div>

            <div className="mt-5 space-y-2">
              {navigation
                .filter((item) => item.roles.includes(user.role))
                .map((item) => {
                const Icon = item.icon;
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl border px-4 py-3 transition-colors",
                      active
                        ? "border-brand/20 bg-brandSoft text-brand"
                        : "border-transparent bg-[#f8fbff] text-slate hover:border-line hover:bg-white"
                    )}
                  >
                    <Icon className="size-4" />
                    <span className="font-medium">{item.label}</span>
                  </Link>
                );
              })}
            </div>

            <div className="mt-5 rounded-2xl border border-line bg-[#f8fbff] p-4">
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-2xl bg-brandSoft text-brand">
                  <Building2 className="size-5" />
                </div>
                <div>
                  <div className="font-semibold text-ink">{user.full_name}</div>
                  <div className="text-sm text-slate">{user.email}</div>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between">
                <Badge tone="ok">{user.role}</Badge>
                <button
                  className="inline-flex items-center gap-2 text-sm font-medium text-slate transition-colors hover:text-ink"
                  onClick={async () => {
                    await logout();
                    router.replace("/login");
                  }}
                  type="button"
                >
                  <LogOut className="size-4" />
                  Sign out
                </button>
              </div>
            </div>
          </Surface>
        </aside>

        <div className="space-y-6">
          <Surface className="relative overflow-hidden">
            <div className="orb left-[-40px] top-[-50px] size-40 bg-brand/20" />
            <div className="orb bottom-[-50px] right-[-20px] size-36 bg-emerald-300/20" />
            <div className="relative flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div className="max-w-3xl">
                <p className="mono-label text-brand">AIOps for finance</p>
                <h2 className="mt-3 text-4xl font-semibold tracking-tight text-ink">{title}</h2>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-slate">{subtitle}</p>
              </div>
              <div className="flex gap-2">
                <Badge tone="neutral">Premium web app</Badge>
                <Badge tone="ok">
                  <span className="inline-flex items-center gap-2">
                    <Sparkles className="size-3.5" /> Live operations
                  </span>
                </Badge>
              </div>
            </div>
            <form
              className="relative mt-6 max-w-2xl"
              onSubmit={(event) => {
                event.preventDefault();
                const query = command.trim();
                if (query) {
                  router.push(`/app/queue?search=${encodeURIComponent(query)}`);
                } else {
                  router.push("/app/queue");
                }
              }}
            >
              <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-slate" />
              <input
                className="w-full rounded-2xl border border-line bg-white/80 py-3 pl-11 pr-4 text-sm font-medium text-ink outline-none transition focus:border-brand/40 focus:bg-white focus:shadow-focus"
                onChange={(event) => setCommand(event.target.value)}
                placeholder="Command search: seller, invoice, PO, or queue keyword"
                value={command}
              />
            </form>
          </Surface>

          {allowed ? (
            <>
              {aside}
              {children}
            </>
          ) : (
            <Surface>
              <p className="mono-label text-brand">Role policy</p>
              <h3 className="mt-3 text-3xl font-semibold tracking-tight text-ink">Access restricted</h3>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-slate">
                Your current role does not include this workspace surface. Switch to an authorized account or ask an
                administrator to update your role before continuing.
              </p>
            </Surface>
          )}
        </div>
      </div>
    </main>
  );
}
