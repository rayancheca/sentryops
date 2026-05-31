"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppShell } from "@/components/shell/app-shell";
import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/lib/auth";

export default function AuthenticatedLayout({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg">
        <Spinner size={28} label="Authenticating" />
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
