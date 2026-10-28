import { callable } from "@decky/api";

export type Reply<T = object> = ({ status: "success" } & T) | { status: "error"; message: string; needs_directory?: boolean };

export type Variant = { id: string; label: string; hint: string };
export type Proxy = { id: string; hint: string };
export type Catalog = { variants: Variant[]; proxies: Proxy[]; default_variant: string; default_proxy: string };
export type RuntimeInfo = {
  installed: boolean;
  version?: string | null;
  default_variant?: string;
  default_variant_label?: string | null;
  catalog: Catalog;
};
export type Kind = "game" | "shortcut";
export type TargetItem = { kind: Kind; appid: string; name: string; installed: boolean; patched: boolean; exe?: string };
export type Proton = { name: string | null; major: number | null; ge: boolean };
export type TargetStatus = {
  kind: Kind;
  appid: string;
  name: string;
  patched: boolean;
  launch_options: string;
  proton: Proton;
  target_dir?: string;
  dll_name?: string;
  dll_present?: boolean;
  variant?: string | null;
  variant_label?: string | null;
  optiscaler_version?: string | null;
  suggested_dir?: string;
  suggestion_error?: string;
};
export type PatchResult = { launch_options: string; message: string; kept_files: string[] };
export type Community = { id: string; name: string; note: string; sha256: string; size: number };
export type Diagnosis = {
  log_found: boolean;
  summary: string[];
  lines: string[];
  note?: string;
  settings: { dx12_upscaler: string; fsr4_gpu_support: string; fsr4_model: string };
};

export const setLanguage = callable<[code: string], Reply>("set_language");
export const runtimeStatus = callable<[], Reply<RuntimeInfo>>("runtime_status");
export const install = callable<[variant: string], Reply<{ message: string }>>("install");
export const installProgress = callable<[], { active: boolean; step?: string; percent?: number | null }>("install_progress");
export const uninstall = callable<[], Reply<{ message: string }>>("uninstall");
export const setDefaultVariant = callable<[variant: string], Reply<{ default_variant: string }>>("set_default_variant");
export const communityList = callable<[], Reply<{ dlls: Community[] }>>("community_list");
export const listTargets = callable<[], Reply<{ games: TargetItem[]; shortcuts: TargetItem[] }>>("list_targets");
export const targetStatus = callable<[kind: Kind, appid: string, directory: string], Reply<TargetStatus>>("status");
export const patch = callable<
  [kind: Kind, appid: string, directory: string, dll: string, variant: string, options: string],
  Reply<PatchResult>
>("patch");
export const unpatch = callable<[kind: Kind, appid: string], Reply<{ launch_options: string | null; message: string }>>("unpatch");
export const setVariant = callable<[kind: Kind, appid: string, variant: string], Reply<{ message: string }>>("set_variant");
export const extras = callable<[kind: Kind, appid: string], Reply<{ anticheat: string[]; show_fps: boolean | null; proton: Proton }>>("extras");
export const setSetting = callable<[kind: Kind, appid: string, setting: string, enabled: boolean], Reply<{ message: string }>>("set_setting");
export const diagnose = callable<[kind: Kind, appid: string], Reply<Diagnosis>>("diagnose");
export const logError = callable<[error: string], void>("log_error");
