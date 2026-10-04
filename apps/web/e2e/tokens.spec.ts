/**
 * Les jetons de la spec §2 et la base de page, mesurés sur la page servie.
 *
 * Un jeton se lit **résolu** : appliqué à une propriété réelle d'un élément sonde, puis comparé à
 * la valeur que la spec écrit, appliquée de la même façon. Lire la propriété personnalisée brute
 * ne prouverait rien — la compilation réécrit `light-dark()` en bascule de variables
 * (docs/frontend-outillage.md §2.4), et Chrome sérialise à sa manière ce qu'il calcule : seule la
 * valeur calculée des deux côtés se compare.
 */
import { expect, test, type Page } from '@playwright/test'

type Mode = 'light' | 'dark'

/** Un jeton : la propriété qui le résout, sa valeur claire, et sa valeur sombre s'il en a une. */
type SpecToken = { property: string; light: string; dark?: string }

/** Les 32 jetons de la spec §2, valeurs recopiées telles que la spec les écrit. */
const SPEC_TOKENS: Record<string, SpecToken> = {
  // §2.1 — couleurs
  '--bg': { property: 'color', light: '#F3EDE4', dark: '#1C1A17' },
  '--paper': { property: 'color', light: '#FBF8F2', dark: '#2B2724' },
  '--ink': { property: 'color', light: '#2A2622', dark: '#EDE6DA' },
  '--ink-2': { property: 'color', light: '#6B635A', dark: '#A69C8F' },
  '--line': { property: 'color', light: '#DCD3C6', dark: '#3B3631' },
  '--accent': { property: 'color', light: '#B4471F', dark: '#E88A5E' },
  '--postit': { property: 'color', light: '#F4E3A1', dark: '#B59F55' },
  '--postit-ink': { property: 'color', light: '#2A2622', dark: '#1C1A17' },
  '--postit-link': {
    property: 'color',
    light: 'color-mix(in srgb, #B4471F 22%, #F4E3A1)',
    dark: 'color-mix(in srgb, #E88A5E 22%, #B59F55)',
  },
  '--tape': { property: 'color', light: '#E8DFCF', dark: '#3D372F' },
  '--tape-ink': { property: 'color', light: '#2A2622', dark: '#D8CFC0' },
  // §2.2 — échelle typographique
  '--fs-body': { property: 'font-size', light: '16px' },
  '--fs-small': { property: 'font-size', light: '13px' },
  '--fs-tiny': { property: 'font-size', light: '11px' },
  // §2.3 — espacements
  '--s-1': { property: 'width', light: '4px' },
  '--s-2': { property: 'width', light: '8px' },
  '--s-3': { property: 'width', light: '12px' },
  '--s-4': { property: 'width', light: '16px' },
  '--s-5': { property: 'width', light: '24px' },
  '--s-6': { property: 'width', light: '32px' },
  '--s-7': { property: 'width', light: '48px' },
  // §2.4 — rayons
  '--r-card': { property: 'border-radius', light: '2px' },
  '--r-tape': { property: 'border-radius', light: '2px' },
  '--r-button': { property: 'border-radius', light: '6px' },
  // §2.5 — ombres
  '--shadow-rest': {
    property: 'box-shadow',
    light: '0 1px 2px rgba(42,38,34,.08), 0 4px 12px rgba(42,38,34,.10)',
    dark: '0 1px 2px rgba(0,0,0,.30), 0 4px 12px rgba(0,0,0,.35)',
  },
  '--shadow-lift': {
    property: 'box-shadow',
    light: '0 4px 8px rgba(42,38,34,.10), 0 20px 40px rgba(42,38,34,.20)',
    dark: '0 4px 8px rgba(0,0,0,.35), 0 20px 40px rgba(0,0,0,.55)',
  },
  // §2.7 — durées et courbes ; `--ease-out` et `--ease-in-out` existent aussi dans le thème par
  // défaut de Tailwind, avec d'autres valeurs : ce sont celles de la spec qui doivent sortir.
  '--dur-fast': { property: 'transition-duration', light: '150ms' },
  '--dur': { property: 'transition-duration', light: '240ms' },
  '--dur-open': { property: 'transition-duration', light: '280ms' },
  '--ease-out': { property: 'transition-timing-function', light: 'cubic-bezier(.22, 1, .36, 1)' },
  '--ease-spring': {
    property: 'transition-timing-function',
    light: 'linear(0, .28 6%, .62 13%, .88 20%, 1.03 28%, 1.01 40%, 1)',
  },
  '--ease-in-out': { property: 'transition-timing-function', light: 'cubic-bezier(.65, 0, .35, 1)' },
}

/** La valeur que la spec donne à un jeton dans un mode. */
function specValue(token: SpecToken, mode: Mode): string {
  return mode === 'dark' ? (token.dark ?? token.light) : token.light
}

/** Le mode du système, et le mode forcé par `data-theme` s'il y en a un. */
type PaletteState = { system: Mode; forced?: Mode }

/**
 * Les quatre états de palette : le système seul, puis `data-theme` forcé à contre-système dans
 * les deux sens. La palette affichée est le mode forcé s'il y en a un, celui du système sinon.
 */
const PALETTE_STATES: PaletteState[] = [
  { system: 'light' },
  { system: 'dark' },
  { system: 'light', forced: 'dark' },
  { system: 'dark', forced: 'light' },
]

