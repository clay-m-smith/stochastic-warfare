/**
 * Generated from the production FastAPI OpenAPI document.
 * Do not edit by hand. Run:
 *   uv run --no-sync python scripts/generate_openapi_types.py
 * OpenAPI SHA-256: dd15e158e72147a64c86bd568156c9f2e3ed208869fb6b76a96908eadae843c8
 */

export interface OpenApiComponents {
  "schemas": {
    "AnalyticsSummary": {
      "casualties"?: OpenApiComponents["schemas"]["CasualtyAnalytics"];
      "engagements"?: OpenApiComponents["schemas"]["EngagementAnalytics"];
      "morale"?: OpenApiComponents["schemas"]["MoraleAnalytics"];
      "suppression"?: OpenApiComponents["schemas"]["SuppressionAnalytics"];
    };
    "BatchDetail": {
      "base_seed": number;
      "batch_id": string;
      "completed_at"?: string | null;
      "completed_iterations"?: number;
      "created_at": string;
      "error_message"?: string | null;
      "max_ticks": number;
      "metrics"?: { [key: string]: unknown } | null;
      "num_iterations": number;
      "ordered_metrics"?: Array<string>;
      "provenance"?: { [key: string]: unknown } | null;
      "raw_metrics"?: { [key: string]: Array<number> } | null;
      "scenario_name": string;
      "status": OpenApiComponents["schemas"]["RunStatus"];
    };
    "BatchSubmitRequest": {
      "base_seed"?: number;
      "config_overrides"?: OpenApiComponents["schemas"]["CalibrationSchema"];
      "max_ticks"?: number;
      "metrics"?: Array<string> | null;
      "num_iterations"?: number;
      "scenario": string;
    };
    "BatchSubmitResponse": {
      "batch_id": string;
      "status"?: OpenApiComponents["schemas"]["RunStatus"];
    };
    "CalibrationSchema": {
      "altitude_sickness_rate"?: number;
      "altitude_sickness_threshold_m"?: number;
      "c2_min_effectiveness"?: number;
      "cbrn_arrhenius_ea"?: number;
      "cbrn_inversion_multiplier"?: number;
      "cbrn_uv_degradation_rate"?: number;
      "cbrn_washout_coefficient"?: number;
      "cloud_ceiling_min_attack_m"?: number;
      "cold_casualty_base_rate"?: number;
      "deception_phantom_count"?: number;
      "defensive_sides"?: Array<string>;
      "degraded_equipment_threshold"?: number;
      "destruction_threshold"?: number;
      "dew_disable_threshold"?: number;
      "dig_in_ticks"?: number;
      "disable_threshold"?: number;
      "drone_provocation_prob"?: number | null;
      "enable_acoustic_layers"?: boolean;
      "enable_air_combat_environment"?: boolean;
      "enable_air_routing"?: boolean;
      "enable_all_modern"?: boolean;
      "enable_ammo_gate"?: boolean;
      "enable_bridge_capacity"?: boolean;
      "enable_c2_friction"?: boolean;
      "enable_carrier_ops"?: boolean;
      "enable_cbrn_environment"?: boolean;
      "enable_command_hierarchy"?: boolean;
      "enable_detection_culling"?: boolean;
      "enable_em_propagation"?: boolean;
      "enable_environmental_fatigue"?: boolean;
      "enable_equipment_stress"?: boolean;
      "enable_event_feedback"?: boolean;
      "enable_fire_zones"?: boolean;
      "enable_fog_of_war"?: boolean;
      "enable_fuel_consumption"?: boolean;
      "enable_human_factors"?: boolean;
      "enable_ice_crossing"?: boolean;
      "enable_lod"?: boolean;
      "enable_mine_persistence"?: boolean;
      "enable_missile_routing"?: boolean;
      "enable_nvg_detection"?: boolean;
      "enable_obscurants"?: boolean;
      "enable_obstacle_effects"?: boolean;
      "enable_parallel_detection"?: boolean;
      "enable_scan_scheduling"?: boolean;
      "enable_sea_state_ops"?: boolean;
      "enable_seasonal_effects"?: boolean;
      "enable_sensing_aware_standoff"?: boolean;
      "enable_soa"?: boolean;
      "enable_space_effects"?: boolean;
      "enable_thermal_crossover"?: boolean;
      "enable_unconventional_warfare"?: boolean;
      "engagement_concealment_threshold"?: number;
      "fire_damage_per_tick"?: number;
      "formation_spacing_m"?: number;
      "gas_casualty_floor"?: number;
      "gas_protection_scaling"?: number;
      "guerrilla_disengage_threshold"?: number;
      "heat_casualty_base_rate"?: number;
      "hit_probability_modifier"?: number;
      "human_shield_pk_reduction"?: number;
      "iads_degradation_rate"?: number | null;
      "icing_maneuver_penalty"?: number;
      "icing_power_penalty"?: number;
      "icing_radar_penalty_db"?: number;
      "jammer_coverage_mult"?: number;
      "lod_distant_interval"?: number;
      "lod_hysteresis_ticks"?: number;
      "lod_nearby_interval"?: number;
      "max_engagers_per_side"?: number;
      "misinterpretation_radius_m"?: number;
      "mopp_comms_factor_4"?: number;
      "mopp_fov_reduction_4"?: number;
      "mopp_reload_factor_4"?: number;
      "morale"?: OpenApiComponents["schemas"]["MoraleCalibration"];
      "morale_degrade_rate_modifier"?: number;
      "night_thermal_floor"?: number;
      "observation_decay_rate"?: number;
      "order_misinterpretation_base"?: number;
      "order_propagation_delay_sigma"?: number;
      "planning_available_time_s"?: number;
      "posture_blast_protection"?: { [key: string]: number } | null;
      "posture_frag_protection"?: { [key: string]: number } | null;
      "rain_attenuation_factor"?: number;
      "retreat_distance_m"?: number;
      "roe_level"?: "WEAPONS_HOLD" | "WEAPONS_TIGHT" | "WEAPONS_FREE" | null;
      "rout_cascade_base_chance"?: number | null;
      "rout_cascade_radius_m"?: number | null;
      "rout_cascade_shaken_susceptibility"?: number | null;
      "sam_suppression_modifier"?: number;
      "sead_arm_effectiveness"?: number | null;
      "sead_effectiveness"?: number | null;
      "side_overrides"?: { [key: string]: OpenApiComponents["schemas"]["SideCalibration"] };
      "sigint_detection_bonus"?: number;
      "stealth_detection_penalty"?: number;
      "stratagem_concentration_bonus"?: number;
      "stratagem_deception_bonus"?: number;
      "stratagem_duration_ticks"?: number;
      "subsystem_weibull_shapes"?: { [key: string]: number };
      "target_selection_mode"?: "closest" | "nearest" | "threat_scored";
      "target_size_modifier"?: number;
      "target_value_weights"?: { [key: string]: number } | null;
      "thermal_contrast"?: number;
      "victory_weights"?: { [key: string]: number } | null;
      "visibility_m"?: number | null;
      "wave_interval_s"?: number;
      "weapon_assignments"?: { [key: string]: string };
      "wind_accuracy_penalty_scale"?: number;
      "wind_bvr_missile_speed_mps"?: number;
    };
    "CasualtyAnalytics": {
      "groups"?: Array<OpenApiComponents["schemas"]["CasualtyGroup"]>;
      "total"?: number;
    };
    "CasualtyGroup": {
      "count"?: number;
      "label": string;
      "side"?: string;
    };
    "CommanderInfo": {
      "description"?: string;
      "display_name"?: string;
      "profile_id": string;
      "traits"?: { [key: string]: number };
    };
    "CompareRequest": {
      "alpha"?: number;
      "base_seed"?: number;
      "label_a"?: string;
      "label_b"?: string;
      "max_ticks"?: number;
      "metrics"?: Array<string> | null;
      "num_iterations"?: number;
      "overrides_a"?: OpenApiComponents["schemas"]["CalibrationSchema"];
      "overrides_b"?: OpenApiComponents["schemas"]["CalibrationSchema"];
      "scenario": string;
    };
    "ContactSource": "NONE" | "NON_FOW_LOCAL_OBSERVATION" | "FOW_OBSERVER_WITNESS" | "FOW_OBSERVER_TRACK_SUPPORT";
    "DoctrineCompareRequest": {
      "base_seed"?: number;
      "max_ticks"?: number;
      "metrics"?: Array<string> | null;
      "num_iterations"?: number;
      "scenario": string;
      "variants": Array<OpenApiComponents["schemas"]["DoctrineVariantRequest"]>;
    };
    "DoctrineCompareResult": {
      "base_seed": number;
      "max_ticks": number;
      "num_iterations": number;
      "ordered_metrics": Array<string>;
      "results"?: Array<OpenApiComponents["schemas"]["DoctrineVariantResult"]>;
      "scenario": string;
      "seeds": Array<number>;
    };
    "DoctrineMetricResult": {
      "mean": number;
      "metric": string;
      "std": number;
      "values": Array<number>;
    };
    "DoctrineSideAssignmentRequest": {
      "school_id": string;
      "side": string;
    };
    "DoctrineVariantRequest": {
      "assignments": Array<OpenApiComponents["schemas"]["DoctrineSideAssignmentRequest"]>;
      "calibration_patch"?: OpenApiComponents["schemas"]["CalibrationSchema"];
      "variant_id": string;
    };
    "DoctrineVariantResult": {
      "assignments": Array<OpenApiComponents["schemas"]["DoctrineSideAssignmentRequest"]>;
      "batch": { [key: string]: unknown };
      "metrics": Array<OpenApiComponents["schemas"]["DoctrineMetricResult"]>;
      "variant_id": string;
    };
    "EffectiveRangeBasis": "AUTHORED" | "LEGACY_DERIVED_80_PERCENT_OF_MAX";
    "EngagementAnalytics": {
      "by_type"?: Array<OpenApiComponents["schemas"]["EngagementTypeGroup"]>;
      "total"?: number;
    };
    "EngagementTypeGroup": {
      "count"?: number;
      "hit_rate"?: number;
      "type": string;
    };
    "EraInfo": {
      "disabled_modules"?: Array<string>;
      "name": string;
      "value": string;
    };
    "EventItem": {
      "data"?: { [key: string]: unknown };
      "event_type": string;
      "source"?: string;
      "tick": number;
    };
    "EventsResponse": {
      "events"?: Array<OpenApiComponents["schemas"]["EventItem"]>;
      "limit"?: number;
      "offset"?: number;
      "total"?: number;
    };
    "FireControlSource": "NONE" | "DIRECT_VISUAL" | "SENSOR_ATTACHMENT";
    "ForcesResponse": {
      "sides"?: { [key: string]: unknown };
    };
    "FramesResponse": {
      "frames"?: Array<OpenApiComponents["schemas"]["ReplayFrame"]>;
      "scope"?: OpenApiComponents["schemas"]["TargetingExposureScope"];
      "total_frames"?: number;
      "viewer_side"?: string | null;
    };
    "GovernedPerformanceFlag": "enable_detection_culling" | "enable_scan_scheduling" | "enable_lod" | "enable_soa" | "enable_parallel_detection";
    "HTTPValidationError": {
      "detail"?: Array<OpenApiComponents["schemas"]["ValidationError"]>;
    };
    "HealthLiveResponse": {
      "status"?: string;
    };
    "HealthReadyResponse": {
      "db_connected"?: boolean;
      "scenario_count"?: number;
      "status"?: string;
      "unit_count"?: number;
      "version"?: string;
    };
    "HealthResponse": {
      "scenario_count"?: number;
      "status"?: string;
      "unit_count"?: number;
      "version"?: string;
    };
    "HistoricalClaimDisposition": "production_validated" | "current_engine_regression_only" | "unsupported";
    "HistoricalValidationClaim": {
      "accepted_artifact_path": string | null;
      "accepted_study_id": string | null;
      "claim_id": string;
      "current_engine_regression_evidence": boolean;
      "disposition": OpenApiComponents["schemas"]["HistoricalClaimDisposition"];
      "event_scope": string;
      "intended_use": string;
      "limitation": string;
      "metric_scope": Array<string>;
      "reason_codes": Array<string>;
    };
    "HistoricalValidationSummary": {
      "accepted_claim_ids": Array<string>;
      "aggregate_disposition": OpenApiComponents["schemas"]["HistoricalClaimDisposition"];
      "claims": Array<OpenApiComponents["schemas"]["HistoricalValidationClaim"]>;
      "current_engine_regression_evidence": boolean;
      "ledger_sha256": string;
    };
    "MapUnitFrame": {
      "ammo_pct"?: number;
      "domain"?: number;
      "engaged"?: boolean;
      "fuel_pct"?: number;
      "heading"?: number;
      "health"?: number;
      "id": string;
      "morale"?: number;
      "posture"?: string;
      "sensor_range"?: number;
      "side": string;
      "status"?: number;
      "suppression"?: number;
      "type"?: string;
      "x": number;
      "y": number;
    };
    "MoraleAnalytics": {
      "timeline"?: Array<OpenApiComponents["schemas"]["MoraleTimelinePoint"]>;
    };
    "MoraleCalibration": {
      "base_degrade_rate"?: number;
      "base_recover_rate"?: number;
      "casualty_weight"?: number;
      "check_interval"?: number;
      "cohesion_weight"?: number;
      "degrade_rate_modifier"?: number;
      "force_ratio_weight"?: number;
      "leadership_weight"?: number;
      "suppression_weight"?: number;
      "transition_cooldown_s"?: number;
      "use_continuous_time"?: boolean;
    };
    "MoraleTimelinePoint": {
      "broken"?: number;
      "routed"?: number;
      "shaken"?: number;
      "steady"?: number;
      "surrendered"?: number;
      "tick": number;
    };
    "NarrativeResponse": {
      "narrative"?: string;
      "tick_count"?: number;
    };
    "ObjectiveInfo": {
      "id": string;
      "radius"?: number;
      "x": number;
      "y": number;
    };
    "PerformanceFlagClassification": "semantics_preserving_execution_optimization" | "model_fidelity_approximation";
    "PerformanceFlagSupportDisposition": "supported_exact_validated" | "unsupported_failed_semantic_validation";
    "PerformanceFlagSupportInfo": {
      "classification": OpenApiComponents["schemas"]["PerformanceFlagClassification"];
      "evidence_manifest_artifact_sha256": string;
      "evidence_plan_id": string;
      "flag": OpenApiComponents["schemas"]["GovernedPerformanceFlag"];
      "required_meaning": string;
      "retained_shard_status": OpenApiComponents["schemas"]["RetainedSemanticVerdict"];
      "support_disposition": OpenApiComponents["schemas"]["PerformanceFlagSupportDisposition"];
    };
    "PrivilegedEngagementRevalidationOutcome": {
      "ammunition_id": string;
      "battle_id": string;
      "consumable": boolean;
      "disposition": OpenApiComponents["schemas"]["TargetingDisposition"];
      "engine_tick": number;
      "fog_of_war_enabled": boolean;
      "logical_time_s": number;
      "revalidation_passed": boolean;
      "shooter_id": string;
      "target_id": string;
      "weapon_id": string;
      "weapon_modeled_role": OpenApiComponents["schemas"]["WeaponModeledRole"];
      "weapon_source_equipment_index": number;
    };
    "PrivilegedObserverTrackSupportEvidence": {
      "covariance": [[number, number, number, number], [number, number, number, number], [number, number, number, number], [number, number, number, number]];
      "fusion_track_id": string;
      "identity": OpenApiComponents["schemas"]["PrivilegedObserverTrackSupportIdentity"];
      "native_due_ordinal": number;
      "native_period": number;
      "native_phase_residue": number;
      "observation_ordinal": number;
      "observation_time_s": number;
      "position_m": [number, number];
      "projection_ordinal": number;
      "projection_time_s": number;
      "sensor_type": "RADAR";
      "velocity_mps": [number, number];
    };
    "PrivilegedObserverTrackSupportIdentity": {
      "modeled_role": "airborne_fire_control_radar" | "airborne_ground_fire_control_radar" | "airborne_multi_domain_fire_control_radar" | "fire_control_radar" | "ground_air_defense_fire_control_radar" | "naval_fire_control_radar" | "naval_air_defense_fire_control_radar";
      "observer_unit_id": string;
      "reporting_side": string;
      "sensor_id": string;
      "source_equipment_index": number;
      "target_id": string;
    };
    "PrivilegedTargetingDecision": {
      "ammunition_id": string | null;
      "authorized_standoff_m": number;
      "battle_id": string;
      "consumable": boolean;
      "contact_range_m": number;
      "contact_sensor_id": string | null;
      "contact_sensor_modeled_role": OpenApiComponents["schemas"]["SensorModeledRole"] | null;
      "contact_sensor_source_equipment_index": number | null;
      "contact_source": OpenApiComponents["schemas"]["ContactSource"];
      "contact_time_s": number | null;
      "disposition": OpenApiComponents["schemas"]["TargetingDisposition"];
      "distance_m": number;
      "effective_range_basis": OpenApiComponents["schemas"]["EffectiveRangeBasis"] | null;
      "engagement_solution_valid": boolean;
      "engine_tick": number;
      "fire_control_range_m": number;
      "fire_control_sensor_id": string | null;
      "fire_control_sensor_modeled_role": OpenApiComponents["schemas"]["SensorModeledRole"] | null;
      "fire_control_sensor_source_equipment_index": number | null;
      "fire_control_source": OpenApiComponents["schemas"]["FireControlSource"];
      "fog_of_war_enabled": boolean;
      "hold_authorized": boolean;
      "legacy_derived_reference_range_m": number;
      "logical_time_s": number;
      "observer_track_support": OpenApiComponents["schemas"]["PrivilegedObserverTrackSupportEvidence"] | null;
      "observing_unit_id": string | null;
      "ordinal": number;
      "physical_max_range_m": number;
      "predictive_effective_range_m": number;
      "sensing_aware_standoff_enabled": boolean;
      "sensing_range_m": number;
      "sensing_sensor_id": string | null;
      "sensing_sensor_modeled_role": OpenApiComponents["schemas"]["SensorModeledRole"] | null;
      "sensing_sensor_source_equipment_index": number | null;
      "shooter_domain": string;
      "shooter_id": string;
      "shooter_side": string;
      "target_domain": string | null;
      "target_id": string | null;
      "target_side": string | null;
      "visibility_bound_m": number;
      "weapon_id": string | null;
      "weapon_modeled_role": OpenApiComponents["schemas"]["WeaponModeledRole"] | null;
      "weapon_source_equipment_index": number | null;
    };
    "PublicIdentificationLevel": "UNKNOWN" | "DETECTED" | "CLASSIFIED" | "IDENTIFIED";
    "PublicTrackStatus": "TENTATIVE" | "CONFIRMED" | "COASTING" | "STALE" | "LOST";
    "ReplayFrame": {
      "detected"?: { [key: string]: Array<string> };
      "scope"?: OpenApiComponents["schemas"]["TargetingExposureScope"];
      "side_targeting"?: Array<OpenApiComponents["schemas"]["SideFowTargetingDecision"]>;
      "side_targeting_outcomes"?: Array<OpenApiComponents["schemas"]["SideFowEngagementRevalidationOutcome"]>;
      "targeting"?: Array<OpenApiComponents["schemas"]["PrivilegedTargetingDecision"]>;
      "targeting_outcomes"?: Array<OpenApiComponents["schemas"]["PrivilegedEngagementRevalidationOutcome"]>;
      "tick": number;
      "tracks"?: Array<OpenApiComponents["schemas"]["SideFowPublicTrack"]>;
      "units"?: Array<OpenApiComponents["schemas"]["MapUnitFrame"]>;
      "viewer_side"?: string | null;
    };
    "RetainedSemanticVerdict": "PASS" | "FAIL";
    "RunDetail": {
      "completed_at"?: string | null;
      "config_overrides"?: { [key: string]: unknown };
      "created_at": string;
      "error_message"?: string | null;
      "max_ticks": number;
      "result"?: { [key: string]: unknown } | null;
      "run_id": string;
      "scenario_name": string;
      "scenario_path": string;
      "seed": number;
      "started_at"?: string | null;
      "status": OpenApiComponents["schemas"]["RunStatus"];
    };
    "RunFromConfigRequest": {
      "config": { [key: string]: unknown };
      "max_ticks"?: number;
      "seed"?: number;
    };
    "RunStatus": "pending" | "running" | "completed" | "failed" | "cancelled";
    "RunSubmitRequest": {
      "config_overrides"?: OpenApiComponents["schemas"]["CalibrationSchema"];
      "frame_interval"?: number | null;
      "max_ticks"?: number;
      "scenario": string;
      "seed"?: number;
    };
    "RunSubmitResponse": {
      "run_id": string;
      "status"?: OpenApiComponents["schemas"]["RunStatus"];
    };
    "RunSummary": {
      "completed_at"?: string | null;
      "created_at": string;
      "error_message"?: string | null;
      "run_id": string;
      "scenario_name": string;
      "seed": number;
      "status": OpenApiComponents["schemas"]["RunStatus"];
    };
    "ScenarioDetail": {
      "config"?: { [key: string]: unknown };
      "force_summary"?: { [key: string]: unknown };
      "historical_validation": OpenApiComponents["schemas"]["HistoricalValidationSummary"];
      "name": string;
    };
    "ScenarioSummary": {
      "display_name"?: string;
      "duration_hours"?: number;
      "era"?: string;
      "has_cbrn"?: boolean;
      "has_dew"?: boolean;
      "has_escalation"?: boolean;
      "has_ew"?: boolean;
      "has_schools"?: boolean;
      "has_space"?: boolean;
      "historical_validation": OpenApiComponents["schemas"]["HistoricalValidationSummary"];
      "name": string;
      "sides"?: Array<string>;
      "terrain_type"?: string;
    };
    "SchoolInfo": {
      "description"?: string;
      "display_name"?: string;
      "ooda_multiplier"?: number;
      "risk_tolerance"?: string;
      "school_id": string;
    };
    "SensorModeledRole": "visual_observation" | "night_vision" | "thermal_targeting" | "airborne_fire_control_radar" | "airborne_ground_fire_control_radar" | "airborne_multi_domain_fire_control_radar" | "airborne_maritime_search_radar" | "air_search_radar" | "ship_air_surface_search_radar" | "surface_search_radar" | "ship_surface_search_radar" | "submarine_surface_search_radar" | "ground_surveillance_radar" | "coastal_surveillance_radar" | "fire_control_radar" | "ground_air_defense_fire_control_radar" | "naval_fire_control_radar" | "naval_air_defense_fire_control_radar" | "ground_visual_sight" | "ground_air_defense_optical_sight" | "airborne_visual_sight" | "airborne_ground_visual_targeting" | "airborne_ground_bombsight" | "naval_visual_director" | "naval_air_defense_optical_director" | "naval_lookout" | "ground_night_sight" | "ground_active_ir_sight" | "airborne_low_light_observation" | "individual_night_vision" | "ground_thermal_targeting" | "airborne_ground_thermal_targeting" | "airborne_air_thermal_search" | "airborne_surface_thermal_search" | "radar_warning_esm" | "electronic_support" | "active_sonar" | "passive_sonar";
    "SideCalibration": {
      "cohesion"?: number | null;
      "force_ratio_modifier"?: number | null;
      "formation_spacing_m"?: number | null;
      "hit_probability_modifier"?: number | null;
      "start_x"?: number | null;
      "start_y"?: number | null;
      "target_size_modifier"?: number | null;
    };
    "SideFowEngagementRevalidationOutcome": {
      "battle_id": string;
      "consumable": boolean;
      "disposition": OpenApiComponents["schemas"]["TargetingDisposition"];
      "engine_tick": number;
      "fog_of_war_enabled": boolean;
      "logical_time_s": number;
      "revalidation_passed": boolean;
      "shooter_id": string;
      "target_track_id": string;
      "viewer_side": string;
    };
    "SideFowPublicTrack": {
      "confidence": number;
      "domain_estimate": string | null;
      "easting_m": number;
      "first_detected_time_s": number;
      "identification_level": OpenApiComponents["schemas"]["PublicIdentificationLevel"];
      "last_sensor_contact_time_s": number;
      "northing_m": number;
      "position_uncertainty_m": number;
      "reporting_side": string;
      "specific_estimate": string | null;
      "status": OpenApiComponents["schemas"]["PublicTrackStatus"];
      "track_id": string;
      "type_estimate": string | null;
      "velocity_east_mps": number;
      "velocity_north_mps": number;
    };
    "SideFowTargetingDecision": {
      "authorized_standoff_m": number;
      "battle_id": string;
      "consumable": boolean;
      "contact_source": OpenApiComponents["schemas"]["ContactSource"];
      "contact_time_s": number | null;
      "disposition": OpenApiComponents["schemas"]["TargetingDisposition"];
      "engagement_solution_valid": boolean;
      "engine_tick": number;
      "fog_of_war_enabled": boolean;
      "hold_authorized": boolean;
      "logical_time_s": number;
      "ordinal": number;
      "sensing_aware_standoff_enabled": boolean;
      "shooter_id": string;
      "target_track_id": string | null;
      "viewer_side": string;
    };
    "SnapshotsResponse": {
      "snapshots"?: Array<{ [key: string]: unknown }>;
    };
    "SuppressionAnalytics": {
      "peak_suppressed"?: number;
      "peak_tick"?: number;
      "rout_cascades"?: number;
      "timeline"?: Array<OpenApiComponents["schemas"]["SuppressionTimelinePoint"]>;
    };
    "SuppressionTimelinePoint": {
      "count"?: number;
      "tick": number;
    };
    "SweepRequest": {
      "base_seed"?: number;
      "max_ticks"?: number;
      "metrics"?: Array<string> | null;
      "num_iterations"?: number;
      "parameter_name": string;
      "scenario": string;
      "values": Array<number>;
    };
    "TargetingDisposition": "VALID_STANDOFF_HOLD" | "VALID_ENGAGEMENT_SOLUTION" | "EFFECTIVE_RANGE_UNKNOWN" | "STANDOFF_DISABLED" | "STANDOFF_NOT_SUPPORTED_FOR_ROLE" | "SHOOTER_INACTIVE" | "NO_TARGET" | "TARGET_INACTIVE" | "TARGET_NOT_HOSTILE" | "TARGET_NOT_IN_BATTLE" | "NO_CONTACT" | "STALE_CONTACT" | "CONTACT_OBSERVER_MISMATCH" | "CONTACT_SENSOR_UNAVAILABLE" | "CONTACT_SENSOR_OFFLINE" | "CONTACT_SENSOR_WRONG_DOMAIN" | "CONTACT_RANGE_EXCEEDED" | "LINE_OF_SIGHT_BLOCKED" | "OUTSIDE_SENSOR_FIELD_OF_VIEW" | "VISIBILITY_LIMITED" | "SENSING_RANGE_EXCEEDED" | "NO_USABLE_WEAPON" | "WEAPON_INOPERABLE" | "NO_FIREABLE_AMMUNITION" | "WEAPON_RESERVED" | "TARGET_DOMAIN_UNSUPPORTED" | "UNSUPPORTED_WEAPON_ROLE" | "ROUTED_WEAPON_ROLE" | "NO_COMPATIBLE_FIRE_CONTROL" | "FIRE_CONTROL_SENSOR_OFFLINE" | "FIRE_CONTROL_SHOOTER_DOMAIN_UNSUPPORTED" | "FIRE_CONTROL_TARGET_DOMAIN_UNSUPPORTED" | "FIRE_CONTROL_RANGE_EXCEEDED" | "OUTSIDE_PHYSICAL_RANGE" | "OUTSIDE_EFFECTIVE_RANGE";
    "TargetingExposureScope": "PRIVILEGED_ENGINE" | "SIDE_FOW";
    "TerrainResponse": {
      "cell_size"?: number;
      "elevation"?: Array<Array<number>>;
      "extent"?: Array<number>;
      "height_cells"?: number;
      "land_cover"?: Array<Array<number>>;
      "objectives"?: Array<OpenApiComponents["schemas"]["ObjectiveInfo"]>;
      "origin_easting"?: number;
      "origin_northing"?: number;
      "width_cells"?: number;
    };
    "UnitDetail": {
      "definition"?: { [key: string]: unknown };
      "unit_type": string;
    };
    "UnitSummary": {
      "category"?: string;
      "crew_size"?: number;
      "display_name"?: string;
      "domain"?: string;
      "era"?: string;
      "max_speed"?: number;
      "unit_type": string;
    };
    "ValidateConfigRequest": {
      "config": { [key: string]: unknown };
    };
    "ValidateConfigResponse": {
      "errors"?: Array<string>;
      "valid"?: boolean;
    };
    "ValidationError": {
      "ctx"?: { [key: string]: unknown };
      "input"?: unknown;
      "loc": Array<string | number>;
      "msg": string;
      "type": string;
    };
    "WeaponDetail": {
      "definition"?: { [key: string]: unknown };
      "weapon_id": string;
    };
    "WeaponModeledRole": "ground_direct_fire" | "air_defense_gun" | "naval_gunfire" | "naval_air_defense_gun" | "field_artillery" | "mortar_fire" | "rocket_artillery" | "assault_rifle" | "muzzle_loading_musket" | "bolt_action_rifle" | "semi_automatic_rifle" | "sniper_rifle" | "anti_materiel_rifle" | "submachine_gun" | "light_machine_gun" | "general_purpose_machine_gun" | "heavy_machine_gun" | "individual_grenade_launcher" | "automatic_grenade_launcher" | "hand_grenade" | "melee" | "ancient_projectile" | "anti_armor" | "air_defense_missile" | "air_to_air_missile" | "air_to_ground_missile" | "anti_ship_missile" | "multi_role_vls" | "bomb_delivery" | "aircraft_gun" | "torpedo" | "anti_submarine" | "close_in_defense" | "directed_energy" | "incendiary_projector";
    "WeaponSummary": {
      "caliber_mm"?: number;
      "category"?: string;
      "display_name"?: string;
      "max_range_m"?: number;
      "weapon_id": string;
    };
  };
}

