"use client"

import { useState } from "react"
import { Search, ArrowRight, X, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

interface TickerInputProps {
  onAnalyze: (ticker: string) => void
  isLoading: boolean
  currentTicker?: string
  onReset?: () => void
}

const popularTickers = ["AAPL", "NVDA", "MSFT", "GOOGL", "TSLA", "META"]

export function TickerInput({ onAnalyze, isLoading, currentTicker, onReset }: TickerInputProps) {
  const [inputValue, setInputValue] = useState("")

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (inputValue.trim() && !isLoading) {
      onAnalyze(inputValue.trim())
    }
  }

  const handleQuickSelect = (ticker: string) => {
    if (!isLoading) {
      setInputValue(ticker)
      onAnalyze(ticker)
    }
  }

  return (
    <div className="space-y-6">
      {/* Hero Text */}
      <div className="max-w-2xl">
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight text-foreground text-balance">
          Transcript-first earnings intelligence
        </h1>
        <p className="mt-3 text-base text-muted-foreground leading-relaxed">
          Analyze earnings calls with FinBERT-powered sentiment scoring. Get actionable signals from 
          management tone, market reaction, and fundamentals in one explainable report.
        </p>
      </div>

      {/* Input Form */}
      <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3 max-w-xl">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Enter ticker symbol (e.g., AAPL)"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value.toUpperCase())}
            disabled={isLoading}
            className="pl-10 pr-4 h-12 text-base bg-secondary border-border focus:border-ring"
          />
          {inputValue && !isLoading && (
            <button
              type="button"
              onClick={() => setInputValue("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        <Button 
          type="submit" 
          disabled={!inputValue.trim() || isLoading}
          className="h-12 px-6 gap-2"
        >
          {isLoading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Analyzing...</span>
            </>
          ) : (
            <>
              <span>Analyze</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </Button>
      </form>

      {/* Quick Select */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Popular:</span>
        {popularTickers.map((ticker) => (
          <button
            key={ticker}
            onClick={() => handleQuickSelect(ticker)}
            disabled={isLoading}
            className={`px-3 py-1.5 text-sm font-mono rounded-md border transition-colors ${
              currentTicker === ticker
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-secondary text-secondary-foreground border-border hover:border-ring hover:bg-accent"
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {ticker}
          </button>
        ))}
      </div>

      {/* Current Analysis Indicator */}
      {currentTicker && (
        <div className="flex items-center gap-3 py-3 px-4 rounded-lg bg-secondary/50 border border-border">
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Analyzing:</span>
            <span className="text-sm font-mono font-medium text-foreground">{currentTicker}</span>
          </div>
          {onReset && !isLoading && (
            <button
              onClick={onReset}
              className="ml-auto text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      )}
    </div>
  )
}
