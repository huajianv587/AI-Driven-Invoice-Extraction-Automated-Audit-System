"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Building2,
  ChartNoAxesCombined,
  ListFilter,
  LogOut,
  Menu,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
  X,
  type LucideIcon
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { SessionPanel } from "@/components/session-panel";
import { Badge, Surface } from "@/components/ui";
import { getApiBaseUrl } from "@/lib/api";
import type { UserRole } from "@/lib/types";
import { cn } from "@/lib/utils";

const navigation: Array<{ href: string; label: string; icon: LucideIcon; roles: UserRole[]; group: string }> = [
  { href: "/app/dashboard", label: "Mission Control", icon: ChartNoAxesCombined, roles: ["admin", "reviewer", "ops"], group: "CORE" },
  { href: "/app/queue", label: "Review Queue", icon: ListFilter, roles: ["admin", "reviewer", "ops"], group: "REVIEW" },
  { href: "/app/control-room", label: "Control Room", icon: Workflow, roles: ["admin", "ops"], group: "OPS" },
  { href: "/app/ops", label: "Ops Center", icon: ShieldCheck, roles: ["admin", "ops"], group: "OPS" }
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
  const { user, ready, logout, isPublicDemo } = useAuth();
  const [command, setCommand] = useState("");
  const [clock, setClock] = useState("");
  const [apiReady, setApiReady] = useState<boolean | null>(null);
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    if (ready && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [pathname, ready, router, user]);

  useEffect(() => {
    const tick = () => {
      setClock(new Date().toLocaleTimeString("en-US", { hour12: false }));
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const response = await fetch(`${getApiBaseUrl()}/api/health`, { cache: "no-store" });
        if (!cancelled) setApiReady(response.ok);
      } catch {
        if (!cancelled) setApiReady(false);
      }
    };
    void check();
    const timer = window.setInterval(check, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    setNavOpen(false);
  }, [pathname]);

  if (!ready || !user) {
    return (
      <main className="mx-auto max-w-[1520px] px-6 py-8">
        <Surface>
          <div className="mono-label text-brand">Session restore</div>
          <div className="mt-3 text-lg font-semibold text-ink">Loading workspace...</div>
          <p className="mt-2 text-sm text-slate">Authenticating and restoring your finance terminal.</p>
        </Surface>
      </main>
    );
  }

  const allowed = !allowedRoles?.length || allowedRoles.includes(user.role);
  const currentGroup = navigation.find((item) => pathname.startsWith(item.href))?.group ?? "APP";
  const visibleNavigation = navigation.filter((item) => item.roles.includes(user.role));

  return (
    <main className="mx-auto max-w-[1640px] px-4 py-4 sm:px-5">
      {navOpen ? (
        <button
          aria-label="Close navigation"
          className="drawer-backdrop fixed inset-0 z-40 bg-black/60 backdrop-blur-sm xl:hidden"
          onClick={() => setNavOpen(false)}
          type="button"
        />
      ) : null}
      <div className="app-shell-grid">
        <aside
          className={cn(
            "drawer-panel space-y-4 xl:static",
            "max-xl:fixed max-xl:inset-y-0 max-xl:left-0 max-xl:z-50 max-xl:w-[min(88vw,360px)] max-xl:overflow-y-auto max-xl:px-4 max-xl:pb-6 max-xl:pt-4 max-xl:transition-transform max-xl:duration-300 max-xl:ease-out",
            navOpen ? "is-open max-xl:translate-x-0" : "max-xl:-translate-x-[108%]"
          )}
        >
          <section className="surface-card interactive-card p-0 xl:sticky xl:top-5">
            <div className="border-b border-line p-4">
              <div className="terminal-logo">
                <div className="terminal-logo-mark">IA</div>
                <div>
                  <div className="display-font text-sm font-bold tracking-[0.08em] text-ink">Invoice Audit Terminal</div>
                  <div className="mono-label mt-1 text-brand">OCR TO REVIEW</div>
                </div>
              </div>
              <button
                aria-label="Close navigation"
                className="terminal-button absolute right-4 top-4 min-h-0 px-2.5 py-2 text-xs xl:hidden"
                onClick={() => setNavOpen(false)}
                type="button"
              >
                <X className="size-3.5" />
              </button>
            </div>

            <nav className="space-y-1 p-3">
              <div className="mono-label px-2 pb-2 text-slate">FINANCE CONTROL DECK</div>
              {visibleNavigation.map((item) => {
                  const Icon = item.icon;
                  const active = pathname.startsWith(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={cn("app-nav-link drawer-nav-item", active ? "is-active" : "text-slate")}
                    >
                      <Icon className="size-4" />
                      <span className="font-semibold">{item.label}</span>
                    </Link>
                  );
                })}
            </nav>

            <div className="border-t border-line p-4">
              <div className="flex items-center gap-3">
                <div className="flex size-9 items-center justify-center border border-line bg-brandSoft text-brand">
                  <Building2 className="size-4" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-ink">{user.full_name}</div>
                  <div className="truncate text-xs text-slate">{user.email}</div>
                </div>
              </div>
              <div className="mt-4 flex items-center justify-between gap-3">
                <Badge tone={isPublicDemo ? "neutral" : "ok"}>{isPublicDemo ? "Public Demo" : user.role}</Badge>
                {isPublicDemo ? (
                  <Link className="terminal-button min-h-0 px-3 py-2 text-xs" href="/login">
                    Admin login
                  </Link>
                ) : (
                  <button
                    className="terminal-button min-h-0 px-3 py-2 text-xs"
                    onClick={async () => {
                      await logout();
                      router.replace("/login");
                    }}
                    type="button"
                  >
                    <LogOut className="mr-2 size-3.5" />
                    Sign out
                  </button>
                )}
              </div>
              {isPublicDemo ? (
                <div className="terminal-row mt-4">
                  <div className="mono-label text-brand">Read-only access</div>
                  <p className="mt-2 text-xs leading-5 text-slate">
                    Explore live demo data without signing in. Review submission, session management, and recovery writes
                    stay locked behind admin login.
                  </p>
                </div>
              ) : (
                <SessionPanel />
              )}
            </div>
          </section>
        </aside>

        <div className="min-w-0 space-y-4">
          <header className="surface-card p-0">
            <div className="flex flex-col gap-2 border-b border-line px-4 py-3 md:flex-row md:items-center md:justify-between">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  aria-label="Open navigation"
                  className="terminal-button min-h-0 px-3 py-2 text-xs xl:hidden"
                  onClick={() => setNavOpen(true)}
                  type="button"
                >
                  <Menu className="mr-2 size-3.5" />
                  Menu
                </button>
                <span className="mono-label text-brand">IA / {currentGroup}</span>
                <span className="text-xs text-slate">/</span>
                <span className="mono-label text-slate">{pathname}</span>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={apiReady ? "ok" : apiReady === false ? "danger" : "neutral"}>
                  <Activity className="size-3" />
                  {apiReady ? "API ONLINE" : apiReady === false ? "API CHECK" : "SYNCING"}
                </Badge>
                <Badge tone="neutral">{clock || "--:--:--"} SGT</Badge>
              </div>
            </div>

            <div className="px-4 py-4">
              <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                <div className="max-w-4xl">
                  <p className="mono-label text-brand">AIOps for finance</p>
                  <h1 className="mt-2 text-[clamp(1.9rem,4.6vw,2.8rem)] font-semibold tracking-tight text-ink">{title}</h1>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate">{subtitle}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge tone="neutral">Terminal UI</Badge>
                  <Badge tone="ok">
                    <Sparkles className="size-3.5" /> Live operations
                  </Badge>
                </div>
              </div>
              <form
                className="relative mt-4 max-w-2xl"
                onSubmit={(event) => {
                  event.preventDefault();
                  const query = command.trim();
                  router.push(query ? `/app/queue?search=${encodeURIComponent(query)}` : "/app/queue");
                }}
              >
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate" />
                <input
                  className="w-full py-2.5 pl-10 pr-4 text-sm font-medium outline-none"
                  onChange={(event) => setCommand(event.target.value)}
                  placeholder="Command search: seller, invoice, PO, or queue keyword"
                  value={command}
                />
              </form>
            </div>
          </header>

          {allowed ? (
            <>
              {aside}
              {children}
            </>
          ) : (
            <Surface>
              <p className="mono-label text-brand">Role policy</p>
              <h2 className="mt-3 text-3xl font-semibold tracking-tight text-ink">Access restricted</h2>
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
