import { useEffect, useMemo, useState } from "react";
import { DropdownItem } from "@decky/ui";
import { Community, communityList, Variant } from "../api";
import { tr } from "../i18n";

type Props = {
  variants: Variant[];
  current?: string | null;
  currentLabel?: string | null;
  label?: string;
  disabled?: boolean;
  onSelect: (variant: string) => void;
};

export function ModelPicker({ variants, current, currentLabel, label, disabled, onSelect }: Props) {
  const [community, setCommunity] = useState<Community[]>([]);

  useEffect(() => {
    let cancelled = false;
    communityList()
      .then((r) => { if (!cancelled && r.status === "success") setCommunity(r.dlls); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const options = useMemo(() => [
    ...variants.map((v) => ({ data: v.id, label: v.label })),
    ...community.map((c) => ({ data: `community:${c.id}`, label: `${tr("Community", "Comunidad")}: ${c.name}` })),
  ], [variants, community]);

  const description = useMemo(() => {
    const official = variants.find((v) => v.id === current);
    if (official) return official.hint;
    const entry = community.find((c) => `community:${c.id}` === current);
    return entry ? `${entry.note} SHA-256 ${entry.sha256.slice(0, 16)}…`.trim() : undefined;
  }, [community, current, variants]);

  return (
    <DropdownItem
      layout="below"
      label={label ?? tr("Upscaler / model for this game", "Escalador / modelo de este juego")}
      description={description}
      menuLabel={tr("FSR4 model", "Modelo FSR4")}
      strDefaultLabel={currentLabel || tr("Custom", "Personalizado")}
      disabled={disabled}
      selectedOption={current ?? undefined}
      rgOptions={options}
      onChange={(o) => onSelect(String(o.data))}
    />
  );
}
