"use client"

import { useMemo, useState } from "react"
import {
  ArrowUpDown,
  ChevronDown,
  Filter,
  Quote,
  User,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Progress } from "@/components/ui/progress"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

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
type SortKey =
  | "speaker"
  | "section_type"
  | "sentiment_direction"
  | "confidence"
  | "evasiveness"
  | "specificity"
  | "topic_label"

function sectionLabel(sectionType: string): string {
  if (sectionType === "prepared_remarks") {
    return "Prepared"
  }
  if (sectionType === "qa") {
    return "Q&A"
  }
  return "Other"
}

export function TranscriptSection({
  data,
  quoteColumns = 2,
  showCoverageDetails = true,
}: TranscriptSectionProps) {
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
    if (!activeSpeaker) {
      return []
    }
    const speakerKey = activeSpeaker.trim().toLowerCase()
    return data.transcripts.map((transcript) => {
      const mentions = transcript.sections.filter(
        (section) => section.speaker.trim().toLowerCase() === speakerKey,
      )
      return {
        transcript,
        mentions,
      }
    })
  }, [activeSpeaker, data.transcripts])

  const selectedTranscriptMentions = speakerModalData.find(
    (item) => item.transcript.id === activeTranscriptId,
  )

  const totalSpeakerMentions = speakerModalData.reduce((sum, item) => sum + item.mentions.length, 0)
  const preparedBlocks = data.speaker_analysis.filter((row) => row.section_type === "prepared_remarks").length
  const qaBlocks = data.speaker_analysis.filter((row) => row.section_type === "qa").length
  const avgConfidence =
    data.speaker_analysis.length > 0
      ? data.speaker_analysis.reduce((sum, row) => sum + row.confidence, 0) / data.speaker_analysis.length
      : 0
  const avgEvasiveness =
    data.speaker_analysis.length > 0
      ? data.speaker_analysis.reduce((sum, row) => sum + row.evasiveness, 0) / data.speaker_analysis.length
      : 0
  const coveragePct =
    data.transcript_count_requested > 0
      ? (data.transcript_count_found / data.transcript_count_requested) * 100
      : 0

  const openSpeakerModal = (speakerName: string) => {
    setActiveSpeaker(speakerName)
    const speakerKey = speakerName.trim().toLowerCase()
    const withCounts = data.transcripts.map((transcript) => ({
      id: transcript.id,
      count: transcript.sections.filter(
        (section) => section.speaker.trim().toLowerCase() === speakerKey,
      ).length,
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
    return (
      <span className="text-[11px] leading-none text-muted-foreground">
        {sortDirection === "asc" ? "↑" : "↓"}
      </span>
    )
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "found":
        return <CheckCircle2 className="w-4 h-4 text-bullish" />
      case "not_found":
        return <XCircle className="w-4 h-4 text-muted-foreground" />
      case "error":
        return <AlertCircle className="w-4 h-4 text-destructive" />
      default:
        return null
    }
  }

  const getSentimentColor = (score: number) => {
    if (score > 0.3) return "text-bullish"
    if (score < -0.3) return "text-bearish"
    return "text-neutral"
  }

  return (
    <div className="space-y-8">
      {/* Availability & Quarter Status */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Coverage Summary */}
        <div className="flex-1 p-6 rounded-xl bg-card border border-border">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
              Transcript Coverage
            </h3>
            <Badge
              variant={data.availability === "available" ? "default" : "secondary"}
              className={data.availability === "available" ? "bg-bullish/10 text-bullish border-bullish/20" : ""}
            >
              {data.availability === "available" ? "Full Coverage" : data.availability === "partial" ? "Partial" : "Missing"}
            </Badge>
          </div>
          <p className="text-sm text-foreground leading-relaxed mb-4">{data.latest_summary}</p>
          {showCoverageDetails && (
            <>
              <div className="mb-4 h-2 overflow-hidden rounded-full bg-secondary">
                <div
                  className="h-full bg-bullish transition-all"
                  style={{ width: `${Math.max(0, Math.min(100, coveragePct))}%` }}
                />
              </div>
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <div className="rounded-lg border border-border bg-secondary/40 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Coverage</div>
                  <div className="text-base font-semibold text-foreground">
                    {data.transcript_count_found}/{data.transcript_count_requested}
                  </div>
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

        {/* Quarter Grid */}
        <div className="lg:w-64 p-6 rounded-xl bg-card border border-border">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
            Quarters Analyzed
          </h3>
          <div className="space-y-2">
            {data.quarter_status.map((q) => (
              <div key={q.quarter} className="flex items-center justify-between py-2 px-3 rounded-lg bg-secondary/50">
                <span className="text-sm font-mono text-foreground">{q.quarter}</span>
                {getStatusIcon(q.status)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Key Quotes */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <div className="flex items-center gap-2 mb-4">
          <Quote className="w-4 h-4 text-muted-foreground" />
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Key Quotes</h3>
        </div>
        <div className={`grid gap-4 ${quoteColumns === 2 ? "grid-cols-1 xl:grid-cols-2" : "grid-cols-1"}`}>
          {data.key_quotes.map((quote, index) => (
            <div
              key={index}
              className={`p-4 rounded-lg border-l-2 ${
                quote.sentiment === "bullish"
                  ? "border-l-bullish bg-bullish/5"
                  : quote.sentiment === "bearish"
                    ? "border-l-bearish bg-bearish/5"
                    : "border-l-neutral bg-neutral/5"
              }`}
            >
              <p className="text-sm text-foreground italic mb-2">{`"${quote.text}"`}</p>
              <div className="flex items-center gap-2">
                <User className="w-3 h-3 text-muted-foreground" />
                <span className="text-xs font-medium text-muted-foreground">{quote.speaker}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Speaker Analysis */}
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-foreground">Speaker Analysis</h3>

        {/* Speaker Rollup Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.speaker_rollup.map((speaker) => (
            <button
              key={speaker.speaker}
              type="button"
              className="p-5 rounded-xl bg-card border border-border transition-all text-left hover:border-ring"
              onClick={() => openSpeakerModal(speaker.speaker)}
            >
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-secondary flex items-center justify-center">
                    <User className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <div>
                    <div className="font-medium text-foreground">{speaker.speaker}</div>
                    <div className="text-xs text-muted-foreground">
                      {speaker.mention_count} mentions • {speaker.dominant_topic}
                    </div>
                  </div>
                </div>
                <ChevronDown className="w-5 h-5 text-muted-foreground" />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Sentiment</div>
                  <div className={`text-lg font-semibold ${getSentimentColor(speaker.avg_sentiment_direction)}`}>
                    {speaker.avg_sentiment_direction > 0 ? "+" : ""}
                    {(speaker.avg_sentiment_direction * 100).toFixed(0)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Confidence</div>
                  <div className="text-lg font-semibold text-foreground">{speaker.avg_confidence}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Evasiveness</div>
                  <div
                    className={`text-lg font-semibold ${
                      speaker.avg_evasiveness > 30 ? "text-bearish" : "text-foreground"
                    }`}
                  >
                    {speaker.avg_evasiveness}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>

        {/* Detailed Analysis Table */}
        <div className="space-y-3">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <h4 className="text-sm font-medium text-foreground">Speaker Block Analysis</h4>
            <div className="flex flex-wrap items-center gap-3">
              <div className="flex items-center gap-2">
                <Filter className="w-4 h-4 text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Filter:</span>
              </div>
              <Select value={selectedSpeaker} onValueChange={setSelectedSpeaker}>
                <SelectTrigger className="w-40 h-9">
                  <SelectValue placeholder="Speaker" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Speakers</SelectItem>
                  {speakers.map((speaker) => (
                    <SelectItem key={speaker} value={speaker}>
                      {speaker}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={selectedSection} onValueChange={setSelectedSection}>
                <SelectTrigger className="w-40 h-9">
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

          <div className="rounded-xl border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="bg-secondary/50 border-b border-border">
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("speaker")}>
                        <span>Speaker</span>
                        {renderSortIndicator("speaker")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("section_type")}>
                        <span>Section</span>
                        {renderSortIndicator("section_type")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <button
                        type="button"
                        className="inline-flex items-center gap-1"
                        onClick={() => toggleSort("sentiment_direction")}
                      >
                        <span>Sentiment</span>
                        {renderSortIndicator("sentiment_direction")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("confidence")}>
                        <span>Confidence</span>
                        {renderSortIndicator("confidence")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("evasiveness")}>
                        <span>Evasiveness</span>
                        {renderSortIndicator("evasiveness")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("specificity")}>
                        <span>Specificity</span>
                        {renderSortIndicator("specificity")}
                      </button>
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                      <button type="button" className="inline-flex items-center gap-1" onClick={() => toggleSort("topic_label")}>
                        <span>Topic</span>
                        {renderSortIndicator("topic_label")}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {sortedAnalysis.map((item, index) => (
                    <tr key={index} className="bg-card hover:bg-secondary/30 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-secondary flex items-center justify-center">
                            <User className="w-3 h-3 text-muted-foreground" />
                          </div>
                          <span className="text-sm font-medium text-foreground">{item.speaker}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="outline" className="text-xs">
                          {sectionLabel(item.section_type)}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`text-sm font-mono font-medium ${getSentimentColor(item.sentiment_direction)}`}>
                          {item.sentiment_direction > 0 ? "+" : ""}
                          {(item.sentiment_direction * 100).toFixed(0)}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Progress value={item.confidence} className="w-16 h-1.5" />
                          <span className="text-sm text-muted-foreground">{item.confidence}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Progress value={item.evasiveness} className="w-16 h-1.5" />
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
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="text-lg">
              {activeSpeaker ? `${activeSpeaker} Mentions` : "Speaker Mentions"}
            </DialogTitle>
            <DialogDescription>
              {totalSpeakerMentions} total mentions across transcripts.
            </DialogDescription>
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
                        <Badge variant="outline" className="text-[11px]">
                          {sectionLabel(mention.section_type)}
                        </Badge>
                        <span>
                          {selectedTranscriptMentions.transcript.label} • Segment {mention.order_index + 1}
                        </span>
                      </div>
                      <p className="text-sm leading-relaxed text-foreground whitespace-pre-wrap">{mention.text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
