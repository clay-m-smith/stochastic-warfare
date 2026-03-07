import yaml from 'js-yaml'
import { useState } from 'react'

interface YamlPreviewProps {
  config: Record<string, unknown>
}

export function YamlPreview({ config }: YamlPreviewProps) {
  const [copied, setCopied] = useState(false)

  const yamlText = yaml.dump(config, { noRefs: true, sortKeys: true, lineWidth: 120 })

  const handleCopy = async () => {
    await navigator.clipboard.writeText(yamlText)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
      <div className="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 px-3 py-2">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">YAML Preview</span>
        <button
          onClick={handleCopy}
          className="text-xs font-medium text-blue-600 hover:text-blue-800"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="max-h-96 overflow-auto p-3 font-mono text-xs text-gray-700 dark:text-gray-300">
        {yamlText}
      </pre>
    </div>
  )
}
