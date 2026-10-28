import { PanelSectionRow } from "@decky/ui";
import { VERSION } from "../version";

export function Header() {
  return (
    <PanelSectionRow>
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center", padding: "14px 8px", marginBottom: 8,
        borderRadius: 8, background: "linear-gradient(120deg, #1b2a41, #324a5f 60%, #0c7489)", color: "#fff", width: "100%",
      }}>
        <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: "0.06em" }}>FSR-KingSteam</div>
        <div style={{ fontSize: 11, opacity: 0.75, letterSpacing: "0.12em", marginTop: 2 }}>v{VERSION}</div>
      </div>
    </PanelSectionRow>
  );
}
