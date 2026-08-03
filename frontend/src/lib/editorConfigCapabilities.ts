export const CONFIG_DEFAULTS: Readonly<Record<string, Readonly<Record<string, unknown>>>> = {
  ew_config: { enable_ew: true },
  cbrn_config: { enable_cbrn: true },
  escalation_config: {},
  dew_config: {},
}

export const CONFIG_CREATION_LIMITATIONS: Readonly<Record<string, string>> = {
  school_config:
    'Adding Doctrinal Schools is unavailable here because production scenario configuration requires exact unit IDs. Use Doctrine Compare for typed per-side variants or author validated YAML with unit_assignments.',
  space_config:
    'Adding Space is unavailable here because production requires explicit catalog constellation IDs. Clone an already configured Space scenario or author validated YAML.',
}

export function configCreationLimitation(key: string): string | undefined {
  return CONFIG_CREATION_LIMITATIONS[key]
}
