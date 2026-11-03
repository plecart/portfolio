/**
 * Le module « Jetons » mesuré sur la page servie : les jetons de la spec §2, la base de page, et le
 * mode forcé restauré avant le premier rendu.
 *
 * Un jeton se lit **résolu** (`css.ts`) : appliqué à une propriété réelle d'un élément sonde, puis
 * comparé à la valeur que la spec écrit, appliquée de la même façon. La propriété personnalisée
 * brute dépendrait du mode de compilation — `light-dark()` en développement, la couleur résolue
 * après la réécriture du build (docs/frontend-outillage.md §2.4).
 */
import type { Locator, Page } from '@playwright/test'
import { expect, test } from './api.ts'
import { resolveAll } from './css.ts'

type Mode = 'light' | 'dark'

/** Un jeton : la propriété qui le résout, sa valeur claire, et sa valeur sombre s'il en a une. */
type SpecToken = { property: string; light: string; dark?: string }

/** Les 38 jetons de la spec §2, valeurs recopiées telles que la spec les écrit. */
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
  // Les durées fixes de §2.7, nommées par #19 (décision 3).
  '--dur-content': { property: 'transition-duration', light: '200ms' },
  '--dur-press': { property: 'transition-duration', light: '80ms' },
  '--delay-column': { property: 'transition-delay', light: '40ms' },
  '--delay-ribbon': { property: 'transition-delay', light: '20ms' },
  '--dur-pulse': { property: 'animation-duration', light: '1.8s' },
  // Les 160 ms du mouvement réduit de §6.3, nommées par #22.
  '--dur-reduced': { property: 'transition-duration', light: '160ms' },
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
 * Pose un bouton à focaliser, propre au scénario : il ne dépend d'aucun élément de la page. En
 * tête du document, il reçoit le premier Tab, avant le nom et le bouton de mode de l'entête ; fixé
 * au milieu de la fenêtre, sur la table vide, il n'est recouvert ni par l'entête fixe ni par les
 * liens de l'auteur, que la page en colonne pose en bas de la fenêtre — l'un ou l'autre prendrait
 * son clic.
 *
 * @returns Le bouton, trouvé par son libellé : la page a d'autres boutons.
 */
async function prependButton(page: Page): Promise<Locator> {
  await page.evaluate(() => {
    const button = document.createElement('button')
    button.textContent = 'cible'
    button.style.position = 'fixed'
    button.style.top = '50%'
    document.body.prepend(button)
  })
  return page.getByRole('button', { name: 'cible' })
}

test('la table des jetons compte les 38 jetons de la spec', () => {
  expect(Object.keys(SPEC_TOKENS)).toHaveLength(38)
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
    const button = await prependButton(page)

    await page.keyboard.press('Tab')

    const ring = await button.evaluate((element) => {
      const style = getComputedStyle(element)
      return [style.outline, style.outlineOffset]
    })
    const [expected] = await resolveAll(page, [
      ['outline', `2px solid ${specValue(SPEC_TOKENS['--accent'], mode)}`],
    ])
    expect(ring).toEqual([expected, '3px'])
  })
}

/** Relève, là où il s'exécute, le mode posé et le fond de page calculé. */
const RECORD =
  'globalThis.firstRender = [document.documentElement.dataset.theme, ' +
  'getComputedStyle(document.documentElement).backgroundColor]'

/**
 * Restauration du mode forcé, avant le premier rendu.
 *
 * Le script d'application est bloqué : ce qui reste visible est ce que voit le premier rendu,
 * avant React. La seconde adresse prouve le chemin absolu du script — la même page est servie
 * sous `/projets/<slug>`, où un chemin relatif rendrait la page elle-même par le repli SPA.
 */
for (const path of ['/', '/projets/exemple']) {
  for (const system of ['light', 'dark'] as const) {
    const stored = system === 'light' ? 'dark' : 'light'

    test(`le mode mémorisé est en place avant le script d'application — ${path}, système ${system}`, async ({
      page,
    }) => {
      await page.emulateMedia({ colorScheme: system })
      await page.addInitScript((mode) => localStorage.setItem('theme', mode), stored)
      await page.route('**/assets/*.js', (route) => route.abort())
      // Le relevé se fait à l'ouverture de `<body>`, avant tout rendu : lu après le chargement,
      // il accepterait un script qui différerait son travail (`DOMContentLoaded`) — et le flash
      // qui va avec. Script en ligne propre au scénario : `vite preview` ne pose pas la CSP.
      await page.route(
        (url) => url.pathname === path,
        async (route) => {
          const response = await route.fetch()
          const html = (await response.text()).replace('<body>', `<body><script>${RECORD}</script>`)
          await route.fulfill({ response, body: html })
        },
      )

      await page.goto(path)

      const [first, root] = await page.evaluate(() => [
        (globalThis as unknown as { firstRender: string[] }).firstRender,
        document.getElementById('root')?.innerHTML,
      ])
      const [background] = await resolveAll(page, [
        ['background-color', specValue(SPEC_TOKENS['--bg'], stored)],
      ])
      // `#root` vide : le témoin que l'application n'a pas tourné.
      expect([first, root]).toEqual([[stored, background], ''])
    })
  }
}

