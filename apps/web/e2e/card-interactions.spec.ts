/**
 * Les interactions d'une carte (spec §1.3, §1.7, §2.7, §3.1, §4.1, §6.1-6.3 ; issue #168), sur la
 * page servie, l'API et les fichiers interceptés par les gestes d'`api.ts`.
 */
import { AxeBuilder } from '@axe-core/playwright'
import type { Locator, Page } from '@playwright/test'
import { expect, holdProjects, serving, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import { buildProject, ONGOING, PROJECT_SETS } from './projects.ts'
import { pageBottom, scrollThrough } from './scroll.ts'
import {
  cardAt,
  cards,
  COLUMN_VIEWPORT,
  enterCards,
  entry,
  expectPlacement,
  face,
  focusByKeyboard,
  FULL_CARD,
  intend,
  openTable,
  pixelDistances,
  pose,
  probeTranche,
  serveUnderCsp,
  straighten,
  strap,
  strapColors,
  STRAPPED,
  summary,
  TWO_CARDS,
  watchPoseAnimations,
  watchTransitions,
} from './table.ts'

/** Le soulèvement (−6 px, ×1,02) et la pression (×0,985) de spec §4.1, en transformation calculée. */
const LIFTED = 'matrix(1.02, 0, 0, 1.02, 0, -6)'
const PRESSED = 'matrix(0.985, 0, 0, 0.985, 0, 0)'

/** Attend l'ombre soulevée et le bandeau, apparus ou effacés. */
async function expectRevealed(card: Locator, revealed: boolean) {
  const opacity = revealed ? '1' : '0'
  await expect(face(card)).toHaveCSS('opacity', opacity, { pseudo: 'after' })
  await expect(summary(card)).toHaveCSS('opacity', opacity)
}

/** Les deux gestes d'une intention, sur un appareil à survol (spec §4.1). */
const INTENTS: [string, (card: Locator) => Promise<void>][] = [
  ['au survol', (card) => card.hover()],
  ['au focus clavier', focusByKeyboard],
]

test('à 15 % de sa surface dans l’écran, une carte entre : 8 px de montée et un fondu de 240 ms', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  const box = (await card.boundingBox())!
  const { height } = page.viewportSize()!
  const [duration, curve] = await resolveAll(page, [
    ['transition-duration', 'var(--dur)'],
    ['transition-timing-function', 'var(--ease-out)'],
  ])

  await expect(entry(card)).toHaveCSS('opacity', '0')
  await expect(entry(card)).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 8)')
  await expect(entry(card)).toHaveCSS('transition-property', 'opacity, transform')
  await expect(entry(card)).toHaveCSS('transition-duration', `${duration}, ${duration}`)
  await expect(entry(card)).toHaveCSS('transition-timing-function', `${curve}, ${curve}`)

  await scrollThrough(page, box.y + box.height * 0.1 - height)
  await expect(card).not.toHaveAttribute('data-entered')

  await scrollThrough(page, box.y + box.height * 0.2 - height)
  await expect(entry(card)).toHaveCSS('opacity', '1')
  await expect(entry(card)).toHaveCSS('transform', 'none')
})

test('une carte n’entre qu’une fois : la revoir ne rejoue rien', async ({ page }) => {
  const turns = await watchPoseAnimations(page)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  await enterCards(page)
  const entered = await turns()
  const transitions = await watchTransitions(page)
  const bottom = await pageBottom(page)

  await scrollThrough(page, bottom, 0, bottom)
  await settle(page)

  expect(await turns()).toEqual(entered)
  expect(await transitions('card-entry')).toEqual([])
})

test('toute la table n’a qu’un observateur, qui lâche chaque carte entrée', async ({ page }) => {
  await page.addInitScript(() => {
    const calls = { created: 0, unobserved: 0 }
    Object.assign(window, { observerCalls: calls })
    const Native = window.IntersectionObserver
    window.IntersectionObserver = class extends Native {
      constructor(...args: ConstructorParameters<typeof Native>) {
        super(...args)
        calls.created += 1
      }

      unobserve(target: Element) {
        calls.unobserved += 1
        super.unobserve(target)
      }
    }
  })
  await openTable(page, PROJECT_SETS.threeWithShowcase)
  await expect(page.locator('.card[data-entered]')).toHaveCount(3)

  const calls = await page.evaluate(() => Reflect.get(window, 'observerCalls'))

  expect(calls).toEqual({ created: 1, unobserved: 3 })
})

test('le retard vaut 40 ms par colonne mesurée, et se relit au redimensionnement', async ({ page }) => {
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const columns = () =>
    cards(page).evaluateAll((links) =>
      links.map((link) => {
        const { transitionDelay } = getComputedStyle(link.querySelector('.card-entry')!)
        return Math.round(parseFloat(transitionDelay) * 1000) / 40
      }),
    )

  await expect.poll(columns).toEqual([0, 2, 3, 2, 3, 0, 1, 2, 3, 0, 1, 2])

  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 1000 })
  await expect.poll(columns).toEqual([0, 2, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2])

  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 400 })
  await expect.poll(columns).toEqual([0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
})

