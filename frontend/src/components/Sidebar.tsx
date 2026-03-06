import { NavLink } from 'react-router-dom'
import { useHealth } from '../hooks/useMeta'

const NAV_ITEMS = [
  { to: '/scenarios', label: 'Scenarios' },
  { to: '/units', label: 'Units' },
  { to: '/runs', label: 'Runs' },
  { to: '/analysis', label: 'Analysis' },
]

interface SidebarProps {
  open: boolean
  onClose: () => void
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const { data: health } = useHealth()

  const sidebar = (
    <aside className="flex h-full w-64 flex-col border-r border-gray-200 bg-white">
      <div className="border-b border-gray-200 px-6 py-4">
        <h2 className="text-lg font-bold text-gray-900">Stochastic Warfare</h2>
        <p className="text-xs text-gray-500">Wargame Simulator</p>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            onClick={onClose}
            className={({ isActive }) =>
              `block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-700 hover:bg-gray-100'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-gray-200 px-6 py-3">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span
            className={`h-2 w-2 rounded-full ${health?.status === 'ok' ? 'bg-green-500' : 'bg-red-500'}`}
          />
          {health
            ? `${health.scenario_count} scenarios, ${health.unit_count} units`
            : 'Connecting...'}
        </div>
        {health?.version && (
          <p className="mt-1 text-xs text-gray-400">v{health.version}</p>
        )}
      </div>
    </aside>
  )

  return (
    <>
      {/* Desktop sidebar: always visible */}
      <div className="fixed left-0 top-0 hidden h-full md:block">
        {sidebar}
      </div>

      {/* Mobile sidebar: overlay */}
      {open && (
        <div className="fixed inset-0 z-30 md:hidden">
          <div className="fixed inset-0 bg-black/30" onClick={onClose} />
          <div className="fixed left-0 top-0 h-full z-40">
            {sidebar}
          </div>
        </div>
      )}
    </>
  )
}
