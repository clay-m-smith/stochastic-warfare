import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import type { EventItem } from '../../../types/api'

interface EngagementDetailModalProps {
  event: EventItem | null
  onClose: () => void
}

function Field({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null
  const display = typeof value === 'object' ? JSON.stringify(value) : String(value)
  return (
    <div className="flex justify-between py-0.5">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="font-mono text-gray-900 dark:text-gray-100">{display}</span>
    </div>
  )
}

export function EngagementDetailModal({ event, onClose }: EngagementDetailModalProps) {
  if (!event) return null

  const d = event.data

  return (
    <Dialog open={!!event} onClose={onClose} className="relative z-50">
      <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div className="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel className="mx-auto max-w-lg rounded-xl bg-white p-6 shadow-xl dark:bg-gray-800">
          <DialogTitle className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            Engagement Detail — Tick {event.tick}
          </DialogTitle>

          <div className="mt-4 space-y-3 text-sm">
            {/* Participants */}
            <section>
              <h4 className="mb-1 font-medium text-gray-700 dark:text-gray-300">Participants</h4>
              <div className="rounded border border-gray-200 p-2 dark:border-gray-700">
                <Field label="Attacker" value={d.attacker_id} />
                <Field label="Attacker Side" value={d.attacker_side} />
                <Field label="Target" value={d.target_id} />
                <Field label="Target Side" value={d.target_side} />
              </div>
            </section>

            {/* Weapon */}
            {!!(d.weapon_id || d.ammo_type) && (
              <section>
                <h4 className="mb-1 font-medium text-gray-700 dark:text-gray-300">Weapon</h4>
                <div className="rounded border border-gray-200 p-2 dark:border-gray-700">
                  <Field label="Weapon" value={d.weapon_id} />
                  <Field label="Ammo Type" value={d.ammo_type} />
                  <Field label="Range (m)" value={d.range_m} />
                </div>
              </section>
            )}

            {/* Resolution */}
            <section>
              <h4 className="mb-1 font-medium text-gray-700 dark:text-gray-300">Resolution</h4>
              <div className="rounded border border-gray-200 p-2 dark:border-gray-700">
                <Field label="Result" value={d.result} />
                <Field label="Hit" value={d.hit} />
                <Field label="Penetrated" value={d.penetrated} />
                <Field label="Pk" value={d.pk} />
              </div>
            </section>

            {/* Damage */}
            {!!(d.damage_type || d.damage_amount) && (
              <section>
                <h4 className="mb-1 font-medium text-gray-700 dark:text-gray-300">Damage</h4>
                <div className="rounded border border-gray-200 p-2 dark:border-gray-700">
                  <Field label="Damage Type" value={d.damage_type} />
                  <Field label="Damage Amount" value={d.damage_amount} />
                  <Field label="Location" value={d.location} />
                </div>
              </section>
            )}

            {/* Raw Data */}
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-gray-500 dark:text-gray-400">
                Raw Event Data
              </summary>
              <pre className="mt-1 max-h-48 overflow-auto rounded bg-gray-50 p-2 text-xs dark:bg-gray-900">
                {JSON.stringify(d, null, 2)}
              </pre>
            </details>
          </div>

          <div className="mt-4 flex justify-end">
            <button
              onClick={onClose}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
            >
              Close
            </button>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}
