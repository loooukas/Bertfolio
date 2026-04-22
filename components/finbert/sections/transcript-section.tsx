"use client"

import { type KeyboardEvent, useMemo, useState } from "react"
import { ArrowUpDown, ChevronDown, Filter, Quote, User, Info, CheckCircle2, XCircle, AlertCircle } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip"

interface SpeakerAnalysis {
  speaker: string
  section_type: string
  sentiment_direction: number
  confidence: number
  evasiveness: number
  specificity: number
  forward_looking_strength: number
  risk_language_intensity: number
  topic_label: string
  mentions: number
}

interface SpeakerRollup {
  speaker: string
  mention_count: number
  avg_sentiment_direction: number
  avg_confidence: number
  avg_evasiveness: number
  dominant_topic: string
}

interface KeyQuote {
  speaker: string
  text: string
  sentiment: string
}

interface QuarterStatus {
  quarter: string
  status: "found" | "not_found" | "error"
}

interface TranscriptDocumentSection {
  section_type: "prepared_remarks" | "qa" | "other"
  speaker: string
  speaker_role?: string
  text: string
  order_index: number
}

interface TranscriptDocument {
  id: string
  label: string
  source: string
  source_url?: string
  title?: string
  published_date?: string
  sections: TranscriptDocumentSection[]
}

interface TranscriptData {
  availability: "available" | "partial" | "missing"
  transcript_count_requested: number
  transcript_count_found: number
  latest_summary: string
  prepared_vs_qa_note: string
  key_quotes: KeyQuote[]
  qa_pressure_points: string[]
  speaker_analysis: SpeakerAnalysis[]
  speaker_rollup: SpeakerRollup[]
  quarter_status: QuarterStatus[]
  transcripts: TranscriptDocument[]
}

interface TranscriptSectionProps {
  data: TranscriptData
  quoteColumns?: 1 | 2
  showCoverageDetails?: boolean
}

type SortDirection = "asc" | "desc"
type SortKey = "speaker" | "section_type" | "sentiment_direction" | "confidence" | "evasiveness" | "specificity" | "topic_label"

function sectionLabel(sectionType: string): string {
  if (sectionType === "prepared_remarks") return "Prepared"
  if (sectionType === "qa") return "Q&A"
  return "Other"
}

function metricHelpCopy(key: "sentiment" | "confidence" | "evasiveness" | "specificity") {
  if (key === "sentiment") {
    return "FinBERT directional tone score for each block. Positive is bullish tone, negative is bearish tone."
  }
  if (key === "confidence") {
    return "Higher when language is concrete and quantified, with fewer hedge terms like may, could, roughly, or at this time."
  }
  if (key === "evasiveness") {
    return "Higher when responses include more qualifiers, deferrals, and lower numeric specificity."
  }
  return "Higher when statements contain concrete details such as explicit numbers, KPI terms, and direct commitments."
}

function MetricHelp({ copy }: { copy: string }) {
  const activate = (event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault()
      event.currentTarget.click()
    }
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          role="button"
          tabIndex={0}
          onKeyDown={activate}
          aria-label="Metric details"
          className="inline-flex cursor-help items-center text-muted-foreground/70 hover:text-foreground"
        >
          <Info className="h-3.5 w-3.5" />
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs">{copy}</TooltipContent>
    </Tooltip>
  )
}