test('en mouvement réduit, une carte entre par un fondu de 150 ms, sans montée, retard conservé', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.twelveWithShowcase)
  const card = cards(page).last()
  const [duration] = await resolveAll(page, [['transition-duration', 'var(--dur-fast)']])

  await expect(entry(card)).toHaveCSS('opacity', '0')
  await expect(entry(card)).toHaveCSS('transform', 'none')
  await expect(entry(card)).toHaveCSS('transition-property', 'opacity')
  await expect(entry(card)).toHaveCSS('transition-duration', duration)
  // La dernière des douze cartes, en troisième colonne à 1280 px.
  await expect(entry(card)).toHaveCSS('transition-delay', '0.08s')

  await card.scrollIntoViewIfNeeded()
  await expect(entry(card)).toHaveCSS('opacity', '1')
})

/**
 * Le projet type (`buildProject`), en cours et commencé avant les douze : la dernière carte, sous
 * l'écran (spec §1.9).
 */
const BELOW_THE_FOLD = [
  ...PROJECT_SETS.twelveWithShowcase,
  buildProject({ ...ONGOING, started_on: '2013-03-01' }),
]

/**
 * La pose de la carte `projet`, calculée hors de JavaScript, par une empreinte FNV-1a 32 bits de
 * référence en Python (2026-11-17).
 */
const PROJET_POSE = 'rotate(-1.728deg) translate(3.528px, 5.232px)'

/**
 * Ouvre la table de `BELOW_THE_FOLD`.
 *
 * @returns Sa dernière carte, `projet`, pas encore entrée, et sa pose, résolue.
 */
async function openBelowTheFold(page: Page) {
  await openTable(page, BELOW_THE_FOLD)
  const card = cards(page).last()
  await expect(card).toHaveAttribute('href', '/projets/projet')
  await expect(card).not.toHaveAttribute('data-entered')
  const [posed] = await resolveAll(page, [['transform', PROJET_POSE]])
  return { card, posed }
}

/** La transformation calculée de la pose d'une carte. */
const poseTransform = (card: Locator) =>
  pose(card).evaluate((layer) => getComputedStyle(layer).transform)

test('une carte entre droite, puis tourne jusqu’à sa pose, une fois entrée seulement', async ({
  page,
}) => {
  const turns = await watchPoseAnimations(page)
  const { card, posed } = await openBelowTheFold(page)
  const ownTurns = async () =>
    (await turns()).filter(({ card: path }) => path === '/projets/projet')

  // Ni relevée, ni en cours : posée dès le rendu, l'animation serait l'une ou l'autre.
  expect(await poseTransform(card)).toBe('none')
  expect(await pose(card).evaluate((layer) => layer.getAnimations().length)).toBe(0)
  expect(await ownTurns()).toEqual([])

  await card.scrollIntoViewIfNeeded()
  await expect(card).toHaveAttribute('data-entered')
  await settle(page)

  expect(await poseTransform(card)).toBe(posed)
  expect(await ownTurns()).toHaveLength(1)
})

test('la pose part de 0°, tenue droite pendant le retard de la montée — 40 ms par colonne —, puis tourne en 240 ms et `--ease-out`', async ({
  page,
}) => {
  await page.setViewportSize(COLUMN_VIEWPORT)
  const turns = await watchPoseAnimations(page)
  await openTable(page, TWO_CARDS)
  const [curve] = await resolveAll(page, [['animation-timing-function', 'var(--ease-out)']])

  await expect(page.locator('.card[data-entered]')).toHaveCount(2)
  await settle(page)

  // `backwards` tient la pose droite pendant le retard : sans lui, l'entrée change sa transformation,
  // et sa transition part aussitôt, sans retard, par-dessus l'animation (Chromium 156, mesuré le
  // 2026-11-17).
  const turn = {
    name: 'card-pose-entry',
    from: 'none',
    fill: 'backwards',
    duration: 240,
    easing: curve,
  }
  expect(await turns()).toEqual([
    { ...turn, card: '/projets/pleine', delay: 0 },
    { ...turn, card: '/projets/voisine', delay: 40 },
  ])
})

test('en mouvement réduit, une carte est à sa pose avant d’entrer, et sa pose ne s’anime pas', async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const turns = await watchPoseAnimations(page)
  const { card, posed } = await openBelowTheFold(page)

  expect(await poseTransform(card)).toBe(posed)

  await card.scrollIntoViewIfNeeded()
  await expect(card).toHaveAttribute('data-entered')
  await settle(page)

  expect(await poseTransform(card)).toBe(posed)
  expect(await turns()).toEqual([])
})

