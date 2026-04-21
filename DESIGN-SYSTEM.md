# FinBERT Earnings Signals - Design System & Implementation Specification

> A complete design constitution for the transcript-first earnings intelligence platform.

---

## Table of Contents

1. [Design Philosophy](#1-design-philosophy)
2. [Technology Stack](#2-technology-stack)
3. [Color System](#3-color-system)
4. [Typography](#4-typography)
5. [Spacing & Layout](#5-spacing--layout)
6. [Icons](#6-icons)
7. [Charts & Data Visualization](#7-charts--data-visualization)
8. [Component Library](#8-component-library)
9. [Page Architecture](#9-page-architecture)
10. [State Management Patterns](#10-state-management-patterns)
11. [Accessibility](#11-accessibility)
12. [Code Patterns](#12-code-patterns)

---

## 1. Design Philosophy

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Institutional Grade** | Professional, trustworthy aesthetic suitable for financial analysts |
| **Data Density** | Maximum information per screen without clutter |
| **Clarity Over Decoration** | Every visual element serves a purpose |
| **Dark-First** | Optimized for extended screen time and data focus |
| **Progressive Disclosure** | Summary → Details → Raw Data hierarchy |

### Visual Language

- **Clean lines** - No gradients, minimal shadows, crisp borders
- **Monochromatic base** - Color used purposefully for data/sentiment only
- **Consistent rhythm** - Predictable spacing and alignment
- **Typography-driven** - Information hierarchy through type, not decoration

---

## 2. Technology Stack

### Core Framework
```json
{
  "framework": "Next.js 15+ (App Router)",
  "language": "TypeScript",
  "styling": "Tailwind CSS v4",
  "components": "shadcn/ui"
}
```

### Key Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| `recharts` | ^2.x | Charts and data visualization |
| `lucide-react` | ^0.400+ | Icon system |
| `tailwindcss` | ^4.x | Utility-first CSS |
| `@radix-ui/*` | latest | Accessible primitives (via shadcn) |
| `clsx` / `tailwind-merge` | latest | Conditional class composition |

### Installation Commands
```bash
# Core dependencies
pnpm add recharts lucide-react

# shadcn/ui components (already included in template)
# Card, Button, Badge, Tabs, Table, Dialog, Input, Progress, Tooltip
```

---

## 3. Color System

### Design Tokens (CSS Custom Properties)

All colors are defined in `app/globals.css` using OKLCH color space for perceptual uniformity.

#### Base Palette

```css
:root {
  /* Backgrounds - Deep slate with subtle blue undertone */
  --background: oklch(0.13 0.005 250);      /* Main background */
  --card: oklch(0.17 0.005 250);            /* Card surfaces */
  --popover: oklch(0.15 0.005 250);         /* Dropdowns, modals */
  --muted: oklch(0.20 0.005 250);           /* Subtle backgrounds */
  --sidebar: oklch(0.11 0.005 250);         /* Sidebar (darker) */

  /* Text */
  --foreground: oklch(0.95 0.01 90);        /* Primary text */
  --muted-foreground: oklch(0.60 0.01 90);  /* Secondary/muted text */

  /* Interactive */
  --primary: oklch(0.98 0 0);               /* Primary buttons (white) */
  --primary-foreground: oklch(0.13 0.005 250);
  --secondary: oklch(0.22 0.005 250);       /* Secondary buttons */
  --secondary-foreground: oklch(0.85 0.01 90);
  --accent: oklch(0.25 0.01 60);            /* Hover states */
  --accent-foreground: oklch(0.95 0.01 90);

  /* Borders & Inputs */
  --border: oklch(0.28 0.005 250);
  --input: oklch(0.22 0.005 250);
  --ring: oklch(0.50 0.01 90);              /* Focus rings */

  /* Destructive */
  --destructive: oklch(0.55 0.20 25);
  --destructive-foreground: oklch(0.98 0.02 25);
}
```

#### Semantic Colors (Sentiment)

```css
:root {
  --bullish: oklch(0.65 0.18 145);   /* Green - positive sentiment */
  --bearish: oklch(0.60 0.20 25);    /* Coral red - negative sentiment */
  --neutral: oklch(0.70 0.12 85);    /* Amber - neutral sentiment */
  --warning: oklch(0.75 0.15 75);    /* Orange - warnings/caution */
}
```

#### Chart Colors

```css
:root {
  --chart-1: oklch(0.70 0.15 145);  /* Primary green */
  --chart-2: oklch(0.65 0.15 25);   /* Secondary coral */
  --chart-3: oklch(0.70 0.12 250);  /* Tertiary blue */
  --chart-4: oklch(0.75 0.15 85);   /* Quaternary amber */
  --chart-5: oklch(0.60 0.10 300);  /* Quinary purple */
}
```

### Color Usage Guidelines

| Use Case | Token | Example |
|----------|-------|---------|
| Page background | `bg-background` | Main app background |
| Card/panel surface | `bg-card` | Content containers |
| Primary text | `text-foreground` | Headlines, body |
| Secondary text | `text-muted-foreground` | Labels, captions |
| Borders | `border-border` | Card borders, dividers |
| Positive data | `text-bullish` / `bg-bullish/20` | +5.2% gains |
| Negative data | `text-bearish` / `bg-bearish/20` | -3.1% losses |
| Neutral data | `text-neutral` / `bg-neutral/20` | Mixed signals |

### Tailwind Theme Extension

In `globals.css` under `@theme inline`:
```css
@theme inline {
  --color-bullish: var(--bullish);
  --color-bearish: var(--bearish);
  --color-neutral: var(--neutral);
  --color-warning: var(--warning);
}
```

Usage in components:
```tsx
<span className="text-bullish">+5.2%</span>
<span className="text-bearish">-3.1%</span>
<div className="bg-bullish/20 text-bullish">Bullish</div>
```

---

## 4. Typography

### Font Stack

```css
@theme inline {
  --font-sans: 'Geist', 'Geist Fallback', system-ui, sans-serif;
  --font-mono: 'Geist Mono', 'Geist Mono Fallback', ui-monospace, monospace;
}
```

### Type Scale

| Element | Class | Size | Weight | Line Height |
|---------|-------|------|--------|-------------|
| Page Title | `text-3xl font-bold` | 30px | 700 | 1.2 |
| Section Header | `text-xl font-semibold` | 20px | 600 | 1.3 |
| Card Title | `text-lg font-medium` | 18px | 500 | 1.4 |
| Body Text | `text-sm` | 14px | 400 | 1.5 |
| Small/Caption | `text-xs` | 12px | 400 | 1.4 |
| Data/Numbers | `font-mono text-sm` | 14px | 400 | 1.5 |

### Typography Patterns

```tsx
// Page title
<h1 className="text-3xl font-bold text-foreground">FinBERT Earnings Signals</h1>

// Section header
<h2 className="text-xl font-semibold text-foreground">Transcript Analysis</h2>

// Card header
<h3 className="text-lg font-medium text-foreground">Key Metrics</h3>

// Body text
<p className="text-sm text-muted-foreground leading-relaxed">
  Analysis complete with 95% confidence.
</p>

// Data values (always monospace)
<span className="font-mono text-2xl font-bold text-foreground">$142.8B</span>

// Labels
<span className="text-xs uppercase tracking-wide text-muted-foreground">Revenue</span>

// Balanced headings (prevent orphans)
<h2 className="text-xl font-semibold text-balance">
  Quarterly Earnings Analysis Summary
</h2>
```

---

## 5. Spacing & Layout

### Spacing Scale (Tailwind Default)

| Token | Value | Use Case |
|-------|-------|----------|
| `1` | 4px | Icon gaps, tight spacing |
| `2` | 8px | Inline element spacing |
| `3` | 12px | Small component padding |
| `4` | 16px | Standard card padding |
| `6` | 24px | Section gaps |
| `8` | 32px | Major section separation |
| `12` | 48px | Page-level spacing |

### Layout Method Priority

1. **Flexbox** (90% of layouts)
2. **CSS Grid** (only for true 2D layouts like metric grids)
3. **Never floats or absolute positioning** (except overlays)

### Common Layout Patterns

```tsx
// Horizontal row with space-between
<div className="flex items-center justify-between">

// Vertical stack with gap
<div className="flex flex-col gap-4">

// Metric grid (2D layout - use grid)
<div className="grid grid-cols-2 md:grid-cols-3 gap-4">

// Centered content
<div className="flex items-center justify-center min-h-[400px]">

// Full-width container with max-width
<div className="w-full max-w-7xl mx-auto px-4 md:px-6">
```

### Container Widths

| Container | Class | Use |
|-----------|-------|-----|
| Full width | `w-full` | Backgrounds, sections |
| Content max | `max-w-7xl` | Main content area |
| Card content | `p-4` or `p-6` | Internal card padding |
| Narrow content | `max-w-2xl` | Forms, modals |

### Border Radius

```css
--radius: 0.5rem; /* 8px - base radius */
```

| Element | Class |
|---------|-------|
| Cards | `rounded-lg` (8px) |
| Buttons | `rounded-md` (6px) |
| Badges | `rounded-full` (pill) or `rounded-md` |
| Inputs | `rounded-md` (6px) |
| Small elements | `rounded-sm` (4px) |

---

## 6. Icons

### Icon Library

**Library:** [Lucide React](https://lucide.dev/)
**Installation:** `pnpm add lucide-react`

### Core Icons Used

```tsx
import {
  // Navigation & Actions
  Search,
  ArrowRight,
  ArrowUpRight,
  ArrowDownRight,
  ChevronRight,
  ChevronDown,
  X,
  Menu,
  Settings,
  ExternalLink,
  
  // Status & State
  Check,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  XCircle,
  Loader2,
  Clock,
  
  // Data & Analytics
  TrendingUp,
  TrendingDown,
  BarChart3,
  LineChart,
  PieChart,
  Activity,
  
  // Content Types
  FileText,
  MessageSquare,
  Quote,
  Users,
  User,
  Building2,
  
  // Social & Sources
  Twitter,
  Globe,
  Newspaper,
  
  // Misc
  Sparkles,
  Shield,
  Database,
  Zap,
  Target,
  Eye,
  ThumbsUp,
  ThumbsDown,
  Repeat,
  Heart,
} from "lucide-react"
```

### Icon Sizing

| Size | Class | Use Case |
|------|-------|----------|
| Small | `h-4 w-4` | Inline with text, badges |
| Medium | `h-5 w-5` | Buttons, list items |
| Large | `h-6 w-6` | Card headers, emphasis |
| XL | `h-8 w-8` | Empty states, features |

### Icon Patterns

```tsx
// Inline with text
<span className="flex items-center gap-1.5 text-sm">
  <TrendingUp className="h-4 w-4 text-bullish" />
  +5.2%
</span>

// Button with icon
<Button>
  <Search className="h-4 w-4 mr-2" />
  Search
</Button>

// Icon-only button
<Button variant="ghost" size="icon">
  <Settings className="h-5 w-5" />
</Button>

// Status indicator
<div className="flex items-center gap-2">
  <CheckCircle2 className="h-5 w-5 text-bullish" />
  <span>Complete</span>
</div>

// Loading spinner
<Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
```

---

## 7. Charts & Data Visualization

### Library: Recharts

**Installation:** `pnpm add recharts`
**Documentation:** https://recharts.org/

### Required Imports

```tsx
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Cell,
} from "recharts"
```

### Chart Container Pattern

Always wrap charts in a fixed-height container with `ResponsiveContainer`:

```tsx
<div className="h-64"> {/* or h-80, h-96 */}
  <ResponsiveContainer width="100%" height="100%">
    <BarChart data={data}>
      {/* chart contents */}
    </BarChart>
  </ResponsiveContainer>
</div>
```

### Axis Configuration (Dark Theme)

```tsx
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
  width={60}
  tickFormatter={(value) => `$${value}B`}
/>
```

### Grid Configuration

```tsx
<CartesianGrid 
  strokeDasharray="3 3" 
  stroke="var(--border)" 
  vertical={false}  // Usually hide vertical grid lines
/>
```

### Custom Tooltip Component

```tsx
<Tooltip
  content={({ active, payload, label }) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-lg border border-border bg-card p-3 shadow-lg">
          <p className="text-sm font-medium text-foreground mb-2">{label}</p>
          {payload.map((entry, index) => (
            <p key={index} className="text-sm text-muted-foreground">
              {entry.name}: 
              <span className="font-mono text-foreground ml-1">
                {typeof entry.value === 'number' ? entry.value.toFixed(2) : entry.value}
              </span>
            </p>
          ))}
        </div>
      )
    }
    return null
  }}
/>
```

### Bar Chart Example

```tsx
<BarChart data={revenueData} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
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
    tickFormatter={(v) => `$${v}B`}
  />
  <Tooltip content={<CustomTooltip />} />
  <Bar 
    dataKey="revenue" 
    name="Revenue"
    fill="var(--chart-1)" 
    radius={[4, 4, 0, 0]}  // Rounded top corners
  />
</BarChart>
```

### Line Chart Example

```tsx
<LineChart data={epsData}>
  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
  <XAxis dataKey="quarter" {...axisConfig} />
  <YAxis {...axisConfig} tickFormatter={(v) => `$${v}`} />
  <Tooltip content={<CustomTooltip />} />
  
  {/* Solid line for actual values */}
  <Line 
    type="monotone" 
    dataKey="eps" 
    name="Reported EPS"
    stroke="var(--bullish)" 
    strokeWidth={2}
    dot={{ fill: 'var(--bullish)', strokeWidth: 0, r: 4 }}
  />
  
  {/* Dashed line for estimates/comparison */}
  <Line 
    type="monotone" 
    dataKey="estimate" 
    name="Consensus"
    stroke="var(--muted-foreground)" 
    strokeWidth={2}
    strokeDasharray="5 5"
    dot={{ fill: 'var(--muted-foreground)', strokeWidth: 0, r: 4 }}
  />
</LineChart>
```

### Radar Chart Example

```tsx
<RadarChart data={speakerMetrics} cx="50%" cy="50%" outerRadius="70%">
  <PolarGrid stroke="var(--border)" />
  <PolarAngleAxis 
    dataKey="metric" 
    tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
  />
  <PolarRadiusAxis 
    angle={90} 
    domain={[0, 100]}
    tick={{ fill: 'var(--muted-foreground)', fontSize: 10 }}
    axisLine={false}
  />
  <Radar 
    name="CEO" 
    dataKey="ceo" 
    stroke="var(--chart-1)" 
    fill="var(--chart-1)" 
    fillOpacity={0.3}
  />
  <Radar 
    name="CFO" 
    dataKey="cfo" 
    stroke="var(--chart-3)" 
    fill="var(--chart-3)" 
    fillOpacity={0.3}
  />
  <Tooltip content={<CustomTooltip />} />
</RadarChart>
```

### Data Shape Examples

```tsx
// Time series data (revenue, EPS, etc.)
const quarterlyData = [
  { quarter: "2024-Q1", revenue: 90.8, eps: 1.52, estimate: 1.48 },
  { quarter: "2024-Q2", revenue: 85.8, eps: 1.38, estimate: 1.35 },
  { quarter: "2024-Q3", revenue: 94.9, eps: 1.64, estimate: 1.58 },
  { quarter: "2024-Q4", revenue: 119.6, eps: 2.18, estimate: 2.10 },
]

// Categorical comparison (speakers, sources)
const speakerData = [
  { name: "Tim Cook", sentiment: 0.72, wordCount: 3240, statements: 45 },
  { name: "Luca Maestri", sentiment: 0.68, wordCount: 2890, statements: 38 },
]

// Radar chart data (multi-dimensional comparison)
const radarData = [
  { metric: "Confidence", ceo: 85, cfo: 82 },
  { metric: "Specificity", ceo: 65, cfo: 88 },
  { metric: "Hedging", ceo: 45, cfo: 52 },
  { metric: "Forward-Looking", ceo: 78, cfo: 71 },
]
```

---

## 8. Component Library

### Base Components (shadcn/ui)

These components are pre-installed and follow our design tokens:

| Component | Import | Notes |
|-----------|--------|-------|
| Button | `@/components/ui/button` | Primary, secondary, ghost, outline variants |
| Card | `@/components/ui/card` | Card, CardHeader, CardTitle, CardContent, CardDescription |
| Badge | `@/components/ui/badge` | Default, outline, destructive + custom sentiment |
| Tabs | `@/components/ui/tabs` | TabsList, TabsTrigger, TabsContent |
| Table | `@/components/ui/table` | Full table primitives |
| Dialog | `@/components/ui/dialog` | Modal dialogs |
| Input | `@/components/ui/input` | Text inputs |
| Progress | `@/components/ui/progress` | Progress bars |
| Tooltip | `@/components/ui/tooltip` | Hover tooltips |
| Skeleton | `@/components/ui/skeleton` | Loading placeholders |

### Button Variants

```tsx
// Primary action (white on dark)
<Button>Analyze</Button>

// Secondary action
<Button variant="secondary">Cancel</Button>

// Ghost (subtle)
<Button variant="ghost">Learn More</Button>

// Outline
<Button variant="outline">Export</Button>

// Destructive
<Button variant="destructive">Delete</Button>

// With loading state
<Button disabled>
  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
  Analyzing...
</Button>

// Icon button
<Button variant="ghost" size="icon">
  <Settings className="h-5 w-5" />
</Button>
```

### Card Patterns

```tsx
// Standard card
<Card>
  <CardHeader>
    <CardTitle>Section Title</CardTitle>
    <CardDescription>Optional description</CardDescription>
  </CardHeader>
  <CardContent>
    {/* Content */}
  </CardContent>
</Card>

// Metric card
<Card>
  <CardContent className="p-4">
    <p className="text-xs uppercase tracking-wide text-muted-foreground mb-1">
      Revenue
    </p>
    <p className="text-2xl font-bold font-mono">$142.8B</p>
    <p className="text-sm text-bullish flex items-center gap-1 mt-1">
      <TrendingUp className="h-3 w-3" />
      +5.2% YoY
    </p>
  </CardContent>
</Card>

// Clickable card
<Card className="cursor-pointer hover:bg-accent/50 transition-colors">
  {/* Content */}
</Card>
```

### Custom Badge Variants (Sentiment)

```tsx
// Define sentiment badge styles
const sentimentStyles = {
  bullish: "bg-bullish/20 text-bullish border-bullish/30",
  bearish: "bg-bearish/20 text-bearish border-bearish/30",
  neutral: "bg-neutral/20 text-neutral border-neutral/30",
}

// Usage
<Badge className={sentimentStyles.bullish}>Bullish</Badge>
<Badge className={sentimentStyles.bearish}>Bearish</Badge>
<Badge className={sentimentStyles.neutral}>Neutral</Badge>

// Or as a component
function SentimentBadge({ sentiment }: { sentiment: 'bullish' | 'bearish' | 'neutral' }) {
  return (
    <Badge className={cn("border", sentimentStyles[sentiment])}>
      {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
    </Badge>
  )
}
```

### Tabs Pattern

```tsx
<Tabs defaultValue="overview" className="w-full">
  <TabsList className="w-full justify-start border-b border-border rounded-none bg-transparent p-0 h-auto">
    <TabsTrigger 
      value="overview"
      className="rounded-none border-b-2 border-transparent data-[state=active]:border-foreground data-[state=active]:bg-transparent px-4 py-3"
    >
      Overview
    </TabsTrigger>
    {/* More triggers */}
  </TabsList>
  
  <TabsContent value="overview" className="mt-6">
    <OverviewSection data={data} />
  </TabsContent>
</Tabs>
```

### Table Pattern

```tsx
<div className="border border-border rounded-lg overflow-hidden">
  <Table>
    <TableHeader>
      <TableRow className="border-border hover:bg-transparent">
        <TableHead className="text-muted-foreground">Speaker</TableHead>
        <TableHead className="text-muted-foreground">Role</TableHead>
        <TableHead className="text-muted-foreground text-right">Sentiment</TableHead>
      </TableRow>
    </TableHeader>
    <TableBody>
      {speakers.map((speaker) => (
        <TableRow key={speaker.id} className="border-border">
          <TableCell className="font-medium">{speaker.name}</TableCell>
          <TableCell className="text-muted-foreground">{speaker.role}</TableCell>
          <TableCell className="text-right">
            <span className={cn(
              "font-mono",
              speaker.sentiment > 0 ? "text-bullish" : "text-bearish"
            )}>
              {speaker.sentiment.toFixed(2)}
            </span>
          </TableCell>
        </TableRow>
      ))}
    </TableBody>
  </Table>
</div>
```

### Dialog Pattern

```tsx
<Dialog>
  <DialogTrigger asChild>
    <Button variant="ghost" size="sm">View Details</Button>
  </DialogTrigger>
  <DialogContent className="max-w-2xl">
    <DialogHeader>
      <DialogTitle>Social Post Details</DialogTitle>
      <DialogDescription>
        Full content and engagement metrics
      </DialogDescription>
    </DialogHeader>
    <div className="space-y-4">
      {/* Detail content */}
    </div>
  </DialogContent>
</Dialog>
```

---

## 9. Page Architecture

### Main Application Page (`/`)

```
┌─────────────────────────────────────────────────────────────────┐
│ HEADER                                                          │
│ [Logo] FinBERT Earnings Signals    [Charts Test] [Settings] [●] │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ TICKER INPUT                                                │ │
│ │ [________________________] [Analyze →]                      │ │
│ │ Quick: AAPL  MSFT  NVDA  GOOGL  AMZN  TSLA                 │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ CONTENT AREA                                                │ │
│ │                                                             │ │
│ │ State: Empty → Loading → Report | Error                     │ │
│ │                                                             │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Report View Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ COMPANY HEADER                                                  │
│ [AAPL] Apple Inc. • Technology • Q4 2024 Earnings Call         │
├─────────────────────────────────────────────────────────────────┤
│ TAB NAVIGATION                                                  │
│ [Overview] [Transcript] [Market Reaction] [Fundamentals] [Audit]│
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ SECTION CONTENT                                                 │
│                                                                 │
│ (Varies by active tab - see section layouts below)             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Section: Overview

```
┌───────────────────────────────────────────────────────────────┐
│ SIGNAL SUMMARY                                                │
│ ┌─────────────────────────────────┬─────────────────────────┐ │
│ │ ● BULLISH                       │ Executive Summary       │ │
│ │ 87% Confidence                  │ Lorem ipsum dolor...    │ │
│ │                                 │                         │ │
│ └─────────────────────────────────┴─────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ KEY METRICS                                                   │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐        │
│ │ Confidence    │ │ Evasiveness   │ │ Outlook       │        │
│ │ 87            │ │ Low           │ │ Strong        │        │
│ │ High          │ │ ↓ vs Q3       │ │ Improving     │        │
│ └───────────────┘ └───────────────┘ └───────────────┘        │
├───────────────────────────────────────────────────────────────┤
│ KEY TAKEAWAYS                                                 │
│ • Revenue beat expectations by 3.2%                          │
│ • Strong iPhone demand in emerging markets                   │
│ • Services growth accelerating                               │
│ • Management raised full-year guidance                       │
└───────────────────────────────────────────────────────────────┘
```

### Section: Transcript Analysis

```
┌───────────────────────────────────────────────────────────────┐
│ QUARTER AVAILABILITY                                          │
│ [Q1 ●] [Q2 ●] [Q3 ●] [Q4 ●]                                   │
├───────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────┬─────────────────────────────┐ │
│ │ KEY QUOTES                  │ Q&A PRESSURE POINTS         │ │
│ │                             │                             │ │
│ │ ┌─── Quote Card ─────────┐  │ ┌─── Analyst Question ───┐  │ │
│ │ │ "Strong demand..."     │  │ │ Morgan Stanley: China  │  │ │
│ │ │ Tim Cook, CEO          │  │ │ Evasiveness: High      │  │ │
│ │ │ [Bullish]              │  │ └────────────────────────┘  │ │
│ │ └────────────────────────┘  │                             │ │
│ └─────────────────────────────┴─────────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ SPEAKER ROLLUP                                                │
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐              │
│ │ Tim Cook    │ │ Luca Maestri│ │ Analysts    │              │
│ │ CEO         │ │ CFO         │ │ Q&A         │              │
│ │ +0.72 sent  │ │ +0.68 sent  │ │ 12 total    │              │
│ └─────────────┘ └─────────────┘ └─────────────┘              │
├───────────────────────────────────────────────────────────────┤
│ DETAILED SPEAKER TABLE                                        │
│ [Filter: All Speakers ▼]                                      │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Speaker      │ Role  │ Statements │ Avg Sent │ Hedging  │ │
│ ├──────────────┼───────┼────────────┼──────────┼──────────┤ │
│ │ Tim Cook     │ CEO   │ 45         │ +0.72    │ 12%      │ │
│ │ Luca Maestri │ CFO   │ 38         │ +0.68    │ 18%      │ │
│ └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### Section: Market Reaction

```
┌───────────────────────────────────────────────────────────────┐
│ ┌─────────────────────────────┬─────────────────────────────┐ │
│ │ NEWS ITEMS                  │ SOCIAL SENTIMENT            │ │
│ │                             │                             │ │
│ │ ┌─── News Card ──────────┐  │ ┌─── Social Card ────────┐  │ │
│ │ │ 📰 Reuters             │  │ │ 𝕏 @analyst            │  │ │
│ │ │ Apple beats Q4...      │  │ │ "Great earnings..."   │  │ │
│ │ │ 2h ago • [Bullish]     │  │ │ ❤️ 234  🔄 45          │  │ │
│ │ └────────────────────────┘  │ │ [Bullish]             │  │ │
│ │                             │ └────────────────────────┘  │ │
│ └─────────────────────────────┴─────────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ SENTIMENT DISTRIBUTION                                        │
│                                                               │
│ News    ████████████████░░░░░  Positive: 68% Neutral: 22%    │
│ Social  ██████████████████░░░  Positive: 72% Neutral: 18%    │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### Section: Fundamentals

```
┌───────────────────────────────────────────────────────────────┐
│ OPERATING CONTEXT                                             │
│ Industry: Technology  |  Market Cap: $2.8T  |  FYE: Sept     │
├───────────────────────────────────────────────────────────────┤
│ KEY METRICS                                                   │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│ │ Revenue │ │ Net Inc │ │ EPS     │ │ P/E     │ │ Margin  │  │
│ │ $119.6B │ │ $33.9B  │ │ $2.18   │ │ 28.4x   │ │ 28.3%   │  │
│ │ +5.2%   │ │ +12.1%  │ │ +8.4%   │ │ —       │ │ +180bps │  │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘  │
├───────────────────────────────────────────────────────────────┤
│ CHARTS                                                        │
│ ┌─────────────────────────────┬─────────────────────────────┐ │
│ │ Revenue by Quarter          │ EPS vs Consensus            │ │
│ │ [Bar Chart]                 │ [Line Chart]                │ │
│ │                             │ ── Actual  - - Estimate     │ │
│ └─────────────────────────────┴─────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

### Section: Data Audit

```
┌───────────────────────────────────────────────────────────────┐
│ CONFIDENCE ASSESSMENT                                         │
│ ┌─────────────────────────────────────────────────────────┐  │
│ │ Overall Quality: A (High Confidence)                    │  │
│ │                                                         │  │
│ │ Transcript:    ████████████████████  95%                │  │
│ │ Fundamentals:  ██████████████████░░  88%                │  │
│ │ Market Data:   ████████████████░░░░  82%                │  │
│ └─────────────────────────────────────────────────────────┘  │
├───────────────────────────────────────────────────────────────┤
│ SOURCE COUNTS                                                 │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Source          │ Items  │ Quality │ Last Updated        │ │
│ ├─────────────────┼────────┼─────────┼─────────────────────┤ │
│ │ SEC Filings     │ 4      │ A       │ 2024-10-31          │ │
│ │ Press Releases  │ 12     │ A       │ 2024-10-31          │ │
│ │ News APIs       │ 45     │ B       │ 2024-11-01          │ │
│ └──────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ PIPELINE TASKS                                                │
│ ┌──────────────────────────────────────────────────────────┐ │
│ │ Task              │ Status  │ Duration │ Records         │ │
│ ├───────────────────┼─────────┼──────────┼─────────────────┤ │
│ │ Transcript Parse  │ ✓ Done  │ 2.3s     │ 1,245 sentences │ │
│ │ NLP Analysis      │ ✓ Done  │ 4.8s     │ 1,245 scored    │ │
│ │ Fundamentals Fetch│ ✓ Done  │ 1.2s     │ 32 metrics      │ │
│ └──────────────────────────────────────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ TRANSCRIPT FUNNEL                                             │
│                                                               │
│ Quarters Searched:  4                                         │
│ Transcripts Found:  4  ████████████████████                   │
│ Successfully Parsed: 4  ████████████████████                  │
│ Quality Validated:   3  ███████████████░░░░░                  │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

### Charts Test Page (`/charts-test`)

```
┌───────────────────────────────────────────────────────────────┐
│ Charts Test                                      [← Back]     │
├───────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────┬─────────────────────────────┐ │
│ │ Speaker Sentiment           │ Word Count by Speaker       │ │
│ │ [Vertical Bar Chart]        │ [Horizontal Bar Chart]      │ │
│ └─────────────────────────────┴─────────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────┬─────────────────────────────┐ │
│ │ Revenue Trend               │ EPS vs Estimates            │ │
│ │ [Area Chart]                │ [Dual Line Chart]           │ │
│ └─────────────────────────────┴─────────────────────────────┘ │
├───────────────────────────────────────────────────────────────┤
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ Speaker Metrics Comparison                                │ │
│ │ [Radar Chart - Full Width]                                │ │
│ └───────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

---

## 10. State Management Patterns

### Application States

| State | Visual Treatment |
|-------|------------------|
| **Empty** | Centered illustration, helpful copy, CTA |
| **Loading** | Skeleton loaders OR progress indicator |
| **Success** | Full content display |
| **Error** | Inline error with red accent, retry button |
| **Partial** | Content with warning badges for missing data |

### Empty State Pattern

```tsx
<div className="flex flex-col items-center justify-center min-h-[400px] text-center">
  <div className="rounded-full bg-muted p-4 mb-4">
    <BarChart3 className="h-8 w-8 text-muted-foreground" />
  </div>
  <h3 className="text-lg font-medium text-foreground mb-2">
    No Analysis Loaded
  </h3>
  <p className="text-sm text-muted-foreground max-w-md mb-6">
    Enter a ticker symbol above to generate a comprehensive earnings analysis.
  </p>
  <div className="flex items-center gap-4 text-sm text-muted-foreground">
    <span className="flex items-center gap-1.5">
      <Sparkles className="h-4 w-4" />
      AI-Powered Insights
    </span>
    {/* More features */}
  </div>
</div>
```

### Loading State Pattern (Progress)

```tsx
<div className="space-y-6">
  <div className="text-center">
    <h3 className="text-lg font-medium mb-2">Analyzing {ticker}...</h3>
    <p className="text-sm text-muted-foreground">
      Processing earnings data and generating insights
    </p>
  </div>
  
  <div className="space-y-3">
    {stages.map((stage) => (
      <div key={stage.id} className="flex items-center gap-3">
        {stage.status === 'complete' && (
          <CheckCircle2 className="h-5 w-5 text-bullish" />
        )}
        {stage.status === 'running' && (
          <Loader2 className="h-5 w-5 text-foreground animate-spin" />
        )}
        {stage.status === 'pending' && (
          <div className="h-5 w-5 rounded-full border-2 border-muted" />
        )}
        <span className={cn(
          stage.status === 'pending' && "text-muted-foreground"
        )}>
          {stage.label}
        </span>
      </div>
    ))}
  </div>
</div>
```

### Loading State Pattern (Skeleton)

```tsx
<Card>
  <CardHeader>
    <Skeleton className="h-6 w-48" />
  </CardHeader>
  <CardContent className="space-y-4">
    <Skeleton className="h-4 w-full" />
    <Skeleton className="h-4 w-3/4" />
    <Skeleton className="h-4 w-1/2" />
  </CardContent>
</Card>
```

### Error State Pattern

```tsx
<div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
  <div className="flex items-start gap-3">
    <XCircle className="h-5 w-5 text-destructive mt-0.5" />
    <div className="flex-1">
      <h4 className="font-medium text-foreground">Analysis Failed</h4>
      <p className="text-sm text-muted-foreground mt-1">
        Unable to fetch earnings data for {ticker}. The ticker may be invalid 
        or there may be no recent earnings calls available.
      </p>
      <Button 
        variant="outline" 
        size="sm" 
        className="mt-3"
        onClick={onRetry}
      >
        Try Again
      </Button>
    </div>
  </div>
</div>
```

---

## 11. Accessibility

### Requirements

| Requirement | Implementation |
|-------------|----------------|
| Color contrast | WCAG AA minimum (4.5:1 for text) |
| Focus states | Visible focus rings on all interactive elements |
| Keyboard nav | Full keyboard accessibility |
| Screen readers | Proper ARIA labels and semantic HTML |
| Motion | Respect `prefers-reduced-motion` |

### Implementation Patterns

```tsx
// Screen reader only text
<span className="sr-only">Loading analysis</span>

// Semantic HTML
<main>
  <header>...</header>
  <nav aria-label="Report sections">...</nav>
  <section aria-labelledby="overview-heading">
    <h2 id="overview-heading">Overview</h2>
  </section>
</main>

// ARIA labels
<Button aria-label="Analyze ticker">
  <Search className="h-4 w-4" />
</Button>

// Focus management
<Input
  className="focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background"
/>

// Reduced motion
<div className="animate-spin motion-reduce:animate-none">
```

---

## 12. Code Patterns

### Component File Structure

```
components/
├── finbert/
│   ├── header.tsx           # App header
│   ├── ticker-input.tsx     # Search input component
│   ├── job-progress.tsx     # Loading progress indicator
│   ├── empty-state.tsx      # Empty state component
│   ├── report-view.tsx      # Main report container with tabs
│   └── sections/
│       ├── overview-section.tsx
│       ├── transcript-section.tsx
│       ├── market-reaction-section.tsx
│       ├── fundamentals-section.tsx
│       └── data-audit-section.tsx
└── ui/
    └── (shadcn components)
```

### Component Template

```tsx
"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { TrendingUp } from "lucide-react"
import { cn } from "@/lib/utils"

interface ComponentProps {
  data: DataType
  className?: string
}

export function ComponentName({ data, className }: ComponentProps) {
  return (
    <Card className={cn("", className)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <TrendingUp className="h-5 w-5" />
          Section Title
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Content */}
      </CardContent>
    </Card>
  )
}
```

### TypeScript Types

```tsx
// Sentiment type
type Sentiment = 'bullish' | 'bearish' | 'neutral'

// Task/job status
type TaskStatus = 'pending' | 'running' | 'complete' | 'error'

// Speaker data
interface Speaker {
  id: string
  name: string
  role: string
  statements: number
  avgSentiment: number
  wordCount: number
  hedgingPercent: number
}

// Quarterly data point
interface QuarterlyMetric {
  quarter: string
  value: number
  yoyChange?: number
}

// Chart data point
interface ChartDataPoint {
  [key: string]: string | number
}
```

### Utility Functions

```tsx
// Class name composition
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Format large numbers
export function formatLargeNumber(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  return `$${value.toLocaleString()}`
}

// Format percentage change
export function formatChange(value: number): string {
  const sign = value >= 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

// Get sentiment color class
export function getSentimentClass(sentiment: Sentiment): string {
  return {
    bullish: 'text-bullish',
    bearish: 'text-bearish',
    neutral: 'text-neutral',
  }[sentiment]
}
```

---

## Quick Reference

### Install Commands
```bash
pnpm add recharts lucide-react
```

### Key Tailwind Classes
```
bg-background bg-card bg-muted
text-foreground text-muted-foreground
text-bullish text-bearish text-neutral
border-border
rounded-lg rounded-md
font-mono
```

### Chart Colors (CSS Variables)
```
var(--chart-1)  # Green
var(--chart-2)  # Coral
var(--chart-3)  # Blue
var(--chart-4)  # Amber
var(--chart-5)  # Purple
var(--bullish)  # Positive
var(--bearish)  # Negative
```

---

*This design system document serves as the single source of truth for the FinBERT Earnings Signals UI implementation.*
