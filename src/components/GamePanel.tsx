import { useCallback, useEffect, useMemo, useState } from "react";
import { ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { FileSelectionType, openFilePicker, toaster } from "@decky/api";
import { FaCheck, FaExclamationTriangle, FaFolderOpen, FaPlus, FaSearch, FaSync, FaTimes } from "react-icons/fa";
import * as api from "../api";
import { Kind, RuntimeInfo, TargetItem, TargetStatus } from "../api";
import { tr } from "../i18n";
import { dirname, getLaunchOptions, nameWithoutExtension, setLaunchOptions } from "../steam";
import { Card, COLORS, errorText, IconText, Mono, Pill } from "../ui";
import { ModelPicker } from "./ModelPicker";

type Props = { info: RuntimeInfo; proxy: string };
type Extras = { anticheat: string[]; showFps: boolean | null; proton: api.Proton | null };

const keyOf = (t: { kind: Kind; appid: string }) => `${t.kind}:${t.appid}`;
let lastKey = ""; // keep the selection while the panel is closed and reopened
const focusable = { focusable: true, highlightOnFocus: true } as const;

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
    if (!status?.patched) { setVariantChoice(next); return; }
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
  const isShortcut = current?.kind === "shortcut";
  const shownFolder = patched ? status?.target_dir : folder || status?.suggested_dir;
  const needsFolder = !patched && !folder && !status?.suggested_dir && Boolean(status);
  const canPatch = Boolean(current && status && !busy && !needsFolder && current.installed);
  const pickedVariant = patched ? status?.variant : variant;
  const pill = !current ? null
    : problem ? { color: COLORS.bad, text: problem }
    : !status ? { color: COLORS.muted, text: tr("Loading...", "Cargando...") }
    : !current.installed ? { color: COLORS.bad, text: tr("Install not found", "Instalación no encontrada") }
    : patched && status.dll_present === false ? { color: COLORS.warn, text: tr("Patch incomplete: reinstall it", "Parche incompleto: reinstálalo") }
    : patched ? { color: COLORS.ok, text: tr("Patched", "Parcheado") }
    : { color: COLORS.muted, text: tr("Not patched", "Sin parchear") };

  const proton = extras.proton ?? status?.proton ?? null;
  const protonWarn = proton && (proton.ge ? (proton.major ?? 99) < 11 : false);
  const patchLabel = busy === "patch" ? tr("Patching...", "Parcheando...")
    : patched ? tr("Reinstall patch", "Reinstalar parche")
    : extras.anticheat.length ? tr("Patch anyway (at your own risk)", "Parchear de todos modos (bajo tu riesgo)")
    : tr("Patch this game", "Parchear este juego");

  return (
    <>
      <PanelSection title={tr("Game", "Juego")}>
        <PanelSectionRow>
          <DropdownItem
            layout="below"
            label={tr("Choose a game", "Elige un juego")}
            menuLabel={tr("Choose a game", "Elige un juego")}
            strDefaultLabel={loading ? tr("Loading games...", "Cargando juegos...") : tr("No games", "No hay juegos")}
            disabled={loading || items.length === 0}
            selectedOption={selected}
            rgOptions={items.map((i) => ({
              data: keyOf(i),
              label: `${i.patched ? "● " : ""}${i.name}${i.installed ? "" : ` (${tr("not installed", "no instalado")})`}`,
            }))}
            onChange={(o) => { lastKey = String(o.data); setSelected(lastKey); }}
          />
        </PanelSectionRow>

        {!current && !loading && (
          <PanelSectionRow>
            <Card color={COLORS.info}>{tr("Pick a game from the list. A game outside Steam: add its .exe with the button below.", "Elige un juego de la lista. Si no es de Steam, añade su .exe con el botón de abajo.")}</Card>
          </PanelSectionRow>
        )}

        {pill && (
          <PanelSectionRow>
            <Field {...focusable} label={tr("Status", "Estado")} description={patched ? status?.variant_label ?? undefined : undefined}>
              <Pill color={pill.color}>● {pill.text}</Pill>
            </Field>
          </PanelSectionRow>
        )}

        {current && status && (isShortcut || patched || folder) && (
          <>
            <PanelSectionRow>
              <Field
                {...focusable}
                label={patched ? tr("Patched folder", "Carpeta parcheada") : folder ? tr("Chosen folder", "Carpeta elegida") : tr("Detected folder", "Carpeta detectada")}
                description={needsFolder ? status.suggestion_error || tr("Choose the folder where the game .exe is.", "Elige la carpeta donde está el .exe del juego.") : undefined}
              >
                <Mono>{shownFolder || "—"}</Mono>
              </Field>
            </PanelSectionRow>
          </>
        )}
        {current && status && !patched && (
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy !== null} onClick={pickFolder}>
              <IconText icon={<FaFolderOpen />}>{tr("Choose another folder", "Elegir otra carpeta")}</IconText>
            </ButtonItem>
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
          <ButtonItem layout="below" disabled={busy !== null} onClick={addExe}
            description={tr("Pick a game's .exe and it gets a Steam entry, needed to set launch options.", "Elige el .exe de un juego y se le crea una entrada en Steam, hace falta para las opciones de lanzamiento.")}>
            <IconText icon={<FaPlus />}>{busy === "add" ? tr("Adding...", "Añadiendo...") : tr("Choose the .exe of a game not in the list", "Elegir el .exe de un juego que no está en la lista")}</IconText>
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy !== null || loading} onClick={() => void loadItems(selected)}>
            <IconText icon={<FaSync />}>{tr("Refresh list", "Actualizar lista")}</IconText>
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      {current && status && (
        <PanelSection title={tr("Upscaler", "Escalador")}>
          <PanelSectionRow>
            <ModelPicker variants={info.catalog.variants} current={pickedVariant} currentLabel={patched ? status.variant_label : undefined}
              disabled={busy !== null} onSelect={doVariant} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={!canPatch} onClick={doPatch}>
              <span style={{ fontWeight: 700 }}><IconText icon={<FaCheck />} color={canPatch ? COLORS.ok : undefined}>{patchLabel}</IconText></span>
            </ButtonItem>
          </PanelSectionRow>
          {patched && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={busy !== null} onClick={doUnpatch}>
                <span style={{ fontWeight: 600 }}>
                  <IconText icon={<FaTimes />} color={COLORS.bad}>{busy === "unpatch" ? tr("Removing...", "Quitando...") : tr("Remove patch", "Quitar parche")}</IconText>
                </span>
              </ButtonItem>
            </PanelSectionRow>
          )}
          {message && <PanelSectionRow><Card color={message.error ? COLORS.bad : COLORS.ok}>{message.text}</Card></PanelSectionRow>}
        </PanelSection>
      )}

      {current && patched && (
        <PanelSection title={tr("Check it works", "Comprobar")}>
          <PanelSectionRow>
            <ToggleField
              label={tr("OptiScaler FPS overlay", "Overlay de FPS de OptiScaler")}
              description={tr("Large overlay with FPS and the upscale ratio (render → output resolution). Useful for comparing models.", "Overlay grande con FPS y la relación de escalado (resolución interna → salida). Útil para comparar modelos.")}
              checked={Boolean(extras.showFps)} disabled={busy !== null} onChange={(v) => void doFps(v)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy !== null} onClick={doDiagnose}>
              <IconText icon={<FaSearch />}>{tr("Does it work? Check status", "¿Funciona? Ver estado")}</IconText>
            </ButtonItem>
          </PanelSectionRow>
          {diagnosis && (
            <PanelSectionRow>
              <Field {...focusable} label={tr("OptiScaler status", "Estado de OptiScaler")} description={diagnosis.note}>
                <Mono>{[
                  `${tr("DX12 upscaler", "Escalador DX12")}: ${diagnosis.settings.dx12_upscaler} · GpuSupport: ${diagnosis.settings.fsr4_gpu_support} · ${tr("Model", "Modelo")}: ${diagnosis.settings.fsr4_model}`,
                  ...diagnosis.summary, ...(diagnosis.lines.length ? ["", ...diagnosis.lines] : []),
                ].join("\n")}</Mono>
              </Field>
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
