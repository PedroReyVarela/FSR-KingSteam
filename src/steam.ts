// The few things only Steam's own UI can do: read/write launch options and add shortcuts.

export function getLaunchOptions(appId: number): Promise<string> {
  return new Promise((resolve) => {
    if (typeof SteamClient === "undefined" || !SteamClient?.Apps?.RegisterForAppDetails) return resolve("");
    let settled = false;
    let stop = () => {};
    const timer = window.setTimeout(() => { if (!settled) { settled = true; stop(); resolve(""); } }, 4000);
    const registration = SteamClient.Apps.RegisterForAppDetails(appId, (details: { strLaunchOptions?: string }) => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      stop();
      resolve(details?.strLaunchOptions ?? "");
    });
    stop = registration.unregister;
  });
}

export function setLaunchOptions(appId: number, options: string): void {
  if (typeof SteamClient !== "undefined" && SteamClient?.Apps?.SetAppLaunchOptions) {
    SteamClient.Apps.SetAppLaunchOptions(appId, options);
  }
}

export const dirname = (path: string) => {
  const p = path.replace(/\\/g, "/");
  const i = p.lastIndexOf("/");
  return i > 0 ? p.slice(0, i) : "/";
};

export const nameWithoutExtension = (path: string) => {
  const p = path.replace(/\\/g, "/");
  const file = p.slice(p.lastIndexOf("/") + 1);
  const dot = file.lastIndexOf(".");
  return dot > 0 ? file.slice(0, dot) : file;
};
