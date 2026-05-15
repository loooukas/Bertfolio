"use client"

import Link from "next/link"
import { ArrowLeft, BarChart3, Activity, TrendingUp, Users } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  LineChart,
  Line,
  Tooltip,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
} from "recharts"

// Synthetic speaker profile data
const speakerProfileData = [
  { speaker: "Tim Cook", confidence: 85, evasiveness: 18, sentiment: 72, specificity: 65 },
  { speaker: "Kevan Parekh", confidence: 82, evasiveness: 12, sentiment: 65, specificity: 88 },
  { speaker: "Suhasini", confidence: 78, evasiveness: 22, sentiment: 58, specificity: 72 },
  { speaker: "Amit", confidence: 75, evasiveness: 28, sentiment: 52, specificity: 68 },
  { speaker: "David", confidence: 72, evasiveness: 35, sentiment: 48, specificity: 62 },
  { speaker: "Wamsi", confidence: 68, evasiveness: 42, sentiment: 45, specificity: 58 },
]

// Synthetic fundamentals trend data
const fundamentalsTrendData = [
  { quarter: "2025-Q1", revenue: 90.8, net_income: 23.6, eps: 1.52, eps_estimate: 1.48 },
  { quarter: "2025-Q2", revenue: 85.8, net_income: 21.4, eps: 1.38, eps_estimate: 1.35 },
  { quarter: "2025-Q3", revenue: 89.5, net_income: 22.8, eps: 1.47, eps_estimate: 1.42 },
  { quarter: "2025-Q4", revenue: 94.9, net_income: 24.2, eps: 1.56, eps_estimate: 1.52 },
  { quarter: "2026-Q1", revenue: 124.3, net_income: 33.9, eps: 2.18, eps_estimate: 2.05 },
  { quarter: "2026-Q2", revenue: 98.5, net_income: 25.8, eps: 1.66, eps_estimate: 1.62 },
]

// Radar chart data for speaker comparison
const radarData = [
  { metric: "Confidence", "Tim Cook": 85, "Kevan Parekh": 82 },
  { metric: "Specificity", "Tim Cook": 65, "Kevan Parekh": 88 },
  { metric: "Forward Looking", "Tim Cook": 78, "Kevan Parekh": 62 },
  { metric: "Sentiment", "Tim Cook": 72, "Kevan Parekh": 65 },
  { metric: "Risk Awareness", "Tim Cook": 22, "Kevan Parekh": 28 },
]

// Sentiment distribution data
const sentimentDistribution = [
  { range: "Strong Bear", count: 3, fill: "var(--bearish)" },
  { range: "Mild Bear", count: 8, fill: "var(--bearish)" },
  { range: "Neutral", count: 12, fill: "var(--neutral)" },
  { range: "Mild Bull", count: 18, fill: "var(--bullish)" },
  { range: "Strong Bull", count: 9, fill: "var(--bullish)" },
]