export function TranscriptSection({ data, quoteColumns = 2, showCoverageDetails = true }: TranscriptSectionProps) {
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>("all")
  const [selectedSection, setSelectedSection] = useState<string>("all")
  const [sortKey, setSortKey] = useState<SortKey>("speaker")
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc")
  const [activeSpeaker, setActiveSpeaker] = useState<string | null>(null)
  const [activeTranscriptId, setActiveTranscriptId] = useState<string | null>(null)

  const speakers = [...new Set(data.speaker_analysis.map((s) => s.speaker))]

  const filteredAnalysis = data.speaker_analysis.filter((item) => {
    if (selectedSpeaker !== "all" && item.speaker !== selectedSpeaker) return false
    if (selectedSection !== "all" && item.section_type !== selectedSection) return false
    return true
  })

  const sortedAnalysis = useMemo(() => {
    const sorted = [...filteredAnalysis]
    sorted.sort((a, b) => {
      const directionFactor = sortDirection === "asc" ? 1 : -1
      if (sortKey === "speaker" || sortKey === "section_type" || sortKey === "topic_label") {
        const left = sortKey === "section_type" ? sectionLabel(a.section_type) : String(a[sortKey])
        const right = sortKey === "section_type" ? sectionLabel(b.section_type) : String(b[sortKey])
        return left.localeCompare(right) * directionFactor
      }
      const left = Number(a[sortKey] || 0)
      const right = Number(b[sortKey] || 0)
      return (left - right) * directionFactor
    })
    return sorted
  }, [filteredAnalysis, sortDirection, sortKey])

  const speakerModalData = useMemo(() => {
    if (!activeSpeaker) return []
    const speakerKey = activeSpeaker.trim().toLowerCase()
    return data.transcripts.map((transcript) => ({
      transcript,
      mentions: transcript.sections.filter((section) => section.speaker.trim().toLowerCase() === speakerKey),
    }))
  }, [activeSpeaker, data.transcripts])

  const selectedTranscriptMentions = speakerModalData.find((item) => item.transcript.id === activeTranscriptId)
  const totalSpeakerMentions = speakerModalData.reduce((sum, item) => sum + item.mentions.length, 0)

  const preparedBlocks = data.speaker_analysis.filter((row) => row.section_type === "prepared_remarks").length
  const qaBlocks = data.speaker_analysis.filter((row) => row.section_type === "qa").length
  const avgConfidence = data.speaker_analysis.length > 0
    ? data.speaker_analysis.reduce((sum, row) => sum + row.confidence, 0) / data.speaker_analysis.length
    : 0
  const avgEvasiveness = data.speaker_analysis.length > 0
    ? data.speaker_analysis.reduce((sum, row) => sum + row.evasiveness, 0) / data.speaker_analysis.length
    : 0
  const coveragePct = data.transcript_count_requested > 0
    ? (data.transcript_count_found / data.transcript_count_requested) * 100
    : 0

  const openSpeakerModal = (speakerName: string) => {
    setActiveSpeaker(speakerName)
    const speakerKey = speakerName.trim().toLowerCase()
    const withCounts = data.transcripts.map((transcript) => ({
      id: transcript.id,
      count: transcript.sections.filter((section) => section.speaker.trim().toLowerCase() === speakerKey).length,
    }))
    const firstWithMentions = withCounts.find((item) => item.count > 0)
    setActiveTranscriptId(firstWithMentions?.id || withCounts[0]?.id || null)
  }

  const closeSpeakerModal = () => {
    setActiveSpeaker(null)
    setActiveTranscriptId(null)
  }

  const toggleSort = (nextSortKey: SortKey) => {
    if (sortKey === nextSortKey) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"))
      return
    }
    setSortKey(nextSortKey)
    setSortDirection("asc")
  }

  const renderSortIndicator = (key: SortKey) => {
    if (sortKey !== key) {
      return <ArrowUpDown className="h-3.5 w-3.5 text-muted-foreground/60" />
    }
    return <span className="text-[11px] leading-none text-muted-foreground">{sortDirection === "asc" ? "↑" : "↓"}</span>
  }

  const getStatusIcon = (status: string) => {
    if (status === "found") return <CheckCircle2 className="w-4 h-4 text-bullish" />
    if (status === "not_found") return <XCircle className="w-4 h-4 text-muted-foreground" />
    if (status === "error") return <AlertCircle className="w-4 h-4 text-destructive" />
    return null
  }

  const getSentimentColor = (score: number) => {
    if (score > 0.3) return "text-bullish"
    if (score < -0.3) return "text-bearish"
    return "text-neutral"
  }

  return (
    <TooltipProvider>
      <div className="space-y-8">
        <div className="flex flex-col gap-6 lg:flex-row">
          <div className="flex-1 rounded-xl border border-border bg-card p-6">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Transcript Coverage</h3>
              <Badge
                variant={data.availability === "available" ? "default" : "secondary"}
                className={data.availability === "available" ? "border-bullish/20 bg-bullish/10 text-bullish" : ""}
              >
                {data.availability === "available" ? "Full Coverage" : data.availability === "partial" ? "Partial" : "Missing"}
              </Badge>
            </div>
            <p className="mb-4 text-sm leading-relaxed text-foreground">{data.latest_summary}</p>
            {showCoverageDetails && (
              <>
                <div className="mb-4 h-2 overflow-hidden rounded-full bg-secondary">
                  <div className="h-full bg-bullish transition-all" style={{ width: `${Math.max(0, Math.min(100, coveragePct))}%` }} />
                </div>
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <div className="rounded-lg border border-border bg-secondary/40 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Coverage</div>
                    <div className="text-base font-semibold text-foreground">{data.transcript_count_found}/{data.transcript_count_requested}</div>
                  </div>
                  <div className="rounded-lg border border-border bg-secondary/40 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Speaker Blocks</div>
                    <div className="text-base font-semibold text-foreground">{data.speaker_analysis.length}</div>
                  </div>
                  <div className="rounded-lg border border-border bg-secondary/40 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Avg Confidence</div>
                    <div className="text-base font-semibold text-foreground">{avgConfidence.toFixed(1)}</div>
                  </div>
                  <div className="rounded-lg border border-border bg-secondary/40 p-3">
                    <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Avg Evasiveness</div>
                    <div className="text-base font-semibold text-foreground">{avgEvasiveness.toFixed(1)}</div>
                  </div>
                </div>
                <div className="mt-3 text-xs text-muted-foreground">
                  {data.prepared_vs_qa_note} Prepared blocks: {preparedBlocks}; Q&A blocks: {qaBlocks}.
                </div>
              </>
            )}
          </div>

          <div className="rounded-xl border border-border bg-card p-6 lg:w-64">
            <h3 className="mb-4 text-sm font-medium uppercase tracking-wider text-muted-foreground">Quarters Analyzed</h3>
            <div className="space-y-2">
              {data.quarter_status.map((q) => (
                <div key={q.quarter} className="flex items-center justify-between rounded-lg bg-secondary/50 px-3 py-2">
                  <span className="text-sm font-mono text-foreground">{q.quarter}</span>
                  {getStatusIcon(q.status)}
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-6">
          <div className="mb-4 flex items-center gap-2">
            <Quote className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-medium uppercase tracking-wider text-muted-foreground">Key Quotes</h3>
          </div>
          <div className={`grid gap-4 ${quoteColumns === 2 ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1"}`}>
            {data.key_quotes.map((quote, index) => (
              <div
                key={index}
                className={`rounded-lg border-l-2 p-4 ${
                  quote.sentiment === "bullish"
                    ? "border-l-bullish bg-bullish/5"
                    : quote.sentiment === "bearish"
                    ? "border-l-bearish bg-bearish/5"
                    : "border-l-neutral bg-neutral/5"
                }`}
              >
                <p className="mb-2 text-sm italic text-foreground">{`\"${quote.text}\"`}</p>
                <div className="flex items-center gap-2">
                  <User className="h-3 w-3 text-muted-foreground" />
                  <span className="text-xs font-medium text-muted-foreground">{quote.speaker}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-foreground">Speaker Analysis</h3>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {data.speaker_rollup.map((speaker) => (
              <div
                key={speaker.speaker}
                role="button"
                tabIndex={0}
                className="cursor-pointer rounded-xl border border-border bg-card p-5 text-left transition-all hover:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                onClick={() => openSpeakerModal(speaker.speaker)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault()
                    openSpeakerModal(speaker.speaker)
                  }
                }}
              >
                <div className="mb-4 flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary">
                      <User className="h-5 w-5 text-muted-foreground" />
                    </div>
                    <div>
                      <div className="font-medium text-foreground">{speaker.speaker}</div>
                      <div className="text-xs text-muted-foreground">{speaker.mention_count} mentions • {speaker.dominant_topic}</div>
                    </div>
                  </div>
                  <ChevronDown className="h-5 w-5 text-muted-foreground" />
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
                      <span>Sentiment</span>
                      <MetricHelp copy={metricHelpCopy("sentiment")} />
                    </div>
                    <div className={`text-lg font-semibold ${getSentimentColor(speaker.avg_sentiment_direction)}`}>
                      {speaker.avg_sentiment_direction > 0 ? "+" : ""}
                      {(speaker.avg_sentiment_direction * 100).toFixed(0)}
                    </div>
                  </div>
                  <div>
                    <div className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
                      <span>Confidence</span>
                      <MetricHelp copy={metricHelpCopy("confidence")} />
                    </div>
                    <div className="text-lg font-semibold text-foreground">{speaker.avg_confidence}</div>
                  </div>
                  <div>
                    <div className="mb-1 flex items-center gap-1 text-xs text-muted-foreground">
                      <span>Evasiveness</span>
                      <MetricHelp copy={metricHelpCopy("evasiveness")} />
                    </div>
                    <div className={`text-lg font-semibold ${speaker.avg_evasiveness > 30 ? "text-bearish" : "text-foreground"}`}>
                      {speaker.avg_evasiveness}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="space-y-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h4 className="text-sm font-medium text-foreground">Speaker Block Analysis</h4>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                  <Filter className="h-4 w-4 text-muted-foreground" />
                  <span className="text-sm text-muted-foreground">Filter:</span>
                </div>
                <Select value={selectedSpeaker} onValueChange={setSelectedSpeaker}>
                  <SelectTrigger className="h-9 w-40">
                    <SelectValue placeholder="Speaker" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Speakers</SelectItem>
                    {speakers.map((speaker) => (
                      <SelectItem key={speaker} value={speaker}>{speaker}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={selectedSection} onValueChange={setSelectedSection}>
                  <SelectTrigger className="h-9 w-40">
                    <SelectValue placeholder="Section" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Sections</SelectItem>
                    <SelectItem value="prepared_remarks">Prepared Remarks</SelectItem>
                    <SelectItem value="qa">Q&A</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="overflow-hidden rounded-xl border border-border">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border bg-secondary/50">
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("speaker")}>
                          <span>Speaker</span>
                          {renderSortIndicator("speaker")}
                        </button>
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("section_type")}>
                          <span>Section</span>
                          {renderSortIndicator("section_type")}
                        </button>
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("sentiment_direction")}>
                          <span>Sentiment</span>
                          <MetricHelp copy={metricHelpCopy("sentiment")} />
                          {renderSortIndicator("sentiment_direction")}
                        </button>
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("confidence")}>
                          <span>Confidence</span>
                          <MetricHelp copy={metricHelpCopy("confidence")} />
                          {renderSortIndicator("confidence")}
                        </button>
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("evasiveness")}>
                          <span>Evasiveness</span>
                          <MetricHelp copy={metricHelpCopy("evasiveness")} />
                          {renderSortIndicator("evasiveness")}
                        </button>
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("specificity")}>
                          <span>Specificity</span>
                          <MetricHelp copy={metricHelpCopy("specificity")} />
                          {renderSortIndicator("specificity")}
                        </button>
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                        <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("topic_label")}>
                          <span>Topic</span>
                          {renderSortIndicator("topic_label")}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {sortedAnalysis.map((item, index) => (
                      <tr key={`${item.speaker}-${item.section_type}-${index}`} className="bg-card transition-colors hover:bg-secondary/30">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary">
                              <User className="h-3 w-3 text-muted-foreground" />
                            </div>
                            <span className="text-sm font-medium text-foreground">{item.speaker}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant="outline" className="text-xs">{sectionLabel(item.section_type)}</Badge>
                        </td>
                        <td className="px-4 py-3">
                          <span className={`text-sm font-mono font-medium ${getSentimentColor(item.sentiment_direction)}`}>
                            {item.sentiment_direction > 0 ? "+" : ""}
                            {(item.sentiment_direction * 100).toFixed(0)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Progress value={item.confidence} className="h-1.5 w-16" />
                            <span className="text-sm text-muted-foreground">{item.confidence}</span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Progress value={item.evasiveness} className="h-1.5 w-16" />
                            <span className={`text-sm ${item.evasiveness > 30 ? "text-bearish" : "text-muted-foreground"}`}>
                              {item.evasiveness}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-muted-foreground">{item.specificity}</span>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-muted-foreground">{item.topic_label}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>

        <Dialog open={!!activeSpeaker} onOpenChange={(open) => (!open ? closeSpeakerModal() : undefined)}>
          <DialogContent className="max-h-[85vh] max-w-4xl overflow-hidden">
            <DialogHeader>
              <DialogTitle className="text-lg">{activeSpeaker ? `${activeSpeaker} Mentions` : "Speaker Mentions"}</DialogTitle>
              <DialogDescription>{totalSpeakerMentions} total mentions across transcripts.</DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {speakerModalData.map((item) => {
                  const mentionCount = item.mentions.length
                  const selected = item.transcript.id === activeTranscriptId
                  return (
                    <button
                      key={item.transcript.id}
                      type="button"
                      disabled={mentionCount === 0}
                      onClick={() => setActiveTranscriptId(item.transcript.id)}
                      className={`rounded-md border px-3 py-1.5 text-xs transition-colors ${
                        selected
                          ? "border-primary bg-primary/10 text-foreground"
                          : "border-border bg-secondary/30 text-muted-foreground"
                      } ${mentionCount === 0 ? "cursor-not-allowed opacity-50" : "hover:border-ring hover:text-foreground"}`}
                    >
                      {item.transcript.label} ({mentionCount})
                    </button>
                  )
                })}
              </div>

              <div className="max-h-[52vh] overflow-y-auto rounded-lg border border-border bg-card p-4">
                {!selectedTranscriptMentions || selectedTranscriptMentions.mentions.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No mentions for this speaker in the selected transcript.</p>
                ) : (
                  <div className="space-y-3">
                    {selectedTranscriptMentions.mentions.map((mention) => (
                      <div key={`${mention.order_index}-${mention.section_type}`} className="rounded-lg border border-border p-3">
                        <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
                          <Badge variant="outline" className="text-[11px]">{sectionLabel(mention.section_type)}</Badge>
                          <span>
                            {selectedTranscriptMentions.transcript.label} • Segment {mention.order_index + 1}
                          </span>
                        </div>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">{mention.text}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </TooltipProvider>
  )
}
