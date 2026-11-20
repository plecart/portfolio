/**
 * La table, ses cartes et la forme des liens de l'auteur, partagées par les scénarios.
 *
 * La table a ses propres cellules — ses cadres de chargement, puis ses cartes — ; pour éprouver la
 * mesure sur des largeurs quelconques, le scénario en pose de factices, au sens du contrat
 * « cellule de la table » — l'attribut `data-table-cell` sur la boîte de grille —, et rien n'entre
 * dans l'application pour cela. Il les pose sur la table servie vide (le `test` d'`api.ts`), que
 * plus rien ne réécrit une fois la liste arrivée.
 */
import type { JSHandle, Locator, Page } from '@playwright/test'
import { expect, serveProjects } from './api.ts'
import { resolveAll, settle } from './css.ts'
import { buildProject, buildTechnology, ONGOING, type Project } from './projects.ts'
import { scrollThrough } from './scroll.ts'

/** La largeur de référence du bureau : la table sans cellule y laisse la colonne (spec §3.4). */
export const COLUMN_VIEWPORT = { width: 1280, height: 800 }

/** Un téléphone plus étroit que le projet mobile (400 px) : les tailles mobiles de §6.1. */
export const NARROW_VIEWPORT = { ...COLUMN_VIEWPORT, width: 375 }

/**
 * La forme des liens, lue sur leur boîte : fixe en colonne, dans le flux en pied de page. Aussi
 * sous une fiche ouverte, qui les cache des technologies d'assistance.
 */
export async function expectPlacement(page: Page, placement: 'column' | 'footer') {
  await expect(page.getByRole('contentinfo', { includeHidden: true })).toHaveCSS(
    'position',
    placement === 'column' ? 'fixed' : 'relative',
  )
}

/**
 * Compte, dès le chargement, les lectures de boîte des cellules de la table (`data-table-cell`) ;
 * la mesure des liens de l'auteur en fait une par cellule à chaque relecture
 * (`useAuthorLinksPlacement`).
 *
 * @returns De quoi lire le compte.
 */
export async function countCellReads(page: Page) {
  await page.addInitScript(() => {
    const read = Element.prototype.getBoundingClientRect
    let cellReads = 0
    Element.prototype.getBoundingClientRect = function (this: Element) {
      if (this.matches('[data-table-cell]')) cellReads += 1
      return read.call(this)
    }
    Object.defineProperty(window, 'cellReads', { get: () => cellReads })
  })
  return () => page.evaluate(() => (window as unknown as { cellReads: number }).cellReads)
}

/** Les cartes de la table, dans son ordre : ses liens. */
export const cards = (page: Page) => page.getByRole('main').getByRole('link')

/** Les couches d'une carte qui bougent, et son bandeau de résumé. */
export const entry = (card: Locator) => card.locator('.card-entry')
export const pose = (card: Locator) => card.locator('.card-pose')
export const face = (card: Locator) => card.locator('.card-face')
export const summary = (card: Locator) => card.locator('.card-summary')

/** La sangle de chantier d'une carte (spec §4.1) : sa boîte, la face et sa tranche. */
export const strap = (card: Locator) => card.locator('.card-strap')

/**
 * Un projet en cours sans couverture : sa photo est un carré `--line` uni, où rien d'autre que la
 * sangle ne prend ses couleurs.
 */
export const STRAPPED = buildProject({ ...ONGOING, slug: 'chantier', gallery: [] })

/**
 * Redresse la pose d'une carte, à 0° et sans décalage : sa face, droite, et ce qu'elle contient se
 * mesurent au pixel près dans une capture.
 */
export async function straighten(card: Locator) {
  await pose(card).evaluate((layer: HTMLElement) => {
    for (const name of ['--card-rotation', '--card-dx', '--card-dy']) layer.style.setProperty(name, '0')
  })
  await settle(card.page())
}

/** Les jetons de couleur de la sangle : ses rayures jaune et encre, puis sa tranche. */
const STRAP_TOKENS = ['--strap', '--strap-ink', '--strap-edge']

