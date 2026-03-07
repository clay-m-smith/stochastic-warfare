interface EmptyStateProps {
  message: string
}

export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex items-center justify-center py-12 text-gray-500 dark:text-gray-400">
      <p className="text-sm">{message}</p>
    </div>
  )
}
