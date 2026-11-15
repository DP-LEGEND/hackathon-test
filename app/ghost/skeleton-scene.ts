// three.js scene for /ghost: a squash court in court coordinates, two skeletons and the two
// PREDICTED ball paths. Court coordinates (metres): x across 0..6.40, y up, z back from the
// front wall 0..9.75. Ball paths arrive in these coordinates already (services/physics/ball.py).
// Imperative on purpose: the React component owns playback and calls setPoses() every frame.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import type { Vec3 } from "@/lib/ghost/types";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import { BONES, HEAD, JOINT_DOTS, NECK, POINT_COUNT, sourceJoints } from "./skeleton-shape";
import type { SkeletonPose, SwingCoordinates } from "./swing";

/** Standard squash court (World Squash singles), metres. */
export const COURT = {
  width: 6.4,
  length: 9.75,
  shortLine: 5.44, // from the front wall
  serviceBox: 1.6,
  frontWallOut: 4.57,
  backWallOut: 2.13,
  serviceLine: 1.78,
  tin: 0.48,
} as const;

/**
 * Pipeline skeletons are hip-centred, y up, and face +z. Our front wall is at z = 0, so both
 * figures turn 180° about y to face it: [x, y, z] -> [-x, y, -z]. It's a turn, not a mirror,
 * so a right-hander's hitting hand stays on their right (+x, towards the right wall). Swings
 * that physics already returns in court coordinates aren't turned (see placeFigures).
 */
export const FACING_Y = Math.PI;

/** Where a hip-centred point lands after the facing turn (what group.rotation.y = FACING_Y does). */
export function turned(p: Vec3): Vec3 {
  return [-p[0], p[1], -p[2]];
}

/**
 * Hip-centred joints have no court position, so where that player stands is for display only:
 * at the T, or (with ball paths) where the hitting hand meets the ball. Court-coordinate swings
 * stand where physics put them.
 */
const T_SPOT = { x: COURT.width / 2, z: COURT.shortLine } as const;
const SIDE_BY_SIDE_OFFSET = 1.1; // metres along x, towards the middle of the court

const BONE_RADIUS = 0.022;
const JOINT_RADIUS = 0.032;
const HEAD_RADIUS = 0.1;

// Guessed joints (the camera couldn't see them) and every bone touching one are drawn faded and
// dashed, frame by frame, so a guess never looks like a measurement.
const FADED_OPACITY = 0.35; // times the figure's own opacity
const DASH_PERIOD = 0.07; // metres of bone per dash plus its gap
const DASH_FILL = 0.55; // share of each period that is dash
const DASH_THIN = 0.7; // dashed bones are thinner than measured ones
const MAX_DASHES = 12; // per bone: enough for 0.84 m at DASH_PERIOD
const HIDDEN = new THREE.Matrix4().makeScale(0, 0, 0);

const PATH_RADIUS = 0.012;
const BOUNCE_RADIUS = 0.035;
const BALL_RADIUS = 0.03; // a squash ball is 40 mm across; drawn a little bigger to be seen

const UP = new THREE.Vector3(0, 1, 0);
const tmpDir = new THREE.Vector3();
const tmpMid = new THREE.Vector3();
const tmpScale = new THREE.Vector3();
const tmpQuat = new THREE.Quaternion();
const tmpMatrix = new THREE.Matrix4();
const dashStart = new THREE.Vector3();
const dashEnd = new THREE.Vector3();

/** Matrix that turns a unit cylinder (height 1 along y) into a segment from a to b. */
function segmentMatrix(a: THREE.Vector3, b: THREE.Vector3, thickness: number): THREE.Matrix4 {
  tmpDir.subVectors(b, a);
  const length = tmpDir.length();
  if (length < 1e-6) return tmpMatrix.makeScale(0, 0, 0);
  tmpQuat.setFromUnitVectors(UP, tmpDir.divideScalar(length));
  tmpMid.addVectors(a, b).multiplyScalar(0.5);
  tmpScale.set(thickness, length, thickness);
  return tmpMatrix.compose(tmpMid, tmpQuat, tmpScale);
}