/** Les couleurs de la sangle, résolues : ses rayures jaune et encre, puis sa tranche. */
export const strapColors = (page: Page) =>
  resolveAll(
    page,
    STRAP_TOKENS.map((token): [string, string] => ['color', `var(${token})`]),
  )

/** Une couleur qu'aucune couche de la carte ne prend, ni aucun mélange des siennes. */
const PROBE = 'rgb(255, 0, 255)'

/**
 * Pose ces jetons sur la sangle d'une carte, à cette couleur.
 *
 * @returns De quoi lui rendre son style en ligne d'avant, ce qu'un appel précédent y a posé
 *   compris.
 */
async function recolorStrap(card: Locator, tokens: string[], color: string) {
  const before = await strap(card).evaluate(
    (element: HTMLElement, [names, value]) => {
      const inline = element.style.cssText
      for (const name of names) element.style.setProperty(name, value)
      return inline
    },
    [tokens, color] as const,
  )
  return () =>
    strap(card).evaluate((element: HTMLElement, inline) => {
      element.style.cssText = inline
    }, before)
}

/**
 * Peint la tranche de la sangle d'une carte de la couleur témoin, jusqu'à la fin du scénario : la
 * sienne, `--strap-edge`, est la moitié exacte du jaune et de l'encre, que traverse le lissage de
 * leurs frontières (`card.css`).
 *
 * @returns La couleur témoin.
 */
export async function probeTranche(card: Locator) {
  await recolorStrap(card, ['--strap-edge'], PROBE)
  return PROBE
}

/** Un rectangle de la page, en px CSS. */
export type Rect = { x: number; y: number; width: number; height: number }

/** L'écart toléré sur chaque canal d'un pixel de couleur unie : l'anticrénelage d'un bord le dépasse. */
const PIXEL_TOLERANCE = 6

/**
 * Une zone capturée, décodée : ses octets RGBA, ses colonnes et ses rangées de pixels, et leur
 * nombre par px CSS.
 */
type Capture = { data: Uint8ClampedArray; columns: number; rows: number; scale: number }

/**
 * Capture une zone de la page et la décode dans la page, où un relevé la lit sans la rapatrier ; à
 * libérer (`dispose`) une fois lue.
 */
async function capture(page: Page, zone: Rect): Promise<JSHandle<Capture>> {
  const png = await page.screenshot({ clip: zone })
  return page.evaluateHandle(
    async ({ url, width }) => {
      const bitmap = await createImageBitmap(await (await fetch(url)).blob())
      const canvas = new OffscreenCanvas(bitmap.width, bitmap.height).getContext('2d')!
      canvas.drawImage(bitmap, 0, 0)
      const { data } = canvas.getImageData(0, 0, bitmap.width, bitmap.height)
      return { data, columns: bitmap.width, rows: bitmap.height, scale: bitmap.width / width }
    },
    { url: `data:image/png;base64,${png.toString('base64')}`, width: zone.width },
  )
}

/**
 * Les pixels de ces couleurs dans une zone de la page, capturée : pour chaque couleur, la distance
 * de chacun de ses pixels à `rect`, en px CSS, mesurée au centre du pixel — la plus grande des
 * quatre, négative dedans. Une couleur résolue, `color(srgb …)` d'un `color-mix()` comprise, passe
 * par un canevas, qui la rend en octets comme la page peint la capture ; un pixel la porte à
 * `PIXEL_TOLERANCE` près sur chaque canal.
 *
 * @param zone La zone capturée.
 * @param colors Les couleurs, résolues (`resolveAll`).
 * @param rect Le rectangle d'où se comptent les distances ; la zone elle-même par défaut.
 */
