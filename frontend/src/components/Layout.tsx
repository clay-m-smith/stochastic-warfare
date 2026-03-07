import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useTheme } from '../hooks/useTheme'

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="flex min-h-screen dark:bg-gray-900">
      {/* Mobile hamburger */}
      <button
        className="fixed left-4 top-4 z-40 rounded-md bg-white p-2 shadow-md dark:bg-gray-800 md:hidden"
        onClick={() => setSidebarOpen(true)}
        aria-label="Open menu"
      >
        <svg className="h-5 w-5 text-gray-700 dark:text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} theme={theme} onToggleTheme={toggleTheme} />
      <main className="flex-1 p-8 pt-16 md:ml-64 md:pt-8">
        <Outlet />
      </main>
    </div>
  )
}
