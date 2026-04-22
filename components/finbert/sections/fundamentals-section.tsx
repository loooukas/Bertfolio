"use client"

import { TrendingUp, TrendingDown } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, LineChart, Line, CartesianGrid, Tooltip } from "recharts"

interface Metric {
  key: string
  label: string
  value: string
}

interface QuarterlyData {
  quarter: string
  revenue: number
  net_income: number
  reported_eps: number
  eps_estimate: number
}

interface FundamentalsData {
  metrics: Metric[]
  quarterly_data: QuarterlyData[]
  analyst_signals: Array<{
    key: string
    label: string
    value: string
    tone: "bullish" | "neutral" | "bearish" | "muted"
    note?: string
  }>
}

interface FundamentalsSectionProps {
  data: FundamentalsData
}

const chartConfig = {
  revenue: {
    label: "Revenue",
    color: "var(--chart-1)",
  },
  net_income: {
    label: "Net Income",
    color: "var(--chart-2)",
  },
  reported_eps: {
    label: "Reported EPS",
    color: "var(--bullish)",
  },
  eps_estimate: {
    label: "EPS Estimate",
    color: "var(--muted-foreground)",
  },
}

function formatCompactCurrency(value?: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "n/a"
  }
  const absolute = Math.abs(value)
  const sign = value < 0 ? "-" : ""
  if (absolute >= 1_000_000_000_000) {
    return `${sign}$${(absolute / 1_000_000_000_000).toFixed(2)}T`
  }
  if (absolute >= 1_000_000_000) {
    return `${sign}$${(absolute / 1_000_000_000).toFixed(2)}B`
  }
  if (absolute >= 1_000_000) {
    return `${sign}$${(absolute / 1_000_000).toFixed(2)}M`
  }
  if (absolute >= 1_000) {
    return `${sign}$${(absolute / 1_000).toFixed(1)}K`
  }
  return `${sign}$${absolute.toFixed(0)}`
}

function formatAxisCurrency(value: number): string {
  if (!Number.isFinite(value)) {
    return "$0"
  }
  const absolute = Math.abs(value)
  if (absolute >= 1_000_000_000_000) {
    return `$${(value / 1_000_000_000_000).toFixed(1)}T`
  }
  if (absolute >= 1_000_000_000) {
    return `$${(value / 1_000_000_000).toFixed(1)}B`
  }
  if (absolute >= 1_000_000) {
    return `$${(value / 1_000_000).toFixed(0)}M`
  }
  if (absolute >= 1_000) {
    return `$${(value / 1_000).toFixed(0)}K`
  }
  return `$${value.toFixed(0)}`
}

