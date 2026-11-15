// Which MediaPipe points the 3D figure draws: its bones, joint dots and head. Shared by the
// three.js scene (drawing) and provenance.ts (which guessed joints actually show), and kept
// free of three.js so the page bundle doesn't load it.

/** Derived points after the 33 MediaPipe landmarks. */
export const NECK = 33; // midpoint of the shoulders
export const HEAD = 34; // midpoint of the ears
export const POINT_COUNT = 35;

export const BONES: ReadonlyArray<readonly [number, number]> = [
  [11, 12], [11, 23], [12, 24], [23, 24], // torso
  [11, 13], [13, 15], [15, 19], // left arm and hand
  [12, 14], [14, 16], [16, 20], // right arm and hand
  [23, 25], [25, 27], [27, 29], [29, 31], [27, 31], // left leg and foot
  [24, 26], [26, 28], [28, 30], [30, 32], [28, 32], // right leg and foot
  [NECK, HEAD],
];

export const JOINT_DOTS: readonly number[] = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];

/** The MediaPipe landmarks a drawn point comes from: the neck and head are midpoints. */
export function sourceJoints(point: number): readonly number[] {
  if (point === NECK) return [11, 12];
  if (point === HEAD) return [7, 8];
  return [point];
}

/** Every MediaPipe landmark the figure shows, directly or through the neck and head. */
export const DRAWN_JOINTS: readonly number[] = [
  ...new Set([...BONES.flat(), ...JOINT_DOTS, HEAD].flatMap((p) => sourceJoints(p))),
].sort((a, b) => a - b);
