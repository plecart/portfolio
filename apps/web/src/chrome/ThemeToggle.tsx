import { strings } from '../strings.ts'
import { MoonIcon, SunIcon } from './icons.tsx'
import { useTheme } from './useTheme.ts'

/**
 * Le bouton de mode de l'entête (spec §3.3) : 36 px, rond, l'icône du mode affiché — l'autre est
 * absente du rendu (§6.2) —, un libellé qui dit le mode visé. `--ink-2`, `--ink` au survol. La
 * bascule est instantanée (spec §4.6 ; brief de #18, décision 10) : `useTheme`.
 */
export function ThemeToggle() {
  const { mode, toggle } = useTheme()

  return (
    <button
      type="button"
      aria-label={mode === 'dark' ? strings.switchToLight : strings.switchToDark}
      onClick={toggle}
      className="flex size-9 items-center justify-center rounded-full text-(--ink-2) transition-colors hover:text-(--ink)"
    >
      {mode === 'dark' ? <MoonIcon /> : <SunIcon />}
    </button>
  )
}
