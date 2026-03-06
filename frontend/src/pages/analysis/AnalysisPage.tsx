import { useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { TabBar } from '../../components/TabBar'
import { BatchPanel } from './BatchPanel'
import { ComparePanel } from './ComparePanel'
import { SweepPanel } from './SweepPanel'

const TABS = [
  { id: 'batch', label: 'Batch MC' },
  { id: 'compare', label: 'A/B Compare' },
  { id: 'sweep', label: 'Sensitivity Sweep' },
]

export function AnalysisPage() {
  const [activeTab, setActiveTab] = useState('batch')

  return (
    <div>
      <PageHeader title="Analysis" />
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />
      <div className="mt-6">
        {activeTab === 'batch' && <BatchPanel />}
        {activeTab === 'compare' && <ComparePanel />}
        {activeTab === 'sweep' && <SweepPanel />}
      </div>
    </div>
  )
}
