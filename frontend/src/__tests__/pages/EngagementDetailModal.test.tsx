import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EngagementDetailModal } from '../../pages/runs/tabs/EngagementDetailModal'
import type { EventItem } from '../../types/api'

const MOCK_EVENT: EventItem = {
  tick: 42,
  event_type: 'EngagementEvent',
  source: 'combat.direct_fire',
  data: {
    attacker_id: 'm1a2_1',
    attacker_side: 'blue',
    target_id: 't72_3',
    target_side: 'red',
    weapon_id: 'm256_120mm',
    ammo_type: 'APFSDS',
    range_m: 2100,
    result: 'hit',
    penetrated: true,
    pk: 0.72,
    damage_type: 'kinetic',
    damage_amount: 0.85,
  },
}

describe('EngagementDetailModal', () => {
  it('renders nothing when event is null', () => {
    const { container } = render(
      <EngagementDetailModal event={null} onClose={vi.fn()} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders engagement fields when event provided', () => {
    render(<EngagementDetailModal event={MOCK_EVENT} onClose={vi.fn()} />)
    expect(screen.getByText('Engagement Detail — Tick 42')).toBeInTheDocument()
    expect(screen.getByText('m1a2_1')).toBeInTheDocument()
    expect(screen.getByText('t72_3')).toBeInTheDocument()
    expect(screen.getByText('m256_120mm')).toBeInTheDocument()
    expect(screen.getByText('hit')).toBeInTheDocument()
  })

  it('handles events with missing optional fields', () => {
    const sparseEvent: EventItem = {
      tick: 10,
      event_type: 'EngagementEvent',
      source: 'combat',
      data: { attacker_id: 'unit1', target_id: 'unit2', result: 'miss' },
    }
    render(<EngagementDetailModal event={sparseEvent} onClose={vi.fn()} />)
    expect(screen.getByText('unit1')).toBeInTheDocument()
    expect(screen.getByText('miss')).toBeInTheDocument()
    // Weapon section should not render when no weapon_id/ammo_type
    expect(screen.queryByText('Weapon')).not.toBeInTheDocument()
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    render(<EngagementDetailModal event={MOCK_EVENT} onClose={onClose} />)
    fireEvent.click(screen.getByText('Close'))
    expect(onClose).toHaveBeenCalled()
  })

  it('renders raw JSON in collapsible details', () => {
    render(<EngagementDetailModal event={MOCK_EVENT} onClose={vi.fn()} />)
    expect(screen.getByText('Raw Event Data')).toBeInTheDocument()
  })
})