test('entrée, une carte de deuxième colonne se redresse à l’intention sans le retard de son entrée', async ({
  page,
  isMobile,
}) => {
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, TWO_CARDS)
  await enterCards(page)
  const card = cards(page).last()
  const [duration] = await resolveAll(page, [['transition-duration', 'var(--dur)']])
  const transitions = await watchTransitions(page)
  await expect(entry(card)).toHaveCSS('transition-delay', '0.04s, 0.04s')

  await intend(card, isMobile)

  await expect(pose(card)).toHaveCSS('transform', 'none')
  await expect(pose(card)).toHaveCSS('transition-delay', '0s')
  expect(await transitions('card-pose')).toEqual([
    { layer: 'card-pose', property: 'transform', duration },
  ])
})

/**
 * Ce qui redresse une carte en pleine entrée : une intention, et l'envol de sa fiche, que
 * `useChoreography` marque de `data-origin`.
 */
const INTERRUPTIONS: [string, (card: Locator, isMobile: boolean) => Promise<unknown>][] = [
  ['une intention', intend],
  ['l’envol de sa fiche', (card) => card.evaluate((link) => link.setAttribute('data-origin', ''))],
]

for (const [cause, interrupt] of INTERRUPTIONS) {
  test(`redressée en pleine entrée par ${cause}, la pose vise 0° et non plus sa pose, sans transition ajoutée`, async ({
    page,
    isMobile,
  }) => {
    // Chaque animation figée dès son départ : placée à mi-course, elle se lit à loisir.
    await page.addInitScript(() =>
      addEventListener('animationstart', ({ target }) => {
        for (const animation of (target as Element).getAnimations()) animation.pause()
      }),
    )
    await openTable(page, TWO_CARDS)
    const card = cards(page).first()
    const states = () =>
      pose(card).evaluate((layer) => layer.getAnimations().map(({ playState }) => playState))
    const midway = () =>
      pose(card).evaluate((layer) => {
        const [turn] = layer.getAnimations()
        turn.currentTime = (turn.effect!.getComputedTiming().endTime as number) / 2
        return getComputedStyle(layer).transform
      })
    await expect.poll(states).toEqual(['paused'])
    expect(await midway()).not.toBe('none')

    await interrupt(card, isMobile)

    expect(await midway()).toBe('none')
    expect(await states()).toEqual(['paused'])
  })
}

test('les cartes remplacent les cadres en entrant, sans changer la forme des liens de l’auteur', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'largeurs de bureau : le projet desktop les porte')
  // À 1200 px, 78 px de marge pour une garde de 76 : une mesure qui suivrait l'entrée basculerait.
  // Douze cartes, et non le jeu que les cadres annoncent : une carte seule laisse 120 px de marge
  // dès 600 px. Les cadres, quel qu'en soit le nombre, laissent la colonne : quatre pistes au plus.
  await page.setViewportSize({ ...COLUMN_VIEWPORT, width: 1200 })
  const release = await holdProjects(page)
  await page.goto('/')
  await expectPlacement(page, 'column')
  const forms = await page.evaluateHandle(() => {
    const seen = { count: 0 }
    new MutationObserver(() => (seen.count += 1)).observe(document.querySelector('footer')!, {
      attributeFilter: ['data-docked'],
    })
    return seen
  })
  const transitions = await watchTransitions(page)

  await release(serving(PROJECT_SETS.twelveWithShowcase))
  await expect(page.locator('.card[data-entered]')).not.toHaveCount(0)
  await settle(page)

  expect(await forms.jsonValue()).toEqual({ count: 0 })
  await expectPlacement(page, 'column')
  // Rien ne transite que la couche d'entrée, dont la pose tourne par son animation : ni la cellule,
  // que les liens mesurent, ni ses voisines.
  const moved = new Set((await transitions()).map(({ layer }) => layer))
  expect([...moved]).toEqual(['card-entry'])
})

for (const width of [1280, 400]) {
  for (const [gesture, act] of INTENTS) {
    test(`${gesture} à ${width} px, la carte se redresse, se soulève, l'ombre s'élargit, le bandeau se révèle`, async ({
      page,
      isMobile,
    }) => {
      test.skip(isMobile, 'appareil sans survol : la révélation au toucher a ses scénarios')
      await page.setViewportSize({ ...COLUMN_VIEWPORT, width })
      await openTable(page, PROJECT_SETS.threeWithShowcase)
      const card = cards(page).first()

      await expectRevealed(card, false)
      await expect(summary(card)).toHaveCSS('transform', 'matrix(1, 0, 0, 1, 0, 6)')

      await act(card)

      await expect(pose(card)).toHaveCSS('transform', 'none')
      await expect(face(card)).toHaveCSS('transform', LIFTED)
      await expectRevealed(card, true)
      await expect(summary(card)).toHaveCSS('transform', 'none')
    })
  }
}

