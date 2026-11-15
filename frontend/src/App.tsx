import { lazy, Suspense } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Landing from './pages/Landing'
import Workspace from './pages/Workspace'
import Analysis from './pages/Analysis'
import Portfolios from './pages/Portfolios'
import Activity from './pages/Activity'
import Report from './pages/Report'
import DataCatalog from './pages/DataCatalog'
import DatasetDetail from './pages/DatasetDetail'
import Docs from './pages/Docs'
import RunPicker from './pages/RunPicker'
import { Spinner } from './components/ui'
const Explorer = lazy(() => import('./pages/Explorer'))

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="workspace" element={<Workspace />} />
        <Route path="explorer" element={<Suspense fallback={<Spinner label="Loading map" />}><Explorer /></Suspense>} />
        <Route path="analysis/:runId" element={<Analysis />} />
        <Route path="portfolios/:runId" element={<Portfolios />} />
        <Route path="data" element={<DataCatalog />} />
        <Route path="data/:datasetId" element={<DatasetDetail />} />
        <Route path="activity/:runId" element={<Activity />} />
        <Route path="reports/:runId" element={<Report />} />
        <Route path="docs" element={<Docs />} />
        <Route path="analysis" element={<RunPicker seg="analysis" />} />
        <Route path="activity" element={<RunPicker seg="activity" />} />
        <Route path="portfolios" element={<RunPicker seg="portfolios" />} />
        <Route path="reports" element={<RunPicker seg="reports" />} />
        <Route path="report" element={<RunPicker seg="reports" />} />
        <Route path="*" element={<div className="mx-auto max-w-3xl px-4 py-16"><h1 className="text-3xl">Page not found</h1><p className="mt-3 text-ivory-dim"><Link className="underline" to="/">Overview</Link> · <Link className="underline" to="/workspace">Workspace</Link> · <Link className="underline" to="/explorer">Explorer</Link></p></div>} />
      </Route>
    </Routes>
  )
}
