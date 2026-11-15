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
  /**
   * The replay stage's height (#76): the 3D view plus the coach's call under it fit a 1440×900
   * screen without scrolling. A minimum, so a tall call on a phone grows the stage rather than
   * squeezing the view. The loading placeholder uses it too, so the page doesn't jump.
   */
  stageHeight: "min-h-[max(26rem,min(72vh,760px))] lg:min-h-[max(26rem,min(760px,calc(100svh-24rem)))]",
  /**
   * A row of buttons that scrolls sideways on phones instead of wrapping into several rows; from
   * `sm` up its buttons join the parent's wrapping row. The padding keeps focus rings unclipped.
   */
  phoneRow: "-mx-1 flex snap-x gap-2 overflow-x-auto p-1 sm:contents",
  /** A button in a `phoneRow`. */
  phoneRowItem: "shrink-0 snap-start",
} as const;
