import { Badge } from '../../components/Badge'

interface ConfigBadgesProps {
  config: Record<string, unknown>
}

export function ConfigBadges({ config }: ConfigBadgesProps) {
  const badges: { label: string; className: string }[] = []

  if ('ew_config' in config) badges.push({ label: 'Electronic Warfare', className: 'bg-yellow-100 text-yellow-800' })
  if ('cbrn_config' in config) badges.push({ label: 'CBRN', className: 'bg-orange-100 text-orange-800' })
  if ('escalation_config' in config) badges.push({ label: 'Escalation', className: 'bg-red-100 text-red-800' })
  if ('schools_config' in config) badges.push({ label: 'Doctrinal Schools', className: 'bg-purple-100 text-purple-800' })
  if ('space_config' in config) badges.push({ label: 'Space', className: 'bg-indigo-100 text-indigo-800' })

  if (badges.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {badges.map((b) => (
        <Badge key={b.label} className={b.className}>
          {b.label}
        </Badge>
      ))}
    </div>
  )
}
