interface CardProps {
  children: React.ReactNode
  onClick?: () => void
  className?: string
}

export function Card({ children, onClick, className = '' }: CardProps) {
  return (
    <div
      onClick={onClick}
      className={`rounded-lg bg-white p-4 shadow hover:ring-2 hover:ring-blue-300 transition-shadow dark:bg-gray-800 ${onClick ? 'cursor-pointer' : ''} ${className}`}
    >
      {children}
    </div>
  )
}
