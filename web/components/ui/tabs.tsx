"use client";

import { useId } from "react";

import { cn } from "@/lib/cn";

export interface TabItem<T extends string = string> {
  value: T;
  label: string;
}

export interface TabsProps<T extends string = string> {
  tabs: ReadonlyArray<TabItem<T>>;
  value: T;
  onValueChange: (value: T) => void;
  className?: string;
}

/**
 * Controlled, dependency-free tab bar with roving keyboard navigation
 * (Arrow keys / Home / End) and visible active state.
 */
export function Tabs<T extends string = string>({
  tabs,
  value,
  onValueChange,
  className,
}: TabsProps<T>) {
  const baseId = useId();

  function focusTab(index: number) {
    const next = ((index % tabs.length) + tabs.length) % tabs.length;
    const target = tabs[next];
    if (target) onValueChange(target.value);
  }

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-border bg-surface p-1",
        className,
      )}
    >
      {tabs.map((tab, index) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            id={`${baseId}-${tab.value}`}
            role="tab"
            type="button"
            aria-selected={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onValueChange(tab.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight") {
                event.preventDefault();
                focusTab(index + 1);
              } else if (event.key === "ArrowLeft") {
                event.preventDefault();
                focusTab(index - 1);
              } else if (event.key === "Home") {
                event.preventDefault();
                focusTab(0);
              } else if (event.key === "End") {
                event.preventDefault();
                focusTab(tabs.length - 1);
              }
            }}
            className={cn(
              "rounded px-3 py-1.5 text-sm font-medium tracking-tight",
              "transition-[color,background-color] duration-[140ms]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
              active ? "bg-surface-2 text-text shadow-panel" : "text-text-dim hover:text-text",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
