import type { Metadata } from "next";
import { GhostShell } from "@/components/ghost/shell";
import { LandingHero, ProcessPanels } from "@/components/ghost/landing";
export const metadata: Metadata = { title: "GHOST — See your swing. Find your edge.", description: "Explore your squash technique in 3D with measured coaching and simulated comparisons." };
export default function Home() {
  return <GhostShell home><LandingHero /><ProcessPanels /></GhostShell>;
}