/** Frees the GPU memory of everything under `root` and removes its HTML tags. */
function disposeTree(root: THREE.Object3D) {
  root.traverse((object) => {
    // A tag only removes its own element when it is removed directly, not via a parent group.
    if (object instanceof CSS2DObject) object.element.remove();
    if (object instanceof THREE.Mesh || object instanceof THREE.LineSegments) {
      object.geometry.dispose();
      const materials: THREE.Material[] = Array.isArray(object.material) ? object.material : [object.material];
      materials.forEach((m) => m.dispose());
    }
    if (object instanceof THREE.InstancedMesh) object.dispose();
  });
}

type FigureStyle = {
  colour: string;
  opacity: number;
  /**
   * Extra radius in metres. The ghost is slightly fatter and drawn back faces only, so where
   * it overlaps the player it shows as a cyan rim and never tints the orange.
   */
  halo: number;
};

class SkeletonFigure {
  readonly group = new THREE.Group();
  private readonly points = Array.from({ length: POINT_COUNT }, () => new THREE.Vector3());
  /** Per drawn point (33 landmarks plus neck and head): guessed on the current frame. */
  private readonly guessed = new Array<boolean>(POINT_COUNT).fill(false);
  private readonly bones: THREE.InstancedMesh;
  private readonly dashes: THREE.InstancedMesh;
  private readonly joints: THREE.InstancedMesh;
  private readonly fadedJoints: THREE.InstancedMesh;
  private readonly head: THREE.Mesh;
  private readonly fadedHead: THREE.Mesh;
  private readonly racket: THREE.Mesh;
  private readonly thickness: number;

  constructor(style: FigureStyle) {
    const colour = new THREE.Color(style.colour);
    const transparent = style.opacity < 1;
    const material = new THREE.MeshStandardMaterial({
      color: colour,
      emissive: colour,
      emissiveIntensity: transparent ? 0.6 : 0.35,
      roughness: 0.55,
      metalness: 0,
      transparent,
      opacity: style.opacity,
      depthWrite: !transparent,
      side: transparent ? THREE.BackSide : THREE.FrontSide,
    });
    // Same colour, so orange stays the player and cyan the ghost, but faint.
    const faded = material.clone();
    faded.transparent = true;
    faded.opacity = style.opacity * FADED_OPACITY;
    faded.depthWrite = false;
    this.thickness = (BONE_RADIUS + style.halo) / BONE_RADIUS;
    const boneGeometry = new THREE.CylinderGeometry(BONE_RADIUS, BONE_RADIUS, 1, 10);
    const jointGeometry = new THREE.SphereGeometry(JOINT_RADIUS + style.halo, 16, 12);
    const headGeometry = new THREE.SphereGeometry(HEAD_RADIUS + style.halo, 24, 16);

    this.bones = new THREE.InstancedMesh(boneGeometry, material, BONES.length);
    this.dashes = new THREE.InstancedMesh(boneGeometry, faded, BONES.length * MAX_DASHES);
    this.joints = new THREE.InstancedMesh(jointGeometry, material, JOINT_DOTS.length);
    this.fadedJoints = new THREE.InstancedMesh(jointGeometry, faded, JOINT_DOTS.length);
    this.head = new THREE.Mesh(headGeometry, material);
    this.fadedHead = new THREE.Mesh(headGeometry, faded);
    this.fadedHead.visible = false;
    this.racket = new THREE.Mesh(boneGeometry, material);
    this.racket.matrixAutoUpdate = false;
    this.racket.visible = false;
    for (const mesh of [this.bones, this.dashes, this.joints, this.fadedJoints]) {
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.frustumCulled = false; // instances move every frame; skip stale bounds
    }
    this.dashes.count = 0;
    this.fadedJoints.count = 0;
    this.group.add(this.bones, this.dashes, this.joints, this.fadedJoints, this.head, this.fadedHead, this.racket);
    this.group.visible = false; // until the first pose arrives
  }

