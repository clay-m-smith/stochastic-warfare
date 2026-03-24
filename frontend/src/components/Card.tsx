interface CardProps {
  children: React.ReactNode
  onClick?: () => void
  className?: string
}

export function Card({ children, onClick, className = '' }: CardProps) {
  return (
    <div
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick()
        }
      } : undefined}
      className={`rounded-lg bg-white p-4 shadow hover:ring-2 hover:ring-blue-300 transition-shadow dark:bg-gray-800 ${onClick ? 'cursor-pointer' : ''} ${className}`}
    >
      {children}
    </div>
  )
}
