import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { LayoutWrapper } from '@/components/layout/LayoutWrapper'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'AWARE Fund | Smart Money Index for Prediction Markets',
  description: 'Track top prediction market traders. Build your portfolio based on proven alpha.',
  keywords: ['prediction markets', 'polymarket', 'trading', 'smart money', 'index fund'],
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-slate-950 text-white antialiased`}>
        <LayoutWrapper>
          {children}
        </LayoutWrapper>
      </body>
    </html>
  )
}
