import { Menu } from '@headlessui/react'

export interface ExportMenuItem {
  label: string
  onClick: () => void
}

interface ExportMenuProps {
  items: ExportMenuItem[]
}

export function ExportMenu({ items }: ExportMenuProps) {
  return (
    <Menu as="div" className="relative inline-block text-left">
      <Menu.Button className="inline-flex items-center rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700">
        Export
        <svg className="-mr-1 ml-1 h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </Menu.Button>

      <Menu.Items className="absolute right-0 z-10 mt-1 w-48 origin-top-right rounded-md bg-white shadow-lg ring-1 ring-black/5 focus:outline-none dark:bg-gray-800 dark:ring-gray-700">
        <div className="py-1">
          {items.map((item) => (
            <Menu.Item key={item.label}>
              {({ active }) => (
                <button
                  className={`block w-full px-4 py-2 text-left text-sm ${
                    active ? 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300'
                  }`}
                  onClick={item.onClick}
                >
                  {item.label}
                </button>
              )}
            </Menu.Item>
          ))}
        </div>
      </Menu.Items>
    </Menu>
  )
}
