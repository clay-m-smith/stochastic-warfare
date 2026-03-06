import yaml from 'js-yaml'

export function configToYaml(config: Record<string, unknown>): string {
  return yaml.dump(config, { noRefs: true, sortKeys: true, lineWidth: 120 })
}
