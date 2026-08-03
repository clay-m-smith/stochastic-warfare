export function CommanderPicker() {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Commander Profiles
      </h3>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Commander selection is unavailable in the scenario editor because the
        current metadata endpoint does not expose the complete era-specific
        catalog. Preserve existing profiles or author validated YAML with a
        canonical commander_profile on every side.
      </p>
    </section>
  )
}