export async function pixelDistances(
  page: Page,
  zone: Rect,
  colors: string[],
  rect: Rect = zone,
): Promise<number[][]> {
  const shot = await capture(page, zone)
  const distances = await shot.evaluate(
    (
      { data, columns, rows, scale },
      { colors: targets, rect: { x, y, width, height }, tolerance },
    ) => {
      const swatch = new OffscreenCanvas(1, 1).getContext('2d')!
      const bytes = targets.map((color) => {
        swatch.fillStyle = color
        swatch.fillRect(0, 0, 1, 1)
        return swatch.getImageData(0, 0, 1, 1).data
      })
      const distances = bytes.map((): number[] => [])
      for (let row = 0; row < rows; row += 1) {
        for (let column = 0; column < columns; column += 1) {
          const at = 4 * (row * columns + column)
          const [left, top] = [(column + 0.5) / scale, (row + 0.5) / scale]
          const distance = Math.max(x - left, left - x - width, y - top, top - y - height)
          bytes.forEach((target, index) => {
            const close = [0, 1, 2].every(
              (channel) => Math.abs(data[at + channel] - target[channel]) <= tolerance,
            )
            if (close) distances[index].push(distance)
          })
        }
      }
      return distances
    },
    {
      colors,
      rect: { ...rect, x: rect.x - zone.x, y: rect.y - zone.y },
      tolerance: PIXEL_TOLERANCE,
    },
  )
  await shot.dispose()
  return distances
}

/**
 * Les pixels que la sangle d'une carte peint dans une zone de la page : ceux qui changent, d'un canal
 * au moins de plus que `PIXEL_TOLERANCE`, la zone capturée de nouveau, ses couleurs passées à la
 * couleur témoin, puis rendues à ce qu'elles étaient, tranche témoin (`probeTranche`) comprise.
 * Chacun par son centre, en px CSS, depuis le coin haut-gauche d'`origin` : abscisse, ordonnée. Son
 * bord anticrénelé compte comme le reste, à cette tolérance près. Repeinte et non masquée : masquée
 * (`visibility: hidden`), 3 à 5 pixels de la bande basse changeaient aussi au bureau, hors de sa
 * portée ; repeinte, aucun (Chromium 156, mesuré le 2026-11-09).
 *
 * @param zone La zone capturée.
 * @param origin Le rectangle d'où se comptent les coordonnées.
 */
export async function strapPixels(card: Locator, zone: Rect, origin: Rect) {
  const page = card.page()
  const shown = await capture(page, zone)
  const restore = await recolorStrap(card, STRAP_TOKENS, PROBE)
  const probed = await capture(page, zone)
  await restore()
  const painted = await shown.evaluate(
    ({ data, columns, rows, scale }, { other, offset: [dx, dy], tolerance }) => {
      const points: [number, number][] = []
      for (let row = 0; row < rows; row += 1) {
        for (let column = 0; column < columns; column += 1) {
          const at = 4 * (row * columns + column)
          const changed = [0, 1, 2].some(
            (channel) => Math.abs(data[at + channel] - other.data[at + channel]) > tolerance,
          )
          if (changed) points.push([(column + 0.5) / scale + dx, (row + 0.5) / scale + dy])
        }
      }
      return points
    },
    {
      other: probed,
      offset: [zone.x - origin.x, zone.y - origin.y],
      tolerance: PIXEL_TOLERANCE,
    },
  )
  await Promise.all([shown.dispose(), probed.dispose()])
  return painted
}

/** Les trois technologies qu'une carte montre au plus (spec §1.4), une par type. */
const THREE_TECHNOLOGIES = (['language', 'framework', 'infrastructure'] as const).map((kind) =>
  buildTechnology(kind, kind),
)

/** Une carte aux trois technologies et aux deux états : sous 600 px, ses rubans vont à la ligne. */
export const FULL_CARD = buildProject({
  ...ONGOING,
  slug: 'pleine',
  demo_url: 'https://demo.test/pleine',
  technologies: THREE_TECHNOLOGIES,
})

/**
 * Une carte aux trois technologies, en ligne : sur la carte simple, ses rubans tiennent sur une
 * rangée au bureau, à 2 px près, et en prennent deux à 375 px (spec §4.1).
 */
