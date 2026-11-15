import type { ReactNode } from "react";
import localFont from "next/font/local";
import { GhostNavigation } from "./navigation";
import styles from "./styles";
import "./ghost.css";

const inter = localFont({ src: "../../public/ghost/fonts/inter-latin.woff2", weight: "100 900", variable: "--ghost-body", display: "swap" });
const manrope = localFont({ src: "../../public/ghost/fonts/manrope-latin.woff2", weight: "200 800", variable: "--ghost-heading", display: "swap" });
const space = localFont({ src: "../../public/ghost/fonts/space-grotesk-latin.woff2", weight: "300 700", variable: "--ghost-wordmark", display: "swap" });

export function GhostShell({ children, home = false }: { children: ReactNode; home?: boolean }) {
  return <div className={`dark ${styles.theme} ${inter.variable} ${manrope.variable} ${space.variable}`}>
    <a href="#main-content" className={styles.skip}>Skip to content</a>
    <GhostNavigation home={home} fontClasses={`${inter.variable} ${manrope.variable} ${space.variable}`} />
    <main id="main-content">{children}</main>
    <footer className={styles.footer}><span>GHOST</span><span>Your game. Another dimension.</span></footer>
  </div>;
}
