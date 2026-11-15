// Lines saying what the coach didn't judge, or physics didn't measure, and why: one line per
// reason, so one guessed elbow reads as one line. The file's own list and reasons; nothing is
// decided here.

import { EyeOff } from "lucide-react";
import { groupNotJudged, listWords, type NotJudged } from "./compare";

export function ReasonList({ label, items }: { label: "Not judged" | "Not measured"; items: NotJudged[] }) {
  const groups = groupNotJudged(items);
  if (groups.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1" aria-label={label}>
      {groups.map((group) => (
        <li key={group.reason} className="flex gap-2 text-sm">
          <EyeOff aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
          <span>
            <span className="font-medium">{label}:</span> {listWords(group.checks)}.{" "}
            <span className="text-muted-foreground">{group.reason.charAt(0).toUpperCase() + group.reason.slice(1)}.</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