export const LIVE_CARD = buildProject({
  slug: 'en-ligne',
  demo_url: 'https://demo.test/en-ligne',
  technologies: THREE_TECHNOLOGIES,
})

/** Deux cartes sur une rangée : la carte pleine, en cours donc en tête, et sa voisine. */
export const TWO_CARDS = [FULL_CARD, buildProject({ slug: 'voisine' })]

/** Les tailles de tout ruban, de carte ou de fiche (spec §4.1, §4.3), lues par `ribbonSizes`. */
export const RIBBON_SIZES = { ribbons: ['32px 13px'], icons: ['24px 24px'] }

/**
 * Les tailles calculées des rubans sous un élément, chacune une fois : hauteur et police des
 * rubans, largeur et hauteur de leurs icônes. Une seule de chaque quand tous ont la même ; aucune
 * sans ruban.
 */
export const ribbonSizes = (container: Locator) =>
  container.locator('.card-ribbon').evaluateAll((ribbons) => {
    /** Les valeurs calculées des propriétés, jointes par élément, chaque combinaison une fois. */
    const distinct = (elements: Element[], properties: string[]) => [
      ...new Set(
        elements.map((element) => {
          const style = getComputedStyle(element)
          return properties.map((property) => style.getPropertyValue(property)).join(' ')
        }),
      ),
    ]
    const icons = ribbons.flatMap((ribbon) => [...ribbon.querySelectorAll('.card-ribbon-icon')])
    return {
      ribbons: distinct(ribbons, ['height', 'font-size']),
      icons: distinct(icons, ['width', 'height']),
    }
  })

/**
 * L'icône de chaque ruban de technologie sous un élément, dans l'ordre (spec §4.1) : le nom de sa
 * technologie, l'encre du ruban, la couleur qui la peint et l'image qui la découpe. Un ruban d'état
 * n'a pas d'icône.
 */
export const ribbonIcons = (container: Locator) =>
  container.locator('.card-ribbon-icon').evaluateAll((icons) =>
    icons.map((icon) => {
      const ribbon = icon.parentElement!
      const { backgroundColor, maskImage } = getComputedStyle(icon)
      return {
        name: ribbon.textContent,
        ink: getComputedStyle(ribbon).color,
        paint: backgroundColor,
        mask: maskImage,
      }
    }),
  )

/**
 * Ce que `ribbonIcons` lit sur les rubans de ces technologies : chaque icône peinte à l'encre `ink`
 * du ruban, et découpée par l'icône de sa technologie (#271).
 */
export const inkedIcons = (technologies: Project['technologies'], ink: string) =>
  technologies.map(({ name, icon }) => ({ name, ink, paint: ink, mask: `url("${icon}")` }))

/**
 * Ouvre la table sur un jeu de projets, ses cartes rendues et sa police arrivée : `font-display:
 * swap` laisse sinon mesurer le texte dans la police de repli, plus étroite.
 */
export async function openTable(page: Page, projects: Project[]) {
  await serveProjects(page, projects)
  await page.goto('/')
  await expect(cards(page)).toHaveCount(projects.length)
  await page.evaluate(async () => void (await document.fonts.ready))
}

/**
 * Sert la page sous une CSP sans `style-src 'unsafe-inline'`, comme celle de Caddy, qu'aucun scénario
 * ne traverse : elle bloque un attribut `style` analysé, jamais le CSSOM.
 */
export async function serveUnderCsp(page: Page) {
  await page.route('/', async (route) => {
    const response = await route.fetch()
    await route.fulfill({
      response,
      headers: { ...response.headers(), 'content-security-policy': "style-src 'self'" },
    })
  })
}

/**
 * Consigne les transitions qui partent à partir de maintenant, sur toute la page : elles se lisent
 * après coup, là où une lecture de `getAnimations()` manquerait une transition déjà finie.
 *
 * @returns De quoi lire celles parties, sur une couche (sa classe) ou partout.
 */
