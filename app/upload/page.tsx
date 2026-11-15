// "Try your own swing": send one clip to the pipeline, then open the new swing in /ghost.
// Owner: Sammy. Flow: upload-form.tsx. Request, answers and limits: README.md.

import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { UploadForm } from "./upload-form";
import "./upload.css";

export const metadata: Metadata = {
  title: "Try your own swing · Ghost",
  description: "Upload one squash swing: the coach names the one fix that matters, and your ghost makes it.",
};

export default function UploadPage() {
  return (
    <main className="upload-page">
      <div className="upload-container">
        <header className="site-page-heading">
          <Link
            href="/ghost"
            className="upload-back site-eyebrow"
          >
            <ArrowLeft aria-hidden className="size-3.5" />
            Ghost
          </Link>
          <h1>Try your own swing</h1>
          <p>
            Film one swing on your phone and drop the video here. Code measures it, the coach names the one fix that
            matters, and your ghost makes it.
          </p>
        </header>
        <UploadForm />
      </div>
    </main>
  );
}
