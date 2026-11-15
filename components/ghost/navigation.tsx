"use client";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import styles from "./styles";

const destinations = [["Home", "/"], ["Demo", "/demo"], ["Your swing", "/upload"]] as const;
export function GhostNavigation({ home, fontClasses }: { home: boolean; fontClasses: string }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const active = path === "/ghost" ? "/demo" : path;
  return <header className={styles.navigation}>
    <Link href="/" aria-label="GHOST home" className={styles.brand}>{home ? <Image src="/ghost/brand.svg" width={44} height={32} alt="" priority /> : "GHOST"}</Link>
    <nav aria-label="Main navigation" className={styles.desktopNav}>{destinations.map(([name, href]) => <Link key={href} href={href} aria-current={active === href ? "page" : undefined}>{name}</Link>)}</nav>
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" className={styles.menuTrigger} />} aria-label="Open navigation"><Menu aria-hidden /> Menu</DialogTrigger>
      <DialogContent showCloseButton={false} className={`dark ${styles.theme} ${styles.mobileMenu} ${fontClasses}`} style={{ translate: "none" }}>
        <div className={styles.menuHeader}><DialogTitle className={styles.brand}>GHOST</DialogTitle><DialogClose render={<Button variant="outline" className={styles.pill} />}>Close <X aria-hidden /></DialogClose></div>
        <p className={styles.eyebrow}>Explore Ghost</p>
        <nav aria-label="Mobile navigation">{destinations.map(([name, href]) => <Link key={href} href={href} aria-current={active === href ? "page" : undefined} onClick={() => setOpen(false)}>{name}</Link>)}</nav>
      </DialogContent>
    </Dialog>
  </header>;
}