export async function watchTransitions(page: Page) {
  const runs = await page.evaluateHandle(() => {
    const seen: { layer: string; property: string; duration: string }[] = []
    addEventListener('transitionrun', ({ target, propertyName: property }) => {
      const element = target as Element
      const { transitionDuration: duration } = getComputedStyle(element)
      seen.push({ layer: element.className, property, duration })
    })
    return seen
  })
  return async (layer?: string) => {
    const seen = await runs.jsonValue()
    return layer ? seen.filter((run) => run.layer === layer) : seen
  }
}

/**
 * Une animation partie sur la pose d'une carte : l'adresse de sa carte ; son nom, sa transformation
 * de départ et son remplissage ; son retard et sa durée en ms, sa courbe.
 */
type PoseAnimation = {
  card: string
  name: string
  from: ComputedKeyframe['transform']
  fill: FillMode | undefined
  delay: number
  duration: number
  easing: string
}

/**
 * Consigne, dès le chargement, les animations CSS qui partent sur la pose d'une carte, lues sur
 * l'animation elle-même à son départ : une lecture de `getAnimations()` après coup la manquerait,
 * finie. Appelée avant d'ouvrir la page.
 *
 * @returns De quoi lire celles parties, dans l'ordre de leur départ.
 */
export async function watchPoseAnimations(page: Page) {
  await page.addInitScript(() => {
    const seen: PoseAnimation[] = []
    Object.defineProperty(window, 'poseAnimations', { value: seen })
    addEventListener('animationstart', ({ target, animationName }) => {
      const layer = target as Element
      if (!layer.classList.contains('card-pose')) return
      const animation = layer
        .getAnimations()
        .find((candidate) => (candidate as CSSAnimation).animationName === animationName)!
      const effect = animation.effect as KeyframeEffect
      const [start] = effect.getKeyframes()
      const { delay, duration, fill } = effect.getTiming()
      seen.push({
        card: layer.closest('.card')!.getAttribute('href')!,
        name: animationName,
        from: start.transform,
        fill,
        delay: delay!,
        duration: duration as number,
        easing: start.easing,
      })
    })
  })
  return () =>
    page.evaluate(() => (window as unknown as { poseAnimations: PoseAnimation[] }).poseAnimations)
}

/** L'intention sur une carte (spec §1.7) : le survol au bureau, le toucher sur un téléphone. */
export const intend = (card: Locator, isMobile: boolean) =>
  isMobile ? card.tap() : card.hover()

/** Focalise une carte au clavier : une touche d'abord, pour que `:focus-visible` s'applique. */
export async function focusByKeyboard(card: Locator) {
  await card.page().keyboard.press('Tab')
  await card.focus()
}

/**
 * Fait entrer toutes les cartes : la page défilée écran par écran, puis ramenée en haut. Une carte
 * qui n'est pas entrée reste à opacité 0, et un contrôle d'accessibilité ne la lirait pas.
 */
export async function enterCards(page: Page) {
  const { clientHeight, scrollHeight } = await page.evaluate(() => {
    const { clientHeight, scrollHeight } = document.documentElement
    return { clientHeight, scrollHeight }
  })
  for (let top = 0; top < scrollHeight; top += clientHeight) await scrollThrough(page, top)
  await scrollThrough(page, 0)
  await expect(page.locator('.card:not([data-entered])')).toHaveCount(0)
  await settle(page)
}

/**
 * Pose des cellules dans la table, centrées comme la grille les centre ; elles remplacent celles
 * qui y étaient.
 *
 * @param widths La largeur de chaque cellule, en px ; aucune vide la table.
 * @param height Leur hauteur, en px : de quoi allonger la page sans autre élément.
 */
export async function placeCells(page: Page, widths: number[], height = 10) {
  await page.evaluate(
    ([cellWidths, cellHeight]) => {
      document.querySelector('main')?.replaceChildren(
        ...cellWidths.map((width) => {
          const cell = document.createElement('div')
          cell.setAttribute('data-table-cell', '')
          cell.style.cssText = `width: ${width}px; height: ${cellHeight}px; margin: 0 auto`
          return cell
        }),
      )
    },
    [widths, height] as const,
  )
}
