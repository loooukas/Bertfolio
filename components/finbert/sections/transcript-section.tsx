"use client"

import { useState } from "react"
import { User, MessageSquare, CheckCircle2, XCircle, AlertCircle, ChevronDown, Quote, Filter } from "lucide-react"
import { Badge } from "@/components/ui/badge"
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
}

interface TranscriptSectionProps {
  data: TranscriptData
}

export function TranscriptSection({ data }: TranscriptSectionProps) {
  const [selectedSpeaker, setSelectedSpeaker] = useState<string>("all")
  const [selectedSection, setSelectedSection] = useState<string>("all")
  const [expandedSpeaker, setExpandedSpeaker] = useState<string | null>(null)

  const speakers = [...new Set(data.speaker_analysis.map((s) => s.speaker))]
  
  const filteredAnalysis = data.speaker_analysis.filter((item) => {
    if (selectedSpeaker !== "all" && item.speaker !== selectedSpeaker) return false
    if (selectedSection !== "all" && item.section_type !== selectedSection) return false
    return true
  })

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
          <p className="text-sm text-foreground leading-relaxed mb-4">
            {data.latest_summary}
          </p>
          <div className="text-xs text-muted-foreground italic">
            {data.prepared_vs_qa_note}
          </div>
        </div>

        {/* Quarter Grid */}
        <div className="lg:w-64 p-6 rounded-xl bg-card border border-border">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
            Quarters Analyzed
          </h3>
          <div className="space-y-2">
            {data.quarter_status.map((q) => (
              <div 
                key={q.quarter}
                className="flex items-center justify-between py-2 px-3 rounded-lg bg-secondary/50"
              >
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
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            Key Quotes
          </h3>
        </div>
        <div className="space-y-4">
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
              <p className="text-sm text-foreground italic mb-2">
                {`"${quote.text}"`}
              </p>
              <div className="flex items-center gap-2">
                <User className="w-3 h-3 text-muted-foreground" />
                <span className="text-xs font-medium text-muted-foreground">{quote.speaker}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Q&A Pressure Points */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <div className="flex items-center gap-2 mb-4">
          <MessageSquare className="w-4 h-4 text-muted-foreground" />
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
            Q&A Pressure Points
          </h3>
        </div>
        <div className="flex flex-wrap gap-2">
          {data.qa_pressure_points.map((point, index) => (
            <Badge key={index} variant="outline" className="text-sm py-1.5 px-3">
              {point}
            </Badge>
          ))}
        </div>
      </div>

      {/* Speaker Analysis */}
      <div className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <h3 className="text-lg font-semibold text-foreground">Speaker Analysis</h3>
          
          {/* Filters */}
          <div className="flex items-center gap-3">
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
                  <SelectItem key={speaker} value={speaker}>{speaker}</SelectItem>
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

        {/* Speaker Rollup Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.speaker_rollup.map((speaker) => (
            <div
              key={speaker.speaker}
              className={`p-5 rounded-xl bg-card border border-border transition-all cursor-pointer ${
                expandedSpeaker === speaker.speaker ? "ring-2 ring-primary/20" : "hover:border-ring"
              }`}
              onClick={() => setExpandedSpeaker(expandedSpeaker === speaker.speaker ? null : speaker.speaker)}
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
                <ChevronDown className={`w-5 h-5 text-muted-foreground transition-transform ${
                  expandedSpeaker === speaker.speaker ? "rotate-180" : ""
                }`} />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Sentiment</div>
                  <div className={`text-lg font-semibold ${getSentimentColor(speaker.avg_sentiment_direction)}`}>
                    {speaker.avg_sentiment_direction > 0 ? "+" : ""}{(speaker.avg_sentiment_direction * 100).toFixed(0)}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Confidence</div>
                  <div className="text-lg font-semibold text-foreground">{speaker.avg_confidence}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Evasiveness</div>
                  <div className={`text-lg font-semibold ${speaker.avg_evasiveness > 30 ? "text-bearish" : "text-foreground"}`}>
                    {speaker.avg_evasiveness}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Detailed Analysis Table */}
        <div className="rounded-xl border border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-secondary/50 border-b border-border">
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Speaker</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Section</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Sentiment</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Confidence</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Evasiveness</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Specificity</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Topic</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredAnalysis.map((item, index) => (
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
                        {item.section_type === "prepared_remarks" ? "Prepared" : "Q&A"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-sm font-mono font-medium ${getSentimentColor(item.sentiment_direction)}`}>
                        {item.sentiment_direction > 0 ? "+" : ""}{(item.sentiment_direction * 100).toFixed(0)}
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
  )
}
