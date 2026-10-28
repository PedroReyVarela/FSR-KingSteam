import { CSSProperties, ReactNode, useRef, useState } from "react";
import { Focusable } from "@decky/ui";

export const COLORS = { ok: "#22c55e", warn: "#f59e0b", bad: "#ef4444", info: "#1a9fff", muted: "#9ca3af" };
const SURFACE = "#161c25";
const BORDER = "#252f3c";

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function Pill({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6, padding: "2px 10px", borderRadius: 999, whiteSpace: "nowrap",
      background: `${color}26`, border: `1px solid ${color}`, color, fontWeight: 700, fontSize: 11, lineHeight: 1.5,
    }}>{children}</span>
  );
}

export function Chip({ children, color = COLORS.muted }: { children: ReactNode; color?: string }) {
  return (
    <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color,
      border: `1px solid ${color}80`, borderRadius: 4, padding: "1px 6px", whiteSpace: "nowrap" }}>{children}</span>
  );
}

export function Card({ color, children }: { color: string; children: ReactNode }) {
  return (
    <div style={{
      padding: "10px 12px", borderRadius: 10, background: SURFACE, border: `1px solid ${BORDER}`,
      borderLeft: `4px solid ${color}`, fontSize: 13, lineHeight: 1.45, wordBreak: "break-word", width: "100%", boxSizing: "border-box",
    }}>{children}</div>
  );
}

export function IconText({ icon, children, color }: { icon: ReactNode; children: ReactNode; color?: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, color }}>
      {icon}<span>{children}</span>
    </span>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <div style={{ fontFamily: "monospace", fontSize: 11.5, color: "#aab2bd", wordBreak: "break-word", whiteSpace: "pre-wrap" }}>{children}</div>;
}

type Tone = "primary" | "danger" | "ghost" | "plain";
const TONES: Record<Tone, CSSProperties> = {
  primary: { background: "linear-gradient(135deg,#15803d,#22c55e)", color: "#04210f", border: "1px solid transparent", fontWeight: 800 },
  danger: { background: "#2a1517", color: "#ff7b7b", border: "1px solid #5b2327", fontWeight: 700 },
  ghost: { background: "#13261b", color: "#4ade80", border: "1px solid #1f4d33", fontWeight: 700 },
  plain: { background: SURFACE, color: "#dcdedf", border: `1px solid ${BORDER}`, fontWeight: 600 },
};

// A gamepad-focusable tile: big tap target, own focus ring, works with touch and with the A button
export function Tile({ onActivate, children, tone = "plain", selected, disabled, style }: {
  onActivate: () => void; children: ReactNode; tone?: Tone; selected?: boolean; disabled?: boolean; style?: CSSProperties;
}) {
  const [focused, setFocused] = useState(false);
  const last = useRef(0);
  const fire = () => {
    const now = Date.now();
    if (disabled || now - last.current < 400) return; // A button can raise both events
    last.current = now;
    onActivate();
  };
  return (
    <Focusable
      noFocusRing
      onActivate={fire}
      onClick={fire}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      style={{
        ...TONES[tone], boxSizing: "border-box", width: "100%", borderRadius: 10, padding: "11px 14px", fontSize: 14,
        textAlign: "center", opacity: disabled ? 0.45 : 1, transition: "box-shadow .12s, transform .12s",
        ...(selected ? { border: `1px solid ${COLORS.info}`, background: "#14263a" } : null),
        ...(focused ? { boxShadow: "0 0 0 3px #ffffff", transform: "scale(1.015)" } : null),
        ...style,
      }}
    >{children}</Focusable>
  );
}

// small section label with an accent bar
export function Heading({ children }: { children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, width: "100%", margin: "4px 0 2px" }}>
      <span style={{ width: 4, height: 14, borderRadius: 2, background: COLORS.info }} />
      <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "#c3c9d1" }}>{children}</span>
    </div>
  );
}
