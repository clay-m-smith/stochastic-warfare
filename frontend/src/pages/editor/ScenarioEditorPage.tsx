import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import yaml from 'js-yaml'
import { ErrorMessage } from '../../components/ErrorMessage'
import { LoadingSpinner } from '../../components/LoadingSpinner'
import { PageHeader } from '../../components/PageHeader'
import { useScenario } from '../../hooks/useScenarios'
import { useScenarioEditor } from '../../hooks/useScenarioEditor'
import { submitRunFromConfig, validateConfig } from '../../api/editor'
import { GeneralSection } from './GeneralSection'
import { TerrainSection } from './TerrainSection'
import { WeatherSection } from './WeatherSection'
import { ForceEditor } from './ForceEditor'
import { ConfigToggles } from './ConfigToggles'
import { CalibrationSliders } from './CalibrationSliders'
import { YamlPreview } from './YamlPreview'
import { TerrainPreview } from './TerrainPreview'

function EditorContent({ initialConfig, scenarioName }: { initialConfig: Record<string, unknown>; scenarioName: string }) {
  const navigate = useNavigate()
  const { state, dispatch, config } = useScenarioEditor(initialConfig)
  const [submitting, setSubmitting] = useState(false)
  const [validating, setValidating] = useState(false)

  const handleValidate = async () => {
    setValidating(true)
    try {
      const result = await validateConfig(config)
      dispatch({ type: 'SET_VALIDATION', errors: result.errors })
    } catch (e) {
      dispatch({ type: 'SET_VALIDATION', errors: [(e as Error).message] })
    } finally {
      setValidating(false)
    }
  }

  const handleRun = async () => {
    setSubmitting(true)
    try {
      const valResult = await validateConfig(config)
      if (!valResult.valid) {
        dispatch({ type: 'SET_VALIDATION', errors: valResult.errors })
        setSubmitting(false)
        return
      }
      const result = await submitRunFromConfig({ config, seed: 42, max_ticks: 10_000 })
      navigate(`/runs/${result.run_id}`)
    } catch (e) {
      dispatch({ type: 'SET_VALIDATION', errors: [(e as Error).message] })
    } finally {
      setSubmitting(false)
    }
  }

  const handleDownload = () => {
    const yamlText = yaml.dump(config, { noRefs: true, sortKeys: true })
    const blob = new Blob([yamlText], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${(config.name as string) ?? scenarioName ?? 'scenario'}.yaml`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div>
      <PageHeader title={`Edit: ${(config.name as string) ?? scenarioName}`} />

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left column: form sections */}
        <div className="space-y-6 lg:col-span-2">
          <GeneralSection config={config} dispatch={dispatch} />
          <TerrainSection config={config} dispatch={dispatch} />
          <WeatherSection config={config} dispatch={dispatch} />
          <ForceEditor config={config} dispatch={dispatch} />
          <ConfigToggles config={config} dispatch={dispatch} />
          <CalibrationSliders config={config} dispatch={dispatch} />
        </div>

        {/* Right column: previews (sticky) */}
        <div className="space-y-4 lg:sticky lg:top-4 lg:self-start">
          <TerrainPreview config={config} />
          <YamlPreview config={config} />
        </div>
      </div>

      {/* Validation errors */}
      {state.validationErrors.length > 0 && (
        <div className="mt-4 rounded-md bg-red-50 dark:bg-red-900/30 p-4">
          <h4 className="text-sm font-medium text-red-800 dark:text-red-300">Validation Errors</h4>
          <ul className="mt-1 list-inside list-disc text-sm text-red-700 dark:text-red-400">
            {state.validationErrors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Action bar */}
      <div className="mt-6 flex gap-3 border-t border-gray-200 dark:border-gray-700 pt-4">
        <button
          onClick={handleValidate}
          disabled={validating}
          className="rounded-md border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          {validating ? 'Validating...' : 'Validate'}
        </button>
        <button
          onClick={handleRun}
          disabled={submitting}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? 'Submitting...' : 'Run This Config'}
        </button>
        <button
          onClick={handleDownload}
          className="rounded-md border border-gray-300 dark:border-gray-600 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          Download YAML
        </button>
      </div>
    </div>
  )
}

export function ScenarioEditorPage() {
  const { name } = useParams<{ name: string }>()
  const { data: scenario, isLoading, error, refetch } = useScenario(name ?? '')

  if (isLoading) return <LoadingSpinner />
  if (error) return <ErrorMessage message={error.message} onRetry={() => refetch()} />
  if (!scenario) return <ErrorMessage message="Scenario not found." />

  return <EditorContent initialConfig={scenario.config} scenarioName={scenario.name} />
}
