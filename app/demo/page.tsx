import type { Metadata } from "next";
import { GhostShell } from "@/components/ghost/shell";
import { Suspense } from "react";
import { GhostDemoFromUrl } from "@/app/ghost/ghost-demo";
import styles from "@/components/ghost/styles";
export const metadata: Metadata = { title: "Demo — GHOST" };
export default function DemoPage() { return <GhostShell><section className={styles.process}><header className={styles.pageHeading}><p className={styles.eyebrow}>The Ghost demo</p><h1>Explore a sample swing.</h1><p className={styles.description}>See the coach’s call, watch your ghost make the fix, and explore the PREDICTED ball paths.</p></header><Suspense fallback={<p role="status">Loading swings…</p>}><GhostDemoFromUrl /></Suspense></section></GhostShell>; }
