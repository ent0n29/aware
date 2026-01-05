'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  Trophy,
  LineChart,
  Users,
  Sparkles,
  Settings,
  HelpCircle,
  TrendingUp,
  Menu,
  X,
  PieChart,
  AlertTriangle,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Fund', href: '/fund', icon: PieChart },
  { name: 'Leaderboard', href: '/leaderboard', icon: Trophy },
  { name: 'PSI Indices', href: '/indices', icon: LineChart },
  { name: 'Consensus', href: '/consensus', icon: Users },
  { name: 'Discovery', href: '/discovery', icon: Sparkles },
  { name: 'Insider Alerts', href: '/insider-alerts', icon: AlertTriangle },
]

const secondaryNav = [
  { name: 'Settings', href: '/settings', icon: Settings },
  { name: 'Help', href: '/help', icon: HelpCircle },
]

interface SidebarProps {
  isOpen?: boolean
  onClose?: () => void
}

export function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname()

  // Close sidebar on route change (mobile)
  useEffect(() => {
    if (onClose) {
      onClose()
    }
  }, [pathname, onClose])

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          // Base styles
          'fixed left-0 top-0 z-40 h-screen w-64 bg-slate-900/95 backdrop-blur-xl border-r border-slate-800',
          // Mobile: hidden by default, shown when isOpen
          'transition-transform duration-300 ease-in-out',
          isOpen ? 'translate-x-0' : '-translate-x-full',
          // Desktop: always visible
          'md:translate-x-0'
        )}
      >
        <div className="flex h-full flex-col">
          {/* Logo & Close button */}
          <div className="flex h-16 items-center justify-between px-6 border-b border-slate-800">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-aware-400 to-aware-600 flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold bg-gradient-to-r from-aware-400 to-cyan-400 bg-clip-text text-transparent">
                  AWARE
                </h1>
                <p className="text-xs text-slate-500">Smart Money Index</p>
              </div>
            </div>
            {/* Mobile close button */}
            <button
              onClick={onClose}
              className="md:hidden p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
              aria-label="Close sidebar"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
            <div className="space-y-1">
              {navigation.map((item) => {
                const isActive = pathname === item.href
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                      isActive
                        ? 'bg-aware-500/20 text-aware-400 shadow-lg shadow-aware-500/10'
                        : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                    )}
                  >
                    <item.icon className={cn('w-5 h-5', isActive && 'text-aware-400')} />
                    {item.name}
                    {isActive && (
                      <div className="ml-auto w-1.5 h-1.5 rounded-full bg-aware-400 animate-pulse" />
                    )}
                  </Link>
                )
              })}
            </div>

            <div className="pt-8">
              <p className="px-3 text-xs font-semibold text-slate-600 uppercase tracking-wider mb-2">
                Other
              </p>
              {secondaryNav.map((item) => {
                const isActive = pathname === item.href
                return (
                  <Link
                    key={item.name}
                    href={item.href}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                      isActive
                        ? 'bg-slate-800 text-white'
                        : 'text-slate-500 hover:bg-slate-800 hover:text-slate-300'
                    )}
                  >
                    <item.icon className="w-5 h-5" />
                    {item.name}
                  </Link>
                )
              })}
            </div>
          </nav>

          {/* Footer */}
          <div className="p-4 border-t border-slate-800">
            <div className="rounded-lg bg-gradient-to-r from-aware-600/20 to-cyan-600/20 p-4">
              <p className="text-xs font-medium text-aware-400 mb-1">PSI-10 Index</p>
              <p className="text-2xl font-bold text-white">$142.50</p>
              <p className="text-xs text-green-400 mt-1">+2.4% today</p>
            </div>
          </div>
        </div>
      </aside>
    </>
  )
}

interface MobileMenuButtonProps {
  onClick: () => void
}

export function MobileMenuButton({ onClick }: MobileMenuButtonProps) {
  return (
    <button
      onClick={onClick}
      className="md:hidden p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
      aria-label="Open menu"
    >
      <Menu className="w-6 h-6" />
    </button>
  )
}
