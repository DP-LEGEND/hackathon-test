"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Menu } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export function MobileNav({ children, appName }: { children: ReactNode; appName: string }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => { if (desktop.matches) setOpen(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="ghost" size="icon" className="size-11 lg:hidden" />}>
        <Menu aria-hidden="true" /><span className="sr-only">Open navigation</span>
      </DialogTrigger>
      <DialogContent className="top-0 left-0 flex h-dvh w-72 max-w-[calc(100%-2rem)] translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none p-0 sm:max-w-72 [&>[data-slot=dialog-close]]:top-6 [&>[data-slot=dialog-close]]:right-3">
        <DialogTitle className="sr-only">{appName} navigation</DialogTitle>
        <DialogDescription className="sr-only">Choose a destination in your workspace.</DialogDescription>
        <div className="min-h-0 flex-1" onClickCapture={(event) => {
          if (event.target instanceof Element && event.target.closest("a")) setOpen(false);
        }}>{children}</div>
      </DialogContent>
    </Dialog>
  );
}
