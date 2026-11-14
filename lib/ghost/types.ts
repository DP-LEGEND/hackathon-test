// DRAFT contract between the Python service and the web app.
// Agree it as a team at 11:00, copy the final version into docs/interfaces.md,
// and keep the Python side (services/) returning exactly these shapes.

/** One [x, y, z] point in metres. Skeleton points are hip-centred; ball points use court coordinates. */
export type Vec3 = [number, number, number];

/** One video frame of the 33 MediaPipe world landmarks. */
export type SwingFrame = {
  t: number; // seconds from the start of the clip
  joints: Vec3[]; // length 33, MediaPipe landmark order
  racketTip?: Vec3 | null;
  racketThroat?: Vec3 | null;
};

export type Swing = {
  id: string;
  fps: number;
  contactFrame: number;
  frames: SwingFrame[];
};

export type Fault = {
  id: string; // e.g. "late_contact"
  label: string; // e.g. "Contact 18 cm behind front foot"
  size: number;
  unit: string; // "cm", "deg", "ms"
  confidence: "high" | "medium" | "low";
};

/** Always shown with a "PREDICTED" badge: there is no real ball in the demo. */
export type PredictedBallPath = {
  points: Vec3[];
  speedKmh: number;
};

export type CoachResult = {
  fix: string;
  why: string; // must quote the numbers the code measured
  drill: string;
  you: { swing: Swing; ball: PredictedBallPath };
  ghost: { swing: Swing; ball: PredictedBallPath };
};
