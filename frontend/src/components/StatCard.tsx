interface StatCardProps {
  label: string
  value: string | number
  className?: string
}

export function StatCard({ label, value, className = '' }: StatCardProps) {
  return (
    <div className={`rounded-lg bg-white p-4 shadow dark:bg-gray-800 ${className}`}>
      <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold text-gray-900 dark:text-gray-100">{value}</dd>
    </div>
  )
}
