export type PollingMode = "fast" | "balanced" | "eco"

export interface AnalyzeRunOverrides {
  news_limit: number
  news_pool_size: number
  news_lookback_days: number
  social_limit: number
  social_pool_size: number
  social_lookback_days: number
  use_cache: boolean
  use_optimized_score_weight_defaults: boolean
  score_weight_transcript: number
  score_weight_fundamentals: number
  score_weight_news: number
  score_weight_social: number
  transcript_internal_model_enabled: boolean
  transcript_internal_intercept: number
  transcript_internal_weight_sentiment: number
  transcript_internal_weight_confidence: number
  transcript_internal_weight_directness: number
  transcript_internal_weight_outlook_strength: number
  transcript_internal_weight_specificity: number
  transcript_internal_weight_risk_intensity: number
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

export const OPTIMIZED_SCORE_WEIGHTS = {
  transcript: 100,
  fundamentals: 0,
  news: 0,
  social: 0,
} as const

export const OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS = {
  intercept: -0.019738131823252437,
  sentiment: -0.1401634692187762,
  confidence: -0.018278288860921532,
  directness: 0.015206414272671791,
  outlook_strength: -0.11552397904346766,
  specificity: -0.08887882362418172,
  risk_intensity: -0.0394870057888973,
} as const

export const DEFAULT_UI_SETTINGS: UISettings = {
  polling_mode: "balanced",
  market_columns: 2,
  quote_columns: 2,
  show_transcript_diagnostics: true,
  auto_open_audit_on_warnings: false,
  run_overrides: {
    news_limit: 50,
    news_pool_size: 240,
    news_lookback_days: 30,
    social_limit: 50,
    social_pool_size: 260,
    social_lookback_days: 30,
    use_cache: false,
    use_optimized_score_weight_defaults: true,
    score_weight_transcript: OPTIMIZED_SCORE_WEIGHTS.transcript,
    score_weight_fundamentals: OPTIMIZED_SCORE_WEIGHTS.fundamentals,
    score_weight_news: OPTIMIZED_SCORE_WEIGHTS.news,
    score_weight_social: OPTIMIZED_SCORE_WEIGHTS.social,
    transcript_internal_model_enabled: true,
    transcript_internal_intercept: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.intercept,
    transcript_internal_weight_sentiment: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.sentiment,
    transcript_internal_weight_confidence: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.confidence,
    transcript_internal_weight_directness: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.directness,
    transcript_internal_weight_outlook_strength: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.outlook_strength,
    transcript_internal_weight_specificity: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.specificity,
    transcript_internal_weight_risk_intensity: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.risk_intensity,
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

export function sanitizeUISettings(settings?: Partial<UISettings> | null): UISettings {
  const incoming = settings || {}
  const pollingMode = incoming.polling_mode
  const marketColumns = incoming.market_columns
  const quoteColumns = incoming.quote_columns

  return {
    polling_mode: pollingMode === "fast" || pollingMode === "eco" || pollingMode === "balanced"
      ? pollingMode
      : DEFAULT_UI_SETTINGS.polling_mode,
    market_columns: marketColumns === 1 || marketColumns === 2 ? marketColumns : DEFAULT_UI_SETTINGS.market_columns,
    quote_columns: quoteColumns === 1 || quoteColumns === 2 ? quoteColumns : DEFAULT_UI_SETTINGS.quote_columns,
    // Transcript diagnostics are intentionally always on.
    show_transcript_diagnostics: true,
    auto_open_audit_on_warnings:
      typeof incoming.auto_open_audit_on_warnings === "boolean"
        ? incoming.auto_open_audit_on_warnings
        : DEFAULT_UI_SETTINGS.auto_open_audit_on_warnings,
    run_overrides: sanitizeAnalyzeRunOverrides(incoming.run_overrides),
  }
}

export function sanitizeAnalyzeRunOverrides(overrides?: Partial<AnalyzeRunOverrides>): AnalyzeRunOverrides {
  const incoming = { ...DEFAULT_UI_SETTINGS.run_overrides, ...(overrides || {}) }
  const useOptimizedScoreWeightDefaults = Boolean(incoming.use_optimized_score_weight_defaults)
  const scoreWeightTranscript = useOptimizedScoreWeightDefaults
    ? OPTIMIZED_SCORE_WEIGHTS.transcript
    : clampInt(incoming.score_weight_transcript, 0, 100)
  const scoreWeightFundamentals = useOptimizedScoreWeightDefaults
    ? OPTIMIZED_SCORE_WEIGHTS.fundamentals
    : clampInt(incoming.score_weight_fundamentals, 0, 100)
  const scoreWeightNews = useOptimizedScoreWeightDefaults
    ? OPTIMIZED_SCORE_WEIGHTS.news
    : clampInt(incoming.score_weight_news, 0, 100)
  const scoreWeightSocial = useOptimizedScoreWeightDefaults
    ? OPTIMIZED_SCORE_WEIGHTS.social
    : clampInt(incoming.score_weight_social, 0, 100)

  return {
    news_limit: clampInt(incoming.news_limit, 10, 120),
    news_pool_size: clampInt(incoming.news_pool_size, 80, 1000),
    news_lookback_days: clampInt(incoming.news_lookback_days, 3, 365),
    social_limit: clampInt(incoming.social_limit, 10, 120),
    social_pool_size: clampInt(incoming.social_pool_size, 80, 1000),
    social_lookback_days: clampInt(incoming.social_lookback_days, 3, 365),
    use_cache: Boolean(incoming.use_cache),
    use_optimized_score_weight_defaults: useOptimizedScoreWeightDefaults,
    score_weight_transcript: scoreWeightTranscript,
    score_weight_fundamentals: scoreWeightFundamentals,
    score_weight_news: scoreWeightNews,
    score_weight_social: scoreWeightSocial,
    // Transcript sub-weights are intentionally always the calibrated defaults.
    transcript_internal_model_enabled: true,
    transcript_internal_intercept: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.intercept,
    transcript_internal_weight_sentiment: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.sentiment,
    transcript_internal_weight_confidence: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.confidence,
    transcript_internal_weight_directness: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.directness,
    transcript_internal_weight_outlook_strength: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.outlook_strength,
    transcript_internal_weight_specificity: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.specificity,
    transcript_internal_weight_risk_intensity: OPTIMIZED_TRANSCRIPT_INTERNAL_WEIGHTS.risk_intensity,
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
