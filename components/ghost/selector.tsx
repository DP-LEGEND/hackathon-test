"use client";
import { useId } from "react";
import styles from "./styles";
export function StageSelector({ label, options, value, onChange }: { label: string; options: readonly string[]; value: number; onChange: (value: number) => void }) {
  const id = useId();
  return <div className={styles.selector}>
    <label htmlFor={id}>{label}</label>
    <input id={id} type="range" min={0} max={options.length - 1} step={1} value={value} onChange={e => onChange(Number(e.target.value))} aria-valuetext={options[value]} />
    <div className={styles.choices}>{options.map((option, i) => <button key={option} type="button" aria-pressed={value === i} onClick={() => onChange(i)}>{option}</button>)}</div>
  </div>;
}
