import { useState } from "react";
import { DropdownItem, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { FaSync, FaTrash } from "react-icons/fa";
import * as api from "../api";
import { RuntimeInfo } from "../api";
import { tr } from "../i18n";
import { Card, COLORS, errorText, Heading, IconText, Tile } from "../ui";
import { useInstaller } from "./InstallPanel";

type Props = { info: RuntimeInfo; proxy: string; onProxy: (id: string) => void; onChange: () => void; installer: ReturnType<typeof useInstaller> };

export function AdvancedPanel({ info, proxy, onProxy, onChange, installer }: Props) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  const remove = async () => {
    if (!confirm) { setConfirm(true); return; }
    setConfirm(false);
    try {
      const r = await api.uninstall();
      setNote({ text: r.status === "success" ? r.message : r.message, error: r.status !== "success" });
    } catch (e) {
      setNote({ text: errorText(e), error: true });
    }
    onChange();
  };

  return (
    <PanelSection>
      <PanelSectionRow><Heading>{tr("Advanced", "Avanzado")}</Heading></PanelSectionRow>
      <PanelSectionRow>
        <ToggleField label={tr("Show advanced options", "Mostrar opciones avanzadas")}
          description={tr("Proxy DLL, reinstall and uninstall.", "DLL proxy, reinstalar y desinstalar.")}
          checked={open} onChange={setOpen} />
      </PanelSectionRow>
      {open && (
        <>
          <PanelSectionRow>
            <DropdownItem layout="below" label={tr("Proxy DLL name", "Nombre de la DLL proxy")}
              description={info.catalog.proxies.find((p) => p.id === proxy)?.hint}
              menuLabel={tr("Proxy DLL name", "Nombre de la DLL proxy")}
              selectedOption={proxy} rgOptions={info.catalog.proxies.map((p) => ({ data: p.id, label: p.id }))}
              onChange={(o) => onProxy(String(o.data))} />
          </PanelSectionRow>
          <PanelSectionRow>
            <Tile disabled={installer.busy} onActivate={() => void installer.run()} style={{ fontSize: 13 }}>
              <IconText icon={<FaSync />}>{installer.busy ? installer.progress || tr("Reinstalling...", "Reinstalando...") : tr("Reinstall runtime", "Reinstalar runtime")}</IconText>
            </Tile>
          </PanelSectionRow>
          <PanelSectionRow>
            <Tile tone="danger" onActivate={() => void remove()} style={{ fontSize: 13 }}>
              <IconText icon={<FaTrash />}>{confirm ? tr("Press again to confirm", "Pulsa otra vez para confirmar") : tr("Remove OptiScaler", "Quitar OptiScaler")}</IconText>
            </Tile>
          </PanelSectionRow>
          <PanelSectionRow>
            <div style={{ fontSize: 11.5, color: "#98a1ad" }}>{tr("Patched games keep working until you remove their patch.", "Los juegos parcheados siguen funcionando hasta que les quites el parche.")}</div>
          </PanelSectionRow>
          {note && <PanelSectionRow><Card color={note.error ? COLORS.bad : COLORS.ok}>{note.text}</Card></PanelSectionRow>}
        </>
      )}
    </PanelSection>
  );
}
