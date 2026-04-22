export type BackendStageStatus = "pending" | "loading" | "done" | "error"
export type BackendJobStatus = "queued" | "running" | "completed" | "failed"

export interface BackendJobProgressStage {
  key: string
  label: string
  status: BackendStageStatus
  progress: number
  message: string
  duration_ms?: number | null
}

export interface BackendJobProgress {
  percent: number
  active_stage: string
  active_subtask: string
  stages: BackendJobProgressStage[]
}

export interface BackendJobPayload {
  job_id: string
  ticker: string
  status: BackendJobStatus
  created_at: string
  updated_at: string
  progress: BackendJobProgress
  error?: string | null
  result?: AnalysisResponseBackend
}

export interface AnalysisResponseBackend {
  analysis_version: string
  ticker: string
  transcripts_found: number
  overall_sentiment_score: number
  overall_sentiment_label: string
  overview: {
    ticker: string
    company_name?: string | null
    stance_label: string
    executive_summary: string
    key_takeaways: string[]
    metrics: Array<{ key: string; label: string; value: string }>
  }
  transcript: {
    availability: "available" | "partial" | "missing"
    transcript_count_requested: number
    transcript_count_found: number
    latest_summary: string
    prepared_vs_qa_note: string
    key_quotes: string[]
    qa_pressure_points: string[]
    speaker_analysis: Array<{
      speaker: string
      section_type: "prepared_remarks" | "qa" | "other"
      order_index?: number
      transcript_source_url?: string | null
      sentiment_direction: number
      confidence: number
      evasiveness: number
      specificity: number
      forward_looking_strength: number
      risk_language_intensity: number
      topic_label: string
      segment_char_count?: number
      evidence_snippets?: string[]
      segment_diagnostics?: {
        transcript_source?: string
        transcript_title?: string
        transcript_published_date?: string
      } | null
    }>
    speaker_rollup: Array<{
      speaker: string
      mention_count: number
      avg_sentiment_direction: number
      avg_confidence: number
      avg_evasiveness: number
      dominant_topic: string
    }>
    quarter_status: Array<{
      quarter: string
      status: "found" | "not_found" | "error"
      detail?: string | null
    }>
    transcripts: Array<{
      ticker: string
      company_name?: string | null
      source: string
      source_url?: string | null
      title?: string | null
      published_date?: string | null
      has_full_transcript: boolean
      extraction_confidence: number
      parsing_warnings: string[]
      participants: Array<{
        name: string
        role?: string | null
      }>
      sections: Array<{
        section_type: "prepared_remarks" | "qa" | "other"
        speaker: string
        speaker_role?: string | null
        text: string
        order_index: number
        evidence_snippets: string[]
      }>
      key_quotes: string[]
      normalization_mode: "openai" | "deterministic_degraded"
    }>
  }
  market_reaction: {
    balance_summary: string
    news_count: number
    social_count: number
    news_items: Array<{
      title: string
      summary: string
      url: string
      source?: string | null
      time_published?: string | null
      sentiment_score: number
      sentiment_label: string
    }>
    social_items: Array<{
      source: string
      title: string
      body: string
      excerpt?: string | null
      url: string
      subreddit?: string | null
      created_utc?: number | null
      relevance_score: number
      sentiment_score: number
      sentiment_label: string
    }>
  }
  fundamentals_workspace: {
    operating_context: string
    metrics: Array<{ key: string; label: string; value: string }>
    analyst_signals?: Array<{
      key: string
      label: string
      value: string
      tone: "bullish" | "neutral" | "bearish" | "muted"
      note?: string | null
    }>
    table: Array<{
      quarter: string
      revenue?: number | null
      net_income?: number | null
      reported_eps?: number | null
      eps_estimate?: number | null
    }>
  }
  data_audit: {
    confidence_note: string
    normalization_mode: "openai" | "deterministic_degraded"
    warnings: string[]
    notices: string[]
    diagnostics: string[]
    missing_items: string[]
    parsing_warnings: string[]
    source_counts: {
      transcripts: number
      news: number
      social: number
    }
    dedupe_counts: {
      news_pool?: number
      news_deduped?: number
      social_pool?: number
      social_deduped?: number
      pool?: number
      deduped?: number
    }
    transcript_discovery: {
      pages_scanned: number
      candidates_total: number
      transcript_like_count: number
      match_filtered_count: number
      selected_count: number
      discarded_near_matches: string[]
      fetch_failures: string[]
      playwright_fallback_used: boolean
    }
    task_breakdown: Array<{
      key: string
      label: string
      status: "done" | "error" | "skipped"
      duration_ms: number
      detail: string
    }>
    fundamentals_validation: {
      yahoo_source_used: boolean
      alpha_source_used: boolean
      compared_fields: string[]
      notes: string[]
      mismatches: Array<{
        key: string
        yahoo_value?: number | null
        alpha_value?: number | null
        relative_diff_pct?: number | null
        severity?: "low" | "medium" | "high" | null
        note?: string | null
      }>
    }
  }
}