  update(pose: SkeletonPose) {
    const p = this.points;
    for (let j = 0; j < pose.joints.length; j++) p[j].fromArray(pose.joints[j]);
    p[NECK].addVectors(p[11], p[12]).multiplyScalar(0.5);
    p[HEAD].addVectors(p[7], p[8]).multiplyScalar(0.5);

    // This frame only: a landmark is faded when the file marks it guessed; the neck and head
    // when any landmark they come from is.
    const guessed = this.guessed;
    for (let j = 0; j < pose.joints.length; j++) guessed[j] = pose.guessed[j] === true;
    for (const point of [NECK, HEAD]) guessed[point] = sourceJoints(point).some((j) => guessed[j]);

    let dashes = 0;
    BONES.forEach(([a, b], i) => {
      if (guessed[a] || guessed[b]) {
        this.bones.setMatrixAt(i, HIDDEN);
        dashes = this.addDashes(p[a], p[b], dashes);
      } else {
        this.bones.setMatrixAt(i, segmentMatrix(p[a], p[b], this.thickness));
      }
    });
    this.bones.instanceMatrix.needsUpdate = true;
    this.dashes.count = dashes;
    this.dashes.instanceMatrix.needsUpdate = true;

    let fadedDots = 0;
    JOINT_DOTS.forEach((j, i) => {
      tmpMatrix.makeTranslation(p[j]);
      if (guessed[j]) {
        this.fadedJoints.setMatrixAt(fadedDots++, tmpMatrix);
        this.joints.setMatrixAt(i, HIDDEN);
      } else {
        this.joints.setMatrixAt(i, tmpMatrix);
      }
    });
    this.joints.instanceMatrix.needsUpdate = true;
    this.fadedJoints.count = fadedDots;
    this.fadedJoints.instanceMatrix.needsUpdate = true;

    this.head.position.copy(p[HEAD]);
    this.fadedHead.position.copy(p[HEAD]);
    this.head.visible = !guessed[HEAD];
    this.fadedHead.visible = guessed[HEAD];

    this.racket.visible = pose.racket !== null;
    if (pose.racket) {
      const [throat, tip] = pose.racket.map((v: Vec3) => new THREE.Vector3().fromArray(v));
      this.racket.matrix.copy(segmentMatrix(throat, tip, this.thickness * 0.6));
    }
    this.group.visible = true;
  }

  /** Dashes along a faded bone from instance `next` on; returns the next free instance. */
  private addDashes(a: THREE.Vector3, b: THREE.Vector3, next: number): number {
    const n = Math.min(MAX_DASHES, Math.max(1, Math.round(a.distanceTo(b) / DASH_PERIOD)));
    for (let k = 0; k < n; k++) {
      dashStart.lerpVectors(a, b, (k + (1 - DASH_FILL) / 2) / n);
      dashEnd.lerpVectors(a, b, (k + (1 + DASH_FILL) / 2) / n);
      this.dashes.setMatrixAt(next++, segmentMatrix(dashStart, dashEnd, this.thickness * DASH_THIN));
    }
    return next;
  }
}

/** One PREDICTED ball path as the scene draws it. Points are court coordinates. */
export type BallPathView = {
  points: Vec3[];
  /** Wall and floor hits. */
  bounces: Vec3[];
  /** [x, z] of the first floor bounce after the front wall, or null. */
  landing: [number, number] | null;
  /** Text of the on-court tag, e.g. "PREDICTED · you · tin". */
  label: string;
};

function pathTag(text: string, colour: string, above: boolean): CSS2DObject {
  const el = document.createElement("div");
  el.className =
    "rounded-md border bg-background/90 px-2 py-0.5 font-mono text-xs leading-tight font-semibold tracking-wide whitespace-nowrap";
  el.style.color = colour;
  el.style.borderColor = colour;
  el.style.margin = above ? "0 0 6px" : "6px 0 0";
  el.textContent = text;
  const tag = new CSS2DObject(el);
  tag.center.set(0.5, above ? 1 : 0); // above or below its anchor so the two tags don't overlap
  return tag;
}

/**
 * Same trick as the skeletons: the ghost's path is fatter and drawn back faces only, so where
 * the two paths coincide it shows as a cyan rim around the orange instead of flickering.
 */
type PathStyle = { colour: string; opacity: number; halo: number; tagAbove: boolean };

