import Link from "next/link";
import { ArrowRight, CheckCircle2, CloudCog, Shield, Workflow } from "lucide-react";

import { Badge, LinkCard, SectionHeader, Surface } from "@/components/ui";

const pillars = [
  {
    icon: Workflow,
    title: "Intake to decision in one lane",
    copy: "OCR, structured extraction, queueing, approval, and cloud replay stay inside one deliberate workflow."
  },
  {
    icon: Shield,
    title: "Premium finance-grade review UX",
    copy: "A calm, dense, high-trust surface designed for operators who make decisions on high-value records."
  },
  {
    icon: CloudCog,
    title: "Operational resilience built in",
    copy: "Connector posture, Feishu replay, and incident recovery live next to the work instead of in separate tools."
  }
];

const highlights = [
  "Protected business workspace with refresh-cookie auth",
  "Dashboard, queue, invoice detail, review desk, and ops center",
  "FastAPI contract layer between frontend and MySQL",
  "Compatible with the current OCR, Dify, Feishu, Mailpit, and MySQL setup"
];

export default function HomePage() {
  return (
    <main className="mx-auto max-w-[1520px] px-6 py-6">
      <div className="hero-grid">
        <Surface className="relative overflow-hidden">
          <div className="orb left-[-60px] top-[-60px] size-48 bg-brand/20" />
          <div className="orb bottom-[-50px] right-[-20px] size-40 bg-emerald-300/20" />
          <div className="relative">
            <Badge tone="neutral">World-class finance operations</Badge>
            <h1 className="mt-5 max-w-4xl text-5xl font-semibold tracking-tight text-ink md:text-6xl">
              Enterprise-grade invoice operations, rebuilt as a modern product surface.
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-8 text-slate">
              The new platform pairs a premium Stripe-style web experience with your existing local finance stack,
              so review, routing, audit traceability, and sync recovery all happen inside one coherent workspace.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                className="inline-flex items-center gap-2 rounded-2xl bg-brand px-5 py-3 text-sm font-semibold text-white shadow-focus"
                href="/login"
              >
                Open secure workspace <ArrowRight className="size-4" />
              </Link>
              <Link
                className="inline-flex items-center rounded-2xl border border-line bg-white px-5 py-3 text-sm font-semibold text-ink"
                href="#platform"
              >
                Explore platform
              </Link>
            </div>
            <div className="mt-10 grid gap-4 md:grid-cols-3">
              <div className="surface-card">
                <p className="mono-label text-brand">Posture</p>
                <div className="mt-3 text-3xl font-semibold text-ink">5</div>
                <p className="mt-2 text-sm text-slate">Purpose-built surfaces for review, queue, detail, auth, and ops.</p>
              </div>
              <div className="surface-card">
                <p className="mono-label text-brand">Architecture</p>
                <div className="mt-3 text-3xl font-semibold text-ink">API-first</div>
                <p className="mt-2 text-sm text-slate">Next.js frontend powered by a FastAPI contract layer instead of direct SQL-bound UI code.</p>
              </div>
              <div className="surface-card">
                <p className="mono-label text-brand">Outcome</p>
                <div className="mt-3 text-3xl font-semibold text-ink">Higher trust</div>
                <p className="mt-2 text-sm text-slate">Clearer hierarchy, stronger brand presence, and better operator confidence in every workflow.</p>
              </div>
            </div>
          </div>
        </Surface>

        <div className="space-y-5">
          <Surface>
            <p className="mono-label text-brand">Platform story</p>
            <h2 className="mt-3 text-2xl font-semibold tracking-tight text-ink">A flagship web front-end for the existing automation engine.</h2>
            <p className="mt-3 text-sm leading-7 text-slate">
              Keep the current OCR, Dify, Feishu, and MySQL runtime. Upgrade the human experience with a dedicated
              brand layer, secure app shell, and premium review desk.
            </p>
            <div className="mt-5 space-y-3">
              {highlights.map((item) => (
                <div key={item} className="flex items-start gap-3 rounded-2xl bg-[#f8fbff] px-4 py-3">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-mint" />
                  <span className="text-sm leading-6 text-slate">{item}</span>
                </div>
              ))}
            </div>
          </Surface>

          <Surface>
            <p className="mono-label text-brand">Showcase</p>
            <div className="mt-3 rounded-[24px] border border-line bg-[#f8fbff] p-4">
              <div className="grid gap-4">
                <div className="rounded-[22px] border border-line bg-white p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="mono-label text-brand">Mission control</div>
                      <div className="mt-2 text-xl font-semibold text-ink">Risk, throughput, sync, and queue posture</div>
                    </div>
                    <Badge tone="ok">Live</Badge>
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-[22px] border border-line bg-white p-4">
                    <div className="mono-label text-brand">Review desk</div>
                    <div className="mt-2 text-base font-semibold text-ink">Dual-column approval workflow</div>
                    <div className="mt-4 h-24 rounded-[18px] bg-gradient-to-br from-brandSoft to-[#f7faff]" />
                  </div>
                  <div className="rounded-[22px] border border-line bg-white p-4">
                    <div className="mono-label text-brand">Ops center</div>
                    <div className="mt-2 text-base font-semibold text-ink">Connector health and replay controls</div>
                    <div className="mt-4 h-24 rounded-[18px] bg-gradient-to-br from-[#effcf8] to-[#f8fbff]" />
                  </div>
                </div>
              </div>
            </div>
          </Surface>
        </div>
      </div>

      <section className="mt-8 space-y-6" id="platform">
        <SectionHeader
          kicker="Why it feels different"
          title="Designed like a premium product, not a stitched-together dashboard."
          copy="The interface is intentionally restrained, structured, and brand-led so the product feels worthy of the decisions people make inside it."
        />
        <div className="grid gap-4 md:grid-cols-3">
          {pillars.map((pillar) => {
            const Icon = pillar.icon;
            return (
              <Surface key={pillar.title}>
                <div className="flex size-12 items-center justify-center rounded-2xl bg-brandSoft text-brand">
                  <Icon className="size-5" />
                </div>
                <h3 className="mt-5 text-xl font-semibold text-ink">{pillar.title}</h3>
                <p className="mt-3 text-sm leading-7 text-slate">{pillar.copy}</p>
              </Surface>
            );
          })}
        </div>
      </section>

      <section className="mt-8 grid gap-4 md:grid-cols-2">
        <LinkCard
          href="/login"
          kicker="Secure entry"
          title="Open the protected app shell"
          copy="Use the bootstrap admin account from the local environment to enter the new finance workspace."
        />
        <LinkCard
          href="/app/dashboard"
          kicker="Direct route"
          title="Jump into Mission Control"
          copy="If you already have an active refresh cookie, the protected workspace will open immediately."
        />
      </section>
    </main>
  );
}
