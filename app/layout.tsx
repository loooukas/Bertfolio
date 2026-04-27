import type { Metadata } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { GeistMono } from "geist/font/mono"
import { GeistSans } from "geist/font/sans"
import './globals.css'

export const metadata: Metadata = {
  title: 'Bertfolio',
  description: 'Transcript-first earnings intelligence platform',
  applicationName: "Bertfolio",
  icons: {
    icon: [
      {
        url: '/icon-light-32x32.png',
        media: '(prefers-color-scheme: light)',
      },
      {
        url: '/icon-dark-32x32.png',
        media: '(prefers-color-scheme: dark)',
      },
      {
        url: '/icon.svg',
        type: 'image/svg+xml',
      },
    ],
    apple: '/apple-icon.png',
  },
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable} bg-background`}>
      <body className="font-sans antialiased min-h-screen bg-background text-foreground">
        {children}
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
