export function formatDuration(hours: number): string {
  if (hours <= 0) return '—'
  if (hours < 1) return `${Math.round(hours * 60)}m`
  if (hours % 1 === 0) return `${hours}h`
  const h = Math.floor(hours)
  const m = Math.round((hours - h) * 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleString()
}

export function formatNumber(n: number): string {
  return n.toLocaleString()
}

export function formatSeconds(s: number): string {
  if (s < 0) return '—'
  if (s < 60) return `${s.toFixed(1)}s`
  const min = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  if (min < 60) return sec > 0 ? `${min}m ${sec}s` : `${min}m`
  const hr = Math.floor(min / 60)
  const rm = min % 60
  return rm > 0 ? `${hr}h ${rm}m` : `${hr}h`
}

export function formatPercent(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}
