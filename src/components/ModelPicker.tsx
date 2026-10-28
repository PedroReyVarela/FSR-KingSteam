import { useEffect, useState } from "react";
import { Menu, MenuItem, showContextMenu } from "@decky/ui";
import { FaChevronDown } from "react-icons/fa";
import { Community, communityList, Variant } from "../api";
import { tr } from "../i18n";
import { Chip, COLORS, Tile } from "../ui";

type Props = {
  variants: Variant[];
  current?: string | null;
  disabled?: boolean;
  recommended?: string;
  onSelect: (variant: string) => void;
};

// one card with the chosen model; pressing it opens the list of the others (same selector as the game list)
export function ModelPicker({ variants, current, disabled, recommended, onSelect }: Props) {
  const [community, setCommunity] = useState<Community[]>([]);

  useEffect(() => {
    let cancelled = false;
    communityList()
      .then((r) => { if (!cancelled && r.status === "success") setCommunity(r.dlls); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, []);

  const entries = [
    ...variants.map((v) => ({ id: v.id, title: v.label, hint: v.hint })),
    ...community.map((c) => ({ id: `community:${c.id}`, title: c.name, hint: `${c.note} SHA-256 ${c.sha256.slice(0, 12)}…`.trim() })),
  ];
  const chosen = entries.find((e) => e.id === current) ?? null;

  const open = () => {
    showContextMenu(
      <Menu label={tr("Upscaler / model", "Escalador / modelo")}>
        {entries.map((e) => (
          <MenuItem key={e.id} onSelected={() => onSelect(e.id)}>
            {`${e.id === current ? "✓ " : ""}${e.title}`}
          </MenuItem>
        ))}
      </Menu>
    );
  };

  return (
    <Tile selected disabled={disabled} onActivate={open} style={{ textAlign: "left", padding: "10px 12px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span style={{ fontSize: 13.5, fontWeight: 700 }}>{chosen?.title ?? tr("Custom", "Personalizado")}</span>
            {chosen?.id === recommended && <Chip color={COLORS.ok}>{tr("Recommended", "Recomendado")}</Chip>}
          </div>
          {chosen && <div style={{ fontSize: 11.5, color: "#98a1ad", marginTop: 2, lineHeight: 1.35, fontWeight: 400 }}>{chosen.hint}</div>}
          <div style={{ fontSize: 11, color: COLORS.info, marginTop: 5, fontWeight: 600 }}>{tr("Tap to see other models", "Pulsa para ver otros modelos")}</div>
        </div>
        <FaChevronDown style={{ opacity: 0.7, flex: "0 0 auto" }} />
      </div>
    </Tile>
  );
}
