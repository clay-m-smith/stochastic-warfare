import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { useDeleteRun } from '../../hooks/useRuns'

interface RunDeleteButtonProps {
  runId: string
}

export function RunDeleteButton({ runId }: RunDeleteButtonProps) {
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const { mutate, isPending } = useDeleteRun()

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        disabled={isPending}
        className="rounded-md border border-red-300 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
      >
        Delete
      </button>
      <ConfirmDialog
        open={open}
        title="Delete Run"
        message="Are you sure you want to delete this run? This action cannot be undone."
        confirmLabel="Delete"
        onConfirm={() => {
          mutate(runId, {
            onSuccess: () => navigate('/runs'),
          })
          setOpen(false)
        }}
        onCancel={() => setOpen(false)}
      />
    </>
  )
}
