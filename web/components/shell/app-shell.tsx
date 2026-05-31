"use client";

import { Menu, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

export interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-bg">
      {/* Fixed sidebar — desktop only. */}
      <aside className="hidden w-60 shrink-0 md:block">
        <div className="fixed inset-y-0 left-0 w-60">
          <Sidebar />
        </div>
      </aside>

      {/* Mobile slide-over drawer. */}
      {mobileNavOpen ? (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true">
          <button
            type="button"
            aria-label="Close navigation"
            className="bg-bg/70 absolute inset-0 backdrop-blur-sm"
            onClick={() => setMobileNavOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-60 animate-fade-in">
            <Sidebar />
            <Button
              variant="ghost"
              size="icon"
              className="absolute right-2 top-3"
              aria-label="Close navigation"
              onClick={() => setMobileNavOpen(false)}
            >
              <X />
            </Button>
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          slot={
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              aria-label="Open navigation"
              onClick={() => setMobileNavOpen(true)}
            >
              <Menu />
            </Button>
          }
        />

        <main className={cn("noc-grid flex-1 overflow-y-auto")}>
          <div className="mx-auto flex w-full max-w-[1600px] animate-fade-in flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