function buildBallPath(path: BallPathView, style: PathStyle): THREE.Group {
  const { colour, opacity, halo, tagAbove } = style;
  const group = new THREE.Group();
  const transparent = opacity < 1;
  const material = new THREE.MeshBasicMaterial({
    color: colour,
    transparent,
    opacity,
    depthWrite: !transparent,
    side: halo > 0 ? THREE.BackSide : THREE.FrontSide,
  });
  const points = path.points.map((p) => new THREE.Vector3().fromArray(p));

  const segments = new THREE.InstancedMesh(
    new THREE.CylinderGeometry(PATH_RADIUS + halo, PATH_RADIUS + halo, 1, 8),
    material,
    points.length - 1,
  );
  for (let i = 1; i < points.length; i++) segments.setMatrixAt(i - 1, segmentMatrix(points[i - 1], points[i], 1));
  segments.instanceMatrix.needsUpdate = true;
  segments.computeBoundingSphere();
  group.add(segments);

  if (path.bounces.length > 0) {
    const dots = new THREE.InstancedMesh(new THREE.SphereGeometry(BOUNCE_RADIUS + halo, 12, 8), material, path.bounces.length);
    path.bounces.forEach((b, i) => dots.setMatrixAt(i, tmpMatrix.makeTranslation(b[0], b[1], b[2])));
    dots.instanceMatrix.needsUpdate = true;
    dots.computeBoundingSphere();
    group.add(dots);
  }

  let anchor = points[points.length - 1];
  if (path.landing) {
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(tagAbove ? 0.11 : 0.17, tagAbove ? 0.16 : 0.21, 32), // ghost ring outside yours
      new THREE.MeshBasicMaterial({ color: colour, side: THREE.DoubleSide, transparent: true, opacity: 0.9 }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(path.landing[0], 0.006, path.landing[1]);
    group.add(ring);
    anchor = ring.position;
  }
  const tag = pathTag(path.label, colour, tagAbove);
  tag.position.copy(anchor);
  group.add(tag);
  return group;
}

function lines(points: number[], colour: number, opacity: number): THREE.LineSegments {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
  const material = new THREE.LineBasicMaterial({ color: colour, transparent: true, opacity });
  return new THREE.LineSegments(geometry, material);
}

/** Pairs of [x, y, z] points; consecutive corners become segments of a closed loop. */
function loop(corners: Vec3[]): number[] {
  return corners.flatMap((c, i) => [...c, ...corners[(i + 1) % corners.length]]);
}

function buildCourt(): THREE.Group {
  const { width: W, length: L } = COURT;
  const court = new THREE.Group();

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(W, L),
    new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.035, depthWrite: false }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.set(W / 2, 0, L / 2);
  court.add(floor);

  // 1 m grid on the floor (court edges are drawn by the outline below).
  const grid: number[] = [];
  for (let x = 1; x < W; x += 1) grid.push(x, 0.002, 0, x, 0.002, L);
  for (let z = 1; z < L; z += 1) grid.push(0, 0.002, z, W, 0.002, z);
  court.add(lines(grid, 0xffffff, 0.09));

  // Floor markings: outline, short line, half-court line, service boxes.
  const y = 0.004;
  const sl = COURT.shortLine;
  const box = COURT.serviceBox;
  const floorLines = [
    ...loop([[0, y, 0], [W, y, 0], [W, y, L], [0, y, L]]),
    0, y, sl, W, y, sl,
    W / 2, y, sl, W / 2, y, L,
    box, y, sl, box, y, sl + box,
    0, y, sl + box, box, y, sl + box,
    W - box, y, sl, W - box, y, sl + box,
    W - box, y, sl + box, W, y, sl + box,
  ];
  court.add(lines(floorLines, 0xd4d8de, 0.5));

  // Wall lines: front wall (out line, service line, tin), side-wall out lines, back wall.
  const { frontWallOut: fo, backWallOut: bo, serviceLine, tin } = COURT;
  const wallLines = [
    0, 0, 0, 0, fo, 0, W, 0, 0, W, fo, 0,
    0, fo, 0, W, fo, 0,
    0, serviceLine, 0, W, serviceLine, 0,
    0, tin, 0, W, tin, 0,
    0, fo, 0, 0, bo, L, W, fo, 0, W, bo, L,
    0, 0, L, 0, bo, L, W, 0, L, W, bo, L,
    0, bo, L, W, bo, L,
  ];
  court.add(lines(wallLines, 0xd4d8de, 0.28));
  return court;
}

export type FloorOffsets = { you: number; ghost: number };
export type CameraView = "player" | "court";

export type ReplayLayout = {
  /** Lowest foot height of each swing, so hip-centred swings stand on the floor. */
  floor: FloorOffsets;
  /** How the swings' joints sit on the court: hip-centred (turned and placed here) or court (as given). */
  coordinates: SwingCoordinates;
  /** Null hides the ball paths. Ghost null = one shared path (the fix doesn't change the ball). */
  ballPaths: { you: BallPathView; ghost: BallPathView | null } | null;
};

