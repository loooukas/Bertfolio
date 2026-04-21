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
          This page documents how every major score is computed, what values usually mean, and why each metric exists.
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Score Scales</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>
            Most sentiment-like values are normalized to <code>-1</code> to <code>+1</code> internally.
          </li>
          <li>
            UI “Score” badges usually show that unit score multiplied by <code>100</code> (for example <code>+0.30</code> becomes <code>+30</code>).
          </li>
          <li>
            Confidence, evasiveness, outlook, specificity, and related communication metrics are on a <code>0-100</code> scale.
          </li>
          <li>
            Transcript coverage is shown as a percent derived from <code>found / requested</code> transcript count.
          </li>
        </ul>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Transcript Metric Formulas</h2>
        <p className="text-sm text-muted-foreground">
          Transcript sections are parsed into speaker blocks, then each block is scored using lexical densities and FinBERT directional output.
        </p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          confidence = clamp(48 + numeric_density*45 - hedge_density*35, 0, 100){"\n"}
          evasiveness = clamp(25 + hedge_density*60 + (1-numeric_density)*20, 0, 100){"\n"}
          specificity = clamp(30 + numeric_density*60, 0, 100){"\n"}
          forward_looking_strength = clamp(25 + forward_density*80, 0, 100){"\n"}
          risk_language_intensity = clamp(20 + risk_density*90, 0, 100){"\n"}
          sentiment_direction = clamp(directional_score, -1, 1)
        </div>
        <p className="text-sm text-muted-foreground">
          Block-level speaker metrics are then aggregated (means/rollups) into section cards, table values, and transcript takeaways.
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Topic Labeling</h2>
        <p className="text-sm text-muted-foreground">
          Topic labels are assigned by deterministic keyword-hit scoring over the block text. The highest-hit topic wins.
        </p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
          <div className="rounded-md border border-border bg-secondary/30 p-3 text-foreground">demand</div>
          <div className="rounded-md border border-border bg-secondary/30 p-3 text-foreground">margins</div>
          <div className="rounded-md border border-border bg-secondary/30 p-3 text-foreground">guidance</div>
          <div className="rounded-md border border-border bg-secondary/30 p-3 text-foreground">capex</div>
          <div className="rounded-md border border-border bg-secondary/30 p-3 text-foreground">costs</div>
          <div className="rounded-md border border-border bg-secondary/30 p-3 text-foreground">general (fallback)</div>
        </div>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Market Reaction Pipeline</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>Fetch larger candidate pools per source family (news/social).</li>
          <li>Filter to ticker/company-related items and apply recency-aware relevance rank.</li>
          <li>Dedupe near-duplicate headlines/posts.</li>
          <li>Score remaining text with FinBERT for directional sentiment.</li>
          <li>Keep top N items (N is controlled by settings).</li>
        </ul>
        <p className="text-sm text-muted-foreground">
          Social feed output is source-balanced so one feed does not dominate final cards when multiple sources are enabled.
        </p>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Fundamentals and Aggregate Scores</h2>
        <p className="text-sm text-muted-foreground">Fundamentals momentum uses quarterly revenue and EPS growth:</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          fundamentals_signal = clamp_unit((revenue_qoq_growth*0.55 + eps_qoq_growth*0.45) / 50.0)
        </div>
        <p className="text-sm text-muted-foreground">Aggregate communication/strength fields are derived as:</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          company_strength_score = clamp(52 + avg_directional*32 + news_avg*10 + social_avg*6 + rev_growth*0.18 + eps_growth*0.20){"\n"}
          outlook_score = clamp(avg_outlook){"\n"}
          confidence_score = clamp(avg_confidence){"\n"}
          evasiveness_score = clamp(avg_evasive)
        </div>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Overall Score and Labels</h2>
        <p className="text-sm text-muted-foreground">Full analysis weighting (when transcript data exists):</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          overall_score = clamp_unit(
          transcript_signal*0.45 + news_avg*0.22 + social_avg*0.13 + fundamentals_signal*0.20
          )
        </div>
        <p className="text-sm text-muted-foreground">Fallback weighting (if transcript coverage is missing):</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          overall_score = clamp_unit(news_avg*0.35 + social_avg*0.20 + fundamentals_signal*0.45)
        </div>
        <p className="text-sm text-muted-foreground">Snapshot endpoint weighting:</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          overall_score = clamp_unit(news_avg*0.45 + social_avg*0.20 + fundamentals_signal*0.35)
        </div>
        <p className="text-sm text-muted-foreground">Label thresholds:</p>
        <div className="rounded-md border border-border bg-secondary/40 p-4 font-mono text-xs text-foreground">
          strongly_bullish if score &gt;= 0.50{"\n"}
          cautiously_bullish if score &gt;= 0.15{"\n"}
          strongly_bearish if score &lt;= -0.50{"\n"}
          cautiously_bearish if score &lt;= -0.15{"\n"}
          mixed otherwise
        </div>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Typical Value Bands</h2>
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-secondary/40 text-muted-foreground">
              <tr>
                <th className="px-4 py-3">Metric</th>
                <th className="px-4 py-3">Typical</th>
                <th className="px-4 py-3">Interpretation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border text-foreground">
              <tr>
                <td className="px-4 py-3">Overall Sentiment (unit)</td>
                <td className="px-4 py-3">-0.25 to +0.35</td>
                <td className="px-4 py-3">Near 0 is mixed; tails indicate stronger directional consensus.</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Confidence (0-100)</td>
                <td className="px-4 py-3">45 to 65</td>
                <td className="px-4 py-3">Higher means more concrete/quantified language and fewer hedges.</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Evasiveness (0-100)</td>
                <td className="px-4 py-3">35 to 60</td>
                <td className="px-4 py-3">Higher means more hedging or less direct numeric specificity.</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Specificity (0-100)</td>
                <td className="px-4 py-3">30 to 70</td>
                <td className="px-4 py-3">Higher means denser concrete facts/metrics per speaker block.</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Outlook Strength (0-100)</td>
                <td className="px-4 py-3">25 to 55</td>
                <td className="px-4 py-3">Higher means stronger forward-looking language intensity.</td>
              </tr>
              <tr>
                <td className="px-4 py-3">Sentiment Direction</td>
                <td className="px-4 py-3">-0.3 to +0.3</td>
                <td className="px-4 py-3">Signed directional tone per block/rollup from FinBERT output.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-4 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Why These Metrics Exist</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>
            <strong>Confidence + Specificity:</strong> capture quality of communication, not just tone.
          </li>
          <li>
            <strong>Evasiveness:</strong> highlights possible avoidance behavior in Q&amp;A or guidance responses.
          </li>
          <li>
            <strong>Outlook + Topic labels:</strong> isolate where management is constructive or weak (demand, margins, capex, etc.).
          </li>
          <li>
            <strong>Market Reaction feeds:</strong> provide external confirmation/challenge signals from recent coverage.
          </li>
          <li>
            <strong>Fundamentals momentum:</strong> ties language-based readouts to hard quarterly business trajectory.
          </li>
        </ul>
      </section>

      <section className="space-y-3 rounded-xl border border-border bg-card p-6">
        <h2 className="text-xl font-semibold text-foreground">Important Notes</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-foreground">
          <li>Scores are model-derived indicators, not investment advice.</li>
          <li>Provider coverage varies by ticker and recency window; low counts reduce confidence.</li>
          <li>
            OpenAI normalization is opportunistic and only used when deterministic parsing quality is weak; deterministic parsing remains the default path.
          </li>
        </ul>
      </section>
    </main>
  )
}
