"use client";

import { useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useAuth } from "@/components/auth-provider";
import { Badge, Surface } from "@/components/ui";

const bootstrapEmail = process.env.NEXT_PUBLIC_BOOTSTRAP_ADMIN_EMAIL ?? "admin@invoice-audit.local";

const loginSchema = z.object({
  email: z.string().email("Enter a valid email."),
  password: z.string().min(8, "Password must be at least 8 characters.")
});

type LoginValues = z.infer<typeof loginSchema>;

export function LoginScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, ready, user } = useAuth();
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      email: bootstrapEmail,
      password: ""
    }
  });

  useEffect(() => {
    if (ready && user) {
      router.replace(searchParams.get("next") || "/app/dashboard");
    }
  }, [ready, router, searchParams, user]);

  return (
    <main className="mx-auto flex min-h-screen max-w-[1320px] items-center px-6 py-10">
      <div className="grid w-full gap-6 md:grid-cols-[1.08fr_0.92fr]">
        <Surface className="relative overflow-hidden">
          <div className="orb left-[-50px] top-[-70px] size-48 bg-brand/20" />
          <div className="relative">
            <Badge tone="neutral">Protected workflow</Badge>
            <h1 className="mt-5 text-5xl font-semibold tracking-tight text-ink">Secure access to the premium finance workspace.</h1>
            <p className="mt-5 max-w-2xl text-base leading-8 text-slate">
              Sign in to review invoices, resolve exceptions, manage sync recovery, and keep the audit trail aligned
              inside the new web application.
            </p>
            <div className="mt-8 grid gap-4 md:grid-cols-2">
              <div className="surface-card">
                <p className="mono-label text-brand">Bootstrap admin</p>
                <div className="mt-3 text-lg font-semibold text-ink">Local self-hosted default</div>
                <p className="mt-3 text-sm text-slate">The backend seeds the initial admin account from AUTH_BOOTSTRAP_ADMIN_* values.</p>
              </div>
              <div className="surface-card">
                <p className="mono-label text-brand">Session model</p>
                <div className="mt-3 text-lg font-semibold text-ink">Access token + refresh cookie</div>
                <p className="mt-3 text-sm text-slate">Short-lived access tokens for API calls, httpOnly refresh cookie for session restoration.</p>
              </div>
            </div>
          </div>
        </Surface>

        <Surface>
          <p className="mono-label text-brand">Login</p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-ink">Enter your workspace</h2>
          <p className="mt-3 text-sm leading-7 text-slate">
            The bootstrap email is prefilled from the local environment; use the password stored in your root .env file.
          </p>
          <form
            className="mt-8 space-y-4"
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
              <input className="w-full rounded-2xl border border-line bg-white px-4 py-3 outline-none" {...form.register("email")} />
              <span className="text-xs text-rose">{form.formState.errors.email?.message}</span>
            </label>
            <label className="block space-y-2 text-sm font-medium text-ink">
              <span>Password</span>
              <input
                className="w-full rounded-2xl border border-line bg-white px-4 py-3 outline-none"
                placeholder="Password from AUTH_BOOTSTRAP_ADMIN_PASSWORD"
                type="password"
                {...form.register("password")}
              />
              <span className="text-xs text-rose">{form.formState.errors.password?.message}</span>
            </label>
            {form.formState.errors.root ? <p className="text-sm text-rose">{form.formState.errors.root.message}</p> : null}
            <button
              className="inline-flex items-center justify-center rounded-2xl bg-brand px-5 py-3 text-sm font-semibold text-white shadow-focus"
              disabled={form.formState.isSubmitting}
              type="submit"
            >
              {form.formState.isSubmitting ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </Surface>
      </div>
    </main>
  );
}
