// "Ask the coach" tools: the agent may call a fix the coach's pick only when it is the coach's
// chosen ghost_fix. Run from the repo root (jiti ships with ESLint and Tailwind):
//   JITI_JSX=1 JITI_ALIAS="{\"@/\":\"$PWD/\"}" node --import jiti/register --test app/ghost/ask-coach-tools.test.ts

import assert from "node:assert/strict";
import { test } from "node:test";
import { COACHS_PICK, YOUR_PICK, ghostResult } from "./ask-coach-tools";
import type { CompareResult } from "./compare";
import type { FixOption } from "./sources";

// Only the fields ghostResult reads; the numbers are placeholders, not swing data.
function compareFor(fixId: string): CompareResult {
  return {
    fix: { id: fixId, amount: 20, unit: "deg" },
    noCorrection: false,
    ghostNote: null,
    metrics: [],
    ball: {
      outcome: { you: "in", ghost: "in" },
      speedKmh: { you: 100, ghost: 110 },
      frontWallHeightM: { you: 1, ghost: 1.5 },
      landingDepthM: { you: 8, ghost: 9 },
    },
    assumptions: { note: "placeholder" },
  } as unknown as CompareResult;
}

function option(id: string, flagged: boolean): FixOption {
  return { id, amount: 20, unit: "deg", flagged, file: null, unavailable: null };
}

test("the coach's chosen ghost_fix is the coach's pick", () => {
  const result = ghostResult(compareFor("turn_shoulders_less"), option("turn_shoulders_less", true), "turn_shoulders_less");
  assert.equal(result.picked_by, COACHS_PICK);
});

test("another flagged fix the player selected is the player's pick, not the coach's", () => {
  // flagged = the coach found that fault too, but it is not the fix the coach chose for the ghost.
  const result = ghostResult(compareFor("straighten_elbow"), option("straighten_elbow", true), "turn_shoulders_less");
  assert.equal(result.picked_by, YOUR_PICK);
  assert.equal(result.demo_size_not_a_coached_fix, false);
});

test("a demo-size fix and a coach file without ghost_fix are never the coach's pick", () => {
  assert.equal(ghostResult(compareFor("close_stance"), option("close_stance", false), "turn_shoulders_less").picked_by, YOUR_PICK);
  assert.equal(ghostResult(compareFor("turn_shoulders_less"), option("turn_shoulders_less", true), null).picked_by, YOUR_PICK);
});

test("the tool result no longer has the flagged-based coachs_pick field", () => {
  const result = ghostResult(compareFor("straighten_elbow"), option("straighten_elbow", true), "turn_shoulders_less");
  assert.equal("coachs_pick" in result, false);
});
