export type PollingMode = "fast" | "balanced" | "eco"

export interface AnalyzeRunOverrides {
  news_limit: number
  news_pool_size: number
  news_lookback_days: number
  social_limit: number
  social_pool_size: number
  social_lookback_days: number
  news_enable_alpha_vantage: boolean
  news_enable_yahoo_finance: boolean
  social_enable_reddit: boolean
  social_enable_stocktwits: boolean
}

export interface UISettings {
  polling_mode: PollingMode
  market_columns: 1 | 2
  quote_columns: 1 | 2
  show_transcript_diagnostics: boolean
  auto_open_audit_on_warnings: boolean
  run_overrides: AnalyzeRunOverrides
}

export const DEFAULT_UI_SETTINGS: UISettings = {
  polling_mode: "balanced",
  market_columns: 2,
  quote_columns: 2,
  show_transcript_diagnostics: true,
  auto_open_audit_on_warnings: true,
  run_overrides: {
    news_limit: 50,
    news_pool_size: 240,
    news_lookback_days: 21,
    social_limit: 50,
    social_pool_size: 260,
    social_lookback_days: 21,
    news_enable_alpha_vantage: true,
    news_enable_yahoo_finance: true,
    social_enable_reddit: true,
    social_enable_stocktwits: true,
  },
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

export function sanitizeAnalyzeRunOverrides(overrides?: Partial<AnalyzeRunOverrides>): AnalyzeRunOverrides {
  const incoming = { ...DEFAULT_UI_SETTINGS.run_overrides, ...(overrides || {}) }
  return {
    news_limit: clampInt(incoming.news_limit, 10, 120),
    news_pool_size: clampInt(incoming.news_pool_size, 80, 1000),
    news_lookback_days: clampInt(incoming.news_lookback_days, 3, 365),
    social_limit: clampInt(incoming.social_limit, 10, 120),
    social_pool_size: clampInt(incoming.social_pool_size, 80, 1000),
    social_lookback_days: clampInt(incoming.social_lookback_days, 3, 365),
    news_enable_alpha_vantage: Boolean(incoming.news_enable_alpha_vantage),
    news_enable_yahoo_finance: Boolean(incoming.news_enable_yahoo_finance),
    social_enable_reddit: Boolean(incoming.social_enable_reddit),
    social_enable_stocktwits: Boolean(incoming.social_enable_stocktwits),
  }
}

function clampInt(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) {
    return min
  }
  return Math.max(min, Math.min(max, Math.round(value)))
}