export type OpenApiSchema<
  Name extends keyof OpenApiComponents["schemas"],
> = OpenApiComponents["schemas"][Name]

/** Response view after FastAPI serializes declared defaults. */
export type OpenApiMaterializedSchema<
  Name extends keyof OpenApiComponents["schemas"],
> = Required<OpenApiSchema<Name>>

export interface OpenApiPaths {
  "/api/analysis/compare": {
    "post": {
      "parameters"?: never;
      "requestBody": {
        "application/json": OpenApiComponents["schemas"]["CompareRequest"];
      };
      "responses": {
        "200": {
          "application/json": { [key: string]: unknown };
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/analysis/doctrine-compare": {
    "post": {
      "parameters"?: never;
      "requestBody": {
        "application/json": OpenApiComponents["schemas"]["DoctrineCompareRequest"];
      };
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["DoctrineCompareResult"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/analysis/sweep": {
    "post": {
      "parameters"?: never;
      "requestBody": {
        "application/json": OpenApiComponents["schemas"]["SweepRequest"];
      };
      "responses": {
        "200": {
          "application/json": { [key: string]: unknown };
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/analysis/tempo/{run_id}": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
        "query": {
          "side"?: string | null;
          "window_s"?: number;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": { [key: string]: unknown };
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/health": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["HealthResponse"];
        };
      };
    };
  };
  "/api/health/live": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["HealthLiveResponse"];
        };
      };
    };
  };
  "/api/health/ready": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["HealthReadyResponse"];
        };
      };
    };
  };
  "/api/meta/commanders": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["CommanderInfo"]>;
        };
      };
    };
  };
  "/api/meta/doctrines": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<{ [key: string]: unknown }>;
        };
      };
    };
  };
  "/api/meta/eras": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["EraInfo"]>;
        };
      };
    };
  };
  "/api/meta/performance-flags": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["PerformanceFlagSupportInfo"]>;
        };
      };
    };
  };
  "/api/meta/schools": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["SchoolInfo"]>;
        };
      };
    };
  };
  "/api/meta/terrain-types": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<string>;
        };
      };
    };
  };
  "/api/meta/weapons": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["WeaponSummary"]>;
        };
      };
    };
  };
  "/api/meta/weapons/{weapon_id}": {
    "get": {
      "parameters": {
        "path": {
          "weapon_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["WeaponDetail"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs": {
    "get": {
      "parameters": {
        "query": {
          "limit"?: number;
          "offset"?: number;
          "scenario"?: string | null;
          "status"?: string | null;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["RunSummary"]>;
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
    "post": {
      "parameters"?: never;
      "requestBody": {
        "application/json": OpenApiComponents["schemas"]["RunSubmitRequest"];
      };
      "responses": {
        "202": {
          "application/json": OpenApiComponents["schemas"]["RunSubmitResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/batch": {
    "post": {
      "parameters"?: never;
      "requestBody": {
        "application/json": OpenApiComponents["schemas"]["BatchSubmitRequest"];
      };
      "responses": {
        "202": {
          "application/json": OpenApiComponents["schemas"]["BatchSubmitResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/batch/{batch_id}": {
    "get": {
      "parameters": {
        "path": {
          "batch_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["BatchDetail"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/from-config": {
    "post": {
      "parameters"?: never;
      "requestBody": {
        "application/json": OpenApiComponents["schemas"]["RunFromConfigRequest"];
      };
      "responses": {
        "202": {
          "application/json": OpenApiComponents["schemas"]["RunSubmitResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}": {
    "delete": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "204": never;
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["RunDetail"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/analytics/casualties": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
        "query": {
          "group_by"?: string;
          "side"?: string | null;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["CasualtyAnalytics"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/analytics/engagements": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["EngagementAnalytics"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/analytics/morale": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["MoraleAnalytics"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/analytics/summary": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["AnalyticsSummary"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/analytics/suppression": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["SuppressionAnalytics"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/events": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
        "query": {
          "event_type"?: string | null;
          "limit"?: number;
          "offset"?: number;
          "search"?: string | null;
          "side"?: string | null;
          "tick_max"?: number | null;
          "tick_min"?: number | null;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["EventsResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/forces": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["ForcesResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/frames": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
        "query": {
          "end_tick"?: number | null;
          "scope"?: OpenApiComponents["schemas"]["TargetingExposureScope"];
          "side"?: string | null;
          "start_tick"?: number | null;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["FramesResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/narrative": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
        "query": {
          "max_ticks"?: number | null;
          "side"?: string | null;
          "style"?: string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["NarrativeResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/snapshots": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["SnapshotsResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/runs/{run_id}/terrain": {
    "get": {
      "parameters": {
        "path": {
          "run_id": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["TerrainResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/scenarios": {
    "get": {
      "parameters"?: never;
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["ScenarioSummary"]>;
        };
      };
    };
  };
  "/api/scenarios/validate": {
    "post": {
      "parameters"?: never;
      "requestBody": {
        "application/json": OpenApiComponents["schemas"]["ValidateConfigRequest"];
      };
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["ValidateConfigResponse"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/scenarios/{name}": {
    "get": {
      "parameters": {
        "path": {
          "name": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["ScenarioDetail"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/units": {
    "get": {
      "parameters": {
        "query": {
          "category"?: string | null;
          "domain"?: string | null;
          "era"?: string | null;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": Array<OpenApiComponents["schemas"]["UnitSummary"]>;
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
  "/api/units/{unit_type}": {
    "get": {
      "parameters": {
        "path": {
          "unit_type": string;
        };
      };
      "requestBody"?: never;
      "responses": {
        "200": {
          "application/json": OpenApiComponents["schemas"]["UnitDetail"];
        };
        "422": {
          "application/json": OpenApiComponents["schemas"]["HTTPValidationError"];
        };
      };
    };
  };
}

export type AnalyticsSummary = OpenApiComponents["schemas"]["AnalyticsSummary"]
export type BatchDetail = OpenApiComponents["schemas"]["BatchDetail"]
export type BatchSubmitRequest = OpenApiComponents["schemas"]["BatchSubmitRequest"]
export type BatchSubmitResponse = OpenApiComponents["schemas"]["BatchSubmitResponse"]
export type CalibrationSchema = OpenApiComponents["schemas"]["CalibrationSchema"]
export type CasualtyAnalytics = OpenApiComponents["schemas"]["CasualtyAnalytics"]
export type CasualtyGroup = OpenApiComponents["schemas"]["CasualtyGroup"]
export type CommanderInfo = OpenApiComponents["schemas"]["CommanderInfo"]
export type CompareRequest = OpenApiComponents["schemas"]["CompareRequest"]
export type ContactSource = OpenApiComponents["schemas"]["ContactSource"]
export type DoctrineCompareRequest = OpenApiComponents["schemas"]["DoctrineCompareRequest"]
export type DoctrineCompareResult = OpenApiComponents["schemas"]["DoctrineCompareResult"]
export type DoctrineMetricResult = OpenApiComponents["schemas"]["DoctrineMetricResult"]
export type DoctrineSideAssignmentRequest = OpenApiComponents["schemas"]["DoctrineSideAssignmentRequest"]
export type DoctrineVariantRequest = OpenApiComponents["schemas"]["DoctrineVariantRequest"]
export type DoctrineVariantResult = OpenApiComponents["schemas"]["DoctrineVariantResult"]
export type EffectiveRangeBasis = OpenApiComponents["schemas"]["EffectiveRangeBasis"]
export type EngagementAnalytics = OpenApiComponents["schemas"]["EngagementAnalytics"]
export type EngagementTypeGroup = OpenApiComponents["schemas"]["EngagementTypeGroup"]
export type EraInfo = OpenApiComponents["schemas"]["EraInfo"]
export type EventItem = OpenApiComponents["schemas"]["EventItem"]
export type EventsResponse = OpenApiComponents["schemas"]["EventsResponse"]
export type FireControlSource = OpenApiComponents["schemas"]["FireControlSource"]
export type ForcesResponse = OpenApiComponents["schemas"]["ForcesResponse"]
export type FramesResponse = OpenApiComponents["schemas"]["FramesResponse"]
export type GovernedPerformanceFlag = OpenApiComponents["schemas"]["GovernedPerformanceFlag"]
export type HTTPValidationError = OpenApiComponents["schemas"]["HTTPValidationError"]
export type HealthLiveResponse = OpenApiComponents["schemas"]["HealthLiveResponse"]
export type HealthReadyResponse = OpenApiComponents["schemas"]["HealthReadyResponse"]
export type HealthResponse = OpenApiComponents["schemas"]["HealthResponse"]
export type HistoricalClaimDisposition = OpenApiComponents["schemas"]["HistoricalClaimDisposition"]
export type HistoricalValidationClaim = OpenApiComponents["schemas"]["HistoricalValidationClaim"]
export type HistoricalValidationSummary = OpenApiComponents["schemas"]["HistoricalValidationSummary"]
export type MapUnitFrame = OpenApiComponents["schemas"]["MapUnitFrame"]
export type MoraleAnalytics = OpenApiComponents["schemas"]["MoraleAnalytics"]
export type MoraleCalibration = OpenApiComponents["schemas"]["MoraleCalibration"]
export type MoraleTimelinePoint = OpenApiComponents["schemas"]["MoraleTimelinePoint"]
export type NarrativeResponse = OpenApiComponents["schemas"]["NarrativeResponse"]
export type ObjectiveInfo = OpenApiComponents["schemas"]["ObjectiveInfo"]
export type PerformanceFlagClassification = OpenApiComponents["schemas"]["PerformanceFlagClassification"]
export type PerformanceFlagSupportDisposition = OpenApiComponents["schemas"]["PerformanceFlagSupportDisposition"]
export type PerformanceFlagSupportInfo = OpenApiComponents["schemas"]["PerformanceFlagSupportInfo"]
export type PrivilegedEngagementRevalidationOutcome = OpenApiComponents["schemas"]["PrivilegedEngagementRevalidationOutcome"]
export type PrivilegedObserverTrackSupportEvidence = OpenApiComponents["schemas"]["PrivilegedObserverTrackSupportEvidence"]
export type PrivilegedObserverTrackSupportIdentity = OpenApiComponents["schemas"]["PrivilegedObserverTrackSupportIdentity"]
export type PrivilegedTargetingDecision = OpenApiComponents["schemas"]["PrivilegedTargetingDecision"]
export type PublicIdentificationLevel = OpenApiComponents["schemas"]["PublicIdentificationLevel"]
export type PublicTrackStatus = OpenApiComponents["schemas"]["PublicTrackStatus"]
export type ReplayFrame = OpenApiComponents["schemas"]["ReplayFrame"]
export type RetainedSemanticVerdict = OpenApiComponents["schemas"]["RetainedSemanticVerdict"]
export type RunDetail = OpenApiComponents["schemas"]["RunDetail"]
export type RunFromConfigRequest = OpenApiComponents["schemas"]["RunFromConfigRequest"]
export type RunStatus = OpenApiComponents["schemas"]["RunStatus"]
export type RunSubmitRequest = OpenApiComponents["schemas"]["RunSubmitRequest"]
export type RunSubmitResponse = OpenApiComponents["schemas"]["RunSubmitResponse"]
export type RunSummary = OpenApiComponents["schemas"]["RunSummary"]
export type ScenarioDetail = OpenApiComponents["schemas"]["ScenarioDetail"]
export type ScenarioSummary = OpenApiComponents["schemas"]["ScenarioSummary"]
export type SchoolInfo = OpenApiComponents["schemas"]["SchoolInfo"]
export type SensorModeledRole = OpenApiComponents["schemas"]["SensorModeledRole"]
export type SideCalibration = OpenApiComponents["schemas"]["SideCalibration"]
export type SideFowEngagementRevalidationOutcome = OpenApiComponents["schemas"]["SideFowEngagementRevalidationOutcome"]
export type SideFowPublicTrack = OpenApiComponents["schemas"]["SideFowPublicTrack"]
export type SideFowTargetingDecision = OpenApiComponents["schemas"]["SideFowTargetingDecision"]
export type SnapshotsResponse = OpenApiComponents["schemas"]["SnapshotsResponse"]
export type SuppressionAnalytics = OpenApiComponents["schemas"]["SuppressionAnalytics"]
export type SuppressionTimelinePoint = OpenApiComponents["schemas"]["SuppressionTimelinePoint"]
export type SweepRequest = OpenApiComponents["schemas"]["SweepRequest"]
export type TargetingDisposition = OpenApiComponents["schemas"]["TargetingDisposition"]
export type TargetingExposureScope = OpenApiComponents["schemas"]["TargetingExposureScope"]
export type TerrainResponse = OpenApiComponents["schemas"]["TerrainResponse"]
export type UnitDetail = OpenApiComponents["schemas"]["UnitDetail"]
export type UnitSummary = OpenApiComponents["schemas"]["UnitSummary"]
export type ValidateConfigRequest = OpenApiComponents["schemas"]["ValidateConfigRequest"]
export type ValidateConfigResponse = OpenApiComponents["schemas"]["ValidateConfigResponse"]
export type ValidationError = OpenApiComponents["schemas"]["ValidationError"]
export type WeaponDetail = OpenApiComponents["schemas"]["WeaponDetail"]
export type WeaponModeledRole = OpenApiComponents["schemas"]["WeaponModeledRole"]
export type WeaponSummary = OpenApiComponents["schemas"]["WeaponSummary"]
