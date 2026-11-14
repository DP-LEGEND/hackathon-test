// three.js scene for /ghost: a squash court in court coordinates and two skeletons.
// Court coordinates (metres): x across 0..6.40, y up, z back from the front wall 0..9.75.
// Imperative on purpose: the React component owns playback and calls setPoses() every frame.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { Vec3 } from "@/lib/ghost/types";
import { GHOST_COLOUR, YOU_COLOUR } from "./colours";
import type { SkeletonPose } from "./swing";

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
 * Where the hip centre is drawn: the T. The pipeline gives hip-centred joints, not a court
 * position, so this placement is for display only.
 */
export const PLAYER_SPOT = { x: COURT.width / 2, z: COURT.shortLine } as const;
const SIDE_BY_SIDE_OFFSET = 1.1; // metres along x

// MediaPipe landmark indices, plus two derived points.
const NECK = 33; // midpoint of the shoulders
const HEAD = 34; // midpoint of the ears
const POINT_COUNT = 35;
const BONES: ReadonlyArray<readonly [number, number]> = [
  [11, 12], [11, 23], [12, 24], [23, 24], // torso
  [11, 13], [13, 15], [15, 19], // left arm and hand
  [12, 14], [14, 16], [16, 20], // right arm and hand
  [23, 25], [25, 27], [27, 29], [29, 31], [27, 31], // left leg and foot
  [24, 26], [26, 28], [28, 30], [30, 32], [28, 32], // right leg and foot
  [NECK, HEAD],
];
const JOINT_DOTS = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28];

const BONE_RADIUS = 0.022;
const JOINT_RADIUS = 0.032;
const HEAD_RADIUS = 0.1;

const UP = new THREE.Vector3(0, 1, 0);
const tmpDir = new THREE.Vector3();
const tmpMid = new THREE.Vector3();
const tmpScale = new THREE.Vector3();
const tmpQuat = new THREE.Quaternion();
const tmpMatrix = new THREE.Matrix4();

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
  private readonly bones: THREE.InstancedMesh;
  private readonly joints: THREE.InstancedMesh;
  private readonly head: THREE.Mesh;
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
    this.thickness = (BONE_RADIUS + style.halo) / BONE_RADIUS;
    const boneGeometry = new THREE.CylinderGeometry(BONE_RADIUS, BONE_RADIUS, 1, 10);
    const jointGeometry = new THREE.SphereGeometry(JOINT_RADIUS + style.halo, 16, 12);

    this.bones = new THREE.InstancedMesh(boneGeometry, material, BONES.length);
    this.joints = new THREE.InstancedMesh(jointGeometry, material, JOINT_DOTS.length);
    this.head = new THREE.Mesh(new THREE.SphereGeometry(HEAD_RADIUS + style.halo, 24, 16), material);
    this.racket = new THREE.Mesh(boneGeometry, material);
    this.racket.matrixAutoUpdate = false;
    this.racket.visible = false;
    for (const mesh of [this.bones, this.joints]) {
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.frustumCulled = false; // instances move every frame; skip stale bounds
    }
    this.group.add(this.bones, this.joints, this.head, this.racket);
  }

  update(pose: SkeletonPose) {
    const p = this.points;
    for (let j = 0; j < pose.joints.length; j++) p[j].fromArray(pose.joints[j]);
    p[NECK].addVectors(p[11], p[12]).multiplyScalar(0.5);
    p[HEAD].addVectors(p[7], p[8]).multiplyScalar(0.5);

    BONES.forEach(([a, b], i) => this.bones.setMatrixAt(i, segmentMatrix(p[a], p[b], this.thickness)));
    this.bones.instanceMatrix.needsUpdate = true;
    JOINT_DOTS.forEach((j, i) => this.joints.setMatrixAt(i, tmpMatrix.makeTranslation(p[j])));
    this.joints.instanceMatrix.needsUpdate = true;
    this.head.position.copy(p[HEAD]);

    this.racket.visible = pose.racket !== null;
    if (pose.racket) {
      const [throat, tip] = pose.racket.map((v: Vec3) => new THREE.Vector3().fromArray(v));
      this.racket.matrix.copy(segmentMatrix(throat, tip, this.thickness * 0.6));
    }
  }
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

export class SkeletonScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera: THREE.PerspectiveCamera;
  private readonly controls: OrbitControls;
  private readonly resizeObserver: ResizeObserver;
  private readonly you = new SkeletonFigure({ colour: YOU_COLOUR, opacity: 1, halo: 0 });
  private readonly ghost = new SkeletonFigure({ colour: GHOST_COLOUR, opacity: 0.5, halo: 0.012 });

  /** Throws if WebGL isn't available. */
  constructor(
    private readonly container: HTMLElement,
    floor: FloorOffsets,
  ) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0); // the container's background shows through
    const canvas = this.renderer.domElement;
    canvas.style.display = "block";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    container.appendChild(canvas);

    this.camera = new THREE.PerspectiveCamera(40, 1, 0.05, 100);
    const target = new THREE.Vector3(PLAYER_SPOT.x, 1, PLAYER_SPOT.z);
    this.camera.position.set(target.x + 2.4, 1.9, target.z + 3.6);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.copy(target);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.minDistance = 1;
    this.controls.maxDistance = 22;
    this.controls.maxPolarAngle = Math.PI * 0.495; // stay above the floor
    this.controls.update();
    this.controls.saveState();

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x1d2027, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(COURT.width / 2 + 3, 6, COURT.length + 2);
    this.scene.add(sun, buildCourt(), this.you.group, this.ghost.group);

    this.you.group.position.set(PLAYER_SPOT.x, -floor.you, PLAYER_SPOT.z);
    this.ghost.group.position.set(PLAYER_SPOT.x, -floor.ghost, PLAYER_SPOT.z);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
  }

  private resize() {
    const { clientWidth: width, clientHeight: height } = this.container;
    if (width === 0 || height === 0) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  setPoses(you: SkeletonPose, ghost: SkeletonPose) {
    this.you.update(you);
    this.ghost.update(ghost);
  }

  /** Overlay (default) or ghost moved beside the player along x. */
  setSideBySide(on: boolean) {
    this.ghost.group.position.x = PLAYER_SPOT.x + (on ? SIDE_BY_SIDE_OFFSET : 0);
  }

  resetView() {
    this.controls.reset();
  }

  render() {
    this.controls.update(); // needed every frame for damping
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    this.resizeObserver.disconnect();
    this.controls.dispose();
    this.scene.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.LineSegments) {
        object.geometry.dispose();
        const materials: THREE.Material[] = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((m) => m.dispose());
      }
    });
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}
