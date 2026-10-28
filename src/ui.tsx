import { ReactNode } from "react";

export const COLORS = { ok: "#22c55e", warn: "#f59e0b", bad: "#ef4444", info: "#60a5fa", muted: "#9ca3af" };

export function Pill({ color, children }: { color: string; children: ReactNode }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 12px", borderRadius: 999,
      background: `${color}26`, border: `1px solid ${color}`, color, fontWeight: 700, fontSize: 12, lineHeight: 1.4,
    }}>{children}</span>
  );
}

export function Card({ color, children }: { color: string; children: ReactNode }) {
  return (
    <div style={{
      padding: "10px 12px", borderRadius: 8, background: "var(--decky-selected-ui-bg, rgba(255,255,255,0.05))",
      borderLeft: `4px solid ${color}`, fontSize: 13, lineHeight: 1.45, wordBreak: "break-word", width: "100%",
    }}>{children}</div>
  );
}

// icon + text; emojis do not always render in Steam's font
export function IconText({ icon, children, color }: { icon: ReactNode; children: ReactNode; color?: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, color }}>
      {icon}<span>{children}</span>
    </span>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <div style={{ fontFamily: "monospace", fontSize: 12, wordBreak: "break-word", whiteSpace: "pre-wrap" }}>{children}</div>;
}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
