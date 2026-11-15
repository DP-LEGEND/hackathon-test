"use client";

import type { ReactNode } from "react";
import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

const destinations = [
  { label: "Home", href: "/" },
  { label: "Demo", href: "/demo" },
  { label: "Try your swing", href: "/upload" },
] as const;
const productRoutes = new Set(["/", "/demo", "/upload", "/ghost"]);

/** The route keeps ownership of its content and state; this layout only supplies the shared frame. */
export function SiteShell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  if (!productRoutes.has(path)) return children;
  const active = path === "/ghost" ? "/demo" : path;
  const links = destinations.map(({ label, href }) => (
    <Link key={href} href={href} aria-current={active === href ? "page" : undefined} onClick={() => setMenuOpen(false)}>
      {label}
    </Link>
  ));

  return (
    <div className="dark ghost-theme site-shell">
      <a href="#site-content" className="site-skip">Skip to content</a>
      <header className="site-header">
        <Link href="/" aria-label="GHOST home" className="site-brand">
          {path === "/" ? <Image src="/ghost/brand.svg" width={44} height={32} alt="" priority /> : "GHOST"}
        </Link>
        <nav aria-label="Main navigation" className="site-nav">{links}</nav>
        <Dialog open={menuOpen} onOpenChange={setMenuOpen}>
          <DialogTrigger render={<Button variant="outline" className="site-menu-trigger" />}>
            <Menu aria-hidden /> Menu
          </DialogTrigger>
          <DialogContent showCloseButton={false} className="dark ghost-theme site-menu" style={{ translate: "none" }}>
            <div className="site-menu-heading">
              <DialogTitle className="site-brand">GHOST</DialogTitle>
              <DialogClose render={<Button variant="outline" className="site-menu-close" />}>Close <X aria-hidden /></DialogClose>
            </div>
            <p className="site-eyebrow">Explore Ghost</p>
            <nav aria-label="Mobile navigation">{links}</nav>
          </DialogContent>
        </Dialog>
      </header>
      {/* /ghost already owns a main landmark; do not nest it in another main. */}
      <div id="site-content" className="site-content" tabIndex={-1}>{children}</div>
      <footer className="site-footer"><span>GHOST</span><span>Your game. Another dimension.</span></footer>
    </div>
  );
}