test('les mouvements d’une carte suivent le tableau de spec §2.7', async ({ page }) => {
  await openTable(page, PROJECT_SETS.one)
  const card = cards(page)
  const [fast, base, out, spring] = await resolveAll(page, [
    ['transition-duration', 'var(--dur-fast)'],
    ['transition-duration', 'var(--dur)'],
    ['transition-timing-function', 'var(--ease-out)'],
    ['transition-timing-function', 'var(--ease-spring)'],
  ])
  const expectMotion = async (layer: Locator, name: string, duration: string, curve: string) => {
    await expect(layer).toHaveCSS('transition-property', name)
    await expect(layer).toHaveCSS('transition-duration', duration)
    await expect(layer).toHaveCSS('transition-timing-function', curve)
  }

  await expectMotion(pose(card), 'transform', base, out)
  await expectMotion(face(card), 'transform', base, spring)
  await expectMotion(summary(card), 'opacity, transform', `${fast}, ${base}`, `${out}, ${out}`)
  await expect(face(card)).toHaveCSS('transition-property', 'opacity', { pseudo: 'after' })
  await expect(face(card)).toHaveCSS('transition-duration', base, { pseudo: 'after' })
  await expect(face(card)).toHaveCSS('transition-timing-function', out, { pseudo: 'after' })
})

test('le bandeau de résumé : absolu en bas de la photo, `--paper` à 94 %, `--ink` (spec §4.1)', async ({
  page,
}) => {
  await openTable(page, [buildProject({ summary: 'Un résumé.' })])
  const card = cards(page)
  const [paper, ink] = await resolveAll(page, [
    ['background-color', 'color-mix(in srgb, var(--paper) 94%, transparent)'],
    ['color', 'var(--ink)'],
  ])

  await expect(summary(card)).toHaveText('Un résumé.')
  await expect(summary(card)).toHaveAttribute('aria-hidden', 'true')
  await expect(summary(card)).toHaveCSS('background-color', paper)
  await expect(summary(card)).toHaveCSS('color', ink)
  await expect(summary(card)).toHaveCSS('padding', '12px')
  const gap = await summary(card).evaluate(
    (overlay) =>
      overlay.parentElement!.getBoundingClientRect().bottom -
      overlay.getBoundingClientRect().bottom,
  )
  // Caché, le bandeau est 6 px plus bas que sa place.
  expect(Math.round(gap)).toBe(-6)
})

/** Le canal vert d'une capture PNG, colonne par colonne, décodé par la page. */
const greenColumns = (page: Page, png: Buffer) =>
  page.evaluate(async (url) => {
    const bitmap = await createImageBitmap(await (await fetch(url)).blob())
    const { width, height } = bitmap
    const context = new OffscreenCanvas(width, height).getContext('2d')!
    context.drawImage(bitmap, 0, 0)
    const { data } = context.getImageData(0, 0, width, height)
    return Array.from({ length: width }, (_, x) =>
      Array.from({ length: height }, (_, y) => data[4 * (y * width + x) + 1]),
    )
  }, `data:image/png;base64,${png.toString('base64')}`)

test('à mi-transition, aucun filet de l’image ne longe le bandeau', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans survol : le filet se mesure sous la carte soulevée')
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, PROJECT_SETS.threeWithoutShowcase)
  await enterCards(page)
  const card = cards(page).first()
  const { x, y, width, height } = (await card.boundingBox())!
  // Figées dès leur départ : lues après coup, elles auraient pu finir sous une machine chargée.
  await page.evaluate(() =>
    addEventListener('transitionrun', () => {
      for (const motion of document.getAnimations()) {
        motion.pause()
        motion.currentTime = 75
      }
    }),
  )

  await page.mouse.move(x + width / 2, y + height * 0.8)
  await expect
    .poll(() => summary(card).evaluate((overlay) => overlay.getAnimations().length))
    .toBe(2)

  // Une bande à cheval sur le bord bas : du bandeau au papier, rien de plus sombre que les deux.
  // Sous le bord, 6 px : les rubans de 32 px commencent 10 px sous la photo, dans une bande de 52.
  const overlay = (await summary(card).boundingBox())!
  const edge = Math.floor(overlay.y + overlay.height)
  const clip = {
    x: Math.ceil(overlay.x) + 2,
    y: edge - 12,
    width: Math.floor(overlay.width) - 4,
    height: 12 + 6,
  }
  const columns = await greenColumns(page, await page.screenshot({ clip }))

  expect(columns[0][0]).toBeLessThan(columns[0].at(-1)!)
  const dips = columns.map((column) => Math.min(column[0], column.at(-1)!) - Math.min(...column))
  expect(Math.max(...dips)).toBeLessThanOrEqual(2)
})

/** Le résumé le plus long de spec §7, 120 caractères, et son voisin : deux cartes simples. */
const LONGEST_SUMMARY = [
  buildProject({
    slug: 'a',
    summary:
      'Une application de suivi des livraisons pour les artisans du bâtiment, avec planning partagé et alertes par messageries.',
  }),
  buildProject({ slug: 'b' }),
]

test('un résumé de 120 caractères tient en sept lignes sur la carte simple mobile (spec §7)', async ({
  page,
  isMobile,
}) => {
  test.skip(!isMobile, 'la carte simple de 176 px, la plus étroite de spec §7')
  expect(LONGEST_SUMMARY[0].summary).toHaveLength(120)
  await openTable(page, LONGEST_SUMMARY)

  const { text, lineHeight, photo } = await summary(cards(page).first()).evaluate(
    (band: HTMLElement) => ({
      text: band.offsetHeight - 2 * 12,
      lineHeight: parseFloat(getComputedStyle(band).lineHeight),
      photo: band.parentElement!.offsetHeight,
    }),
  )

  expect(Math.round(text / lineHeight)).toBeLessThanOrEqual(7)
  expect(text + 2 * 12).toBeLessThanOrEqual(photo)
})

