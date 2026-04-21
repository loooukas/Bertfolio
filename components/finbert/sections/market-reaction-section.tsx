"use client"

import { useState } from "react"
import { Newspaper, MessageCircle, ExternalLink, TrendingUp, TrendingDown, Minus, Clock } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"

interface NewsItem {
  title: string
  summary: string
  url: string
  source: string
  time_published: string
  sentiment_score: number
  sentiment_label: "bullish" | "bearish" | "neutral"
}

interface SocialItem {
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
}

interface MarketReactionData {
  balance_summary: string
  news_count: number
  social_count: number
  news_items: NewsItem[]
  social_items: SocialItem[]
}

interface MarketReactionSectionProps {
  data: MarketReactionData
  gridColumns?: 1 | 2
}

const getSentimentIcon = (sentiment: string) => {
  switch (sentiment) {
    case "bullish":
      return <TrendingUp className="w-4 h-4 text-bullish" />
    case "bearish":
      return <TrendingDown className="w-4 h-4 text-bearish" />
    default:
      return <Minus className="w-4 h-4 text-neutral" />
  }
}

const getSentimentBadgeClass = (sentiment: string) => {
  switch (sentiment) {
    case "bullish":
      return "bg-bullish/10 text-bullish border-bullish/20"
    case "bearish":
      return "bg-bearish/10 text-bearish border-bearish/20"
    default:
      return "bg-neutral/10 text-neutral border-neutral/20"
  }
}

const formatTime = (timestamp: string) => {
  const date = new Date(timestamp)
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  })
}

