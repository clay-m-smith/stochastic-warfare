import { useEffect } from 'react'

export interface ShortcutConfig {
  key: string
  ctrl?: boolean
  action: () => void
  description: string
}

export function useKeyboardShortcuts(shortcuts: ShortcutConfig[], enabled: boolean = true) {
  useEffect(() => {
    if (!enabled) return

    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const tag = target?.tagName?.toLowerCase() ?? ''
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return

      for (const shortcut of shortcuts) {
        if (shortcut.ctrl && !e.ctrlKey && !e.metaKey) continue
        if (!shortcut.ctrl && (e.ctrlKey || e.metaKey)) continue
        if (e.key === shortcut.key) {
          e.preventDefault()
          shortcut.action()
          return
        }
      }
    }

    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [shortcuts, enabled])
}
