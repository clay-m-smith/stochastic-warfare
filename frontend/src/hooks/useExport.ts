import { useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { configToYaml } from '../lib/yamlExport'

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useExport() {
  const navigate = useNavigate()

  const downloadJSON = useCallback((data: unknown, filename: string) => {
    const json = JSON.stringify(data, null, 2)
    triggerDownload(new Blob([json], { type: 'application/json' }), filename)
  }, [])

  const downloadCSV = useCallback((headers: string[], rows: unknown[][], filename: string) => {
    const lines = [
      headers.join(','),
      ...rows.map((row) =>
        row.map((cell) => {
          const s = String(cell ?? '')
          return s.includes(',') || s.includes('"') || s.includes('\n')
            ? `"${s.replace(/"/g, '""')}"`
            : s
        }).join(','),
      ),
    ]
    triggerDownload(new Blob([lines.join('\n')], { type: 'text/csv' }), filename)
  }, [])

  const downloadYAML = useCallback((config: Record<string, unknown>, filename: string) => {
    const text = configToYaml(config)
    triggerDownload(new Blob([text], { type: 'text/yaml' }), filename)
  }, [])

  const printReport = useCallback(
    (runId: string) => {
      navigate(`/runs/${runId}/print`)
    },
    [navigate],
  )

  return { downloadJSON, downloadCSV, downloadYAML, printReport }
}