export function MarketReactionSection({ data, gridColumns = 2 }: MarketReactionSectionProps) {
  const [selectedSocial, setSelectedSocial] = useState<SocialItem | null>(null)
  const gridClass = gridColumns === 2 ? "grid grid-cols-1 xl:grid-cols-2 gap-3" : "space-y-3"

  const bullishCount = [...data.news_items, ...data.social_items].filter(
    (item) => item.sentiment_label === "bullish"
  ).length
  const bearishCount = [...data.news_items, ...data.social_items].filter(
    (item) => item.sentiment_label === "bearish"
  ).length
  const totalCount = data.news_count + data.social_count
  const bullishPct = totalCount > 0 ? (bullishCount / totalCount) * 100 : 0
  const bearishPct = totalCount > 0 ? (bearishCount / totalCount) * 100 : 0

  return (
    <div className="space-y-8">
      {/* Summary */}
      <div className="p-6 rounded-xl bg-card border border-border">
        <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider mb-3">
          Market Sentiment Summary
        </h3>
        <p className="text-base text-foreground leading-relaxed mb-6">
          {data.balance_summary}
        </p>
        
        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-secondary/50">
            <div className="text-2xl font-bold text-foreground">{data.news_count}</div>
            <div className="text-xs text-muted-foreground">News Articles</div>
          </div>
          <div className="p-4 rounded-lg bg-secondary/50">
            <div className="text-2xl font-bold text-foreground">{data.social_count}</div>
            <div className="text-xs text-muted-foreground">Social Posts</div>
          </div>
          <div className="p-4 rounded-lg bg-bullish/10">
            <div className="text-2xl font-bold text-bullish">{bullishCount}</div>
            <div className="text-xs text-muted-foreground">Bullish</div>
          </div>
          <div className="p-4 rounded-lg bg-bearish/10">
            <div className="text-2xl font-bold text-bearish">{bearishCount}</div>
            <div className="text-xs text-muted-foreground">Bearish</div>
          </div>
        </div>

        {/* Sentiment Bar */}
        <div className="mt-6">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-2">
            <span>Sentiment Distribution</span>
            <span>{Math.round(bullishPct)}% Bullish</span>
          </div>
          <div className="h-3 rounded-full bg-secondary overflow-hidden flex">
            <div 
              className="h-full bg-bullish" 
              style={{ width: `${bullishPct}%` }} 
            />
            <div 
              className="h-full bg-bearish" 
              style={{ width: `${bearishPct}%` }} 
            />
          </div>
        </div>
      </div>

      {/* Content Tabs */}
      <Tabs defaultValue="news" className="space-y-4">
        <TabsList className="bg-secondary/50">
          <TabsTrigger value="news" className="gap-2">
            <Newspaper className="w-4 h-4" />
            News ({data.news_count})
          </TabsTrigger>
          <TabsTrigger value="social" className="gap-2">
            <MessageCircle className="w-4 h-4" />
            Social ({data.social_count})
          </TabsTrigger>
        </TabsList>

        {/* News Tab */}
        <TabsContent value="news" className={gridClass}>
          {data.news_items.map((item, index) => (
            <div
              key={index}
              className="h-full p-5 rounded-xl bg-card border border-border hover:border-ring transition-colors group"
            >
              <div className="flex items-start justify-between gap-4 mb-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="outline" className="text-xs">
                      {item.source}
                    </Badge>
                    <Badge className={`text-xs ${getSentimentBadgeClass(item.sentiment_label)}`}>
                      {getSentimentIcon(item.sentiment_label)}
                      <span className="ml-1 capitalize">{item.sentiment_label}</span>
                    </Badge>
                  </div>
                  <h4 className="text-base font-medium text-foreground group-hover:text-primary transition-colors">
                    {item.title}
                  </h4>
                </div>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-shrink-0 p-2 rounded-lg bg-secondary/50 text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed mb-3">
                {item.summary}
              </p>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>{formatTime(item.time_published)}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span>Score:</span>
                  <span className={`font-mono ${
                    item.sentiment_score > 0.3 ? "text-bullish" : 
                    item.sentiment_score < -0.3 ? "text-bearish" : "text-neutral"
                  }`}>
                    {item.sentiment_score > 0 ? "+" : ""}{(item.sentiment_score * 100).toFixed(0)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </TabsContent>

        {/* Social Tab */}
        <TabsContent value="social" className={gridClass}>
          {data.social_items.map((item, index) => (
            <div
              key={index}
              onClick={() => setSelectedSocial(item)}
              className="h-full p-5 rounded-xl bg-card border border-border hover:border-ring transition-colors cursor-pointer group"
            >
              <div className="flex items-start justify-between gap-4 mb-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="outline" className="text-xs">
                      {item.source}
                    </Badge>
                    {item.subreddit && (
                      <Badge variant="outline" className="text-xs font-mono">
                        r/{item.subreddit}
                      </Badge>
                    )}
                    <Badge className={`text-xs ${getSentimentBadgeClass(item.sentiment_label)}`}>
                      {getSentimentIcon(item.sentiment_label)}
                      <span className="ml-1 capitalize">{item.sentiment_label}</span>
                    </Badge>
                  </div>
                  <h4 className="text-base font-medium text-foreground group-hover:text-primary transition-colors">
                    {item.title}
                  </h4>
                </div>
              </div>
              <p className="text-sm text-muted-foreground leading-relaxed mb-3 line-clamp-2">
                {item.excerpt}
              </p>
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                <div className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  <span>{formatTime(item.created_utc)}</span>
                </div>
                <div className="flex items-center gap-1">
                  <span>Relevance:</span>
                  <span className="font-mono">{(item.relevance_score * 100).toFixed(0)}%</span>
                </div>
                <div className="flex items-center gap-1">
                  <span>Sentiment:</span>
                  <span className={`font-mono ${
                    item.sentiment_score > 0.3 ? "text-bullish" : 
                    item.sentiment_score < -0.3 ? "text-bearish" : "text-neutral"
                  }`}>
                    {item.sentiment_score > 0 ? "+" : ""}{(item.sentiment_score * 100).toFixed(0)}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </TabsContent>
      </Tabs>

      {/* Social Detail Dialog */}
      <Dialog open={!!selectedSocial} onOpenChange={() => setSelectedSocial(null)}>
        <DialogContent className="max-h-[85vh] max-w-2xl overflow-hidden">
          {selectedSocial && (
            <>
              <DialogHeader>
                <div className="flex items-center gap-2 mb-2">
                  <Badge variant="outline" className="text-xs">
                    {selectedSocial.source}
                  </Badge>
                  {selectedSocial.subreddit && (
                    <Badge variant="outline" className="text-xs font-mono">
                      r/{selectedSocial.subreddit}
                    </Badge>
                  )}
                  <Badge className={`text-xs ${getSentimentBadgeClass(selectedSocial.sentiment_label)}`}>
                    <span className="capitalize">{selectedSocial.sentiment_label}</span>
                  </Badge>
                </div>
                <DialogTitle className="text-lg">{selectedSocial.title}</DialogTitle>
              </DialogHeader>
              <div className="max-h-[65vh] space-y-4 overflow-y-auto pr-1">
                <div className="break-words whitespace-pre-wrap rounded-lg bg-secondary/50 p-4 text-sm leading-relaxed text-foreground">
                  {selectedSocial.body}
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <div className="flex items-center gap-4">
                    <span>{formatTime(selectedSocial.created_utc)}</span>
                    <span>Relevance: {(selectedSocial.relevance_score * 100).toFixed(0)}%</span>
                    <span>Sentiment: {(selectedSocial.sentiment_score * 100).toFixed(0)}</span>
                  </div>
                  <a
                    href={selectedSocial.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-primary hover:underline"
                  >
                    <span>View Source</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
