import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Database, FileSearch, Mail, RefreshCcw, ShieldCheck, Workflow } from "lucide-react";

import { AnimatedTerminalCanvas } from "@/components/animated-terminal-canvas";

const metrics = [
  ["6", "seeded invoices"],
  ["5", "runtime connectors"],
  ["100%", "audit trail focus"]
];

const workflow = [
  { icon: FileSearch, title: "OCR intake", copy: "Invoice files enter a local extraction lane with traceable source evidence." },
  { icon: Workflow, title: "Dify structuring", copy: "LLM extraction turns scanned evidence into reviewable business fields." },
  { icon: Database, title: "PO matching", copy: "Purchase order facts are compared against invoice totals and supplier identity." },
  { icon: ShieldCheck, title: "Risk review", copy: "Amount deltas, missing evidence, and workflow state stay visible for sign-off." },
  { icon: RefreshCcw, title: "Feishu replay", copy: "Failed syncs remain recoverable from the operations console." },
  { icon: Mail, title: "Mailpit alerts", copy: "Local alert delivery can be inspected without touching production mailboxes." }
];

const sampleImages = [
  { src: "/assets/invoices/sample-1.jpg", alt: "Invoice sample with extracted fields" },
  { src: "/assets/invoices/sample-2.jpg", alt: "Invoice sample queued for review" },
  { src: "/assets/invoices/sample-3.jpg", alt: "Invoice sample used for audit evidence" }
];

const mailpitUrl = process.env.NEXT_PUBLIC_MAILPIT_URL ?? "http://127.0.0.1:8025";

export function TerminalLanding() {
  return (
    <main className="h-screen snap-y snap-mandatory overflow-y-auto overflow-x-hidden">
      <nav className="terminal-nav">
        <div className="terminal-logo">
          <div className="terminal-logo-mark">IA</div>
          <div>
            <div className="display-font text-sm font-bold tracking-[0.08em] text-ink">Invoice Audit Terminal</div>
            <div className="mono-label mt-1 text-brand">OCR TO REVIEW</div>
          </div>
        </div>
        <div className="terminal-link-row">
          <a href="#workflow">Workflow</a>
          <a href="#evidence">Evidence</a>
          <Link className="terminal-primary min-h-0 px-4 py-2" href="/app/dashboard">
            Enter workspace
          </Link>
        </div>
      </nav>

      <section className="terminal-screen terminal-screen--center">
        <AnimatedTerminalCanvas variant="market" />
        <div className="relative z-10 flex max-w-5xl flex-col items-center">
          <p className="mono-label text-brand">FINANCE CONTROL DECK / LOCAL STACK</p>
          <h1 className="landing-hero-title mt-5 max-w-5xl font-extrabold tracking-tight text-ink">
            Invoice evidence, risk review, and sync recovery in one terminal.
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-7 text-slate">
            A dark operations surface for OCR intake, Dify extraction, purchase-order matching, reviewer decisions, and
            Feishu recovery across the existing local FastAPI and MySQL stack.
          </p>
          <div className="landing-cta-row mt-6">
            <Link className="terminal-primary" href="/app/dashboard">
              Open secure workspace <ArrowRight className="ml-2 size-4" />
            </Link>
            <Link className="terminal-secondary" href="/login">
              Admin login
            </Link>
            <Link className="terminal-secondary" href="/app/dashboard">
              Mission Control
            </Link>
          </div>
          <div className="terminal-kpi-grid mt-8 w-full max-w-3xl">
            {metrics.map(([value, label]) => (
              <div key={label} className="terminal-kpi">
                <div className="font-mono text-3xl font-semibold text-brand">{value}</div>
                <div className="mono-label mt-2 text-slate">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="workflow" className="terminal-screen">
        <div className="terminal-panel-grid relative z-10 w-full">
          <div className="stagger-in">
            <p className="mono-label text-brand">WORKFLOW</p>
            <h2 className="mt-4 text-4xl font-bold leading-tight text-ink">From scanned invoice to auditable decision.</h2>
            <p className="mt-4 text-sm leading-6 text-slate">
              The interface keeps machine extraction, human review, connector posture, and downstream replay in the same
              operating language, so finance teams can see what happened and what needs action.
            </p>
            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              {workflow.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.title} className="terminal-row interactive-card">
                    <Icon className="size-5 text-brand" />
                    <div className="mt-3 font-semibold text-ink">{item.title}</div>
                    <p className="mt-2 text-xs leading-5 text-slate">{item.copy}</p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="surface-card stagger-in dense-surface" id="evidence">
            <div className="flex items-center justify-between gap-4 border-b border-line pb-3">
              <div>
                <p className="mono-label text-brand">LIVE EVIDENCE PREVIEW</p>
                <h3 className="mt-2 text-2xl font-semibold text-ink">Invoice samples on the review rail</h3>
              </div>
              <span className="h-2 w-2 bg-brand shadow-[0_0_18px_rgba(0,255,136,0.7)]" />
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              {sampleImages.map((image, index) => (
                <div key={image.src} className="terminal-image relative min-h-[220px] overflow-hidden">
                  <Image
                    alt={image.alt}
                    className="object-cover"
                    fill
                    priority={index === 0}
                    sizes="(max-width: 768px) 100vw, 33vw"
                    src={image.src}
                  />
                </div>
              ))}
            </div>
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="terminal-row dense-row">
                <div className="mono-label text-brand">OCR</div>
                <div className="mt-2 text-xl font-semibold text-ink">ready</div>
              </div>
              <div className="terminal-row dense-row">
                <div className="mono-label text-brand">Risk queue</div>
                <div className="mt-2 text-xl font-semibold text-ink">prioritized</div>
              </div>
              <div className="terminal-row dense-row">
                <div className="mono-label text-brand">Feishu</div>
                <div className="mt-2 text-xl font-semibold text-ink">recoverable</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="terminal-screen terminal-screen--center">
        <div className="relative z-10 max-w-4xl">
          <p className="mono-label text-brand">READY FOR LOCAL OPERATIONS</p>
          <h2 className="mt-4 text-[clamp(2.2rem,6vw,4.2rem)] font-extrabold leading-tight text-ink">
            Start reviewing without leaving the stack.
          </h2>
          <p className="mt-4 text-base leading-7 text-slate">
            Open the public read-only workspace instantly, inspect alerts in Mailpit, and sign in only when you need to
            submit review decisions or run recovery actions.
          </p>
          <div className="landing-cta-row mt-7">
            <Link className="terminal-primary" href="/app/dashboard">
              Open workspace
            </Link>
            <Link className="terminal-secondary" href="/app/control-room">
              Control Room
            </Link>
            <Link className="terminal-secondary" href="/login">
              Admin login
            </Link>
            <a className="terminal-secondary" href={mailpitUrl}>
              Open Mailpit
            </a>
          </div>
          <div className="terminal-divider mt-10" />
          <div className="mt-5 text-xs text-slate">Invoice Audit Terminal / FastAPI / MySQL / OCR / Dify / Feishu / Mailpit</div>
        </div>
      </section>
    </main>
  );
}
