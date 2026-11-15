import type { Metadata } from "next";
import { Suspense } from "react";
import { GhostDemoFromUrl } from "@/app/ghost/ghost-demo";
export const metadata: Metadata = { title: "Demo — GHOST" };
export default function DemoPage() { return <main className="site-demo"><header className="site-page-heading"><p className="site-eyebrow">The Ghost demo</p><h1>Explore a sample swing.</h1><p>See the coach’s call, watch your ghost make the fix, and explore the PREDICTED ball paths.</p></header><Suspense fallback={<p role="status">Loading swings…</p>}><GhostDemoFromUrl /></Suspense></main>; }