for (const [width, maxLines] of [
  [320, 4],
  [340, 5],
  [380, 6],
] as const) {
  test(`à ${width} px, le bandeau s'arrête à ${maxLines} lignes : le haut du texte reste sous le post-it`, async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'des cartes simples plus étroites que celle de spec §7')
    await page.setViewportSize({ ...COLUMN_VIEWPORT, width })
    await openTable(page, LONGEST_SUMMARY)

    const overlay = await summary(cards(page).first()).evaluate((element: HTMLElement) => {
      const { lineHeight, paddingBottom, paddingTop } = getComputedStyle(element)
      const inset = parseFloat(paddingTop) + parseFloat(paddingBottom)
      // Depuis le haut de la photo, repère du bandeau ; le post-it se place dans la face.
      const photo = element.offsetParent as HTMLElement
      const postit = element.closest('.card-face')!.querySelector<HTMLElement>('.card-postit')!
      return {
        textTop: element.offsetTop + parseFloat(paddingTop),
        postitBottom: postit.offsetTop + postit.offsetHeight - photo.offsetTop,
        lines: Math.round((element.offsetHeight - inset) / parseFloat(lineHeight)),
        overflow: element.scrollHeight - element.clientHeight,
      }
    })

    expect(overlay.textTop).toBeGreaterThanOrEqual(overlay.postitBottom)
    expect(overlay.lines).toBe(maxLines)
    // Les lignes cachées ne reparaissent pas dans la marge basse du bandeau.
    expect(overlay.overflow).toBe(0)
  })
}

/**
 * La carte sanglée au résumé le plus long, et sa voisine : son bandeau, le plus haut, est celui qui
 * approche le plus le coin où va la sangle.
 */
const STRAPPED_LONGEST = [{ ...STRAPPED, summary: LONGEST_SUMMARY[0].summary }, LONGEST_SUMMARY[1]]

/** Ouvre la table de `STRAPPED_LONGEST`, ses cartes entrées : rend la carte sanglée. */
async function openStrappedCard(page: Page): Promise<Locator> {
  await openTable(page, STRAPPED_LONGEST)
  await enterCards(page)
  return cardAt(page, '/projets/chantier')
}

/**
 * Les pixels de la sangle dans la boîte du bandeau de résumé d'une carte : son jaune, et la moitié de
 * son jaune et de son encre, teinte de sa tranche et des frontières lissées de ses rayures. Son
 * encre, non : en mode clair, c'est celle du texte (`--strap-ink`, `--ink`).
 */
async function strapOverSummary(card: Locator): Promise<number> {
  const [yellow, , edge] = await strapColors(card.page())
  const box = (await summary(card).boundingBox())!
  return (await pixelDistances(card.page(), box, [yellow, edge])).flat().length
}

/**
 * Attend la sangle au coin haut-gauche de la face : son jaune visible, dans le quart haut-gauche
 * seulement, et sa tranche, à la couleur témoin (`probeTranche`), nulle part sur la face, à 1 px de
 * son bord près.
 */
async function expectCornered(card: Locator) {
  const page = card.page()
  const [yellow] = await strapColors(page)
  const tranche = await probeTranche(card)
  const box = (await face(card).boundingBox())!
  const corner = { ...box, width: box.width / 2, height: box.height / 2 }
  const [yellows] = await pixelDistances(page, box, [yellow], corner)
  const [tranches] = await pixelDistances(page, box, [tranche], box)

  expect(yellows.length).toBeGreaterThan(0)
  expect(yellows.filter((distance) => distance > 0)).toEqual([])
  expect(tranches.filter((distance) => distance <= -1)).toEqual([])
}

/**
 * Les transitions parties sur les bandes de la sangle (`watchTransitions`) : la boîte de chacune,
 * puis sa propriété, triées.
 */
const strapRuns = async (transitions: Awaited<ReturnType<typeof watchTransitions>>) =>
  (await transitions())
    .filter(({ layer }) => layer.startsWith('card-strap'))
    .map(({ layer, property }) => [layer, property])
    .sort()

/** Les deux boîtes de la sangle, qui portent chacune sa bande : sa tranche, puis ses rayures. */
const strapBoxes = (card: Locator) => [strap(card), strap(card).locator('.card-strap-stripes')]

/** Le glissement : une transition de la transformation de la bande, dans chaque boîte. */
const GLIDE_RUNS = [
  ['card-strap', 'transform'],
  ['card-strap-stripes', 'transform'],
]

