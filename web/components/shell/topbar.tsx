"use client";

import { LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import type { Role } from "@/lib/types";

const ROLE_VARIANT: Record<Role, "info" | "warn" | "critical"> = {
  viewer: "info",
  operator: "warn",
  admin: "critical",
};

const ENVIRONMENT = process.env.NEXT_PUBLIC_ENVIRONMENT ?? "production";

export interface TopbarProps {
  /** Page-level slot rendered at the left (e.g. mobile menu trigger, title). */
  slot?: ReactNode;
}

export function Topbar({ slot }: TopbarProps) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  async function handleLogout() {
    setSigningOut(true);
    try {
      await logout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <header className="bg-surface/80 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border px-4 backdrop-blur">
      <div className="flex min-w-0 items-center gap-3">{slot}</div>

      <div className="flex items-center gap-3">
        <span
          className="hidden items-center gap-2 rounded-md border border-border bg-surface-2 px-2.5 py-1 sm:inline-flex"
          title={`Environment: ${ENVIRONMENT}`}
        >
          <span className="size-1.5 rounded-full bg-ok" aria-hidden="true" />
          <span className="font-mono text-xs uppercase tracking-wide text-text-dim">
            {ENVIRONMENT}
          </span>
        </span>

        {user ? (
          <div className="flex items-center gap-2.5">
            <div className="hidden flex-col items-end leading-tight md:flex">
              <span className="font-mono text-xs text-text">{user.email}</span>
            </div>
            <Badge variant={ROLE_VARIANT[user.role]}>{user.role.toUpperCase()}</Badge>
          </div>
        ) : null}

        <Button
          variant="ghost"
          size="icon"
          onClick={handleLogout}
          disabled={signingOut}
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut />
        </Button>
      </div>
    </header>
  );
}
