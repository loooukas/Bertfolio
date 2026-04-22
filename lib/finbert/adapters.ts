import type {
  AnalysisResponseBackend,
  BackendJobProgress,
  BackendJobProgressStage,
  UIReportModel,
} from "@/lib/finbert/types"

export const DEFAULT_PROGRESS_STAGES: BackendJobProgressStage[] = [
  { key: "news_fetch", label: "News Fetch", status: "pending", progress: 0, message: "Waiting" },
  { key: "social_fetch", label: "Social Fetch", status: "pending", progress: 0, message: "Waiting" },
  { key: "news_sentiment_scoring", label: "News Sentiment Scoring", status: "pending", progress: 0, message: "Waiting" },
  { key: "social_sentiment_scoring", label: "Social Sentiment Scoring", status: "pending", progress: 0, message: "Waiting" },
  { key: "fundamentals_fetch", label: "Fundamentals Fetch", status: "pending", progress: 0, message: "Waiting" },
  { key: "fundamentals_validation", label: "Fundamentals Validation", status: "pending", progress: 0, message: "Waiting" },
  { key: "transcript_discovery_scrape", label: "Transcript Discovery + Scrape", status: "pending", progress: 0, message: "Waiting" },
  { key: "transcript_normalization", label: "Transcript Normalization", status: "pending", progress: 0, message: "Waiting" },
  { key: "transcript_sentiment_speaker_scoring", label: "Transcript Sentiment + Speaker Scoring", status: "pending", progress: 0, message: "Waiting" },
  { key: "data_audit_report_assembly", label: "Data Audit / Report Assembly", status: "pending", progress: 0, message: "Waiting" },
]

export const DEFAULT_PROGRESS: BackendJobProgress = {
  percent: 0,
  active_stage: "news_fetch",
  active_subtask: "Initializing analysis",
  stages: DEFAULT_PROGRESS_STAGES,
}

const SENTIMENT_NEUTRAL_LABELS = new Set(["mixed", "neutral", "none"])

function toNumber(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value
  }
  if (typeof value !== "string") {
    return 0
  }
  const raw = value.trim()
  if (!raw) {
    return 0
  }
  if (raw.includes("/") && !raw.includes("%")) {
    const [left, right] = raw.split("/")
    const numerator = Number(left)
    const denominator = Number(right)
    if (Number.isFinite(numerator) && Number.isFinite(denominator) && denominator > 0) {
      return (numerator / denominator) * 100
    }
  }
  const parsed = Number(raw.replace(/[^0-9.+-]/g, ""))
  return Number.isFinite(parsed) ? parsed : 0
}

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value))
}