test('une valeur mémorisée autre que light ou dark est ignorée', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('theme', 'sepia'))

  await page.goto('/')

  expect(await page.evaluate(() => document.documentElement.hasAttribute('data-theme'))).toBe(false)
})

test('un stockage qui lève une exception ne casse rien', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  // Navigation privée, cookies bloqués : l'accès même à `localStorage` lève une exception.
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      get() {
        throw new DOMException('Stockage refusé', 'SecurityError')
      },
    })
  })

  await page.goto('/')

  await expect(page.locator('h1')).toBeVisible()
  expect([errors, await page.evaluate(() => document.documentElement.dataset.theme)]).toEqual([
    [],
    undefined,
  ])
})

/**
 * L'`index.html` compilé, lu par l'analyseur HTML du navigateur.
 *
 * La politique du site n'admet que des fichiers servis par le site (`default-src 'self'`, sans
 * `unsafe-inline` — Caddyfile, #16) ; `vite preview` ne la pose pas, d'où ce contrôle sur le HTML
 * lui-même.
 */
test("l'index compilé ne porte que des scripts servis en fichier, la restauration en tête", async ({
  page,
  request,
}) => {
  const html = await (await request.get('/')).text()

  const inspection = await page.evaluate((source) => {
    const doc = new DOMParser().parseFromString(source, 'text/html')
    const elements = [...doc.querySelectorAll('*')]
    const headNodes = [...doc.head.childNodes]
    const marker = (text: string) =>
      headNodes.findIndex((node) => node.nodeType === Node.COMMENT_NODE && node.textContent === text)
    const restore = doc.head.querySelector('script[src="/theme.js"]')
    const index = restore ? headNodes.indexOf(restore) : -1

    return {
      inlineScripts: [...doc.scripts].filter((script) => !script.hasAttribute('src')).length,
      styles: doc.querySelectorAll('style').length,
      styleAttributes: elements.filter((element) => element.hasAttribute('style')).length,
      handlers: elements.flatMap((element) =>
        [...element.attributes]
          .filter((attribute) => attribute.name.startsWith('on'))
          .map((attribute) => `${element.tagName} ${attribute.name}`),
      ),
      restore: restore && {
        // Classique et bloquant : ni module, ni `async`, ni `defer` (brief de #18, décision 4).
        blocking: ['type', 'async', 'defer'].every((name) => !restore.hasAttribute(name)),
        outsidePreviewBlock: index < marker('meta:start') || index > marker('meta:end'),
      },
    }
  }, html)
  const script = await request.get('/theme.js')

  expect(inspection).toEqual({
    inlineScripts: 0,
    styles: 0,
    styleAttributes: 0,
    handlers: [],
    restore: { blocking: true, outsidePreviewBlock: true },
  })
  expect([script.status(), script.headers()['content-type']]).toEqual([
    200,
    expect.stringContaining('javascript'),
  ])
})

test("la base de page cède à l'utilitaire d'un composant", async ({ page }) => {
  await page.goto('/')
  // L'anneau d'une carte est à 4 px de sa face (spec §6.2) : la base doit rester dans la couche
  // `base`, sous `components` et `utilities`. Hors couche, elle battrait toute classe.
  await page.evaluate(() => {
    const style = document.createElement('style')
    style.textContent = '@layer utilities { .probe-offset { outline-offset: 7px } }'
    document.head.append(style)
  })
  const button = await prependButton(page)
  await button.evaluate((element) => element.classList.add('probe-offset'))

  await page.keyboard.press('Tab')

  expect(await button.evaluate((element) => getComputedStyle(element).outlineOffset)).toBe('7px')
})

test("l'anneau de focus n'apparaît pas au pointeur", async ({ page }) => {
  await page.goto('/')
  const button = await prependButton(page)

  await button.click()

  // Focalisé, mais sans anneau : `:focus-visible` ne s'allume qu'au clavier (spec §6.2).
  expect(
    await button.evaluate((element) => [
      element === document.activeElement,
      getComputedStyle(element).outlineStyle,
    ]),
  ).toEqual([true, 'none'])
})