export default function ChartsTestPage() {
  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-4">
              <Link href="/">
                <Button variant="ghost" size="sm" className="gap-2">
                  <ArrowLeft className="w-4 h-4" />
                  Back to Analysis
                </Button>
              </Link>
              <div className="h-6 w-px bg-border" />
              <div className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">Charts Test Utility</span>
              </div>
            </div>
            <Badge variant="outline" className="text-xs">
              Synthetic Data
            </Badge>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-foreground mb-2">Chart Rendering Test</h1>
          <p className="text-muted-foreground">
            Verify chart behavior with synthetic data independent of backend analysis runtime.
          </p>
        </div>

        <div className="space-y-8">
          {/* Speaker Profile Bar Chart */}
          <section className="p-6 rounded-xl bg-card border border-border">
            <div className="flex items-center gap-2 mb-6">
              <Users className="w-5 h-5 text-muted-foreground" />
              <h2 className="text-lg font-semibold text-foreground">Speaker Confidence & Evasiveness</h2>
            </div>
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={speakerProfileData} layout="vertical" barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={true} vertical={false} />
                  <XAxis 
                    type="number" 
                    domain={[0, 100]}
                    tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                    axisLine={{ stroke: 'var(--border)' }}
                    tickLine={false}
                  />
                  <YAxis 
                    type="category" 
                    dataKey="speaker" 
                    width={100}
                    tick={{ fill: 'var(--foreground)', fontSize: 12 }}
                    axisLine={{ stroke: 'var(--border)' }}
                    tickLine={false}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
                            <p className="text-sm font-medium text-foreground mb-2">{label}</p>
                            {payload.map((entry, index) => (
                              <p key={index} className="text-sm text-muted-foreground">
                                {entry.name}: <span className="font-mono text-foreground">{entry.value}</span>
                              </p>
                            ))}
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                  <Bar 
                    dataKey="confidence" 
                    name="Confidence" 
                    fill="var(--bullish)" 
                    radius={[0, 4, 4, 0]}
                  />
                  <Bar 
                    dataKey="evasiveness" 
                    name="Evasiveness" 
                    fill="var(--bearish)" 
                    radius={[0, 4, 4, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          {/* Fundamentals Trend Charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Revenue Trend */}
            <section className="p-6 rounded-xl bg-card border border-border">
              <div className="flex items-center gap-2 mb-6">
                <TrendingUp className="w-5 h-5 text-muted-foreground" />
                <h2 className="text-lg font-semibold text-foreground">Revenue Trend ($B)</h2>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={fundamentalsTrendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis 
                      dataKey="quarter" 
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                      axisLine={{ stroke: 'var(--border)' }}
                      tickLine={false}
                    />
                    <YAxis 
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                      axisLine={{ stroke: 'var(--border)' }}
                      tickLine={false}
                      tickFormatter={(value) => `$${value}`}
                    />
                    <Tooltip
                      content={({ active, payload, label }) => {
                        if (active && payload && payload.length) {
                          return (
                            <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
                              <p className="text-sm font-medium text-foreground mb-2">{label}</p>
                              <p className="text-sm text-muted-foreground">
                                Revenue: <span className="font-mono text-foreground">${payload[0].value}B</span>
                              </p>
                            </div>
                          )
                        }
                        return null
                      }}
                    />
                    <Bar 
                      dataKey="revenue" 
                      fill="var(--chart-1)" 
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>

            {/* EPS vs Estimate */}
            <section className="p-6 rounded-xl bg-card border border-border">
              <div className="flex items-center gap-2 mb-6">
                <Activity className="w-5 h-5 text-muted-foreground" />
                <h2 className="text-lg font-semibold text-foreground">EPS vs Estimate</h2>
              </div>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={fundamentalsTrendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                    <XAxis 
                      dataKey="quarter" 
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                      axisLine={{ stroke: 'var(--border)' }}
                      tickLine={false}
                    />
                    <YAxis 
                      tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                      axisLine={{ stroke: 'var(--border)' }}
                      tickLine={false}
                      tickFormatter={(value) => `$${value}`}
                      domain={['auto', 'auto']}
                    />
                    <Tooltip
                      content={({ active, payload, label }) => {
                        if (active && payload && payload.length) {
                          return (
                            <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
                              <p className="text-sm font-medium text-foreground mb-2">{label}</p>
                              {payload.map((entry, index) => (
                                <p key={index} className="text-sm text-muted-foreground">
                                  {entry.name}: <span className="font-mono text-foreground">${Number(entry.value).toFixed(2)}</span>
                                </p>
                              ))}
                            </div>
                          )
                        }
                        return null
                      }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="eps" 
                      name="Reported EPS"
                      stroke="var(--bullish)" 
                      strokeWidth={2}
                      dot={{ fill: 'var(--bullish)', strokeWidth: 0, r: 4 }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="eps_estimate" 
                      name="Estimate"
                      stroke="var(--muted-foreground)" 
                      strokeWidth={2}
                      strokeDasharray="5 5"
                      dot={{ fill: 'var(--muted-foreground)', strokeWidth: 0, r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>

          {/* Radar Chart - Speaker Comparison */}
          <section className="p-6 rounded-xl bg-card border border-border">
            <h2 className="text-lg font-semibold text-foreground mb-6">Speaker Comparison Radar</h2>
            <div className="h-80 flex items-center justify-center">
              <ResponsiveContainer width="100%" height="100%">
                <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                  <PolarGrid stroke="var(--border)" />
                  <PolarAngleAxis 
                    dataKey="metric" 
                    tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                  />
                  <PolarRadiusAxis 
                    angle={90} 
                    domain={[0, 100]}
                    tick={{ fill: 'var(--muted-foreground)', fontSize: 10 }}
                  />
                  <Radar 
                    name="Tim Cook" 
                    dataKey="Tim Cook" 
                    stroke="var(--chart-1)" 
                    fill="var(--chart-1)" 
                    fillOpacity={0.3}
                  />
                  <Radar 
                    name="Kevan Parekh" 
                    dataKey="Kevan Parekh" 
                    stroke="var(--chart-3)" 
                    fill="var(--chart-3)" 
                    fillOpacity={0.3}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
                            <p className="text-sm font-medium text-foreground mb-2">{payload[0].payload.metric}</p>
                            {payload.map((entry, index) => (
                              <p key={index} className="text-sm text-muted-foreground">
                                {entry.name}: <span className="font-mono text-foreground">{entry.value}</span>
                              </p>
                            ))}
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex items-center justify-center gap-6 mt-4">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: 'var(--chart-1)' }} />
                <span className="text-sm text-muted-foreground">Tim Cook</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: 'var(--chart-3)' }} />
                <span className="text-sm text-muted-foreground">Kevan Parekh</span>
              </div>
            </div>
          </section>

          {/* Sentiment Distribution */}
          <section className="p-6 rounded-xl bg-card border border-border">
            <h2 className="text-lg font-semibold text-foreground mb-6">Sentiment Distribution</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sentimentDistribution}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis 
                    dataKey="range" 
                    tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                    axisLine={{ stroke: 'var(--border)' }}
                    tickLine={false}
                  />
                  <YAxis 
                    tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                    axisLine={{ stroke: 'var(--border)' }}
                    tickLine={false}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
                            <p className="text-sm font-medium text-foreground mb-1">{label}</p>
                            <p className="text-sm text-muted-foreground">
                              Count: <span className="font-mono text-foreground">{payload[0].value}</span>
                            </p>
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                  <Bar 
                    dataKey="count" 
                    radius={[4, 4, 0, 0]}
                  >
                    {sentimentDistribution.map((entry, index) => (
                      <Bar key={`cell-${index}`} fill={entry.fill} dataKey="count" />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          {/* Net Income + Revenue Stacked View */}
          <section className="p-6 rounded-xl bg-card border border-border">
            <h2 className="text-lg font-semibold text-foreground mb-6">Revenue & Net Income Comparison</h2>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={fundamentalsTrendData} barGap={8}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis 
                    dataKey="quarter" 
                    tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                    axisLine={{ stroke: 'var(--border)' }}
                    tickLine={false}
                  />
                  <YAxis 
                    tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                    axisLine={{ stroke: 'var(--border)' }}
                    tickLine={false}
                    tickFormatter={(value) => `$${value}B`}
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (active && payload && payload.length) {
                        return (
                          <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
                            <p className="text-sm font-medium text-foreground mb-2">{label}</p>
                            {payload.map((entry, index) => (
                              <p key={index} className="text-sm text-muted-foreground">
                                {entry.name}: <span className="font-mono text-foreground">${entry.value}B</span>
                              </p>
                            ))}
                          </div>
                        )
                      }
                      return null
                    }}
                  />
                  <Bar 
                    dataKey="revenue" 
                    name="Revenue"
                    fill="var(--chart-1)" 
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar 
                    dataKey="net_income" 
                    name="Net Income"
                    fill="var(--chart-3)" 
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex items-center justify-center gap-6 mt-4">
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: 'var(--chart-1)' }} />
                <span className="text-sm text-muted-foreground">Revenue</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: 'var(--chart-3)' }} />
                <span className="text-sm text-muted-foreground">Net Income</span>
              </div>
            </div>
          </section>
        </div>

        {/* Footer */}
        <div className="mt-12 text-center">
          <p className="text-sm text-muted-foreground">
            This page uses synthetic data for chart validation purposes only.
          </p>
        </div>
      </main>
    </div>
  )
}
