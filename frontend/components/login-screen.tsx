"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { AnimatedTerminalCanvas } from "@/components/animated-terminal-canvas";
import { useAuth } from "@/components/auth-provider";
import { Badge } from "@/components/ui";

const bootstrapEmail = process.env.NEXT_PUBLIC_BOOTSTRAP_ADMIN_EMAIL ?? "admin@invoice-audit.local";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email."),
  password: z.string().min(8, "Password must be at least 8 characters.")
});

type LoginValues = z.infer<typeof loginSchema>;

export function LoginScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, ready, user, isPublicDemo } = useAuth();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: bootstrapEmail,
      password: ""
    }
  });

  useEffect(() => {
    if (ready && user && !isPublicDemo) {
      router.replace(searchParams.get("next") || "/app/dashboard");
    }
  }, [isPublicDemo, ready, router, searchParams, user]);

  return (
    <main className="grid min-h-screen lg:grid-cols-[1.08fr_0.92fr]">
      <section className="relative hidden overflow-hidden border-r border-line p-8 lg:flex lg:flex-col lg:justify-between">
        <AnimatedTerminalCanvas className="opacity-45" variant="signal" />
        <div className="relative z-10">
          <div className="terminal-logo">
            <div className="terminal-logo-mark">IA</div>
            <div>
              <div className="display-font text-sm font-bold tracking-[0.08em] text-ink">Invoice Audit Terminal</div>
              <div className="mono-label mt-1 text-brand">PROTECTED ENTRY</div>
            </div>
          </div>
          <h1 className="mt-14 max-w-2xl text-[clamp(2.8rem,4vw,4.4rem)] font-extrabold leading-tight tracking-tight text-ink">
            Secure access to the finance control deck.
          </h1>
          <p className="mt-4 max-w-xl text-sm leading-6 text-slate">
            Restore your refresh-cookie session, inspect invoice evidence, review high-risk deltas, and recover
            connector syncs from the same terminal shell.
          </p>
        </div>

        <div className="relative z-10 grid grid-cols-3 gap-3">
          <div className="terminal-row">
            <div className="mono-label text-brand">Auth</div>
            <div className="mt-2 text-xl font-semibold text-ink">cookie</div>
          </div>
          <div className="terminal-row">
            <div className="mono-label text-brand">Role</div>
            <div className="mt-2 text-xl font-semibold text-ink">RBAC</div>
          </div>
          <div className="terminal-row">
            <div className="mono-label text-brand">Audit</div>
            <div className="mt-2 text-xl font-semibold text-ink">logged</div>
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center px-4 py-7 sm:px-5 sm:py-8">
        <div className="surface-card dense-surface w-full max-w-[448px]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="mono-label text-brand">Login</p>
              <h2 className="mt-2.5 text-[2rem] font-semibold tracking-tight text-ink">Enter your workspace</h2>
            </div>
            <Badge tone="ok">Local</Badge>
          </div>
          <p className="mt-3 text-sm leading-6 text-slate">
            The bootstrap email is prefilled from the local environment; use the password stored in your root .env file.
          </p>
          <form
            className="mt-5 space-y-4 sm:mt-6"
            onSubmit={form.handleSubmit(async (values) => {
              try {
                await login(values.email, values.password);
                router.replace(searchParams.get("next") || "/app/dashboard");
              } catch (error) {
                form.setError("root", {
                  type: "server",
                  message: error instanceof Error ? error.message : "Unable to sign in."
                });
              }
            })}
          >
            <label className="block space-y-2 text-sm font-medium text-ink">
              <span>Email</span>
              <input className="w-full px-4 py-2.5 outline-none" {...form.register("email")} />
              <span className="text-xs text-rose">{form.formState.errors.email?.message}</span>
            </label>
            <label className="block space-y-2 text-sm font-medium text-ink">
              <span>Password</span>
              <input
                className="w-full px-4 py-2.5 outline-none"
                placeholder="Admin password"
                type="password"
                {...form.register("password")}
              />
              <span className="text-xs text-rose">{form.formState.errors.password?.message}</span>
            </label>
            {form.formState.errors.root ? <p className="text-sm text-rose">{form.formState.errors.root.message}</p> : null}
            <div className="flex flex-wrap gap-3 pt-1">
              <button className="terminal-primary" disabled={form.formState.isSubmitting} type="submit">
                {form.formState.isSubmitting ? "Signing in..." : "Sign in"}
              </button>
              <button className="terminal-secondary" onClick={() => router.push("/")} type="button">
                Back home
              </button>
            </div>
          </form>
          <div className="terminal-row dense-row mt-5">
            <div className="mono-label text-brand">Bootstrap admin</div>
            <p className="mt-2 text-xs leading-5 text-slate">
              The backend seeds the initial admin account from AUTH_BOOTSTRAP_ADMIN_EMAIL and
              AUTH_BOOTSTRAP_ADMIN_PASSWORD.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
