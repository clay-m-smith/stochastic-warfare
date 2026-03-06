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
    <div className="rounded-lg border border-gray-200 bg-gray-50">
      <div className="flex items-center justify-between border-b border-gray-200 px-3 py-2">
        <span className="text-xs font-medium text-gray-500">YAML Preview</span>
        <button
          onClick={handleCopy}
          className="text-xs font-medium text-blue-600 hover:text-blue-800"
        >
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre className="max-h-96 overflow-auto p-3 font-mono text-xs text-gray-700">
        {yamlText}
      </pre>
    </div>
  )
}