function titleFromSnake(value: string): string {
  return value
    .replace(/_/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function normalizeSentimentLabel(label: string): "bullish" | "bearish" | "neutral" {
  const lower = label.toLowerCase().trim()
  if (!lower || SENTIMENT_NEUTRAL_LABELS.has(lower)) {
    return "neutral"
  }
  if (lower.includes("bull") || lower.includes("positive")) {
    return "bullish"
  }
  if (lower.includes("bear") || lower.includes("negative")) {
    return "bearish"
  }
  return "neutral"
}

function formatIsoTime(input?: string | null): string {
  if (!input) {
    return new Date(0).toISOString()
  }
  const parsed = new Date(input)
  return Number.isNaN(parsed.valueOf()) ? new Date(0).toISOString() : parsed.toISOString()
}

function formatCreatedUtc(input?: number | null): string {
  if (typeof input !== "number" || !Number.isFinite(input) || input <= 0) {
    return new Date(0).toISOString()
  }
  return new Date(input * 1000).toISOString()
}

function quoteSentimentFromScore(score: number): "bullish" | "bearish" | "neutral" {
  if (score >= 0.12) {
    return "bullish"
  }
  if (score <= -0.12) {
    return "bearish"
  }
  return "neutral"
}

function safeProgress(stage?: BackendJobProgress): BackendJobProgress {
  if (!stage) {
    return DEFAULT_PROGRESS
  }
  const normalizedStages = (stage.stages || [])
    .filter((item) => item && typeof item.key === "string" && item.key.trim())
    .map((item) => ({
      ...item,
      progress: Number.isFinite(item.progress) ? clamp(item.progress, 0, 1) : 0,
      duration_ms: typeof item.duration_ms === "number" ? item.duration_ms : undefined,
    }))

  return {
    percent: Number.isFinite(stage.percent) ? stage.percent : 0,
    active_stage: stage.active_stage || "",
    active_subtask: stage.active_subtask || "",
    stages: normalizedStages.length > 0 ? normalizedStages : DEFAULT_PROGRESS_STAGES,
  }
}

function normalizeQuoteText(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function quarterLabelFromDate(dateRaw?: string | null): string | null {
  if (!dateRaw) {
    return null
  }
  const date = new Date(dateRaw)
  if (Number.isNaN(date.valueOf())) {
    return null
  }
  const month = date.getUTCMonth() + 1
  const quarter = Math.floor((month - 1) / 3) + 1
  return `Q${quarter} ${date.getUTCFullYear()}`
}

function quarterLabelFromTitle(titleRaw?: string | null): string | null {
  if (!titleRaw) {
    return null
  }
  const title = titleRaw.trim()
  if (!title) {
    return null
  }
  const matched = title.match(/\bQ([1-4])\s*(?:FY)?\s*(20\d{2})\b/i)
  if (!matched) {
    return null
  }
  return `Q${matched[1]} ${matched[2]}`
}

function transcriptLabelFromMetadata(
  titleRaw: string | null | undefined,
  publishedDateRaw: string | null | undefined,
  index: number,
): string {
  const fromTitle = quarterLabelFromTitle(titleRaw)
  if (fromTitle) {
    return fromTitle
  }
  const fromDate = quarterLabelFromDate(publishedDateRaw)
  if (fromDate) {
    return fromDate
  }
  return `Transcript ${index + 1}`
}

export function adaptJobProgress(progress?: BackendJobProgress): BackendJobProgress {
  return safeProgress(progress)
}

export function adaptAnalysisResponseToUI(report: AnalysisResponseBackend): UIReportModel {
  const avgSpeakerDirection =
    report.transcript.speaker_analysis.length > 0
      ? report.transcript.speaker_analysis.reduce((sum, row) => sum + row.sentiment_direction, 0) /
        report.transcript.speaker_analysis.length
      : 0

  const quotesFromStrings =
    report.transcript.key_quotes.length > 0
      ? report.transcript.key_quotes
      : report.transcript.speaker_analysis.flatMap((row) => row.evidence_snippets || [])

  const quoteSpeakerCandidates = report.transcript.speaker_analysis.flatMap((row) => {
    const snippets = row.evidence_snippets || []
    return snippets.map((snippet) => ({
      speaker: row.speaker,
      normalized: normalizeQuoteText(snippet),
    }))
  })

  const keyQuotes = quotesFromStrings.slice(0, 8).map((text) => {
    const normalizedQuote = normalizeQuoteText(text)
    const directMatch = quoteSpeakerCandidates.find((candidate) => candidate.normalized === normalizedQuote)
    const fuzzyMatch =
      directMatch ||
      quoteSpeakerCandidates.find(
        (candidate) =>
          candidate.normalized.length >= 24 &&
          (candidate.normalized.includes(normalizedQuote) || normalizedQuote.includes(candidate.normalized)),
      )

    return {
      speaker: fuzzyMatch?.speaker || "Management",
      text,
      sentiment: quoteSentimentFromScore(avgSpeakerDirection),
    }
  })

  const speakerRows = report.transcript.speaker_analysis.map((row) => ({
    speaker: row.speaker,
    speaker_role: row.speaker_role || undefined,
    section_type: row.section_type,
    order_index: typeof row.order_index === "number" ? row.order_index : undefined,
    transcript_source_url: row.transcript_source_url || undefined,
    sentiment_direction: row.sentiment_direction,
    confidence: row.confidence,
    evasiveness: row.evasiveness,
    specificity: row.specificity,
    forward_looking_strength: row.forward_looking_strength,
    risk_language_intensity: row.risk_language_intensity,
    topic_label: row.topic_label,
    mentions: Math.max(1, Math.round((row.segment_char_count || 220) / 220)),
  }))

  const dedupePool =
    (report.data_audit.dedupe_counts.news_pool || 0) +
    (report.data_audit.dedupe_counts.social_pool || 0) +
    (report.data_audit.dedupe_counts.pool || 0)
  const dedupeCount =
    (report.data_audit.dedupe_counts.news_deduped || 0) +
    (report.data_audit.dedupe_counts.social_deduped || 0) +
    (report.data_audit.dedupe_counts.deduped || 0)
  const diagnosticsCompat = Array.from(
    new Set(
      [...(report.data_audit.diagnostics || []), ...(report.data_audit.parsing_warnings || [])]
        .map((item) => String(item || "").trim())
        .filter(Boolean),
    ),
  )

  const transcriptDocs = report.transcript.transcripts.map((doc, index) => {
    const label = transcriptLabelFromMetadata(doc.title, doc.published_date, index)
    return {
      id: doc.source_url || `transcript-${index + 1}`,
      label,
      source: doc.source,
      source_url: doc.source_url || undefined,
      title: doc.title || undefined,
      published_date: doc.published_date || undefined,
      sections: doc.sections.map((section) => ({
        section_type: section.section_type,
        speaker: section.speaker,
        speaker_role: section.speaker_role || undefined,
        text: section.text,
        order_index: section.order_index,
      })),
    }
  })

  return {
    ticker: report.ticker,
    company_name: report.overview.company_name || report.ticker,
    analysis_version: report.analysis_version,
    overall_sentiment_score: report.overall_sentiment_score,
    overall_sentiment_label: titleFromSnake(report.overall_sentiment_label),
    transcripts_found: report.transcripts_found,
    overview: {
      stance_label: titleFromSnake(report.overview.stance_label),
      executive_summary: report.overview.executive_summary,
      key_takeaways: report.overview.key_takeaways,
      metrics: report.overview.metrics.map((metric) => ({
        key: metric.key,
        label: metric.label,
        value: clamp(Math.round(toNumber(metric.value)), 0, 100),
      })),
    },
    transcript: {
      availability: report.transcript.availability,
      transcript_count_requested: report.transcript.transcript_count_requested,
      transcript_count_found: report.transcript.transcript_count_found,
      latest_summary: report.transcript.latest_summary,
      prepared_vs_qa_note: report.transcript.prepared_vs_qa_note,
      key_quotes: keyQuotes,
      qa_pressure_points: report.transcript.qa_pressure_points,
      speaker_analysis: speakerRows,
      speaker_rollup: report.transcript.speaker_rollup,
      quarter_status: report.transcript.quarter_status.map((quarter) => ({
        quarter: quarter.quarter,
        status: quarter.status,
      })),
      transcripts: transcriptDocs,
    },
    market_reaction: {
      balance_summary: report.market_reaction.balance_summary,
      news_count: report.market_reaction.news_count,
      social_count: report.market_reaction.social_count,
      news_items: report.market_reaction.news_items.map((item) => ({
        title: item.title,
        summary: item.summary,
        url: item.url,
        source: item.source || "Unknown",
        time_published: formatIsoTime(item.time_published),
        sentiment_score: item.sentiment_score,
        sentiment_label: normalizeSentimentLabel(item.sentiment_label),
      })),
      social_items: report.market_reaction.social_items.map((item) => ({
        source: item.source,
        title: item.title,
        body: item.body,
        excerpt: item.excerpt || item.body,
        url: item.url,
        subreddit: item.subreddit || undefined,
        created_utc: formatCreatedUtc(item.created_utc),
        relevance_score: item.relevance_score,
        sentiment_score: item.sentiment_score,
        sentiment_label: normalizeSentimentLabel(item.sentiment_label),
      })),
    },
    fundamentals: {
      operating_context: report.fundamentals_workspace.operating_context,
      metrics: report.fundamentals_workspace.metrics.slice(0, 12),
      analyst_signals: (report.fundamentals_workspace.analyst_signals || []).map((signal) => ({
        key: signal.key,
        label: signal.label,
        value: signal.value,
        tone: signal.tone,
        note: signal.note || undefined,
      })),
      quarterly_data: report.fundamentals_workspace.table.map((quarter) => ({
        quarter: quarter.quarter,
        revenue: quarter.revenue || 0,
        net_income: quarter.net_income || 0,
        reported_eps: quarter.reported_eps || 0,
        eps_estimate: quarter.eps_estimate || 0,
      })),
    },
    data_audit: {
      confidence_note: report.data_audit.confidence_note,
      normalization_mode: report.data_audit.normalization_mode,
      warnings: report.data_audit.warnings,
      notices: report.data_audit.notices || [],
      diagnostics: diagnosticsCompat,
      missing_items: report.data_audit.missing_items,
      parsing_warnings: diagnosticsCompat,
      source_counts: report.data_audit.source_counts,
      dedupe_counts: {
        pool: dedupePool,
        deduped: dedupeCount,
      },
      transcript_discovery: report.data_audit.transcript_discovery,
      task_breakdown: report.data_audit.task_breakdown,
      fundamentals_validation: {
        yahoo_source_used: report.data_audit.fundamentals_validation.yahoo_source_used,
        alpha_source_used: report.data_audit.fundamentals_validation.alpha_source_used,
        compared_fields: report.data_audit.fundamentals_validation.compared_fields,
        notes: report.data_audit.fundamentals_validation.notes,
        mismatches: report.data_audit.fundamentals_validation.mismatches.map((mismatch) => ({
          key: mismatch.key,
          yahoo_value:
            typeof mismatch.yahoo_value === "number" ? mismatch.yahoo_value.toFixed(4) : "n/a",
          alpha_value:
            typeof mismatch.alpha_value === "number" ? mismatch.alpha_value.toFixed(4) : "n/a",
          relative_diff_pct:
            typeof mismatch.relative_diff_pct === "number" ? mismatch.relative_diff_pct : 0,
          severity: mismatch.severity || "low",
          note: mismatch.note || "",
        })),
      },
    },
  }
}
