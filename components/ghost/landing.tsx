"use client";
import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { ArrowDown, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StageSelector } from "./selector";
import styles from "./styles";

export const PROCESS_STAGES = [
  { title: "Input", description: "One swing. A new perspective. Film your technique and turn your movement into a 3D replay.", poster: "/ghost/input-poster.png", width: 434, height: 216 },
  { title: "Coach’s call", description: "See the key movement cues in your swing, with clear coaching guidance alongside the replay.", poster: "/ghost/input-poster.png", width: 434, height: 216 },
  { title: "Predicted shots", description: "Explore the simulated shot path and compare how a change in technique could affect the outcome.", poster: "/ghost/court.svg", width: 434, height: 243 },
] as const;

export function LandingHero() {
  const hero = useRef<HTMLElement>(null);
  const ghost = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame = 0;
    const draw = () => {
      frame = 0;
      if (!hero.current || !ghost.current) return;
      const p = media.matches ? 0 : Math.min(1, Math.max(0, -hero.current.getBoundingClientRect().top / hero.current.offsetHeight));
      ghost.current.style.transform = `translate3d(${Math.sin(p * Math.PI * 1.5) * window.innerWidth * .2}px, ${p * hero.current.offsetHeight * .8}px, 0) rotate(${p * 28}deg)`;
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(draw); };
    window.addEventListener("scroll", schedule, { passive: true }); window.addEventListener("resize", schedule); media.addEventListener("change", schedule); draw();
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", schedule); window.removeEventListener("resize", schedule); media.removeEventListener("change", schedule); };
  }, []);
  return <section className={styles.hero} ref={hero} aria-labelledby="hero-title">
    <div className={styles.heroArt} aria-hidden="true">
      <div className={styles.rearTrail}><Image src="/ghost/trail.svg" width={740} height={206} alt="" priority /></div>
      <div className={styles.wordmark}>GHOST</div>
      <div className={styles.flyingGhost} ref={ghost}><div className={styles.ghostAsset}><Image src="/ghost/ghost.svg" width={194} height={124} alt="" priority /></div></div>
    </div>
    <div className={styles.heroMessage}>
      <p className={styles.heroEyebrow}>Pose-tracked squash analysis</p><h1 id="hero-title">See your swing. Find your edge.</h1>
      <div className={styles.heroActions}>
        <Button nativeButton={false} role="link" render={<Link href="/demo?swing=7178110a0b06-swing-0027" />} className={styles.heroCta}>See the demo <ArrowRight aria-hidden /></Button>
        <Button nativeButton={false} role="link" variant="outline" render={<Link href="/upload" />} className={styles.heroCta}>Analyse your swing <ArrowRight aria-hidden /></Button>
      </div>
    </div>
    <div className={styles.heroFooter}><span>Your game. Another dimension.</span><a href="#process">Scroll to explore <ArrowDown size={16} aria-hidden /></a></div>
  </section>;
}

function ProcessPreview({ poster, width, height }: { poster: string; width: number; height: number }) {
  return <div className={styles.processMedia}>
    <Image src={poster} width={width} height={height} alt="Illustration of squash swing analysis" className={styles.poster} />
    <span className={styles.previewLabel}>Illustrative preview</span>
  </div>;
}

export function ProcessPanels() {
  const [selected, setSelected] = useState(0);
  const track = useRef<HTMLDivElement>(null);
  const touchStart = useRef<number | null>(null);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 600px)");
    const align = () => { if (media.matches && track.current) track.current.scrollTo({ left: (track.current.children[selected] as HTMLElement).offsetLeft, behavior: "instant" }); };
    window.addEventListener("resize", align);
    return () => window.removeEventListener("resize", align);
  }, [selected]);
  function select(index: number) {
    setSelected(index);
    if (window.matchMedia("(max-width: 600px)").matches && track.current) {
      const panel = track.current.children[index] as HTMLElement;
      track.current.scrollTo({ left: panel.offsetLeft, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
    }
  }
  return <section id="process" className={styles.process} aria-labelledby="process-title">
    <p className={styles.eyebrow}>From input to insight</p><h2 id="process-title">Your swing. Three perspectives.</h2><p className={styles.description}>Move the slider to explore each part of the process.</p>
    <div ref={track} className={styles.processPanels} onScrollEnd={e => { if (window.matchMedia("(max-width: 600px)").matches) setSelected(Math.max(0, Math.min(2, Math.round(e.currentTarget.scrollLeft / (e.currentTarget.clientWidth + 16))))); }} onTouchStart={e => { touchStart.current = e.touches[0].clientX; }} onTouchEnd={e => { if (touchStart.current === null) return; const delta = touchStart.current - e.changedTouches[0].clientX; if (Math.abs(delta) > 45) select(Math.max(0, Math.min(2, selected + (delta > 0 ? 1 : -1)))); touchStart.current = null; }}>
      {PROCESS_STAGES.map((stage, index) => <article key={stage.title} className={styles.processPanel} data-active={selected === index} onClick={() => { if (selected !== index) select(index); }}>
        <ProcessPreview {...stage} /><p className={styles.eyebrow}>0{index + 1} / The process</p>
        <h3><button type="button" onClick={() => select(index)} aria-pressed={selected === index}>{stage.title}</button></h3><p className={styles.description}>{stage.description}</p>
      </article>)}
    </div>
    <StageSelector label="Explore the process" options={PROCESS_STAGES.map(s => s.title)} value={selected} onChange={select} />
  </section>;
}
