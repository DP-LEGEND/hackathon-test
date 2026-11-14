import { ArrowUpRight, Check, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

const priorities = [
  { number: "01", title: "Make one promise", detail: "Choose a single user and an outcome that can be demonstrated in under two minutes." },
  { number: "02", title: "Build the complete loop", detail: "Connect input, agent execution, and a useful result before expanding the feature set." },
  { number: "03", title: "Design for the unexpected", detail: "Make progress visible, preserve the brief on failure, and provide an obvious retry." },
];

export function ResultPreview({ brief, onReset }: { brief: string; onReset: () => void }) {
  return (
    <article className="lab-resultArticle">
      <div className="lab-resultContent">
        <div className="lab-resultSummary"><p className="lab-completionLabel"><Check aria-hidden="true" className="size-3.5" />SIMULATION COMPLETE</p><h3>A smaller scope.<br />A stronger demonstration.</h3><p className="lab-recommendation">Build one complete journey before adding more features.</p><p className="lab-outputDisclosure">Fixed mock output for interface testing. This plan is not generated from, or tailored to, your input.</p></div>
        <section aria-labelledby="priorities-heading" className="lab-priorities"><div className="lab-priorityHeader"><h4 id="priorities-heading">Recommended priorities</h4><span>Sample plan</span></div><ol>{priorities.map(item => <li key={item.number}><span className="lab-priorityNumber">{item.number}</span><div><h5>{item.title}</h5><p>{item.detail}</p></div></li>)}</ol></section>
        <section aria-labelledby="next-heading" className="lab-nextMove"><h4 id="next-heading">The next move <ArrowUpRight aria-hidden="true" className="size-4" /></h4><p>Write the happy-path demo script together. Assign one owner to each step, then agree on the API contract before implementation.</p></section>
        <section aria-labelledby="submitted-heading" className="lab-submittedBrief"><h4 id="submitted-heading">Your submitted brief</h4><p tabIndex={brief.length > 300 ? 0 : undefined}>{brief}</p></section>
      </div>
      <div className="lab-resultFooter"><span>Human review before any action.</span><Button variant="outline" className="lab-controlButton" onClick={onReset}><RotateCcw aria-hidden="true" />Reset preview</Button></div>
    </article>
  );
}