export type Placement = {
  /** Group positions in court coordinates. */
  you: Vec3;
  ghost: Vec3;
  /** Turn about y for both groups: FACING_Y for hip-centred swings, 0 for court ones. */
  facingY: number;
  /** Where the player stands on court: the camera aims here. */
  spot: { x: number; z: number };
  /** Direction along x towards the middle of the court: -1 on the right half, +1 on the left. */
  towardsMiddle: 1 | -1;
  /**
   * Offset for the ghost's PREDICTED ball path. Court swings: the same side-by-side shift as the
   * ghost, so its ball still leaves from its hand. Hip-centred swings: none (both paths start
   * at the ball's assumed spot, under your hand).
   */
  ghostBall: Vec3;
};

/**
 * Where both figures stand and which way they face.
 * - Court coordinates: exactly as given. No turn, no floor offset, no placement; the ghost and
 *   its ball path only get the side-by-side shift.
 * - Hip-centred: turned to face the front wall, feet on the floor, at the T. With `youWrist` and
 *   the ball's start, the "you" figure moves so its hitting wrist at the contact frame, after the
 *   turn and the floor offset, is exactly over the ball's start in x and z. Height isn't snapped:
 *   the wrist is measured about 0.9 m up at contact and the ball's assumed start is 0.6 m, so
 *   snapping would sink the feet into the floor. The ghost moves by the same offset, plus the
 *   side-by-side shift.
 */
export function placeFigures(
  floor: FloorOffsets,
  coordinates: SwingCoordinates,
  ballStart: Vec3 | null,
  sideBySide: boolean,
): Placement {
  if (coordinates.system === "court") {
    const [x, , z] = coordinates.youHips;
    const towardsMiddle = x >= COURT.width / 2 ? -1 : 1;
    const shift = sideBySide ? towardsMiddle * SIDE_BY_SIDE_OFFSET : 0;
    return { you: [0, 0, 0], ghost: [shift, 0, 0], facingY: 0, spot: { x, z }, towardsMiddle, ghostBall: [shift, 0, 0] };
  }
  let x: number = T_SPOT.x;
  let z: number = T_SPOT.z;
  if (coordinates.youWrist && ballStart) {
    const wrist = turned(coordinates.youWrist);
    x = ballStart[0] - wrist[0];
    z = ballStart[2] - wrist[2];
  }
  const towardsMiddle = x >= COURT.width / 2 ? -1 : 1;
  const shift = sideBySide ? towardsMiddle * SIDE_BY_SIDE_OFFSET : 0;
  return {
    you: [x, -floor.you, z],
    ghost: [x + shift, -floor.ghost, z],
    facingY: FACING_Y,
    spot: { x, z },
    towardsMiddle,
    ghostBall: [0, 0, 0],
  };
}

