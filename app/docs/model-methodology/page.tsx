import Link from "next/link"

export default function ModelMethodologyPage() {
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-4 py-10 sm:px-6 lg:px-8">
      <section className="space-y-3 rounded-xl border border-border bg-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">Model Methodology Guide</h1>
          <Link
            href="/docs"
            className="inline-flex items-center rounded-md border border-border bg-secondary/40 px-3 py-2 text-sm text-foreground transition-colors hover:bg-secondary"
          >
            Back to Docs
          </Link>
        </div>
        <p className="text-sm text-muted-foreground">
          Canonical implementation reference for scoring, pipeline progress, data-audit taxonomy, and run-time settings behavior.
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Score Scales</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>Directional sentiment scores are normalized to <code>-1</code> to <code>+1</code>.</li>
          <li>UI score badges typically show unit scores multiplied by <code>100</code>.</li>
          <li>Confidence, evasiveness, outlook strength, and specificity are <code>0-100</code> metrics.</li>
          <li>Transcript coverage shows <code>found / requested</code> quarter capture.</li>
        </ul>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">10-Stage Progress Semantics</h2>
        <p className="text-sm text-muted-foreground">
          Job progress is emitted from backend as the canonical ordered stage list below and rendered directly by frontend without collapsing to
          coarse buckets.
        </p>
        <ol className="list-decimal space-y-2 pl-5 text-sm text-foreground">
          <li>News Fetch</li>
          <li>Social Fetch</li>
          <li>News Sentiment Scoring</li>
          <li>Social Sentiment Scoring</li>
          <li>Fundamentals Fetch</li>
          <li>Fundamentals Validation</li>
          <li>Transcript Discovery + Scrape</li>
          <li>Transcript Normalization</li>
          <li>Transcript Sentiment + Speaker Scoring</li>
          <li>Data Audit / Report Assembly</li>
        </ol>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Transcript Lexicon + Anti-Signal Model</h2>
        <p className="text-sm text-muted-foreground">
          Communication metrics use hybrid lexical densities with optional OpenAI block-feature blending. Each major signal includes positive and
          counter lexicons, then uses net density and smoothing.
        </p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          net_density = positive_density - counter_weight * counter_density{"\n"}
          smoothed_pct = 100 * (0.5 + 0.5*tanh(net_density * curve)){"\n"}
          confidence/evasiveness/specificity/outlook = bounded mixes of smoothed signals + numeric density + AI blend
        </div>
        <p className="text-sm text-muted-foreground">
          AI feature blending remains active and confidence-bounded; lexical layers provide broader directional coverage and anti-signal handling.
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Overall Scoring and Fundamentals Analyst Blend</h2>
        <p className="text-sm text-muted-foreground">Default aggregate weighting (user-adjustable in Run Settings):</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          overall = transcript*0.40 + fundamentals*0.35 + news*0.15 + social*0.10
        </div>
        <p className="text-sm text-muted-foreground">Fundamentals blend:</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          growth_signal = clamp_unit((revenue_qoq_growth*0.55 + eps_qoq_growth*0.45) / 50.0){"\n"}
          analyst_signal = blend(recommendation_mean_signal, target_upside_signal) when available{"\n"}
          fundamentals_blended = 0.80 * growth_signal + 0.20 * analyst_signal{"\n"}
          fallback = growth_signal when analyst fields unavailable
        </div>
        <p className="text-sm text-muted-foreground">Label thresholds are unchanged in this calibration pass.</p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Executive Summary Generation</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>Executive summary is an OpenAI-required quality step for full analysis.</li>
          <li>Target output is exactly 5-6 analyst-style sentences with confidence/evasiveness/outlook + market/fundamental context.</li>
          <li>Summary is rendered as one coherent paragraph and should start with the company name/ticker context.</li>
          <li>
            If generation fails, the summary section is hidden and Data Audit receives an actionable warning with failure cause.
          </li>
        </ul>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Data Audit Taxonomy</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li><code>warnings[]</code>: actionable failures that need attention.</li>
          <li><code>notices[]</code>: non-blocking drift/variance.</li>
          <li><code>diagnostics[]</code>: parser traces and internal method diagnostics.</li>
          <li>
            Legacy <code>parsing_warnings[]</code> is retained for compatibility and mapped into diagnostics in UI adapters.
          </li>
          <li>
            Fundamentals mismatch table includes severity (<code>low/medium/high</code>); only high-severity drift escalates into warnings.
          </li>
          <li><code>missing_items[]</code> is reserved for true absence of required data (not provider drift).</li>
        </ul>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Run Settings That Affect Backend Behavior</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>Data collection knobs: <code>news/social pool size</code>, <code>kept limits</code>, <code>lookback days</code>.</li>
          <li>Source toggles: Alpha Vantage/Yahoo for news, Reddit/Stocktwits for social.</li>
          <li>
            Transcript segmentation knobs: <code>TRANSCRIPT_SENTIMENT_SEGMENT_CHARS</code>, <code>MAX</code>, <code>MIN</code>,{" "}
            <code>OVERLAP_SENTENCES</code>.
          </li>
          <li>
            Feature blending knobs: <code>TRANSCRIPT_FEATURE_AI_* </code>, <code>TRANSCRIPT_FEATURE_COUNTER_WEIGHT</code>,{" "}
            <code>TRANSCRIPT_FEATURE_DENSITY_SMOOTHING</code>.
          </li>
          <li>OpenAI request resiliency knobs: <code>OPENAI_REQUEST_RETRIES</code>, <code>OPENAI_RETRY_BACKOFF_SECONDS</code>.</li>
        </ul>
      </section>
    </main>
  )
}
