import { useEffect, useState } from "react";
import { FaCheck } from "react-icons/fa";
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

// every model is a card you can see at once: title, one line of help, and a check on the chosen one
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, width: "100%" }}>
      {entries.map((entry) => {
        const chosen = entry.id === current;
        return (
          <Tile key={entry.id} selected={chosen} disabled={disabled} onActivate={() => onSelect(entry.id)} style={{ textAlign: "left", padding: "9px 12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{
                flex: "0 0 18px", height: 18, borderRadius: 9, display: "flex", alignItems: "center", justifyContent: "center",
                border: `2px solid ${chosen ? COLORS.info : "#4b5563"}`, background: chosen ? COLORS.info : "transparent", color: "#fff", fontSize: 10,
              }}>{chosen ? <FaCheck /> : null}</span>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13.5, fontWeight: 700 }}>{entry.title}</span>
                  {entry.id === recommended && <Chip color={COLORS.ok}>{tr("Recommended", "Recomendado")}</Chip>}
                </div>
                <div style={{ fontSize: 11.5, color: "#98a1ad", marginTop: 2, lineHeight: 1.35, fontWeight: 400 }}>{entry.hint}</div>
              </div>
            </div>
          </Tile>
        );
      })}
    </div>
  );
}