export class SkeletonScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly labels: CSS2DRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly resizeObserver: ResizeObserver;
  private readonly you = new SkeletonFigure({ colour: YOU_COLOUR, opacity: 1, halo: 0 });
  private readonly ghost = new SkeletonFigure({ colour: GHOST_COLOUR, opacity: 0.5, halo: 0.012 });
  private balls: THREE.Group | null = null;
  /** The ghost's own ball path inside `balls` (null when there's one shared path). */
  private ghostBall: THREE.Group | null = null;
  private floor: FloorOffsets = { you: 0, ghost: 0 };
  private coordinates: SwingCoordinates = { system: "hip-centred", youWrist: null };
  private ballStart: Vec3 | null = null;
  private sideBySide = false;
  private placement: Placement = placeFigures(this.floor, this.coordinates, null, false);
  private view: CameraView = "player";

  /** Throws if WebGL isn't available. */
  constructor(private readonly container: HTMLElement) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0); // the container's background shows through
    const canvas = this.renderer.domElement;
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    container.appendChild(canvas);

    // On-court tags (PREDICTED) are HTML laid over the canvas; clicks pass through to the canvas.
    this.labels = new CSS2DRenderer();
    const overlay = this.labels.domElement;
    overlay.style.position = "absolute";
    overlay.style.inset = "0";
    overlay.style.pointerEvents = "none";
    overlay.setAttribute("aria-hidden", "true");
    container.appendChild(overlay);

    this.camera = new THREE.PerspectiveCamera(40, 1, 0.05, 100);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 1;
    this.controls.maxDistance = 22;
    this.controls.maxPolarAngle = Math.PI * 0.495; // stay above the floor
    this.applyView();

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x1d2027, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(COURT.width / 2 + 3, 6, COURT.length + 2);
    this.scene.add(sun, buildCourt(), this.you.group, this.ghost.group);
    this.applyPlacement();

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  private resize() {
    const { clientWidth: width, clientHeight: height } = this.container;
    if (width === 0 || height === 0) return;
    this.renderer.setSize(width, height, false);
    this.labels.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  /** Turns and moves both figures to the current placement. True when the player's spot changed. */
  private applyPlacement(): boolean {
    const before = this.placement.spot;
    this.placement = placeFigures(this.floor, this.coordinates, this.ballStart, this.sideBySide);
    this.you.group.rotation.y = this.placement.facingY;
    this.ghost.group.rotation.y = this.placement.facingY;
    this.you.group.position.fromArray(this.placement.you);
    this.ghost.group.position.fromArray(this.placement.ghost);
    this.ghostBall?.position.fromArray(this.placement.ghostBall);
    const { x, z } = this.placement.spot;
    return x !== before.x || z !== before.z;
  }

  /** Moves the camera to the current preset and makes it what "Reset view" returns to. */
  private applyView() {
    const target = new THREE.Vector3();
    if (this.view === "court") {
      target.set(COURT.width / 2, 1.2, COURT.length * 0.45);
      this.camera.position.set(COURT.width / 2 + 2.6, 5.2, COURT.length + 5.2);
    } else {
      // From behind the player (they face the front wall, -z), a little towards the middle.
      const { x, z } = this.placement.spot;
      target.set(x, 1, z);
      this.camera.position.set(x + this.placement.towardsMiddle * 2.4, 1.9, z + 3.6);
    }
    this.controls.target.copy(target);
    this.controls.update();
    this.controls.saveState();
  }

  /** New swings or ball paths. Keeps the camera unless the player moved. */
  setReplay({ floor, coordinates, ballPaths }: ReplayLayout) {
    this.floor = floor;
    this.coordinates = coordinates;
    this.ballStart = ballPaths ? ballPaths.you.points[0] : null;
    if (this.applyPlacement()) this.applyView();

    if (this.balls) {
      this.scene.remove(this.balls);
      disposeTree(this.balls);
      this.balls = null;
      this.ghostBall = null;
    }
    if (ballPaths) {
      const group = new THREE.Group();
      group.add(buildBallPath(ballPaths.you, { colour: YOU_COLOUR, opacity: 1, halo: 0, tagAbove: true }));
      if (ballPaths.ghost) {
        const ghostBall = buildBallPath(ballPaths.ghost, { colour: GHOST_COLOUR, opacity: 0.7, halo: 0.007, tagAbove: false });
        ghostBall.position.fromArray(this.placement.ghostBall); // follows the ghost in side by side (court swings)
        group.add(ghostBall);
        this.ghostBall = ghostBall;
      }
      const ball = new THREE.Mesh(
        new THREE.SphereGeometry(BALL_RADIUS, 16, 12),
        new THREE.MeshBasicMaterial({ color: 0xf5f5f5 }),
      );
      ball.position.fromArray(ballPaths.you.points[0]);
      group.add(ball);
      this.balls = group;
      this.scene.add(group);
    }
  }

  /** Ghost null = hide the ghost. */
  setPoses(you: SkeletonPose, ghost: SkeletonPose | null) {
    this.you.update(you);
    if (ghost) this.ghost.update(ghost);
    else this.ghost.group.visible = false;
  }

  /** Overlay (default) or ghost moved beside the player, towards the middle of the court. */
  setSideBySide(on: boolean) {
    this.sideBySide = on;
    this.applyPlacement();
  }

  /** Close on the player, or the whole court to see both ball paths. */
  setView(view: CameraView) {
    this.view = view;
    this.applyView();
  }

  resetView() {
    this.controls.reset();
  }

  render() {
    this.controls.update(); // needed every frame for damping
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  }

  dispose() {
    this.resizeObserver.disconnect();
    this.controls.dispose();
    disposeTree(this.scene);
    this.renderer.dispose();
    this.renderer.domElement.remove();
    this.labels.domElement.remove();
  }
}
