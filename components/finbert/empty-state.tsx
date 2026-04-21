"use client"

import { BarChart3, FileText, TrendingUp, Shield } from "lucide-react"

const features = [
  {
    icon: FileText,
    title: "Transcript Analysis",
    description: "Deep NLP analysis of earnings call transcripts with speaker-level sentiment scoring.",
  },
  {
    icon: TrendingUp,
    title: "Market Reaction",
    description: "Curated news and social sentiment around earnings events with relevance filtering.",
  },
  {
    icon: BarChart3,
    title: "Fundamentals Context",
    description: "Operating metrics and quarterly trends to ground sentiment in business performance.",
  },
  {
    icon: Shield,
    title: "Data Audit",
    description: "Full transparency into data quality, sources, and pipeline reliability.",
  },
]

export function EmptyState() {
  return (
    <div className="py-12">
      {/* Feature Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {features.map((feature) => (
          <div
            key={feature.title}
            className="group p-6 rounded-xl border border-border bg-card hover:bg-secondary/50 transition-colors"
          >
            <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-secondary mb-4">
              <feature.icon className="w-5 h-5 text-foreground" />
            </div>
            <h3 className="text-sm font-semibold text-foreground mb-2">
              {feature.title}
            </h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {feature.description}
            </p>
          </div>
        ))}
      </div>

      {/* How it Works */}
      <div className="mt-16 max-w-3xl mx-auto">
        <h2 className="text-lg font-semibold text-foreground text-center mb-8">
          How it works
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {[
            {
              step: "01",
              title: "Enter Ticker",
              description: "Input any stock ticker to begin analysis.",
            },
            {
              step: "02",
              title: "Pipeline Runs",
              description: "We gather transcripts, news, social, and fundamentals data.",
            },
            {
              step: "03",
              title: "Get Insights",
              description: "Review scored signals with full source transparency.",
            },
          ].map((item) => (
            <div key={item.step} className="text-center">
              <div className="text-3xl font-bold text-muted-foreground/30 mb-2">
                {item.step}
              </div>
              <h3 className="text-sm font-semibold text-foreground mb-1">
                {item.title}
              </h3>
              <p className="text-sm text-muted-foreground">
                {item.description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Bottom CTA */}
      <div className="mt-16 text-center">
        <p className="text-sm text-muted-foreground">
          Enter a ticker symbol above to start your first analysis
        </p>
      </div>
    </div>
  )
}