for (const [gesture, act] of INTENTS) {
  test(`${gesture}, la sangle glisse au coin haut-gauche, amincie, en \`--dur-strap\` et \`--ease-out\`, et dégage le bandeau de résumé`, async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, 'appareil sans survol : la révélation au toucher a son scénario')
    const card = await openStrappedCard(page)
    const [duration, easing] = await resolveAll(page, [
      ['transition-duration', 'var(--dur-strap)'],
      ['transition-timing-function', 'var(--ease-out)'],
    ])
    const transitions = await watchTransitions(page)
    expect(await strapOverSummary(card)).toBeGreaterThan(0)

    await act(card)
    await expectRevealed(card, true)
    await settle(page)

    expect(await strapOverSummary(card)).toBe(0)
    await expectCornered(card)
    expect(await strapRuns(transitions)).toEqual(GLIDE_RUNS)
    for (const band of strapBoxes(card)) {
      await expect(band).toHaveCSS('transition-duration', duration, { pseudo: 'before' })
      await expect(band).toHaveCSS('transition-timing-function', easing, { pseudo: 'before' })
      // Amincie : sa transformation, hors de sa rotation, la réduit.
      const scales = await band.evaluate((element) => {
        const { a, d } = new DOMMatrix(getComputedStyle(element, '::before').transform)
        return [a, d]
      })
      expect(scales.every((scale) => scale > 0 && scale < 1)).toBe(true)
    }

    // Au retour, le trajet inverse : la sangle revient en travers de la face, en glissant.
    await page.mouse.move(0, 0)
    await card.evaluate((link: HTMLElement) => link.blur())
    await settle(page)

    expect(await strapOverSummary(card)).toBeGreaterThan(0)
    expect(await strapRuns(transitions)).toEqual([...GLIDE_RUNS, ...GLIDE_RUNS].sort())
  })
}

test('focus clavier : un anneau de 2 px `--accent` à 4 px de la face, aucun sur la cellule', async ({
  page,
}) => {
  await openTable(page, PROJECT_SETS.threeWithShowcase)
  const card = cards(page).first()
  const [accent] = await resolveAll(page, [['outline-color', 'var(--accent)']])

  await focusByKeyboard(card)

  await expect(card).toHaveCSS('outline-style', 'none')
  await expect(face(card)).toHaveCSS('outline-style', 'solid')
  await expect(face(card)).toHaveCSS('outline-width', '2px')
  await expect(face(card)).toHaveCSS('outline-offset', '4px')
  await expect(face(card)).toHaveCSS('outline-color', accent)
})

/** Le nombre d'écouteurs de `pointerdown` sur le document, lu par le débogueur du navigateur. */
async function documentPointerListeners(page: Page): Promise<number> {
  const client = await page.context().newCDPSession(page)
  const { result } = await client.send('Runtime.evaluate', { expression: 'document' })
  const { listeners } = await client.send('DOMDebugger.getEventListeners', {
    objectId: result.objectId!,
  })
  await client.detach()
  return listeners.filter(({ type }) => type === 'pointerdown').length
}

