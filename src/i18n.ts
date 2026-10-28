// Idioma de la interfaz: sigue el idioma de Steam (español o inglés)
function steamLanguage(): string {
  try {
    const w = window as any;
    const locales = w.LocalizationManager?.m_rgLocalesToUse;
    if (Array.isArray(locales) && locales.length > 0) return String(locales[0]);
    if (typeof w.LocalizationManager?.m_strPreferredLocale === "string") return w.LocalizationManager.m_strPreferredLocale;
  } catch {
    // sin LocalizationManager, se usa el del navegador
  }
  return typeof navigator !== "undefined" ? navigator.language || "en" : "en";
}

export const LANGUAGE: "es" | "en" = (() => {
  const lang = steamLanguage().toLowerCase();
  return lang.startsWith("es") || lang.includes("spanish") ? "es" : "en";
})();

// tr("English text", "Texto en español")
export function tr(en: string, es: string): string {
  return LANGUAGE === "es" ? es : en;
}
