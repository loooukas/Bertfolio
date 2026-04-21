export type PollingMode = "fast" | "balanced" | "eco"

export interface UISettings {
  polling_mode: PollingMode
  market_columns: 1 | 2
  quote_columns: 1 | 2
  show_transcript_diagnostics: boolean
  auto_open_audit_on_warnings: boolean
}

export const DEFAULT_UI_SETTINGS: UISettings = {
  polling_mode: "balanced",
  market_columns: 2,
  quote_columns: 2,
  show_transcript_diagnostics: true,
  auto_open_audit_on_warnings: true,
}

export function pollIntervalMs(mode: PollingMode): number {
  if (mode === "fast") {
    return 900
  }
  if (mode === "eco") {
    return 3000
  }
  return 1800
}
