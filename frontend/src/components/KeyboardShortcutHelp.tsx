import { Dialog } from '@headlessui/react'
import type { ShortcutConfig } from '../hooks/useKeyboardShortcuts'

interface KeyboardShortcutHelpProps {
  open: boolean
  onClose: () => void
  shortcuts: ShortcutConfig[]
}

export function KeyboardShortcutHelp({ open, onClose, shortcuts }: KeyboardShortcutHelpProps) {
  return (
    <Dialog open={open} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto max-w-sm rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="mb-4 text-lg font-semibold text-gray-900">
            Keyboard Shortcuts
          </Dialog.Title>
          <div className="space-y-2">
            {shortcuts.map((s, i) => (
              <div key={i} className="flex items-center justify-between">
                <span className="text-sm text-gray-600">{s.description}</span>
                <kbd className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-800">
                  {s.ctrl ? 'Ctrl+' : ''}{s.key === ' ' ? 'Space' : s.key}
                </kbd>
              </div>
            ))}
          </div>
          <button
            onClick={onClose}
            className="mt-4 w-full rounded-md bg-gray-100 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
          >
            Close
          </button>
        </Dialog.Panel>
      </div>
    </Dialog>
  )
}
