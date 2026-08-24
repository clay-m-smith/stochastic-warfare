/** Analytics response DTOs derived from FastAPI OpenAPI. */
import type { OpenApiMaterializedSchema } from './openapi.generated'

export type CasualtyGroup = OpenApiMaterializedSchema<'CasualtyGroup'>
export type CasualtyAnalytics = Omit<
  OpenApiMaterializedSchema<'CasualtyAnalytics'>,
  'groups'
> & {
  groups: CasualtyGroup[]
}

export type SuppressionTimelinePoint =
  OpenApiMaterializedSchema<'SuppressionTimelinePoint'>
export type SuppressionAnalytics = Omit<
  OpenApiMaterializedSchema<'SuppressionAnalytics'>,
  'timeline'
> & {
  timeline: SuppressionTimelinePoint[]
}

export type MoraleTimelinePoint =
  OpenApiMaterializedSchema<'MoraleTimelinePoint'>
export type MoraleAnalytics = Omit<
  OpenApiMaterializedSchema<'MoraleAnalytics'>,
  'timeline'
> & {
  timeline: MoraleTimelinePoint[]
}

export type EngagementTypeGroup =
  OpenApiMaterializedSchema<'EngagementTypeGroup'>
export type EngagementAnalytics = Omit<
  OpenApiMaterializedSchema<'EngagementAnalytics'>,
  'by_type'
> & {
  by_type: EngagementTypeGroup[]
}

/** Nested defaults are present after FastAPI response serialization. */
export type AnalyticsSummary = Omit<
  OpenApiMaterializedSchema<'AnalyticsSummary'>,
  'casualties' | 'suppression' | 'morale' | 'engagements'
> & {
  casualties: CasualtyAnalytics
  suppression: SuppressionAnalytics
  morale: MoraleAnalytics
  engagements: EngagementAnalytics
}
