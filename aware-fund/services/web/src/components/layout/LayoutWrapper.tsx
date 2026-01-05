'use client'

import { useState, useCallback } from 'react'
import { Sidebar, MobileMenuButton } from './Sidebar'
import { Header } from './Header'

interface LayoutWrapperProps {
  children: React.ReactNode
}

export function LayoutWrapper({ children }: LayoutWrapperProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const handleCloseSidebar = useCallback(() => {
    setSidebarOpen(false)
  }, [])

  const handleOpenSidebar = useCallback(() => {
    setSidebarOpen(true)
  }, [])

  return (
    <div className="flex min-h-screen">
      <Sidebar isOpen={sidebarOpen} onClose={handleCloseSidebar} />
      <div className="flex-1 flex flex-col md:ml-64">
        <Header onMenuClick={handleOpenSidebar} />
        <main className="flex-1 p-4 md:p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
