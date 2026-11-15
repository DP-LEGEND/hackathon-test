import type { Metadata } from "next";
import localFont from "next/font/local";
import { SiteShell } from "@/components/layout/site-shell";
import "./globals.css";
import "@/components/ghost/ghost.css";
import "@/components/layout/site-shell.css";

const inter = localFont({ src: "../public/ghost/fonts/inter-latin.woff2", weight: "100 900", variable: "--ghost-body", display: "swap" });
const manrope = localFont({ src: "../public/ghost/fonts/manrope-latin.woff2", weight: "200 800", variable: "--ghost-heading", display: "swap" });
const space = localFont({ src: "../public/ghost/fonts/space-grotesk-latin.woff2", weight: "300 700", variable: "--ghost-wordmark", display: "swap" });

export const metadata: Metadata = {
  title: "GHOST · Swing coach",
  description: "See your swing. Find your edge.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${manrope.variable} ${space.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col"><SiteShell>{children}</SiteShell></body>
    </html>
  );
}

