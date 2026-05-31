"use client";

import { Lock, ShieldAlert, Terminal } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const DEMO_CREDENTIALS: ReadonlyArray<{ email: string; password: string; note: string }> = [
  { email: "admin@sentryops.local", password: "admin12345", note: "full access" },
  { email: "viewer@sentryops.local", password: "viewer12345", note: "read-only" },
];

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.status === 401 ? "Invalid credentials. Check email and password." : error.message;
  }
  if (error instanceof Error) return error.message;
  return "Unable to reach the authentication service.";
}

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      router.push("/dashboard");
    } catch (err) {
      setError(errorMessage(err));
      setSubmitting(false);
    }
  }

  function applyDemo(demoEmail: string, demoPassword: string) {
    setEmail(demoEmail);
    setPassword(demoPassword);
    setError(null);
  }

  return (
    <main className="noc-grid relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-10">
      <div className="w-full max-w-md animate-fade-in">
        {/* Brand mark */}
        <div className="mb-6 flex items-center gap-2.5">
          <span className="relative flex size-3 items-center justify-center">
            <span className="absolute inline-flex size-3 animate-pulse-dot rounded-full bg-accent" />
            <span className="relative inline-flex size-2 rounded-full bg-accent" />
          </span>
          <span className="font-mono text-xl font-bold tracking-tight text-text">
            Sentry<span className="text-accent">Ops</span>
          </span>
        </div>

        <div className="rounded-card border border-border bg-surface shadow-panel">
          <div className="flex items-center gap-2 border-b border-border px-6 py-4">
            <Terminal className="size-4 text-accent" aria-hidden="true" />
            <h1 className="font-mono text-sm uppercase tracking-widest text-text-dim">
              Operator Sign-In
            </h1>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4 px-6 py-6" noValidate>
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="email"
                className="font-mono text-xs uppercase tracking-wider text-text-dim"
              >
                Email
              </label>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="operator@sentryops.local"
                className="font-mono"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="password"
                className="font-mono text-xs uppercase tracking-wider text-text-dim"
              >
                Password
              </label>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••"
                className="font-mono"
              />
            </div>

            {error ? (
              <div
                role="alert"
                className="border-danger/40 bg-danger/10 flex items-start gap-2 rounded-md border px-3 py-2 text-sm text-danger"
              >
                <ShieldAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                <span>{error}</span>
              </div>
            ) : null}

            <Button type="submit" disabled={submitting} className="mt-1 w-full">
              {submitting ? "Authenticating…" : "Sign in"}
              {!submitting ? <Lock /> : null}
            </Button>
          </form>

          <div className="bg-surface-2/40 border-t border-border px-6 py-4">
            <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-muted">
              Demo credentials
            </p>
            <div className="flex flex-col gap-1.5">
              {DEMO_CREDENTIALS.map((cred) => (
                <button
                  key={cred.email}
                  type="button"
                  onClick={() => applyDemo(cred.email, cred.password)}
                  className="group flex items-center justify-between gap-2 rounded-md border border-transparent px-2 py-1.5 text-left transition-colors duration-[140ms] hover:border-border hover:bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                >
                  <span className="tabular text-xs text-text-dim group-hover:text-text">
                    {cred.email}
                    <span className="mx-1.5 text-muted">/</span>
                    {cred.password}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-wide text-muted">
                    {cred.note}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <p className="mt-4 text-center font-mono text-[10px] uppercase tracking-widest text-muted">
          Self-hosted IT operations command center
        </p>
      </div>
    </main>
  );
}
