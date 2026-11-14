// Which joints the camera measured and which the pipeline guessed, frame by frame. Read
// straight from the swing file: nothing here measures anything. A joint is guessed on a frame
// when the file says so in any of these ways (docs/interfaces.md, PR #39):
//   frames[i].filled[j] is true             interpolated, repaired or copied from a parent joint
//   frames[i].visibility[j] is below 0.5    the pose model barely saw it
//   frames[i].approximatedJoints lists it   (joint names or indices)
//   metadata.approximatedJoints lists it    (for the whole swing, so every frame)
// A file with none of these fields doesn't say. Its joints are drawn as measured, and the page
// says the file doesn't record it: absence means unknown, not measured.

import { DRAWN_JOINTS } from "./skeleton-shape";

const LANDMARK_COUNT = 33;

/** Same cut-off as the coach (services/coach/measure_extra.py MIN_VISIBILITY). */
export const MIN_VISIBILITY = 0.5;

/** MediaPipe pose landmark names, in index order. */
const LANDMARKS = [
  "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner", "right_eye", "right_eye_outer",
  "left_ear", "right_ear", "mouth_left", "mouth_right",
  "left_shoulder", "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
  "left_pinky", "right_pinky", "left_index", "right_index", "left_thumb", "right_thumb",
  "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle",
  "left_heel", "right_heel", "left_foot_index", "right_foot_index",
] as const;

/** Plain words for each landmark: the player's own left and right. */
const WORDS = [
  "nose", "left eye", "left eye", "left eye", "right eye", "right eye", "right eye",
  "head (left ear)", "head (right ear)", "mouth", "mouth",
  "left shoulder", "right shoulder", "left elbow", "right elbow", "left wrist", "right wrist",
  "left little finger", "right little finger", "left index finger", "right index finger", "left thumb", "right thumb",
  "left hip", "right hip", "left knee", "right knee", "left ankle", "right ankle",
  "left heel", "right heel", "left toes", "right toes",
] as const;

export function jointWords(joint: number): string {
  return WORDS[joint] ?? `joint ${joint}`;
}

export type GuessField = "filled" | "visibility" | "approximatedJoints";

export type GuessedJoints = {
  /** One list per frame, one flag per landmark: true = guessed. All false where the file says nothing. */
  frames: boolean[][];
  /** Per frame: the frame carries its own record (filled, visibility or approximatedJoints). */
  recorded: boolean[];
  /** Landmarks `metadata.approximatedJoints` lists for the whole swing, or null without that list. */
  swingList: number[] | null;
  /** Which fields the file used. */
  fields: GuessField[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function squash(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]/g, "");
}

const BY_NAME = new Map<string, number>(LANDMARKS.map((name, i) => [squash(name), i]));

/** 16, "16", "right_wrist", "RIGHT_WRIST" or "rightWrist" -> 16. Null for anything else. */
function landmarkIndex(value: unknown): number | null {
  if (typeof value === "number") return Number.isInteger(value) && value >= 0 && value < LANDMARK_COUNT ? value : null;
  if (typeof value !== "string") return null;
  const key = squash(value);
  if (/^\d+$/.test(key)) return landmarkIndex(Number(key));
  return BY_NAME.get(key) ?? null;
}

function listedJoints(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null;
  return value.map(landmarkIndex).filter((j): j is number => j !== null);
}

/** frame[key] when it has one entry per landmark, else null: unknown, the way the coach reads it. */
function perLandmark(frame: Record<string, unknown>, key: string): unknown[] | null {
  const value = frame[key];
  return Array.isArray(value) && value.length === LANDMARK_COUNT ? value : null;
}

/** Reads every guessed-joint field the swing JSON has. Never throws: unreadable fields count as absent. */
export function readGuessedJoints(swing: unknown): GuessedJoints {
  const rawFrames = isRecord(swing) && Array.isArray(swing.frames) ? swing.frames : [];
  const metadata = isRecord(swing) && isRecord(swing.metadata) ? swing.metadata : {};
  const swingList = listedJoints(metadata.approximatedJoints);
  const fields = new Set<GuessField>();
  if (swingList) fields.add("approximatedJoints");

  const recorded: boolean[] = [];
  const frames = rawFrames.map((frame: unknown) => {
    const flags = new Array<boolean>(LANDMARK_COUNT).fill(false);
    for (const j of swingList ?? []) flags[j] = true;
    let own = false;
    if (isRecord(frame)) {
      const filled = perLandmark(frame, "filled");
      if (filled) {
        own = true;
        fields.add("filled");
        filled.forEach((f, j) => {
          if (f === true) flags[j] = true;
        });
      }
      const visibility = perLandmark(frame, "visibility");
      if (visibility) {
        own = true;
        fields.add("visibility");
        visibility.forEach((v, j) => {
          if (typeof v === "number" && Number.isFinite(v) && v < MIN_VISIBILITY) flags[j] = true;
        });
      }
      const approximated = listedJoints(frame.approximatedJoints);
      if (approximated) {
        own = true;
        fields.add("approximatedJoints");
        for (const j of approximated) flags[j] = true;
      }
    }
    recorded.push(own);
    return flags;
  });
  return { frames, recorded, swingList, fields: [...fields] };
}

