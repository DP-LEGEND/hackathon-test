import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { WorkflowLab } from "./workflow-lab";
import { StudioStyles } from "./studio-styles";

export const metadata: Metadata = {
  title: "Workflow studio · UI Lab",
  description: "An isolated, mock-only AI workflow interface experiment.",
};

export default function UiLabPage() {
  return (
    <div className="lab-shell dark" data-ui-lab>
      <StudioStyles />
      <a href="#lab-main" className="lab-skipLink">Skip to workspace</a>
      <header className="lab-topbar">
        <div className="lab-topbarInner">
          <div className="lab-brand">
            <span className="lab-logoMark" aria-hidden="true"><i /><i /><i /></span>
            <span>Copper Signal</span><Badge variant="outline" className="lab-labBadge">UI lab</Badge>
          </div>
          <span className="lab-workspaceLabel">Intent. Execution. Outcome.</span>
          <Link href="/" aria-label="Back to starter" className="lab-backLink">
            <ArrowLeft aria-hidden="true" className="size-4" /><span className="hidden sm:inline">Back to starter</span>
          </Link>
        </div>
      </header>
      <main id="lab-main" tabIndex={-1} className="lab-main">
        <div className="lab-intro">
          <div>
            <p className="lab-eyebrow"><span aria-hidden="true" />A WORKSPACE FOR WHAT COMES NEXT</p>
            <h1>Ideas become actions.<span className="sr-only"> From intent to a clear next step.</span></h1>
            <p className="lab-introDescription">A calm command surface with a vivid, traceable execution story.</p>
          </div>
          <p className="lab-disclosure"><span className="lab-disclosureTitle"><span aria-hidden="true" />Local simulation</span>Mock progress. Fixed sample output.<br />No AI provider is connected.</p>
        </div>
        <WorkflowLab />
        <footer className="lab-footer"><span>Imperial AI Hackathon · Frontend experiment</span><span>No requests sent. Nothing stored.</span></footer>
      </main>
    </div>
  );
}
