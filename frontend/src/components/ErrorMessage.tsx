interface ErrorMessageProps {
  message: string
  onRetry?: () => void
  variant?: 'error' | 'warning' | 'connection'
}

const VARIANT_STYLES = {
  error: { bg: 'bg-red-50 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-400', button: 'text-red-600 hover:text-red-500' },
  warning: { bg: 'bg-yellow-50 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-400', button: 'text-yellow-600 hover:text-yellow-500' },
  connection: { bg: 'bg-gray-50 dark:bg-gray-800', text: 'text-gray-700 dark:text-gray-300', button: 'text-blue-600 hover:text-blue-500' },
}

export function ErrorMessage({ message, onRetry, variant = 'error' }: ErrorMessageProps) {
  const styles = VARIANT_STYLES[variant]
  return (
    <div className={`rounded-md p-4 ${styles.bg}`}>
      {variant === 'connection' && (
        <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">Connection Lost</p>
      )}
      <p className={`text-sm ${styles.text}`}>{message}</p>
      {variant === 'connection' && (
        <p className="mt-1 text-xs text-gray-500">Will retry automatically...</p>
      )}
      {onRetry && (
        <button
          onClick={onRetry}
          className={`mt-2 text-sm font-medium ${styles.button}`}
        >
          Retry
        </button>
      )}
    </div>
  )
}
