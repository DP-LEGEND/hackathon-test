// Static, route-scoped CSS travels with the server markup. This also avoids the
// active development server's CSS-module cache without changing shared config.
export function StudioStyles() {
  return <style>{`
[data-ui-lab] {
  --studio-accent: #C9855C;
  --studio-highlight: #E8AF89;
  --studio-copper-surface: #49382E;
  --studio-success: #98D8B8;
  --studio-muted: #8997A5;
  --background: #11151B;
  --foreground: #F3F4F5;
  --card: #1B212A;
  --card-foreground: #F3F4F5;
  --popover: #242D36;
  --popover-foreground: #F3F4F5;
  --primary: var(--studio-accent);
  --primary-foreground: #11151B;
  --secondary: #242D36;
  --secondary-foreground: #A9B4C0;
  --muted: #141A22;
  --muted-foreground: #A9B4C0;
  --accent: #242D36;
  --accent-foreground: #F3F4F5;
  --destructive: #F1A99C;
  --border: #37404B;
  --input: #8997A5;
  --ring: var(--studio-highlight);
  min-height: 100dvh;
  color-scheme: dark;
  background: var(--background);
  color: var(--foreground);
  font-family: var(--font-geist-sans), sans-serif;
  -webkit-font-smoothing: antialiased;

  & *, & *::before, & *::after { box-sizing: border-box; }
  & :is(a, button, input, textarea, [tabindex]):focus-visible { outline: 2px solid var(--ring); outline-offset: 4px; }
  & :is(h1, h2, h3, h4, h5, p) { margin: 0; }
  & :is(button, a, textarea, .lab-stepList li, .lab-stepIcon) { transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease, box-shadow 160ms ease; }
  & button { cursor: pointer; }
  & button:disabled { cursor: not-allowed; }
  .lab-skipLink { position: fixed; z-index: 100; top: 12px; left: 16px; padding: 12px 16px; border-radius: 8px; background: var(--foreground); color: var(--background); transform: translateY(-160%); }
  .lab-skipLink:focus { transform: translateY(0); }
  .lab-topbar { border-bottom: 1px solid var(--border); background: var(--muted); }
  .lab-topbarInner, .lab-main { width: calc(100% - 80px); max-width: 1200px; margin: 0 auto; }
  .lab-topbarInner { display: flex; align-items: center; justify-content: space-between; gap: 24px; min-height: 64px; }
  .lab-brand { display: flex; align-items: center; gap: 12px; font-size: 16px; font-weight: 550; letter-spacing: -.03em; }
  .lab-logoMark { display: flex; align-items: center; gap: 3px; width: 24px; height: 24px; color: var(--studio-accent); }
  .lab-logoMark i { display: block; width: 4px; height: 12px; border-radius: 2px; background: currentColor; }
  .lab-logoMark i:nth-child(2) { height: 22px; }
  .lab-logoMark i:nth-child(3) { height: 16px; }
  .lab-labBadge { height: 22px; padding: 0 7px; border-radius: 5px; border-color: var(--border); color: var(--muted-foreground); font-size: 10px; font-weight: 500; letter-spacing: .02em; }
  .lab-workspaceLabel { color: var(--studio-muted); font-size: 12px; }
  .lab-backLink { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px; min-width: 40px; color: var(--muted-foreground); font-size: 12px; text-decoration: none; }
  .lab-backLink:hover { color: var(--foreground); }
  .lab-main { padding: 48px 0 24px; }
  .lab-intro { display: flex; justify-content: space-between; align-items: flex-end; gap: 32px; margin-bottom: 32px; }
  .lab-eyebrow { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; color: var(--studio-highlight); font-size: 10px; font-weight: 500; line-height: 1.5; letter-spacing: .12em; }
  .lab-eyebrow > span { width: 5px; height: 5px; flex: none; border-radius: 50%; background: var(--studio-accent); }
  .lab-intro h1 { font-size: clamp(36px, 3.7vw, 48px); font-weight: 500; line-height: 1.12; letter-spacing: -.055em; }
  .lab-introDescription { margin-top: 12px; color: var(--muted-foreground); font-size: 14px; line-height: 1.6; }
  .lab-disclosure { flex: none; padding: 0 0 2px 20px; border-left: 1px solid var(--border); color: var(--studio-muted); font-size: 11px; line-height: 1.7; }
  .lab-disclosureTitle { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; color: var(--muted-foreground); font-weight: 500; }
  .lab-disclosureTitle > span { width: 5px; height: 5px; border-radius: 50%; background: var(--studio-success); }
  .lab-workspace { display: grid; grid-template-columns: 345px minmax(0, 1fr); align-items: start; gap: 24px; }
  .lab-panel { min-width: 0; border: 1px solid var(--border); border-radius: 14px; background: var(--card); }
  .lab-composerPanel { display: flex; flex-direction: column; min-height: 602px; padding: 24px; }
  .lab-sectionHeader { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 24px; }
  .lab-sectionHeader h2 { display: flex; align-items: center; gap: 10px; min-width: 0; font-size: 14px; font-weight: 500; line-height: 1.5; letter-spacing: -.02em; }
  .lab-sectionIndex { color: var(--studio-muted); font: 10px/1.5 var(--font-geist-mono), monospace; }
  .lab-mockBadge { height: 23px; padding: 0 8px; border: 1px solid var(--border); border-radius: 5px; color: var(--muted-foreground); background: var(--secondary); font-size: 10px; font-weight: 500; }
  .lab-composerPanel form { display: flex; flex: 1; flex-direction: column; }
  .lab-fieldLabel { font-size: 14px; font-weight: 500; line-height: 1.5; }
  .lab-fieldHelp { margin-top: 8px; color: var(--muted-foreground); font-size: 12px; line-height: 1.7; }
  .lab-textarea { display: block; width: 100%; min-height: 172px; margin-top: 18px; padding: 14px; resize: vertical; border: 1px solid var(--input); border-radius: 8px; background: var(--muted); color: var(--foreground); font: 14px/1.7 var(--font-geist-sans), sans-serif; }
  .lab-textarea::placeholder { color: var(--studio-muted); }
  .lab-textarea:hover:not(:disabled) { border-color: var(--studio-highlight); }
  .lab-textarea:disabled { opacity: .8; cursor: not-allowed; }
  .lab-composerMeta { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 4px; }
  .lab-exampleButton { min-height: 40px; padding: 0 4px; color: var(--studio-highlight); font-size: 12px; font-weight: 400; }
  .lab-exampleButton:hover { color: var(--studio-highlight); background: var(--studio-copper-surface); }
  .lab-exampleButton svg { width: 13px; height: 13px; }
  .lab-characterCount { color: var(--studio-muted); font: 10px/1.5 var(--font-geist-mono), monospace; white-space: nowrap; }
  .lab-simulationToggle { display: flex; align-items: center; gap: 10px; min-height: 48px; margin: 8px 0 18px; color: var(--muted-foreground); font-size: 12px; line-height: 1.6; cursor: pointer; }
  .lab-simulationToggle input { flex: none; width: 16px; height: 16px; margin: 0; accent-color: var(--studio-accent); }
  .lab-controls { display: flex; gap: 10px; margin-top: auto; }
  .lab-controls .lab-runButton { flex: 1; min-width: 0; white-space: normal; }
  .lab-controls .lab-controlButton { flex: none; }
  .lab-runButton, .lab-controlButton { min-height: 42px; height: auto; padding: 10px 14px; border-radius: 7px; font-size: 13px; }
  .lab-runButton { width: 100%; border: 1px solid var(--studio-accent); color: var(--primary-foreground); background: var(--studio-accent); box-shadow: 0 1px 0 inset #ffffff20; }
  .lab-runButton:hover:not(:disabled) { background: var(--studio-highlight); border-color: var(--studio-highlight); }
  .lab-runButton:disabled { opacity: 1; background: var(--secondary); color: var(--studio-muted); border-color: var(--border); box-shadow: none; }
  .lab-workspace[data-state="success"] .lab-runButton { border-color: var(--border); background: var(--secondary); color: var(--foreground); box-shadow: none; }
  .lab-workspace[data-state="success"] .lab-runButton:hover { border-color: var(--studio-accent); background: var(--studio-copper-surface); }
  .lab-runButton svg, .lab-controlButton svg { width: 15px; height: 15px; }
  .lab-controlButton { color: var(--foreground); background: var(--secondary); border-color: var(--border); }
  .lab-controlButton:hover { background: var(--studio-copper-surface); border-color: var(--studio-accent); }
  .lab-privacyNote { display: flex; align-items: center; gap: 7px; margin-top: 18px; color: var(--studio-muted); font-size: 11px; line-height: 1.7; }
  .lab-activityPanel { display: flex; flex-direction: column; min-height: 602px; overflow: clip; }
  .lab-progressPanel { padding: 24px 28px 18px; border-bottom: 1px solid var(--border); background: var(--muted); transition: background-color 180ms ease; }
  .lab-progressPanel .lab-sectionHeader { margin-bottom: 20px; }
  .lab-progressCount { color: var(--studio-muted); font: 10px/1.5 var(--font-geist-mono), monospace; }
  .lab-stepList { position: relative; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 0; margin: 0; list-style: none; }
  .lab-stepList::before { position: absolute; top: 20px; left: 20px; right: 20px; border-top: 1px solid var(--border); content: ''; }
  .lab-stepList li { z-index: 1; min-width: 0; padding: 12px; border: 1px solid var(--border); border-radius: 9px; background: var(--card); }
  .lab-stageTop { display: flex; align-items: center; gap: 8px; }
  .lab-stepIcon { display: flex; align-items: center; justify-content: center; flex: none; width: 24px; height: 24px; border: 1px solid var(--border); border-radius: 6px; color: var(--studio-muted); background: var(--muted); }
  .lab-stageLabel { color: var(--muted-foreground); font: 10px/1.5 var(--font-geist-mono), monospace; letter-spacing: .08em; }
  .lab-stageState { margin-left: auto; color: var(--studio-muted); font-size: 10px; }
  .lab-stageDescription { margin-top: 12px; }
  .lab-stepTitle { color: var(--foreground); font-size: 12px; font-weight: 500; line-height: 1.6; }
  .lab-stepDetail { margin-top: 4px; color: var(--studio-muted); font-size: 11px; line-height: 1.7; }
  .lab-stepList li[data-active="true"] { background: var(--studio-copper-surface); border-color: var(--studio-accent); box-shadow: 0 0 0 1px #C9855C14; }
  .lab-stepActive, .lab-stepList li[data-active="true"] :is(.lab-stageLabel, .lab-stageState) { color: var(--studio-highlight); border-color: var(--studio-accent); }
  .lab-stepList li[data-active="true"] .lab-stepDetail { color: var(--muted-foreground); }
  .lab-stepDone, .lab-stepList li[data-done="true"] .lab-stageState { color: var(--studio-success); }
  .lab-stepDone { border-color: var(--studio-success); }
  .lab-stepFailed, .lab-stepList li[data-failed="true"] .lab-stageState { color: var(--destructive); border-color: var(--destructive); }
  .lab-statusMessage { margin-top: 16px; color: var(--muted-foreground); font-size: 12px; line-height: 1.7; }
  .lab-workspace[data-state="running"] .lab-progressPanel { background: #191D24; }
  .lab-workspace[data-state="success"] .lab-stageDescription { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .lab-workspace[data-state="success"] .lab-progressPanel { padding-bottom: 16px; }
  .lab-workspace[data-state="success"] .lab-stepList li { padding: 8px 10px; border-color: transparent; background: transparent; }
  .lab-workspace[data-state="success"] .lab-stepList::before { display: none; }
  .lab-workspace[data-state="success"] .lab-statusMessage { color: var(--studio-success); }
  .lab-resultPanel { display: flex; flex: 1; flex-direction: column; min-width: 0; }
  .lab-resultHeader { min-height: 58px; margin: 0; padding: 16px 28px; }
  .lab-resultHeader h2 { color: var(--muted-foreground); font-size: 12px; }
  .lab-resultBadge { height: 23px; padding: 0 8px; border-color: var(--border); border-radius: 5px; color: var(--muted-foreground); font-size: 10px; font-weight: 400; }
  .lab-resultBadge svg { width: 12px; height: 12px; }
  .lab-workspace[data-state="success"] .lab-resultBadge { color: var(--studio-success); }
  .lab-workspace[data-state="error"] .lab-resultBadge { color: var(--destructive); background: transparent; }
  .lab-resultBody { display: flex; flex: 1; flex-direction: column; }
  .lab-emptyLayout { display: flex; flex: 1; flex-direction: column; justify-content: center; padding: 10px 28px 28px; }
  .lab-documentLabel { color: var(--studio-highlight); font-size: 10px; line-height: 1.6; letter-spacing: .1em; }
  .lab-emptyMessage > div { align-items: flex-start; padding: 16px 0 24px; text-align: left; }
  .lab-emptyMessage > div > div[aria-hidden="true"] { display: none; }
  .lab-emptyMessage h3, .lab-runningPreview h3 { font-size: clamp(26px, 2.5vw, 34px); font-weight: 500; line-height: 1.25; letter-spacing: -.045em; }
  .lab-emptyMessage p { max-width: 45ch; margin-top: 10px; color: var(--muted-foreground); font-size: 14px; line-height: 1.7; }
  .lab-outputOutline { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin: 0; padding-top: 20px; border-top: 1px solid var(--border); }
  .lab-outputOutline dt { font-size: 12px; font-weight: 500; line-height: 1.6; }
  .lab-outputOutline dd { margin: 5px 0 0; color: var(--studio-muted); font-size: 12px; line-height: 1.7; }
  .lab-emptyFootnote { margin-top: 24px; color: var(--studio-muted); font-size: 11px; line-height: 1.7; }
  .lab-runningPreview { display: flex; flex: 1; flex-direction: column; justify-content: center; padding: 14px 28px 28px; }
  .lab-runningPreview h3 { margin-top: 14px; }
  .lab-runningDescription { max-width: 52ch; margin-top: 12px; color: var(--muted-foreground); font-size: 14px; line-height: 1.7; }
  .lab-progressBar { display: block; width: 100%; height: 3px; margin-top: 24px; border: 0; border-radius: 4px; background: var(--secondary); accent-color: var(--studio-accent); }
  .lab-progressBar::-webkit-progress-bar { background: var(--secondary); border-radius: 4px; }
  .lab-progressBar::-webkit-progress-value { background: var(--studio-accent); border-radius: 4px; transition: width 180ms ease; }
  .lab-skeleton { display: grid; gap: 10px; max-width: 460px; margin-top: 20px; }
  .lab-skeleton > div { height: 6px; border-radius: 3px; background: var(--secondary); }
  .lab-errorLayout { display: flex; flex: 1; align-items: center; justify-content: center; min-height: 300px; padding: 16px 28px 28px; }
  .lab-errorLayout > div { padding: 16px 0; }
  .lab-errorLayout h3 { font-size: 26px; font-weight: 500; letter-spacing: -.035em; }
  .lab-errorLayout p { color: var(--muted-foreground); font-size: 14px; line-height: 1.8; }
  .lab-staleNotice { padding: 12px 28px; border-block: 1px solid var(--border); background: var(--studio-copper-surface); color: var(--foreground); font-size: 12px; line-height: 1.7; }
  .lab-resultArticle { display: flex; flex: 1; flex-direction: column; animation: copper-signal-reveal 180ms ease-out; }
  .lab-runningPreview { animation: copper-signal-reveal 160ms ease-out; }
  .lab-resultContent { display: grid; grid-template-columns: minmax(0, 1fr); gap: 24px; padding: 10px 28px 24px; }
  .lab-completionLabel { display: flex; align-items: center; gap: 7px; margin-bottom: 12px; color: var(--studio-success); font: 10px/1.6 var(--font-geist-mono), monospace; letter-spacing: .08em; }
  .lab-resultSummary h3 { max-width: 24ch; font-size: clamp(30px, 2.7vw, 38px); font-weight: 500; letter-spacing: -.045em; line-height: 1.15; }
  .lab-recommendation { max-width: 52ch; margin-top: 14px; color: var(--foreground); font-size: 15px; line-height: 1.7; }
  .lab-outputDisclosure { max-width: 64ch; margin-top: 10px; color: var(--muted-foreground); font-size: 12px; line-height: 1.7; }
  .lab-priorityHeader { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; margin-bottom: 4px; }
  .lab-priorityHeader h4, .lab-nextMove h4, .lab-submittedBrief h4 { font-size: 12px; font-weight: 500; line-height: 1.7; }
  .lab-priorityHeader > span { color: var(--studio-muted); font: 10px/1.6 var(--font-geist-mono), monospace; }
  .lab-priorities ol { margin: 0; padding: 0; list-style: none; }
  .lab-priorities li { display: flex; gap: 14px; padding: 12px 0; border-bottom: 1px solid var(--border); }
  .lab-priorities li:last-child { border: 0; padding-bottom: 0; }
  .lab-priorityNumber { padding-top: 2px; color: var(--studio-highlight); font: 10px/1.6 var(--font-geist-mono), monospace; }
  .lab-priorities h5 { font-size: 13px; font-weight: 500; line-height: 1.6; }
  .lab-priorities li p { max-width: 64ch; margin-top: 3px; color: var(--muted-foreground); font-size: 14px; line-height: 1.7; }
  .lab-nextMove { padding: 16px; border: 1px solid var(--border); border-left: 2px solid var(--studio-accent); border-radius: 8px; background: var(--muted); }
  .lab-nextMove h4 { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: var(--studio-highlight); }
  .lab-nextMove p { margin-top: 6px; color: var(--muted-foreground); font-size: 14px; line-height: 1.7; }
  .lab-submittedBrief { padding-top: 16px; border-top: 1px solid var(--border); }
  .lab-submittedBrief h4 { color: var(--studio-muted); }
  .lab-submittedBrief p { max-height: 120px; overflow-y: auto; margin-top: 6px; white-space: pre-wrap; overflow-wrap: anywhere; color: var(--muted-foreground); font-size: 13px; line-height: 1.8; }
  .lab-resultFooter { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; margin-top: auto; padding: 16px 28px; border-top: 1px solid var(--border); background: var(--muted); }
  .lab-resultFooter > span { color: var(--studio-muted); font-size: 11px; line-height: 1.7; }
  .lab-footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 24px; margin-top: 20px; color: var(--studio-muted); font-size: 10px; line-height: 1.7; }

  @media (max-width: 1099px) {
    .lab-workspace { grid-template-columns: 300px minmax(0, 1fr); gap: 20px; }
    .lab-topbarInner, .lab-main { width: calc(100% - 48px); }
    .lab-workspaceLabel, .lab-disclosure { display: none; }
    .lab-intro h1 { font-size: 40px; }
    .lab-progressPanel { padding: 20px; }
    .lab-stepList { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .lab-stepList::before { display: none; }
    .lab-stepList li { padding: 10px; }
    .lab-stageTop { flex-direction: column; gap: 7px; }
    .lab-stageState { margin-left: 0; }
    .lab-stageDescription { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
    .lab-resultHeader { padding: 16px 20px; }
    .lab-emptyLayout, .lab-runningPreview, .lab-errorLayout { padding: 8px 20px 24px; }
    .lab-outputOutline { grid-template-columns: minmax(0, 1fr); gap: 12px; }
    .lab-outputOutline > div { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; }
    .lab-outputOutline dd { margin: 0; }
    .lab-resultContent { padding: 10px 20px 24px; }
    .lab-resultFooter { padding: 16px 20px; }
    .lab-staleNotice { padding: 12px 20px; }
  }
  @media (max-width: 719px) {
    .lab-topbarInner, .lab-main { width: calc(100% - 32px); }
    .lab-topbarInner { min-height: 62px; gap: 12px; }
    .lab-brand { gap: 9px; font-size: 15px; }
    .lab-backLink { min-height: 44px; min-width: 44px; }
    .lab-main { padding-top: 32px; }
    .lab-intro { margin-bottom: 24px; }
    .lab-eyebrow { font-size: 9px; letter-spacing: .08em; }
    .lab-intro h1 { max-width: 12ch; font-size: 40px; }
    .lab-introDescription { max-width: 34ch; font-size: 13px; line-height: 1.8; }
    .lab-workspace { grid-template-columns: minmax(0, 1fr); gap: 20px; }
    .lab-composerPanel { min-height: 0; padding: 20px; }
    .lab-sectionHeader { margin-bottom: 20px; }
    .lab-fieldHelp { font-size: 12px; }
    .lab-textarea { min-height: 136px; }
    .lab-exampleButton, .lab-runButton, .lab-controlButton { min-height: 44px; }
    .lab-simulationToggle { margin: 4px 0 14px; min-height: 44px; }
    .lab-privacyNote { margin-top: 14px; }
    .lab-activityPanel { min-height: 0; }
    .lab-stepList { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .lab-stepList li { padding: 10px 6px; }
    .lab-stageTop { flex-direction: column; gap: 7px; }
    .lab-stageState { margin-left: 0; font-size: 10px; }
    .lab-stageLabel { font-size: 10px; }
    .lab-statusMessage { margin-top: 14px; font-size: 12px; }
    .lab-resultHeader h2 { font-size: 11px; }
    .lab-resultBadge { font-size: 10px; }
    .lab-emptyLayout { padding-top: 14px; }
    .lab-emptyMessage h3, .lab-runningPreview h3 { font-size: 27px; }
    .lab-emptyMessage > div { padding: 14px 0 24px; }
    .lab-outputOutline { gap: 14px; padding-top: 18px; }
    .lab-emptyFootnote { margin-top: 22px; }
    .lab-runningPreview { min-height: 340px; padding-top: 18px; }
    .lab-errorLayout { min-height: 340px; }
    .lab-errorLayout h3 { font-size: 24px; }
    .lab-workspace[data-state="success"] .lab-stepList li { padding: 8px 4px; }
    .lab-workspace[data-state="success"] .lab-stageTop { gap: 6px; }
    .lab-resultContent { gap: 24px; padding-top: 10px; }
    .lab-resultSummary h3 { font-size: 32px; }
    .lab-resultFooter { gap: 14px; }
    .lab-resultFooter .lab-controlButton { width: 100%; }
    .lab-footer { font-size: 10px; }
  }
  @media (max-width: 359px) {
    .lab-controls { flex-direction: column; }
  }
  @media (prefers-reduced-motion: reduce) {
    & *, & *::before, & *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
    .lab-progressBar::-webkit-progress-value { transition: none; }
  }
}
@keyframes copper-signal-reveal { from { opacity: .65; } to { opacity: 1; } }
`}</style>;
}
