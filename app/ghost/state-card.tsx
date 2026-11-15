// Loading, empty and failed states in the swing view, in the Figma empty-state look: an icon,
// the message, then what you can do about it. The wording always comes from the caller.

import type { ReactNode } from "react";
import { CircleAlert, Inbox, LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { look } from "./look";

const ICONS = { loading: LoaderCircle, error: CircleAlert, empty: Inbox } as const;

export function StateCard({
  tone,
  role,
  actions,
  className,
  children,
}: {
  tone: keyof typeof ICONS;
  /** "status" for loading, "alert" for a failure; none for a plain empty list. */
  role?: "status" | "alert";
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  const Icon = ICONS[tone];
  return (
    <div
      role={role}
      className={cn(look.card, "flex flex-col items-center gap-3 px-5 py-8 text-center sm:px-8 sm:py-10", className)}
    >
      <Icon
        aria-hidden
        className={cn(
          "size-6 shrink-0",
          tone === "error" ? "text-destructive" : "text-primary",
          tone === "loading" && "motion-safe:animate-spin",
        )}
      />
      <div
        className={cn(
          "max-w-xl text-sm leading-relaxed text-pretty",
          tone === "error" ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {children}
      </div>
      {actions && <div className="flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}
