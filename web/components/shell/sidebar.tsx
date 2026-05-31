"use client";

import {
  Activity,
  Boxes,
  LayoutDashboard,
  ShieldCheck,
  Siren,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: ReadonlyArray<NavItem> = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/assets", label: "Assets", icon: Boxes },
  { href: "/compliance", label: "Compliance", icon: ShieldCheck },
  { href: "/observability", label: "Observability", icon: Activity },
  { href: "/incidents", label: "Incidents", icon: Siren },
];

const ADMIN_ITEM: NavItem = { href: "/users", label: "Users", icon: Users };

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "group relative flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium",
        "transition-[color,background-color] duration-[140ms]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        active ? "bg-surface-2 text-text" : "hover:bg-surface-2/60 text-text-dim hover:text-text",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "absolute left-0 h-5 w-0.5 rounded-r-full bg-accent transition-opacity duration-[140ms]",
          active ? "opacity-100" : "opacity-0",
        )}
      />
      <Icon
        className={cn(
          "size-4 shrink-0",
          active ? "text-accent" : "text-text-dim group-hover:text-text",
        )}
        aria-hidden="true"
      />
      {item.label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const { hasRole } = useAuth();

  return (
    <nav
      aria-label="Primary navigation"
      className="bg-surface/80 flex h-full flex-col gap-6 border-r border-border px-3 py-5"
    >
      <Link
        href="/dashboard"
        className="flex items-center gap-2.5 px-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      >
        <span className="relative flex size-2.5 items-center justify-center">
          <span className="absolute inline-flex size-2.5 animate-pulse-dot rounded-full bg-accent" />
          <span className="relative inline-flex size-1.5 rounded-full bg-accent" />
        </span>
        <span className="font-mono text-base font-bold tracking-tight text-text">
          Sentry<span className="text-accent">Ops</span>
        </span>
      </Link>

      <div className="flex flex-1 flex-col gap-1">
        <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-widest text-muted">
          Operations
        </p>
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.href} item={item} active={isActive(pathname, item.href)} />
        ))}

        {hasRole("admin") ? (
          <>
            <p className="px-3 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-widest text-muted">
              Administration
            </p>
            <NavLink item={ADMIN_ITEM} active={isActive(pathname, ADMIN_ITEM.href)} />
          </>
        ) : null}
      </div>

      <p className="px-3 font-mono text-[10px] uppercase tracking-widest text-muted">NOC · v0.1</p>
    </nav>
  );
}
