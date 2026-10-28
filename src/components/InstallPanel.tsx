import { useEffect, useState } from "react";
import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { FaDownload, FaSync } from "react-icons/fa";
import { install, installProgress, RuntimeInfo } from "../api";
import { tr } from "../i18n";
import { Card, COLORS, errorText, IconText, Pill } from "../ui";

type Props = { info: RuntimeInfo | null; onChange: () => void };

export function InstallPanel({ info, onChange }: Props) {
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
    setBusy(true);
    setError("");
    try {
      const result = await install(info?.default_variant ?? info?.catalog.default_variant ?? "fsr4-lite");
      if (result.status !== "success") setError(result.message);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
      onChange();
    }
  };

  if (!info) return null;

  const steps = [
    tr("Press Install (downloads the AMD files, a few minutes once)", "Pulsa Instalar (descarga los archivos de AMD, unos minutos una sola vez)"),
    tr("Choose a game and an upscaler", "Elige un juego y un escalador"),
    tr("Press Patch and launch the game", "Pulsa Parchear y abre el juego"),
    tr("In the game graphics, turn on DLSS, FSR or XeSS", "En los gráficos del juego, activa DLSS, FSR o XeSS"),
  ];

  return (
    <PanelSection>
      <PanelSectionRow>
        {info.installed ? (
          <Card color={COLORS.ok}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
              <Pill color={COLORS.ok}>● {tr("Ready", "Listo")}</Pill>
              {info.version && <span style={{ opacity: 0.8 }}>OptiScaler {info.version}</span>}
            </div>
            {info.default_variant_label && (
              <div style={{ marginTop: 6, opacity: 0.85 }}>{tr("Default", "Por defecto")}: <strong>{info.default_variant_label}</strong></div>
            )}
          </Card>
        ) : (
          <Card color={COLORS.warn}>
            <div style={{ marginBottom: 8 }}><Pill color={COLORS.warn}>● {tr("Not installed", "No instalado")}</Pill></div>
            {steps.map((text, i) => (
              <div key={i} style={{ display: "flex", gap: 8, marginTop: 4 }}>
                <strong style={{ color: COLORS.warn }}>{i + 1}</strong><span>{text}</span>
              </div>
            ))}
          </Card>
        )}
      </PanelSectionRow>
      {!info.installed && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={run}>
            <IconText icon={<FaDownload />}>{busy ? progress || tr("Installing...", "Instalando...") : tr("Install OptiScaler", "Instalar OptiScaler")}</IconText>
          </ButtonItem>
        </PanelSectionRow>
      )}
      {info.installed && busy && (
        <PanelSectionRow><Card color={COLORS.info}>{progress || tr("Reinstalling...", "Reinstalando...")}</Card></PanelSectionRow>
      )}
      {error && <PanelSectionRow><Card color={COLORS.bad}>{error}</Card></PanelSectionRow>}
      {info.installed && !busy && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={run}>
            <IconText icon={<FaSync />}>{tr("Reinstall runtime", "Reinstalar runtime")}</IconText>
          </ButtonItem>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