test.describe('au toucher', () => {
  test.skip(({ isMobile }) => !isMobile, 'un appareil sans survol : le projet mobile')

  /** « Ouvrir », visible sur la page. */
  const open = (page: Page) => page.getByText('Ouvrir').filter({ visible: true })

  for (const width of [400, 1280]) {
    test(`à ${width} px, premier toucher : redressement, ombre et bandeau, sans soulèvement ; second : le lien`, async ({
      page,
    }) => {
      await page.setViewportSize({ ...COLUMN_VIEWPORT, width })
      await openTable(page, TWO_CARDS)
      const card = cards(page).first()

      await card.tap()

      await expect(page).toHaveURL('/')
      await expect(pose(card)).toHaveCSS('transform', 'none')
      await expectRevealed(card, true)
      await expect(face(card)).toHaveCSS('transform', 'none')
      await expect(open(page)).toHaveCount(1)
      await expect(card.locator('.card-ribbons').first()).toBeHidden()

      await card.tap()

      await expect(page).toHaveURL('/projets/pleine')
    })
  }

  test('premier toucher : la sangle glisse au coin et dégage le bandeau, au résumé le plus long', async ({
    page,
  }) => {
    const card = await openStrappedCard(page)
    const transitions = await watchTransitions(page)
    expect(await strapOverSummary(card)).toBeGreaterThan(0)

    await card.tap()
    await expectRevealed(card, true)
    await settle(page)

    expect(await strapOverSummary(card)).toBe(0)
    await expectCornered(card)
    expect(await strapRuns(transitions)).toEqual(GLIDE_RUNS)
  })

  test('« Ouvrir » suit le lien : il ne remplace les rubans que pendant la révélation', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    const card = cards(page).first()
    await expect(open(page)).toHaveCount(0)

    await card.tap()
    await open(page).tap()

    await expect(page).toHaveURL('/projets/pleine')
  })

  test('« Ouvrir » : 30 px de haut, marge 0 12 px, bordure 1 px `--ink`, `--paper`, rayon 6 px, 13 / 600', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    await cards(page).first().tap()
    const [ink, paper] = await resolveAll(page, [
      ['border-top-color', 'var(--ink)'],
      ['background-color', 'var(--paper)'],
    ])

    const button = open(page)
    await expect(button).toHaveCSS('height', '30px')
    await expect(button).toHaveCSS('padding', '0px 12px')
    await expect(button).toHaveCSS('border-top-width', '1px')
    await expect(button).toHaveCSS('border-top-color', ink)
    await expect(button).toHaveCSS('background-color', paper)
    await expect(button).toHaveCSS('border-top-left-radius', '6px')
    await expect(button).toHaveCSS('font-size', '13px')
    await expect(button).toHaveCSS('font-weight', '600')
  })

  for (const [band, project] of [
    ['d’une ligne', buildProject({ slug: 'pleine' })],
    ['de deux lignes', FULL_CARD],
  ] as const) {
    test(`la hauteur de la carte ne change pas quand « Ouvrir » remplace une bande ${band}`, async ({
      page,
    }) => {
      await openTable(page, [buildProject({ slug: 'voisine' }), project])
      const card = cardAt(page, '/projets/pleine')
      const height = () => face(card).evaluate((element: HTMLElement) => element.offsetHeight)
      const before = await height()

      await card.tap()
      await expect(open(page)).toHaveCount(1)

      expect(await height()).toBe(before)
    })
  }

  test('une seule carte révélée : toucher une autre carte déplace la révélation', async ({ page }) => {
    await openTable(page, TWO_CARDS)
    const [first, second] = [cards(page).first(), cards(page).last()]

    await first.tap()
    await expectRevealed(first, true)
    await second.tap()

    await expectRevealed(first, false)
    await expectRevealed(second, true)
    await expect(open(page)).toHaveCount(1)
    await expect(page).toHaveURL('/')
  })

  test('toucher hors des cartes referme, et l’écoute du document cesse avec la révélation', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    const card = cards(page).first()
    const box = (await card.boundingBox())!
    expect(await documentPointerListeners(page)).toBe(0)

    await card.tap()
    await expect(open(page)).toHaveCount(1)
    await expect.poll(() => documentPointerListeners(page)).toBe(1)

    // Loin sous la table : le navigateur ajuste vers un lien proche le toucher qui le frôle.
    await page.touchscreen.tap(box.x + box.width, box.y + box.height + 100)

    await expect(open(page)).toHaveCount(0)
    await expectRevealed(card, false)
    await expect.poll(() => documentPointerListeners(page)).toBe(0)
    await expect(page).toHaveURL('/')
  })

  test('un `pointerdown` seul referme : iOS n’émet aucun `click` hors d’un élément cliquable', async ({
    page,
  }) => {
    await openTable(page, TWO_CARDS)
    await cards(page).first().tap()
    await expect(open(page)).toHaveCount(1)

    await page.evaluate(() =>
      document.querySelector('main')!.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })),
    )

    await expect(open(page)).toHaveCount(0)
  })

  test('Entrée ouvre directement la carte focalisée, sans révélation (spec §6.2)', async ({ page }) => {
    await openTable(page, TWO_CARDS)
    await cards(page).first().focus()

    await page.keyboard.press('Enter')

    await expect(page).toHaveURL('/projets/pleine')
  })

  test('un toucher enfonce la carte en 80 ms (spec §1.6, §4.1)', async ({ page }) => {
    await openTable(page, TWO_CARDS)
    const [press] = await resolveAll(page, [['transition-duration', 'var(--dur-press)']])
    // Un contact tenu par le protocole ne rend jamais `:active`, que Chromium ne pose qu'à la relève,
    // le temps du toucher (mesuré le 2026-11-01), et déjà retombé quand `transitionrun` arrive sur un
    // poste lent (rouge en CI, run 41291811020). L'état se force donc, pour lire sa règle.
    const client = await page.context().newCDPSession(page)
    await client.send('DOM.enable')
    await client.send('CSS.enable')
    const { root } = await client.send('DOM.getDocument')
    const { nodeId } = await client.send('DOM.querySelector', { nodeId: root.nodeId, selector: 'a.card' })

    await client.send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: ['active'] })

    await expect(face(cards(page).first())).toHaveCSS('transition-duration', press)
  })
})

test('sur un appareil à survol, un clic ouvre d’emblée', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans survol : le premier toucher révèle')
  await openTable(page, TWO_CARDS)

  await cards(page).first().click()

  await expect(page).toHaveURL('/projets/pleine')
})

test('pressée au pointeur, la carte s’enfonce à ×0,985 en 80 ms (spec §4.1)', async ({ page, isMobile }) => {
  test.skip(isMobile, 'appareil sans pointeur : le toucher a son scénario')
  await openTable(page, PROJECT_SETS.one)
  const card = cards(page)
  const [press] = await resolveAll(page, [['transition-duration', 'var(--dur-press)']])
  await card.hover()

  await page.mouse.down()

  await expect(face(card)).toHaveCSS('transform', PRESSED)
  await expect(face(card)).toHaveCSS('transition-duration', press)
})