/**
 * The ghost is your swing with one fix applied, frame for frame, so a joint guessed in yours is
 * guessed in the ghost too, whatever the ghost's own file says. Needs the same frame count.
 */
export function withGuessesFrom(target: GuessedJoints, source: GuessedJoints): GuessedJoints {
  if (target.frames.length !== source.frames.length) return target;
  const lists = [target.swingList, source.swingList].filter((l): l is number[] => l !== null);
  return {
    frames: target.frames.map((flags, i) => flags.map((guessed, j) => guessed || source.frames[i][j])),
    recorded: target.recorded.map((own, i) => own || source.recorded[i]),
    swingList: lists.length > 0 ? [...new Set(lists.flat())].sort((a, b) => a - b) : null,
    fields: [...new Set([...target.fields, ...source.fields])],
  };
}

const DRAWN = new Set(DRAWN_JOINTS);

/** Landmarks the figure draws that are guessed on this frame, i.e. what shows faded. */
export function fadedJointsAt(guessed: GuessedJoints, frame: number): number[] {
  const flags = guessed.frames[frame];
  return flags ? DRAWN_JOINTS.filter((j) => flags[j]) : [];
}

export type JointFrames = {
  joint: number;
  words: string;
  /** How many frames it's guessed on. */
  count: number;
  /** Runs of consecutive frames, [first, last], zero-based like the frame counter under the view. */
  ranges: [number, number][];
};

export type GuessSummary = {
  totalFrames: number;
  /** Frames with their own record. 0 = the file doesn't mark guessed joints frame by frame. */
  recordedFrames: number;
  /** Frames where at least one joint the figure draws is guessed: those show something faded. */
  fadedFrames: number;
  /** Drawn joints guessed on at least one frame. */
  faded: JointFrames[];
  /** Guessed landmarks the figure doesn't draw (face, little fingers, thumbs). */
  hidden: JointFrames[];
  fields: GuessField[];
  swingList: number[] | null;
};

function framesOf(guessed: GuessedJoints, joint: number): JointFrames | null {
  const ranges: [number, number][] = [];
  let count = 0;
  guessed.frames.forEach((flags, i) => {
    if (!flags[joint]) return;
    count++;
    const last = ranges[ranges.length - 1];
    if (last && last[1] === i - 1) last[1] = i;
    else ranges.push([i, i]);
  });
  return count > 0 ? { joint, words: jointWords(joint), count, ranges } : null;
}

/** Counts of the file's own flags, for the page to quote. A tally, not a measurement. */
export function summariseGuesses(guessed: GuessedJoints): GuessSummary {
  const all = Array.from({ length: LANDMARK_COUNT }, (_, j) => framesOf(guessed, j)).filter(
    (f): f is JointFrames => f !== null,
  );
  return {
    totalFrames: guessed.frames.length,
    recordedFrames: guessed.recorded.filter(Boolean).length,
    fadedFrames: guessed.frames.filter((flags) => DRAWN_JOINTS.some((j) => flags[j])).length,
    faded: all.filter((f) => DRAWN.has(f.joint)),
    hidden: all.filter((f) => !DRAWN.has(f.joint)),
    fields: guessed.fields,
    swingList: guessed.swingList,
  };
}

/** [[21, 35], [60, 73]] -> "frames 21–35 and 60–73". */
export function formatFrameRanges(ranges: [number, number][], totalFrames: number): string {
  if (ranges.length === 1 && ranges[0][0] === 0 && ranges[0][1] === totalFrames - 1) return "every frame";
  const parts = ranges.map(([a, b]) => (a === b ? `${a}` : `${a}–${b}`));
  const single = ranges.length === 1 && ranges[0][0] === ranges[0][1];
  const list = parts.length > 1 ? `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}` : parts[0];
  return `${single ? "frame" : "frames"} ${list}`;
}

/** Share of frames, as a whole percent, for display. */
export function percentOf(part: number, whole: number): number {
  return whole > 0 ? Math.round((100 * part) / whole) : 0;
}
