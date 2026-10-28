import { definePlugin } from "@decky/api";
import { useCallback, useEffect, useState } from "react";
import { MdOutlineAutoAwesomeMotion } from "react-icons/md";
import { RuntimeInfo, runtimeStatus, setLanguage } from "./api";
import { AdvancedPanel } from "./components/AdvancedPanel";
import { GamePanel } from "./components/GamePanel";
import { InstallPanel, useInstaller } from "./components/InstallPanel";
import { LANGUAGE } from "./i18n";

function Main() {
  const [info, setInfo] = useState<RuntimeInfo | null>(null);
  const [proxy, setProxy] = useState("dxgi.dll");

  // the backend writes its messages and labels in Steam's language, so tell it first
  const refresh = useCallback(async () => {
    try {
      await setLanguage(LANGUAGE);
      const r = await runtimeStatus();
      if (r.status === "success") setInfo(r);
    } catch (e) {
      console.error("FSR-KingSteam: runtime status failed", e);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  const installer = useInstaller(info, refresh);

  return (
    <>
      <InstallPanel info={info} installer={installer} />
      {info?.installed && <GamePanel info={info} proxy={proxy} />}
      {info?.installed && <AdvancedPanel info={info} proxy={proxy} onProxy={setProxy} onChange={refresh} installer={installer} />}
    </>
  );
}

export default definePlugin(() => ({
  name: "FSR-KingSteam",
  titleView: <div>FSR-KingSteam</div>,
  alwaysRender: true,
  content: <Main />,
  icon: <MdOutlineAutoAwesomeMotion />,
}));
