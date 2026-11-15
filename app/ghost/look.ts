// Shared classes for the swing view's GHOST look (#71 and the Figma Results frames 21:651 and
// 21:723): 20px cards on the panel fill, Manrope titles, small uppercase labels, pill buttons.
// The tokens and fonts behind them are in swing-view.css.

export const look = {
  /** A card: 20px radius, panel fill, hairline border. */
  card: "rounded-[20px] border bg-(--panel)",
  /** Card padding, roomier from tablet up. */
  pad: "p-4 sm:p-6",
  /** A card title in Manrope. */
  title: "ghost-swing-title text-[17px] leading-snug tracking-[-0.01em]",
  /** A small uppercase label, like the Figma "COACH'S CALL". */
  label: "text-[11px] leading-4 font-semibold tracking-[0.14em] uppercase",
  /** A pill button. */
  pill: "rounded-full px-4",
  /** A small chip (badges). */
  chip: "h-6 rounded-full px-2.5 text-[11px] font-semibold tracking-[0.06em]",
  /** A number with its unit, kept on one line ("133.2 km/h"). */
  value: "whitespace-nowrap tabular-nums",
  /** The 3D view's height below lg, where the coach's call sits under it and the stage grows with the call. */
  stageView: "h-[max(20rem,min(52vh,520px))]",
  /**
   * The replay stage's height from lg up (#76), where the coach's call sits beside the 3D view: it
   * fills the screen under the page heading, so the whole view and the call fit above the fold (a
   * 516 px view at 1440×900, 336 px at 1280×720). A long call scrolls in its column instead of
   * resizing the view. The loading placeholder uses both heights, so the page doesn't jump.
   */
  stageWide: "lg:h-[max(20rem,min(760px,calc(100svh-24rem)))]",
  /**
   * A row of buttons that scrolls sideways on phones instead of wrapping into several rows; from
   * `sm` up its buttons join the parent's wrapping row. The padding keeps focus rings unclipped.
   */
  phoneRow: "-mx-1 flex snap-x gap-2 overflow-x-auto p-1 sm:contents",
  /** A button in a `phoneRow`. */
  phoneRowItem: "shrink-0 snap-start",
} as const;
