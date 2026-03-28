/** Phase 92 analytics response types — mirrors api/schemas.py */

export interface CasualtyGroup {
  label: string
  count: number
  side: string
}

export interface CasualtyAnalytics {
  groups: CasualtyGroup[]
  total: number
}

export interface SuppressionTimelinePoint {
  tick: number
  count: number
}

export interface SuppressionAnalytics {
  peak_suppressed: number
  peak_tick: number
  rout_cascades: number
  timeline: SuppressionTimelinePoint[]
}

export interface MoraleTimelinePoint {
  tick: number
  steady: number
  shaken: number
  broken: number
  routed: number
  surrendered: number
}

export interface MoraleAnalytics {
  timeline: MoraleTimelinePoint[]
}

export interface EngagementTypeGroup {
  type: string
  count: number
  hit_rate: number
}

export interface EngagementAnalytics {
  by_type: EngagementTypeGroup[]
  total: number
}

export interface AnalyticsSummary {
  casualties: CasualtyAnalytics
  suppression: SuppressionAnalytics
  morale: MoraleAnalytics
  engagements: EngagementAnalytics
}
