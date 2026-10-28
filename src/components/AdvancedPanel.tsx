import { useState } from "react";
import { ButtonItem, DropdownItem, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { FaTrash } from "react-icons/fa";
import * as api from "../api";
import { RuntimeInfo } from "../api";
import { tr } from "../i18n";
import { Card, COLORS, errorText, IconText } from "../ui";
import { ModelPicker } from "./ModelPicker";

type Props = { info: RuntimeInfo; proxy: string; onProxy: (id: string) => void; onChange: () => void };

export function AdvancedPanel({ info, proxy, onProxy, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [note, setNote] = useState<{ text: string; error: boolean } | null>(null);

  const setDefault = async (variant: string) => {
    try {
      const r = await api.setDefaultVariant(variant);
      setNote(r.status === "success" ? null : { text: r.message, error: true });
    } catch (e) {
      setNote({ text: errorText(e), error: true });
    }
    onChange();
  };

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
    <PanelSection title={tr("Advanced", "Avanzado")}>
      <PanelSectionRow>
        <ToggleField label={tr("Show advanced options", "Mostrar opciones avanzadas")}
          description={tr("Default upscaler, proxy DLL and uninstall.", "Escalador por defecto, DLL proxy y desinstalar.")}
          checked={open} onChange={setOpen} />
      </PanelSectionRow>
      {open && (
        <>
          <PanelSectionRow>
            <ModelPicker variants={info.catalog.variants} current={info.default_variant} label={tr("Default upscaler", "Escalador por defecto")}
              onSelect={(v) => void setDefault(v.startsWith("community:") ? info.catalog.default_variant : v)} />
          </PanelSectionRow>
          <PanelSectionRow>
            <DropdownItem layout="below" label={tr("Proxy DLL name", "Nombre de la DLL proxy")}
              description={info.catalog.proxies.find((p) => p.id === proxy)?.hint}
              menuLabel={tr("Proxy DLL name", "Nombre de la DLL proxy")}
              selectedOption={proxy} rgOptions={info.catalog.proxies.map((p) => ({ data: p.id, label: p.id }))}
              onChange={(o) => onProxy(String(o.data))} />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={remove}
              description={confirm ? tr("Press again to confirm.", "Pulsa otra vez para confirmar.") : tr("Patched games keep working until you remove their patch.", "Los juegos parcheados siguen funcionando hasta que les quites el parche.")}>
              <IconText icon={<FaTrash />} color={COLORS.bad}>{confirm ? tr("Yes, remove OptiScaler", "Sí, quitar OptiScaler") : tr("Remove OptiScaler", "Quitar OptiScaler")}</IconText>
            </ButtonItem>
          </PanelSectionRow>
          {note && <PanelSectionRow><Card color={note.error ? COLORS.bad : COLORS.ok}>{note.text}</Card></PanelSectionRow>}
        </>
      )}
    </PanelSection>
  );
}