export interface UIReportModel {
  ticker: string
  company_name: string
  analysis_version: string
  overall_sentiment_score: number
  overall_sentiment_label: string
  transcripts_found: number
  overview: {
    stance_label: string
    executive_summary: string
    key_takeaways: string[]
    metrics: Array<{ key: string; label: string; value: number }>
  }
  transcript: {
    availability: "available" | "partial" | "missing"
    transcript_count_requested: number
    transcript_count_found: number
    latest_summary: string
    prepared_vs_qa_note: string
    key_quotes: Array<{ speaker: string; text: string; sentiment: "bullish" | "bearish" | "neutral" }>
    qa_pressure_points: string[]
    speaker_analysis: Array<{
      speaker: string
      section_type: "prepared_remarks" | "qa" | "other"
      order_index?: number
      transcript_source_url?: string
      sentiment_direction: number
      confidence: number
      evasiveness: number
      specificity: number
      forward_looking_strength: number
      risk_language_intensity: number
      topic_label: string
      mentions: number
    }>
    speaker_rollup: Array<{
      speaker: string
      mention_count: number
      avg_sentiment_direction: number
      avg_confidence: number
      avg_evasiveness: number
      dominant_topic: string
    }>
    quarter_status: Array<{
      quarter: string
      status: "found" | "not_found" | "error"
    }>
    transcripts: Array<{
      id: string
      label: string
      source: string
      source_url?: string
      title?: string
      published_date?: string
      sections: Array<{
        section_type: "prepared_remarks" | "qa" | "other"
        speaker: string
        speaker_role?: string
        text: string
        order_index: number
      }>
    }>
  }
  market_reaction: {
    balance_summary: string
    news_count: number
    social_count: number
    news_items: Array<{
      title: string
      summary: string
      url: string
      source: string
      time_published: string
      sentiment_score: number
      sentiment_label: "bullish" | "bearish" | "neutral"
    }>
    social_items: Array<{
      source: string
      title: string
      body: string
      excerpt: string
      url: string
      subreddit?: string
      created_utc: string
      relevance_score: number
      sentiment_score: number
      sentiment_label: "bullish" | "bearish" | "neutral"
    }>
  }
  fundamentals: {
    operating_context: string
    metrics: Array<{ key: string; label: string; value: string }>
    analyst_signals: Array<{
      key: string
      label: string
      value: string
      tone: "bullish" | "neutral" | "bearish" | "muted"
      note?: string
    }>
    quarterly_data: Array<{
      quarter: string
      revenue: number
      net_income: number
      reported_eps: number
      eps_estimate: number
    }>
  }
  data_audit: {
    confidence_note: string
    normalization_mode: "openai" | "deterministic_degraded"
    warnings: string[]
    notices: string[]
    diagnostics: string[]
    missing_items: string[]
    parsing_warnings: string[]
    source_counts: {
      transcripts: number
      news: number
      social: number
    }
    dedupe_counts: {
      pool: number
      deduped: number
    }
    transcript_discovery: {
      pages_scanned: number
      candidates_total: number
      transcript_like_count: number
      match_filtered_count: number
      selected_count: number
      discarded_near_matches: string[]
      fetch_failures: string[]
      playwright_fallback_used: boolean
    }
    task_breakdown: Array<{
      key: string
      label: string
      status: "done" | "error" | "skipped"
      duration_ms: number
      detail: string
    }>
    fundamentals_validation: {
      yahoo_source_used: boolean
      alpha_source_used: boolean
      compared_fields: string[]
      notes: string[]
      mismatches: Array<{
        key: string
        yahoo_value: string
        alpha_value: string
        relative_diff_pct: number
        severity: "low" | "medium" | "high"
        note: string
      }>
    }
  }
}
