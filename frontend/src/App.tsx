import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { Layout } from './components/Layout'
import { LoadingSpinner } from './components/LoadingSpinner'
import { AnalysisPage } from './pages/analysis/AnalysisPage'
import { RunConfigPage } from './pages/runs/RunConfigPage'
import { RunDetailPage } from './pages/runs/RunDetailPage'
import { RunListPage } from './pages/runs/RunListPage'
import { ScenarioDetailPage } from './pages/scenarios/ScenarioDetailPage'
import { ScenarioListPage } from './pages/scenarios/ScenarioListPage'
import { FullscreenMapPage } from './pages/map/FullscreenMapPage'
import { UnitCatalogPage } from './pages/units/UnitCatalogPage'
import { WeaponCatalogPage } from './pages/weapons/WeaponCatalogPage'
import { DoctrineCatalogPage } from './pages/doctrines/DoctrineCatalogPage'

const ScenarioEditorPage = lazy(() =>
  import('./pages/editor/ScenarioEditorPage').then((m) => ({ default: m.ScenarioEditorPage })),
)
const PrintReportPage = lazy(() =>
  import('./pages/runs/PrintReportPage').then((m) => ({ default: m.PrintReportPage })),
)

const LazyFallback = <LoadingSpinner />

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/scenarios" replace /> },
      { path: 'scenarios', element: <ScenarioListPage /> },
      { path: 'scenarios/:name', element: <ScenarioDetailPage /> },
      { path: 'scenarios/:name/edit', element: <Suspense fallback={LazyFallback}><ScenarioEditorPage /></Suspense> },
      { path: 'units', element: <UnitCatalogPage /> },
      { path: 'weapons', element: <WeaponCatalogPage /> },
      { path: 'doctrines', element: <DoctrineCatalogPage /> },
      { path: 'runs', element: <RunListPage /> },
      { path: 'runs/new', element: <RunConfigPage /> },
      { path: 'runs/:runId', element: <RunDetailPage /> },
      { path: 'runs/:runId/print', element: <Suspense fallback={LazyFallback}><PrintReportPage /></Suspense> },
      { path: 'analysis', element: <AnalysisPage /> },
      { path: 'map/:runId', element: <FullscreenMapPage /> },
    ],
  },
])

export function App() {
  return <RouterProvider router={router} />
}
