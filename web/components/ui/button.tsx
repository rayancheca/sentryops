import { cva, type VariantProps } from "class-variance-authority";
import {
  Children,
  cloneElement,
  forwardRef,
  isValidElement,
  type ButtonHTMLAttributes,
  type ReactElement,
} from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  // base: dense, monospace-friendly, compositor-only transitions
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium tracking-tight " +
    "transition-[transform,opacity,background-color,border-color,box-shadow,color] duration-[140ms] ease-[cubic-bezier(0.16,1,0.3,1)] " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-bg " +
    "disabled:pointer-events-none disabled:opacity-40 active:translate-y-px " +
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-bg shadow-panel hover:bg-accent/90 hover:shadow-glow active:bg-accent",
        outline:
          "border border-border bg-surface text-text hover:border-accent-dim hover:bg-surface-2 hover:text-text",
        ghost: "text-text-dim hover:bg-surface-2 hover:text-text",
        danger:
          "bg-danger/15 text-danger border border-danger/40 hover:bg-danger/25 hover:border-danger",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-4",
        icon: "size-10 p-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  /** Render the single child element with button styles (e.g. an <a> or <Link>). */
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, children, ...props }, ref) => {
    const classes = cn(buttonVariants({ variant, size }), className);

    if (asChild) {
      const child = Children.only(children) as ReactElement<{ className?: string }>;
      if (!isValidElement(child)) {
        throw new Error("Button with asChild requires a single valid React element child.");
      }
      return cloneElement(child, {
        className: cn(classes, child.props.className),
      });
    }

    return (
      <button ref={ref} className={classes} {...props}>
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
