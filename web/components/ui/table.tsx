import {
  forwardRef,
  type HTMLAttributes,
  type TdHTMLAttributes,
  type ThHTMLAttributes,
} from "react";

import { cn } from "@/lib/cn";

export const Table = forwardRef<HTMLTableElement, HTMLAttributes<HTMLTableElement>>(
  ({ className, ...props }, ref) => (
    <div className="relative w-full overflow-x-auto">
      <table
        ref={ref}
        className={cn("w-full border-collapse text-left text-sm", className)}
        {...props}
      />
    </div>
  ),
);
Table.displayName = "Table";

export interface THeadProps extends HTMLAttributes<HTMLTableSectionElement> {
  /** Stick the header to the top of a scroll container. */
  sticky?: boolean;
}

export const THead = forwardRef<HTMLTableSectionElement, THeadProps>(
  ({ className, sticky = false, ...props }, ref) => (
    <thead
      ref={ref}
      className={cn(
        "text-text-dim",
        sticky && "bg-surface/95 sticky top-0 z-10 backdrop-blur",
        className,
      )}
      {...props}
    />
  ),
);
THead.displayName = "THead";

export const TBody = forwardRef<HTMLTableSectionElement, HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => (
    <tbody ref={ref} className={cn("divide-y divide-border", className)} {...props} />
  ),
);
TBody.displayName = "TBody";

export const TR = forwardRef<HTMLTableRowElement, HTMLAttributes<HTMLTableRowElement>>(
  ({ className, ...props }, ref) => (
    <tr
      ref={ref}
      className={cn(
        "hover:bg-surface-2/60 border-b border-border transition-colors duration-[140ms]",
        className,
      )}
      {...props}
    />
  ),
);
TR.displayName = "TR";

export const TH = forwardRef<HTMLTableCellElement, ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      scope="col"
      className={cn(
        "border-b border-border px-4 py-2.5 text-xs font-semibold uppercase tracking-wider",
        className,
      )}
      {...props}
    />
  ),
);
TH.displayName = "TH";

export const TD = forwardRef<HTMLTableCellElement, TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <td ref={ref} className={cn("px-4 py-3 align-middle text-text", className)} {...props} />
  ),
);
TD.displayName = "TD";