export function FundamentalsSection({ data }: FundamentalsSectionProps) {
  const latestQuarter = data.quarterly_data[0]
  const previousQuarter = data.quarterly_data[1]
  
  const revenueChange = latestQuarter && previousQuarter
    ? ((latestQuarter.revenue - previousQuarter.revenue) / previousQuarter.revenue) * 100
    : 0
  
  const epsBeats = latestQuarter 
    ? latestQuarter.reported_eps > latestQuarter.eps_estimate 
    : false

  const toneClass = (tone: "bullish" | "neutral" | "bearish" | "muted") => {
    if (tone === "bullish") return "text-bullish"
    if (tone === "bearish") return "text-bearish"
    if (tone === "neutral") return "text-neutral"
    return "text-muted-foreground"
  }

  return (
    <div className="space-y-8">
      {/* Analyst Signals */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-4">
          Analyst Signals
        </h3>
        {data.analyst_signals.length === 0 ? (
          <p className="text-sm text-muted-foreground">Analyst consensus data is currently unavailable for this ticker.</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            {data.analyst_signals.map((signal) => (
              <div key={signal.key} className="rounded-lg border border-border bg-secondary/30 p-4">
                <div className="text-xs text-muted-foreground mb-1">{signal.label}</div>
                <div className={`text-lg font-semibold ${toneClass(signal.tone)}`}>{signal.value}</div>
                {signal.note && <div className="mt-1 text-xs text-muted-foreground">{signal.note}</div>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {data.metrics.slice(0, 8).map((metric) => (
          <div
            key={metric.key}
            className="p-4 rounded-xl bg-card border border-border"
          >
            <div className="text-xs text-muted-foreground mb-1">
              {metric.label}
            </div>
            <div className="text-xl font-semibold text-foreground font-mono">
              {metric.value}
            </div>
          </div>
        ))}
      </div>

      {/* Latest Quarter Highlights */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-5 rounded-xl bg-card border border-border">
          <div className="text-xs text-muted-foreground mb-2">Revenue</div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-foreground">{formatCompactCurrency(latestQuarter?.revenue)}</span>
            <div className={`flex items-center gap-1 text-sm ${revenueChange >= 0 ? "text-bullish" : "text-bearish"}`}>
              {revenueChange >= 0 ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
              <span>{Math.abs(revenueChange).toFixed(1)}%</span>
            </div>
          </div>
          <div className="text-xs text-muted-foreground mt-1">vs previous quarter</div>
        </div>

        <div className="p-5 rounded-xl bg-card border border-border">
          <div className="text-xs text-muted-foreground mb-2">Net Income</div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-foreground">{formatCompactCurrency(latestQuarter?.net_income)}</span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">{latestQuarter?.quarter}</div>
        </div>

        <div className="p-5 rounded-xl bg-card border border-border">
          <div className="text-xs text-muted-foreground mb-2">Reported EPS</div>
          <div className="flex items-center gap-2">
            <span className="text-2xl font-bold text-foreground">${latestQuarter?.reported_eps}</span>
            <Badge className={`${epsBeats ? "bg-bullish/10 text-bullish border-bullish/20" : "bg-bearish/10 text-bearish border-bearish/20"}`}>
              {epsBeats ? "Beat" : "Miss"}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Est: ${latestQuarter?.eps_estimate}
          </div>
        </div>

        <div className="p-5 rounded-xl bg-card border border-border">
          <div className="text-xs text-muted-foreground mb-2">EPS Surprise</div>
          <div className="flex items-baseline gap-2">
            <span className={`text-2xl font-bold ${epsBeats ? "text-bullish" : "text-bearish"}`}>
              {epsBeats ? "+" : ""}{latestQuarter 
                ? ((latestQuarter.reported_eps - latestQuarter.eps_estimate) / latestQuarter.eps_estimate * 100).toFixed(1) 
                : 0}%
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">vs consensus</div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Revenue & Net Income Chart */}
        <div className="p-6 rounded-xl bg-card border border-border">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-6">
            Revenue & Net Income Trend
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[...data.quarterly_data].reverse()} barGap={4}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis 
                  dataKey="quarter" 
                  tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                  axisLine={{ stroke: 'var(--border)' }}
                  tickLine={false}
                />
                <YAxis 
                  tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
                  axisLine={{ stroke: 'var(--border)' }}
                  tickLine={false}
                  tickFormatter={formatAxisCurrency}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
                          <p className="text-sm font-medium text-foreground mb-2">{label}</p>
                          {payload.map((entry, index) => (
                            <p key={index} className="text-sm text-muted-foreground">
                              {entry.name}: <span className="font-mono text-foreground">{formatCompactCurrency(Number(entry.value))}</span>
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
        </div>

        {/* EPS vs Estimates Chart */}
        <div className="p-6 rounded-xl bg-card border border-border">
          <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-6">
            EPS vs Estimates
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={[...data.quarterly_data].reverse()}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis 
                  dataKey="quarter" 
                  tick={{ fill: 'var(--muted-foreground)', fontSize: 12 }}
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
                  dataKey="reported_eps" 
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
        </div>
      </div>

      {/* Quarterly Data Table */}
      <div className="rounded-xl border border-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="bg-secondary/50 border-b border-border">
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Quarter</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Revenue</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Net Income</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">EPS</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Estimate</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Surprise</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.quarterly_data.map((quarter) => {
                const surprise = ((quarter.reported_eps - quarter.eps_estimate) / quarter.eps_estimate) * 100
                const isPositive = surprise > 0
                
                return (
                  <tr key={quarter.quarter} className="bg-card hover:bg-secondary/30 transition-colors">
                    <td className="px-4 py-3">
                      <span className="text-sm font-mono font-medium text-foreground">{quarter.quarter}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm font-mono text-foreground">{formatCompactCurrency(quarter.revenue)}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm font-mono text-foreground">{formatCompactCurrency(quarter.net_income)}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm font-mono text-foreground">${quarter.reported_eps}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className="text-sm font-mono text-muted-foreground">${quarter.eps_estimate}</span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <span className={`text-sm font-mono font-medium ${isPositive ? "text-bullish" : "text-bearish"}`}>
                        {isPositive ? "+" : ""}{surprise.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
