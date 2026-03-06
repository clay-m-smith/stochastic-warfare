import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { Layout } from './components/Layout'
import { AnalysisPage } from './pages/analysis/AnalysisPage'
import { RunConfigPage } from './pages/runs/RunConfigPage'
import { RunDetailPage } from './pages/runs/RunDetailPage'
import { RunListPage } from './pages/runs/RunListPage'
import { ScenarioDetailPage } from './pages/scenarios/ScenarioDetailPage'
import { ScenarioListPage } from './pages/scenarios/ScenarioListPage'
import { UnitCatalogPage } from './pages/units/UnitCatalogPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/scenarios" replace /> },
      { path: 'scenarios', element: <ScenarioListPage /> },
      { path: 'scenarios/:name', element: <ScenarioDetailPage /> },
      { path: 'units', element: <UnitCatalogPage /> },
      { path: 'runs', element: <RunListPage /> },
      { path: 'runs/new', element: <RunConfigPage /> },
      { path: 'runs/:runId', element: <RunDetailPage /> },
      { path: 'analysis', element: <AnalysisPage /> },
    ],
  },
])

export function App() {
  return <RouterProvider router={router} />
}
