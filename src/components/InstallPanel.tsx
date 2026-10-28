import { useEffect, useState } from "react";
import { PanelSection, PanelSectionRow } from "@decky/ui";
import { FaDownload } from "react-icons/fa";
import { install, installProgress, RuntimeInfo } from "../api";
import { tr } from "../i18n";
import { VERSION } from "../version";
import { Card, COLORS, errorText, IconText, Pill, Tile } from "../ui";

export function useInstaller(info: RuntimeInfo | null, onChange: () => void) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!busy) { setProgress(""); return; }
    let stopped = false;
    const tick = async () => {
      try {
        const p = await installProgress();
        if (!stopped && p.active && p.step) setProgress(`${p.step}${typeof p.percent === "number" ? ` ${p.percent}%` : ""}`);
      } catch { /* keep the last label */ }
    };
    const id = window.setInterval(tick, 1000);
    return () => { stopped = true; window.clearInterval(id); };
  }, [busy]);

  const run = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const r = await install(info?.default_variant ?? info?.catalog.default_variant ?? "fsr4-lite");
      if (r.status !== "success") setError(r.message);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
      onChange();
    }
  };
  return { busy, progress, error, run };
}

type Props = { info: RuntimeInfo | null; installer: ReturnType<typeof useInstaller> };

// top strip: state of the runtime on the left, plugin version on the right
export function InstallPanel({ info, installer }: Props) {
  if (!info) return null;
  const { busy, progress, error, run } = installer;
  const steps = [
    tr("Press Install (downloads AMD's files, a few minutes once)", "Pulsa Instalar (descarga los archivos de AMD, unos minutos una sola vez)"),
    tr("Choose a game and an upscaler", "Elige un juego y un escalador"),
    tr("Press Patch and launch the game", "Pulsa Parchear y abre el juego"),
    tr("In the game graphics, turn on DLSS, FSR or XeSS", "En los gráficos del juego, activa DLSS, FSR o XeSS"),
  ];
  return (
    <PanelSection>
      <PanelSectionRow>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <Pill color={info.installed ? COLORS.ok : COLORS.warn}>● {info.installed ? tr("Ready", "Listo") : tr("Not installed", "No instalado")}</Pill>
            {info.installed && info.version && <span style={{ fontSize: 12, opacity: 0.75 }}>OptiScaler {info.version}</span>}
          </div>
          <span style={{ fontSize: 11, letterSpacing: "0.12em", color: "#7b8591" }}>v{VERSION}</span>
        </div>
      </PanelSectionRow>
      {!info.installed && (
        <>
          <PanelSectionRow>
            <Card color={COLORS.warn}>
              {steps.map((text, i) => (
                <div key={i} style={{ display: "flex", gap: 10, marginTop: i ? 6 : 0, alignItems: "flex-start" }}>
                  <span style={{ flex: "0 0 20px", height: 20, borderRadius: 10, background: `${COLORS.warn}33`, color: COLORS.warn, fontWeight: 800, fontSize: 12, display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</span>
                  <span>{text}</span>
                </div>
              ))}
            </Card>
          </PanelSectionRow>
          <PanelSectionRow>
            <Tile tone="primary" disabled={busy} onActivate={() => void run()}>
              <IconText icon={<FaDownload />}>{busy ? progress || tr("Installing...", "Instalando...") : tr("Install OptiScaler", "Instalar OptiScaler")}</IconText>
            </Tile>
          </PanelSectionRow>
        </>
      )}
      {info.installed && busy && <PanelSectionRow><Card color={COLORS.info}>{progress || tr("Reinstalling...", "Reinstalando...")}</Card></PanelSectionRow>}
      {error && <PanelSectionRow><Card color={COLORS.bad}>{error}</Card></PanelSectionRow>}
    </PanelSection>
  );
}
