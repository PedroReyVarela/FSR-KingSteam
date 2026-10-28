import { useCallback, useEffect, useMemo, useState } from "react";
import { Menu, MenuItem, PanelSection, PanelSectionRow, showContextMenu, ToggleField } from "@decky/ui";
import { FileSelectionType, openFilePicker, toaster } from "@decky/api";
import { FaCheck, FaChevronDown, FaExclamationTriangle, FaFolderOpen, FaPlus, FaSearch, FaSync, FaTimes } from "react-icons/fa";
import * as api from "../api";
import { Kind, RuntimeInfo, TargetItem, TargetStatus } from "../api";
import { tr } from "../i18n";
import { dirname, getLaunchOptions, nameWithoutExtension, setLaunchOptions } from "../steam";
import { Card, Chip, COLORS, errorText, Heading, IconText, Mono, Pill, Tile } from "../ui";
import { ModelPicker } from "./ModelPicker";

type Props = { info: RuntimeInfo; proxy: string };
type Extras = { anticheat: string[]; showFps: boolean | null; proton: api.Proton | null };

const keyOf = (t: { kind: Kind; appid: string }) => `${t.kind}:${t.appid}`;
let lastKey = ""; // keep the selection while the panel is closed and reopened

export function GamePanel({ info, proxy }: Props) {
  const [items, setItems] = useState<TargetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(lastKey);
  const [status, setStatus] = useState<TargetStatus | null>(null);
  const [problem, setProblem] = useState("");
  const [folder, setFolder] = useState("");
  const [variant, setVariantChoice] = useState(info.default_variant ?? info.catalog.default_variant);
  const [extras, setExtras] = useState<Extras>({ anticheat: [], showFps: null, proton: null });
  const [diagnosis, setDiagnosis] = useState<api.Diagnosis | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);

  const current = useMemo(() => items.find((i) => keyOf(i) === selected) ?? null, [items, selected]);
  const say = (text: string, error = false) => setMessage({ text, error });

  const loadItems = useCallback(async (prefer?: string) => {
    setLoading(true);
    try {
      const r = await api.listTargets();
      if (r.status !== "success") return say(r.message, true);
      const list = [...r.games, ...r.shortcuts].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: "base" }));
      setItems(list);
      setSelected((now) => {
        const wanted = prefer || now;
        lastKey = wanted && list.some((i) => keyOf(i) === wanted) ? wanted : list[0] ? keyOf(list[0]) : "";
        return lastKey;
      });
    } catch (e) {
      say(errorText(e), true);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadStatus = useCallback(async (item: TargetItem | null, directory: string) => {
    if (!item) { setStatus(null); setProblem(""); return; }
    api.extras(item.kind, item.appid)
      .then((r) => setExtras(r.status === "success" ? { anticheat: r.anticheat, showFps: r.show_fps, proton: r.proton } : { anticheat: [], showFps: null, proton: null }))
      .catch(() => setExtras({ anticheat: [], showFps: null, proton: null }));
    try {
      const r = await api.targetStatus(item.kind, item.appid, directory);
      if (r.status === "success") { setStatus(r); setProblem(""); } else { setStatus(null); setProblem(r.message); }
    } catch (e) {
      setStatus(null);
      setProblem(errorText(e));
    }
  }, []);

  useEffect(() => { void loadItems(); }, [loadItems]);
  useEffect(() => {
    setFolder(""); setMessage(null); setDiagnosis(null); setStatus(null);
    void loadStatus(current, "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, items.length]);

  const guard = async (name: string, work: () => Promise<void>) => {
    if (busy) return;
    setBusy(name);
    setMessage(null);
    try { await work(); } catch (e) { say(errorText(e), true); } finally { setBusy(null); }
  };

  const pickFolder = () => guard("folder", async () => {
    const start = folder || status?.suggested_dir || "/";
    const picked = await openFilePicker(FileSelectionType.FOLDER, start, true, true, undefined, undefined, true);
    if (picked?.path) {
      const dir = picked.path.replace(/\\/g, "/");
      setFolder(dir);
      await loadStatus(current, dir);
    }
  });

  const doPatch = () => guard("patch", async () => {
    if (!current) return;
    const options = await getLaunchOptions(Number(current.appid));
    const r = await api.patch(current.kind, current.appid, folder, proxy, variant, options);
    if (r.status !== "success") {
      return say(r.needs_directory ? `${r.message} ${tr('Press "Choose another folder".', 'Pulsa "Elegir otra carpeta".')}` : r.message, true);
    }
    setLaunchOptions(Number(current.appid), r.launch_options);
    say(r.message);
    toaster.toast({ title: "FSR-KingSteam", body: r.message });
    setFolder("");
    await Promise.all([loadStatus(current, ""), loadItems(selected)]);
  });

  const doUnpatch = () => guard("unpatch", async () => {
    if (!current) return;
    const r = await api.unpatch(current.kind, current.appid);
    if (r.status !== "success") return say(r.message, true);
    if (r.launch_options !== null) setLaunchOptions(Number(current.appid), r.launch_options);
    say(r.message);
    await Promise.all([loadStatus(current, ""), loadItems(selected)]);
  });

  const doVariant = (next: string) => {
    if (!status?.patched) {
      setVariantChoice(next);
      // the model picked for a new patch is remembered as the default for the next games
      if (!next.startsWith("community:")) void api.setDefaultVariant(next).catch(() => undefined);
      return;
    }
    void guard("variant", async () => {
      if (!current) return;
      const r = await api.setVariant(current.kind, current.appid, next);
      if (r.status !== "success") return say(r.message, true);
      say(`${r.message} ${tr("It applies when the game is opened.", "Se aplica al abrir el juego.")}`);
      await loadStatus(current, "");
    });
  };

  const doFps = (enabled: boolean) => guard("fps", async () => {
    if (!current) return;
    const r = await api.setSetting(current.kind, current.appid, "show_fps", enabled);
    if (r.status !== "success") return say(r.message, true);
    setExtras((e) => ({ ...e, showFps: enabled }));
  });

  const doDiagnose = () => guard("diagnose", async () => {
    if (!current) return;
    const r = await api.diagnose(current.kind, current.appid);
    if (r.status !== "success") return say(r.message, true);
    setDiagnosis(r);
  });

  const addExe = () => guard("add", async () => {
    if (typeof SteamClient === "undefined" || !SteamClient?.Apps?.AddShortcut) {
      throw new Error(tr("This Steam version does not allow adding shortcuts from the plugin.", "Esta versión de Steam no permite añadir accesos directos desde el plugin."));
    }
    const picked = await openFilePicker(FileSelectionType.FILE, "/", true, true, undefined, ["exe"], true);
    if (!picked?.path) return;
    const exe = picked.path.replace(/\\/g, "/");
    const name = nameWithoutExtension(exe);
    const created = await SteamClient.Apps.AddShortcut(name, exe, dirname(exe), "");
    const appid = typeof created === "number" ? String(created >>> 0) : "";
    if (appid && SteamClient.Apps.SetShortcutName) SteamClient.Apps.SetShortcutName(Number(created), name);
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
    await loadItems(appid ? `shortcut:${appid}` : undefined);
    say(tr(`${name} added to Steam. Open its Properties > Compatibility and pick your Proton before launching it.`,
      `${name} añadido a Steam. Entra en sus Propiedades > Compatibilidad y elige tu Proton antes de lanzarlo.`));
  });

  // ── render ────────────────────────────────────────────────────────────────
  const patched = Boolean(status?.patched);
  const shownFolder = patched ? status?.target_dir : folder || status?.suggested_dir;
  const needsFolder = !patched && !folder && !status?.suggested_dir && Boolean(status);
  const canPatch = Boolean(current && status && !busy && !needsFolder && current.installed);
  const pickedVariant = patched ? status?.variant : variant;
  const pill = !current ? null
    : problem ? { color: COLORS.bad, text: problem }
    : !status ? { color: COLORS.muted, text: tr("Loading...", "Cargando...") }
    : !current.installed ? { color: COLORS.bad, text: tr("Install not found", "Instalación no encontrada") }
    : patched && status.dll_present === false ? { color: COLORS.warn, text: tr("Incomplete: reinstall", "Incompleto: reinstala") }
    : patched ? { color: COLORS.ok, text: tr("Patched", "Parcheado") }
    : { color: COLORS.muted, text: tr("Not patched", "Sin parchear") };

  const proton = extras.proton ?? status?.proton ?? null;
  const protonWarn = proton && (proton.ge ? (proton.major ?? 99) < 11 : false);
  const patchLabel = busy === "patch" ? tr("Patching...", "Parcheando...")
    : patched ? tr("Reinstall", "Reinstalar")
    : extras.anticheat.length ? tr("Patch anyway (at your own risk)", "Parchear igualmente (bajo tu riesgo)")
    : tr("Patch this game", "Parchear este juego");

  const openMenu = () => {
    if (!items.length) return;
    showContextMenu(
      <Menu label={tr("Choose a game", "Elige un juego")}>
        {items.map((i) => (
          <MenuItem key={keyOf(i)} onSelected={() => { lastKey = keyOf(i); setSelected(lastKey); }}>
            {`${i.patched ? "● " : ""}${i.name}${i.installed ? "" : ` (${tr("not installed", "no instalado")})`}`}
          </MenuItem>
        ))}
      </Menu>
    );
  };

  return (
    <>
      <PanelSection>
        <PanelSectionRow><Heading>{tr("Game", "Juego")}</Heading></PanelSectionRow>
        <PanelSectionRow>
          <Tile onActivate={openMenu} disabled={loading || items.length === 0} style={{ textAlign: "left", padding: "12px 14px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 800, lineHeight: 1.25, wordBreak: "break-word" }}>
                  {current ? current.name : loading ? tr("Loading games...", "Cargando juegos...") : tr("Pick a game", "Elige un juego")}
                </div>
                {current && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                    {pill && <Pill color={pill.color}>● {pill.text}</Pill>}
                    <Chip>{current.kind === "game" ? "Steam" : tr("Non-Steam", "Fuera de Steam")}</Chip>
                  </div>
                )}
                {patched && status?.variant_label && (
                  <div style={{ fontSize: 12, color: "#98a1ad", marginTop: 6, fontWeight: 400 }}>{status.variant_label}</div>
                )}
              </div>
              <FaChevronDown style={{ opacity: 0.7 }} />
            </div>
          </Tile>
        </PanelSectionRow>

        {current && status && (patched || current.kind === "shortcut" || folder) && (
          <PanelSectionRow>
            <div style={{ width: "100%", fontSize: 11.5, color: "#98a1ad" }}>
              <div style={{ marginBottom: 2 }}>
                {patched ? tr("Patched folder", "Carpeta parcheada") : folder ? tr("Chosen folder", "Carpeta elegida") : tr("Detected folder", "Carpeta detectada")}
              </div>
              <Mono>{shownFolder || "—"}</Mono>
              {needsFolder && <div style={{ color: COLORS.warn, marginTop: 4 }}>{status.suggestion_error || tr("Choose the folder where the game .exe is.", "Elige la carpeta donde está el .exe del juego.")}</div>}
            </div>
          </PanelSectionRow>
        )}

        {extras.anticheat.length > 0 && (
          <PanelSectionRow>
            <Card color={COLORS.warn}>
              <strong style={{ color: COLORS.warn }}><IconText icon={<FaExclamationTriangle />}>{tr("Anticheat detected", "Anticheat detectado")}</IconText></strong>
              <div style={{ marginTop: 4 }}>{extras.anticheat.join(", ")}</div>
              <div style={{ marginTop: 4, opacity: 0.85 }}>{tr("Do not use the patch in online matches: ban risk.", "No uses el parche en partidas online: riesgo de baneo.")}</div>
            </Card>
          </PanelSectionRow>
        )}

        {protonWarn && (
          <PanelSectionRow>
            <Card color={COLORS.warn}>
              {tr(`This game uses ${proton?.name}. FSR 4 INT8 is reported to need GE-Proton 11 or newer; if it does not work, change the compatibility tool in the game's Properties.`,
                `Este juego usa ${proton?.name}. Se dice que FSR 4 INT8 necesita GE-Proton 11 o más nuevo; si no funciona, cambia la herramienta de compatibilidad en las Propiedades del juego.`)}
            </Card>
          </PanelSectionRow>
        )}

        <PanelSectionRow>
          <div style={{ display: "flex", gap: 8, width: "100%" }}>
            <Tile disabled={busy !== null} onActivate={() => void addExe()} style={{ flex: 3, fontSize: 13 }}>
              <IconText icon={<FaPlus />}>{busy === "add" ? tr("Adding...", "Añadiendo...") : tr("Add a game .exe", "Añadir .exe de un juego")}</IconText>
            </Tile>
            <Tile disabled={busy !== null || loading} onActivate={() => void loadItems(selected)} style={{ flex: 1 }}>
              <IconText icon={<FaSync />}>{""}</IconText>
            </Tile>
          </div>
        </PanelSectionRow>
        {current && status && !patched && (
          <PanelSectionRow>
            <Tile disabled={busy !== null} onActivate={() => void pickFolder()} style={{ fontSize: 13 }}>
              <IconText icon={<FaFolderOpen />}>{tr("Choose another folder", "Elegir otra carpeta")}</IconText>
            </Tile>
          </PanelSectionRow>
        )}
        {!current && !loading && (
          <PanelSectionRow>
            <Card color={COLORS.info}>{tr("Pick a game from the list. A game outside Steam: add its .exe with the button above.", "Elige un juego de la lista. Si no es de Steam, añade su .exe con el botón de arriba.")}</Card>
          </PanelSectionRow>
        )}
      </PanelSection>

      {current && status && (
        <PanelSection>
          <PanelSectionRow><Heading>{tr("Upscaler", "Escalador")}</Heading></PanelSectionRow>
          <PanelSectionRow>
            <ModelPicker variants={info.catalog.variants} current={pickedVariant} disabled={busy !== null}
              recommended={info.catalog.default_variant} onSelect={doVariant} />
          </PanelSectionRow>
          {patched && (
            <PanelSectionRow>
              <div style={{ fontSize: 11.5, color: "#98a1ad" }}>{tr("Changing the model applies when the game is opened.", "Al cambiar el modelo se aplica al abrir el juego.")}</div>
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            {patched ? (
              <div style={{ display: "flex", gap: 8, width: "100%" }}>
                <Tile tone="ghost" disabled={!canPatch} onActivate={() => void doPatch()} style={{ flex: 1 }}>
                  <IconText icon={<FaCheck />}>{patchLabel}</IconText>
                </Tile>
                <Tile tone="danger" disabled={busy !== null} onActivate={() => void doUnpatch()} style={{ flex: 1 }}>
                  <IconText icon={<FaTimes />}>{busy === "unpatch" ? tr("Removing...", "Quitando...") : tr("Remove patch", "Quitar parche")}</IconText>
                </Tile>
              </div>
            ) : (
              <Tile tone="primary" disabled={!canPatch} onActivate={() => void doPatch()} style={{ padding: "14px" }}>
                <IconText icon={<FaCheck />}>{patchLabel}</IconText>
              </Tile>
            )}
          </PanelSectionRow>
          {message && <PanelSectionRow><Card color={message.error ? COLORS.bad : COLORS.ok}>{message.text}</Card></PanelSectionRow>}
        </PanelSection>
      )}

      {current && patched && (
        <PanelSection>
          <PanelSectionRow><Heading>{tr("Check it works", "Comprobar")}</Heading></PanelSectionRow>
          <PanelSectionRow>
            <ToggleField
              label={tr("OptiScaler FPS overlay", "Overlay de FPS de OptiScaler")}
              description={tr("Large overlay with FPS and the upscale ratio (render → output resolution). Useful for comparing models.", "Overlay grande con FPS y la relación de escalado (resolución interna → salida). Útil para comparar modelos.")}
              checked={Boolean(extras.showFps)} disabled={busy !== null} onChange={(v) => void doFps(v)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <Tile disabled={busy !== null} onActivate={() => void doDiagnose()} style={{ fontSize: 13 }}>
              <IconText icon={<FaSearch />}>{tr("Does it work? Check status", "¿Funciona? Ver estado")}</IconText>
            </Tile>
          </PanelSectionRow>
          {diagnosis && (
            <PanelSectionRow>
              <Card color={COLORS.info}>
                <div style={{ fontWeight: 700, marginBottom: 4 }}>{tr("OptiScaler status", "Estado de OptiScaler")}</div>
                <Mono>{[
                  `${tr("DX12 upscaler", "Escalador DX12")}: ${diagnosis.settings.dx12_upscaler} · GpuSupport: ${diagnosis.settings.fsr4_gpu_support} · ${tr("Model", "Modelo")}: ${diagnosis.settings.fsr4_model}`,
                  ...diagnosis.summary, ...(diagnosis.lines.length ? ["", ...diagnosis.lines] : []),
                ].join("\n")}</Mono>
                {diagnosis.note && <div style={{ fontSize: 11.5, opacity: 0.7, marginTop: 6 }}>{diagnosis.note}</div>}
              </Card>
            </PanelSectionRow>
          )}
        </PanelSection>
      )}

      {!current && message && (
        <PanelSection><PanelSectionRow><Card color={message.error ? COLORS.bad : COLORS.ok}>{message.text}</Card></PanelSectionRow></PanelSection>
      )}
    </>
  );
}
