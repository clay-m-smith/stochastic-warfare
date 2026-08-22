import { describe, it, expect, expectTypeOf, vi, beforeEach } from 'vitest'
import { fetchRunTerrain, fetchRunFrames } from '../../api/map'
import type {
  ContactSource,
  PrivilegedObserverTrackSupportEvidence,
  PrivilegedTargetingDecision,
  PrivilegedFramesData,
  RunFramesParams,
  SideFowTargetingDecision,
  SideFowFramesData,
  TargetingDisposition,
} from '../../types/map'

const PRIVILEGED_FRAMES: PrivilegedFramesData = {
  scope: 'PRIVILEGED_ENGINE',
  viewer_side: null,
  frames: [],
  total_frames: 0,
}

const SIDE_FOW_FRAMES: SideFowFramesData = {
  scope: 'SIDE_FOW',
  viewer_side: 'blue/one',
  frames: [],
  total_frames: 0,
}

beforeEach(() => {
  vi.restoreAllMocks()
})

describe('fetchRunTerrain', () => {
  it('fetches terrain from /api/runs/:id/terrain', async () => {
    const terrain = { width_cells: 10, height_cells: 10, cell_size: 100 }
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(terrain), { status: 200 }),
    )
    const result = await fetchRunTerrain('r1')
    expect(result).toEqual(terrain)
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/terrain')
  })

  it('encodes special characters in run id', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), { status: 200 }),
    )
    await fetchRunTerrain('run with space')
    expect(fetch).toHaveBeenCalledWith('/api/runs/run%20with%20space/terrain')
  })
})

describe('fetchRunFrames', () => {
  it('includes every production targeting disposition in the wire union', () => {
    const shooterInactive: TargetingDisposition = 'SHOOTER_INACTIVE'

    expect(shooterInactive).toBe('SHOOTER_INACTIVE')
  })

  it('types privileged observer support without widening the side-safe wire', () => {
    const source: ContactSource = 'FOW_OBSERVER_TRACK_SUPPORT'
    const support: PrivilegedObserverTrackSupportEvidence = {
      identity: {
        reporting_side: 'blue',
        observer_unit_id: 'blue-1',
        source_equipment_index: 3,
        sensor_id: 'fire-control-radar',
        modeled_role: 'fire_control_radar',
        target_id: 'red-1',
      },
      fusion_track_id: 'fow-track-0042',
      sensor_type: 'RADAR',
      observation_ordinal: 1,
      observation_time_s: 25,
      native_period: 2,
      native_phase_residue: 1,
      native_due_ordinal: 3,
      position_m: [0, 500],
      velocity_mps: [0, 0],
      covariance: [
        [100, 0, 0, 0],
        [0, 100, 0, 0],
        [0, 0, 100, 0],
        [0, 0, 0, 100],
      ],
      projection_ordinal: 2,
      projection_time_s: 30,
    }
    type SideCarriesExactSupport =
      'observer_track_support' extends keyof SideFowTargetingDecision
        ? true
        : false

    expect(source).toBe('FOW_OBSERVER_TRACK_SUPPORT')
    expect(support.identity.modeled_role).toBe('fire_control_radar')
    expectTypeOf<PrivilegedTargetingDecision['observer_track_support']>()
      .toEqualTypeOf<PrivilegedObserverTrackSupportEvidence | null>()
    expectTypeOf<SideCarriesExactSupport>().toEqualTypeOf<false>()
  })

  it('fetches frames from /api/runs/:id/frames', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(PRIVILEGED_FRAMES), { status: 200 }),
    )
    const result = await fetchRunFrames('r1')
    expectTypeOf(result).toEqualTypeOf<PrivilegedFramesData>()
    expect(result).toEqual(PRIVILEGED_FRAMES)
    expect(result.scope).toBe('PRIVILEGED_ENGINE')
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/frames')
  })

  it('passes tick range params', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(PRIVILEGED_FRAMES), { status: 200 }),
    )
    await fetchRunFrames('r1', { start_tick: 10, end_tick: 50 })
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/frames?start_tick=10&end_tick=50')
  })

  it('omits unset params', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(PRIVILEGED_FRAMES), { status: 200 }),
    )
    await fetchRunFrames('r1', { start_tick: 5 })
    expect(fetch).toHaveBeenCalledWith('/api/runs/r1/frames?start_tick=5')
  })

  it('can request an explicit privileged scope without a side', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(PRIVILEGED_FRAMES), { status: 200 }),
    )

    await fetchRunFrames('r1', { scope: 'PRIVILEGED_ENGINE' })

    expect(fetch).toHaveBeenCalledWith(
      '/api/runs/r1/frames?scope=PRIVILEGED_ENGINE',
    )
  })

  it('requests a paired SIDE_FOW scope and encoded side', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify(SIDE_FOW_FRAMES), { status: 200 }),
    )

    const result = await fetchRunFrames('r1', {
      scope: 'SIDE_FOW',
      side: 'blue/one',
      start_tick: 10,
    })

    expectTypeOf(result).toEqualTypeOf<SideFowFramesData>()
    expect(result.scope).toBe('SIDE_FOW')
    expect(fetch).toHaveBeenCalledWith(
      '/api/runs/r1/frames?start_tick=10&scope=SIDE_FOW&side=blue%2Fone',
    )
  })

  it('rejects an untrimmed SIDE_FOW side before issuing a request', () => {
    vi.spyOn(globalThis, 'fetch')

    expect(() => fetchRunFrames('r1', {
      scope: 'SIDE_FOW',
      side: ' blue ',
    })).toThrow('require a non-empty trimmed side')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('fails closed on a runtime side without SIDE_FOW scope', () => {
    vi.spyOn(globalThis, 'fetch')
    const invalid = {
      scope: 'PRIVILEGED_ENGINE',
      side: 'blue',
    } as unknown as RunFramesParams

    expect(() => fetchRunFrames('r1', invalid)).toThrow(
      'side is valid only for SIDE_FOW',
    )
    expect(fetch).not.toHaveBeenCalled()
  })

  it('fails closed on an unknown runtime scope', () => {
    vi.spyOn(globalThis, 'fetch')
    const invalid = { scope: 'PUBLIC' } as unknown as RunFramesParams

    expect(() => fetchRunFrames('r1', invalid)).toThrow(
      'unknown targeting exposure scope',
    )
    expect(fetch).not.toHaveBeenCalled()
  })
})
