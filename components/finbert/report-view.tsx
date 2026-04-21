"use client"

import { useEffect, useState } from "react"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { OverviewSection } from "./sections/overview-section"
import { TranscriptSection } from "./sections/transcript-section"
import { MarketReactionSection } from "./sections/market-reaction-section"
import { FundamentalsSection } from "./sections/fundamentals-section"
import { DataAuditSection } from "./sections/data-audit-section"
import { FileText, BarChart3, TrendingUp, PieChart, Shield } from "lucide-react"
import type { UIReportModel } from "@/lib/finbert/types"
import type { UISettings } from "@/lib/finbert/ui-settings"

interface ReportViewProps {
  report: UIReportModel
  settings: UISettings
}

const tabs = [
  { id: "overview", label: "Overview", icon: PieChart },
  { id: "transcript", label: "Transcript", icon: FileText },
  { id: "market", label: "Market Reaction", icon: TrendingUp },
  { id: "fundamentals", label: "Fundamentals", icon: BarChart3 },
  { id: "audit", label: "Data Audit", icon: Shield },
]

export function ReportView({ report, settings }: ReportViewProps) {
  const [activeTab, setActiveTab] = useState("overview")

  useEffect(() => {
    if (settings.auto_open_audit_on_warnings && report.data_audit.warnings.length > 0) {
      setActiveTab("audit")
      return
    }
    setActiveTab("overview")
  }, [report, settings.auto_open_audit_on_warnings])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 border-b border-border pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-3">
            <h2 className="text-2xl font-bold text-foreground">{report.company_name}</h2>
            <span className="rounded bg-secondary px-2 py-0.5 text-sm font-mono text-muted-foreground">{report.ticker}</span>
          </div>
          <p className="text-sm text-muted-foreground">
            Analysis v{report.analysis_version} • {report.transcripts_found} transcripts analyzed
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div
            className={`rounded-lg px-4 py-2 ${
              report.overall_sentiment_score > 0.3
                ? "border border-bullish/20 bg-bullish/10"
                : report.overall_sentiment_score < -0.3
                  ? "border border-bearish/20 bg-bearish/10"
                  : "border border-neutral/20 bg-neutral/10"
            }`}
          >
            <div className="mb-0.5 text-xs text-muted-foreground">Overall Signal</div>
            <div
              className={`text-lg font-semibold ${
                report.overall_sentiment_score > 0.3
                  ? "text-bullish"
                  : report.overall_sentiment_score < -0.3
                    ? "text-bearish"
                    : "text-neutral"
              }`}
            >
              {report.overall_sentiment_label}
            </div>
          </div>
          <div className="text-right">
            <div className="mb-0.5 text-xs text-muted-foreground">Score</div>
            <div className="text-2xl font-mono font-bold text-foreground">
              {report.overall_sentiment_score > 0 ? "+" : ""}
              {(report.overall_sentiment_score * 100).toFixed(0)}
            </div>
          </div>
        </div>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList className="h-auto w-full flex-wrap justify-start gap-1 bg-secondary/50 p-1">
          {tabs.map((tab) => (
            <TabsTrigger
              key={tab.id}
              value={tab.id}
              className="gap-2 px-4 py-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
            >
              <tab.icon className="h-4 w-4" />
              <span className="hidden sm:inline">{tab.label}</span>
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="overview" className="mt-6">
          <OverviewSection data={report.overview} />
        </TabsContent>

        <TabsContent value="transcript" className="mt-6">
          <TranscriptSection
            data={report.transcript}
            quoteColumns={settings.quote_columns}
            showCoverageDetails={settings.show_transcript_diagnostics}
          />
        </TabsContent>

        <TabsContent value="market" className="mt-6">
          <MarketReactionSection data={report.market_reaction} gridColumns={settings.market_columns} />
        </TabsContent>

        <TabsContent value="fundamentals" className="mt-6">
          <FundamentalsSection data={report.fundamentals} />
        </TabsContent>

        <TabsContent value="audit" className="mt-6">
          <DataAuditSection data={report.data_audit} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
