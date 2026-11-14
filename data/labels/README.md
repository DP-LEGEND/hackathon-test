# Swing labels (Owner: Henoch)

One CSV per filming session, e.g. `2026-11-13_courts.csv`, with columns:

`clip, swing, side, intended_fault, severity, quality_1_to_5, outcome, held_out, comment`

Clips themselves go in `data/raw/` (git-ignored). Never commit video files.

## labels.csv (14 Nov session)

`labels.csv` labels every swing written by the pipeline runs `fh-04`/`bh-04` (PR #17) and
`fh-05`/`bh-05` (PR #30 flags; ids carry an `@fh-05`/`@bh-05` suffix because the session id
is shared). Same columns as above plus `pipeline_run` and `contact_playback_s` (iPhone
QuickTime seconds of the contact frame). `intended_fault` comes from aryan's block timestamps:
`none` (good block), `early_wrist`, `over_rotation`, `straight_arm`, `open_stance` (forehand);
`none`, `rolled_wrist`, `straight_arm`, `open_stance` (backhand); `unlabelled` = outside any block.
Labels are the INTENDED (acted) fault for the block, not a rating of each swing. Severity,
quality and outcome are left blank.