/**
 * Ouvre la page dans un état de palette.
 *
 * `data-theme` est posé après le chargement, comme le fera le bouton de mode : ce qui est mesuré
 * ici, c'est la palette qu'il déclenche, pas la restauration au chargement.
 */
async function openInState(page: Page, { system, forced }: PaletteState) {
  await page.emulateMedia({ colorScheme: system })
  await page.goto('/')
  if (forced) {
    await page.evaluate((mode) => {
      document.documentElement.dataset.theme = mode
    }, forced)
  }
}

/**
 * Valeurs calculées de déclarations appliquées une à une à un élément sonde du document.
 *
 * @param page Page ouverte : la sonde hérite des propriétés personnalisées de `:root`.
 * @param declarations Paires `[propriété, valeur]`, par exemple `['color', 'var(--bg)']`.
 * @returns La valeur calculée de chaque propriété, dans l'ordre reçu ; une valeur invalide ou un
 *   jeton absent rend la valeur initiale de la propriété, qui ne correspond à aucune attente.
 */
async function resolveAll(page: Page, declarations: [string, string][]): Promise<string[]> {
  return page.evaluate((pairs) => {
    const probe = document.createElement('div')
    document.body.append(probe)
    const values = pairs.map(([property, value]) => {
      probe.style.setProperty(property, value)
      const resolved = getComputedStyle(probe).getPropertyValue(property)
      probe.style.removeProperty(property)
      return resolved
    })
    probe.remove()
    return values
  }, declarations)
}

/** Pose un bouton à focaliser : la page du lot 1 de #18 n'a encore rien de focalisable. */
async function appendButton(page: Page) {
  await page.evaluate(() => {
    const button = document.createElement('button')
    button.textContent = 'cible'
    document.body.append(button)
  })
}

test('la table des jetons compte les 32 jetons de la spec', () => {
  expect(Object.keys(SPEC_TOKENS)).toHaveLength(32)
})

for (const state of PALETTE_STATES) {
  const mode = state.forced ?? state.system
  const label = `système ${state.system}, data-theme ${state.forced ?? 'absent'}`

  test(`chaque jeton rend la valeur de la spec — ${label}`, async ({ page }) => {
    await openInState(page, state)

    const entries = Object.entries(SPEC_TOKENS)
    // Un jeton absent rend la valeur héritée ou initiale de sa propriété, que trois attentes
    // partagent (`--fs-body` 16 px, `--postit-ink` et `--tape-ink` clairs = `--ink`) : sa
    // présence sur `:root` se vérifie à part.
    const missing = await page.evaluate(
      (names) =>
        names.filter(
          (name) => getComputedStyle(document.documentElement).getPropertyValue(name) === '',
        ),
      entries.map(([name]) => name),
    )
    expect(missing).toEqual([])

    const resolved = await resolveAll(
      page,
      entries.map(([name, { property }]) => [property, `var(${name})`]),
    )
    const expected = await resolveAll(
      page,
      entries.map(([, token]) => [token.property, specValue(token, mode)]),
    )

    // Appariés au nom du jeton : un écart se lit sur la ligne du jeton fautif.
    const byName = (values: string[]) => entries.map(([name], index) => [name, values[index]])
    expect(byName(resolved)).toEqual(byName(expected))
  })

  test(`la page prend fond, texte, schéma et barre de défilement dans les jetons — ${label}`, async ({
    page,
  }) => {
    await openInState(page, state)

    const root = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement)
      return [
        style.backgroundColor,
        style.color,
        style.colorScheme,
        style.scrollbarWidth,
        style.scrollbarColor,
      ]
    })
    const [background, ink, line] = await resolveAll(page, [
      ['background-color', specValue(SPEC_TOKENS['--bg'], mode)],
      ['color', specValue(SPEC_TOKENS['--ink'], mode)],
      ['scrollbar-color', `${specValue(SPEC_TOKENS['--line'], mode)} transparent`],
    ])

    // Le schéma suit le mode forcé : sans lui, les éléments natifs du navigateur resteraient dans
    // celui du système, et `light-dark()` choisirait la mauvaise valeur.
    expect(root).toEqual([background, ink, state.forced ?? 'light dark', 'thin', line])
  })

  test(`l'anneau de focus clavier est l'accent, à 3 px — ${label}`, async ({ page }) => {
    await openInState(page, state)
    await appendButton(page)

    await page.keyboard.press('Tab')

    const ring = await page
      .locator('button')
      .evaluate((button) => {
        const style = getComputedStyle(button)
        return [style.outline, style.outlineOffset]
      })
    const [expected] = await resolveAll(page, [
      ['outline', `2px solid ${specValue(SPEC_TOKENS['--accent'], mode)}`],
    ])
    expect(ring).toEqual([expected, '3px'])
  })
}

test("l'anneau de focus n'apparaît pas au pointeur", async ({ page }) => {
  await page.goto('/')
  await appendButton(page)

  await page.locator('button').click()

  // Focalisé, mais sans anneau : `:focus-visible` ne s'allume qu'au clavier (spec §6.2).
  expect(
    await page.locator('button').evaluate((button) => [
      button === document.activeElement,
      getComputedStyle(button).outlineStyle,
    ]),
  ).toEqual([true, 'none'])
})