test.describe('en mouvement réduit', () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
  })

  for (const [gesture, act] of INTENTS) {
    test(`${gesture}, ni redressement ni soulèvement : l'ombre et le fondu du bandeau seulement`, async ({
      page,
      isMobile,
    }) => {
      test.skip(isMobile, 'appareil sans survol : la révélation au toucher a son scénario')
      await openTable(page, PROJECT_SETS.one)
      const card = cards(page)
      const rest = await pose(card).evaluate((layer) => getComputedStyle(layer).transform)
      await expect(summary(card)).toHaveCSS('transform', 'none')

      await act(card)

      await expectRevealed(card, true)
      await expect(pose(card)).toHaveCSS('transform', rest)
      await expect(face(card)).toHaveCSS('transform', 'none')
    })
  }

  test('au toucher, ni redressement ni soulèvement : l’ombre et le fondu du bandeau seulement', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'un appareil sans survol : le projet mobile')
    await openTable(page, TWO_CARDS)
    const card = cards(page).first()
    const rest = await pose(card).evaluate((layer) => getComputedStyle(layer).transform)

    await card.tap()

    await expectRevealed(card, true)
    await expect(pose(card)).toHaveCSS('transform', rest)
  })

  test('sur une intention, la sangle passe au coin par un fondu croisé, sans transformation animée, et dégage le bandeau', async ({
    page,
    isMobile,
  }) => {
    const card = await openStrappedCard(page)
    // La pose reste en mouvement réduit : redressée, la boîte du bandeau est le bandeau.
    await straighten(card)
    const transitions = await watchTransitions(page)

    await intend(card, isMobile)
    await expectRevealed(card, true)
    await settle(page)

    expect(await strapOverSummary(card)).toBe(0)
    await expectCornered(card)
    // Les deux bandes de chaque boîte, celle qui s'efface et celle qui apparaît.
    expect(await strapRuns(transitions)).toEqual([
      ['card-strap', 'opacity'],
      ['card-strap', 'opacity'],
      ['card-strap-stripes', 'opacity'],
      ['card-strap-stripes', 'opacity'],
    ])
    for (const band of strapBoxes(card)) {
      await expect(band).toHaveCSS('opacity', '0', { pseudo: 'before' })
      await expect(band).toHaveCSS('opacity', '1', { pseudo: 'after' })
    }
  })

  test('pressée, la carte ne s’enfonce pas', async ({ page, isMobile }) => {
    test.skip(isMobile, 'appareil sans pointeur')
    await openTable(page, PROJECT_SETS.one)
    const card = cards(page)
    await card.hover()

    await page.mouse.down()

    await expect(face(card)).toHaveCSS('transform', 'none')
  })
})

for (const colorScheme of ['light', 'dark'] as const) {
  test(`une carte révélée : aucune violation d'accessibilité — ${colorScheme}`, async ({
    page,
    isMobile,
  }) => {
    await page.emulateMedia({ colorScheme })
    await openTable(page, TWO_CARDS)
    await enterCards(page)
    const card = cards(page).first()

    await intend(card, isMobile)
    await expectRevealed(card, true)
    await settle(page)

    const { violations } = await new AxeBuilder({ page }).analyze()
    expect(violations.map((violation) => violation.id)).toEqual([])
  })
}

/** Les quatre propriétés de transformation : `transform` et les trois individuelles. */
const MOTIONS = ['transform', 'rotate', 'translate', 'scale']

/**
 * Les transformations de chaque élément de la carte que le pointeur pourrait faire bouger — la
 * pose, la face et chaque élément de la face —, dans l'ordre du document : leurs quatre propriétés
 * calculées.
 */
const cardMotions = (card: Locator) =>
  pose(card).evaluate(
    (layer, properties) =>
      [layer, ...layer.querySelectorAll('*')].map((element) => {
        const style = getComputedStyle(element)
        return properties.map((property) => style.getPropertyValue(property))
      }),
    MOTIONS,
  )

test('au pointeur, rien ne bouge dans la carte : du coin au coin opposé, la pose, la face et son contenu gardent les mouvements du focus clavier', async ({
  page,
  isMobile,
}) => {
  test.skip(isMobile, 'appareil sans survol')
  await openTable(page, TWO_CARDS)
  const card = cards(page).first()
  await focusByKeyboard(card)
  await settle(page)
  const focused = await cardMotions(card)
  const { x, y, width, height } = (await card.boundingBox())!

  await page.mouse.move(x + width - 1, y + 1)
  await settle(page)
  const atCorner = await cardMotions(card)
  await page.mouse.move(x + 1, y + height - 1)
  await settle(page)

  expect([atCorner, await cardMotions(card)]).toEqual([focused, focused])
})

test('sous la CSP de production, le retard d’entrée s’écrit : rien par un attribut analysé', async ({
  page,
}) => {
  await serveUnderCsp(page)
  await page.setViewportSize(COLUMN_VIEWPORT)
  await openTable(page, TWO_CARDS)

  await expect(entry(cards(page).last())).toHaveCSS('transition-delay', '0.04s, 0.04s')
})
