interface BadgeProps {
  children: React.ReactNode
  className?: string
}

export function Badge({ children, className = 'bg-gray-500 text-white' }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  )
}
