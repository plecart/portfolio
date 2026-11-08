/**
 * Les gestes de la couche plein écran (issue #243, décision 8) : double clic et double tape,
 * glisser, molette, pincement et balayage, à la souris et au doigt, aux deux largeurs ; la fermeture
 * au fond, qu'aucun autre geste ne déclenche ; les états qu'ils laissent, et ce qui les solde ; les
 * transitions, et le mouvement réduit. Les images
 * sont carrées : à ×1, l'image a pour côté le plus petit de la zone d'image — sa hauteur au bureau,
 * sa largeur sur téléphone.
 */
import type { Page } from '@playwright/test'
import type { Point } from '../src/project/zoom.ts'
import { expect, test } from './api.ts'
import { resolveAll, settle } from './css.ts'
import {
  arriveAt,
  FIT,
  gallery,
  openViewer,
  outlastOpening,
  panel,
  penDrag,
  transformOf,
  viewer,
  viewerCounter,
  viewerImage,
  viewerZone,
  watchAnimations,
} from './project.ts'
import { buildImage } from './projects.ts'
import { watchTransitions } from './table.ts'

const THREE_IMAGES = ['Écran d’accueil', 'Détail de l’interface', 'Vue d’ensemble'].map((caption) =>
  buildImage('fiche', caption),
)

/**
 * Le cran d'une molette de souris, en px, tel que Playwright l'envoie : la page le reçoit divisé par
 * la densité de l'écran — 100 au bureau, 36,4 sur le Pixel 5 (×2,75), mesuré le 2026-11-08.
 */
const NOTCH = 100

/**
 * Le zoom attendu d'une molette, d'après le `deltaY` que la page a reçu : 2 puissance (−`deltaY` ×
 * 0,002), décuplé avec Ctrl — le `wheelDelta` par défaut de d3-zoom.
 */
const wheelFactor = (deltaY: number, ctrl = false) => 2 ** (-deltaY * 0.002 * (ctrl ? 10 : 1))

test.use({ hasTouch: true })

test.beforeEach(async ({ page }) => {
  await arriveAt(page, { gallery: THREE_IMAGES })
})

/**
 * La vue que la couche écrit sur son image : facteur et translation. Le CSSOM sérialise le facteur
 * sur six chiffres significatifs : un facteur calculé se compare à 4 décimales.
 */
const viewOf = (page: Page) =>
  viewerImage(page).evaluate((image: HTMLElement) => {
    const { a: scale, e: x, f: y } = new DOMMatrix(image.style.transform)
    return { scale, x, y }
  })

/** Les bornes de la translation à ce facteur : le débord de l'image carrée, de chaque côté. */
async function boundsAt(page: Page, scale: number): Promise<Point> {
  const zone = await viewerZone(page)
  const side = Math.min(zone.width, zone.height)
  return {
    x: Math.max(0, (side * scale - zone.width) / 2),
    y: Math.max(0, (side * scale - zone.height) / 2),
  }
}

/** Le centre de l'image. */
async function imageCenter(page: Page): Promise<Point> {
  const { x, y, width, height } = (await viewerImage(page).boundingBox())!
  return { x: x + width / 2, y: y + height / 2 }
}

/**
 * Un point de l'image loin de son centre, que tout zoom depuis ×1 garde sous le pointeur, bornes
 * comprises : à 30 % du côté vers le haut ou la gauche, sur l'axe où l'image remplit la zone — hors
 * des flèches, à 8 px du bord ; au milieu de l'autre, où l'image ne se translate pas avant de
 * remplir la zone.
 */
async function offCenter(page: Page): Promise<Point> {
  const zone = await viewerZone(page)
  const side = Math.min(zone.width, zone.height)
  const reach = (length: number) => (side < length ? 0 : 0.3 * side)
  return {
    x: zone.x + zone.width / 2 - reach(zone.width),
    y: zone.y + zone.height / 2 - reach(zone.height),
  }
}

/** Un point du fond à ×1, au milieu de la marge qui borde l'image : à gauche, ou au-dessus. */
async function backgroundPoint(page: Page): Promise<Point> {
  const zone = await viewerZone(page)
  const image = (await viewerImage(page).boundingBox())!
  return image.x > zone.x
    ? { x: (zone.x + image.x) / 2, y: zone.y + zone.height / 2 }
    : { x: zone.x + zone.width / 2, y: (zone.y + image.y) / 2 }
}

/** Le point de l'image sous un point de la fenêtre, en fraction de sa boîte. */
async function imagePointAt(page: Page, { x, y }: Point): Promise<Point> {
  const box = (await viewerImage(page).boundingBox())!
  return { x: (x - box.x) / box.width, y: (y - box.y) / box.height }
}

/** Attend ce point de l'image sous ce point de la fenêtre, à 1 px près, transitions achevées. */
async function expectUnder(page: Page, imagePoint: Point, { x, y }: Point) {
  await settle(page)
  const box = (await viewerImage(page).boundingBox())!
  expect(Math.abs(box.x + imagePoint.x * box.width - x)).toBeLessThanOrEqual(1)
  expect(Math.abs(box.y + imagePoint.y * box.height - y)).toBeLessThanOrEqual(1)
}

/** Un glisser de la souris, en quatre pas. */
async function mouseDrag(page: Page, from: Point, to: Point) {
  await page.mouse.move(from.x, from.y)
  await page.mouse.down()
  await page.mouse.move(to.x, to.y, { steps: 4 })
  await page.mouse.up()
}

/**
 * Des doigts posés ensemble, menés chacun de son départ à son arrivée en quatre temps, puis levés —
 * ou interrompus par le navigateur (`touchCancel`).
 */
async function fingers(
  page: Page,
  paths: [Point, Point][],
  end: 'touchEnd' | 'touchCancel' = 'touchEnd',
) {
  const client = await page.context().newCDPSession(page)
  const at = (step: number) =>
    paths.map(([from, to], id) => ({
      id,
      x: from.x + ((to.x - from.x) * step) / 4,
      y: from.y + ((to.y - from.y) * step) / 4,
    }))

  await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: at(0) })
  for (const step of [1, 2, 3, 4]) {
    await client.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: at(step) })
  }
  await client.send('Input.dispatchTouchEvent', { type: end, touchPoints: [] })
  await client.detach()
}

/**
 * Deux doigts écartés de 50 px à 100 px autour d'un point, qui double l'image, leur milieu mené de
 * ce point à `to`.
 */
const pinchOut = (page: Page, from: Point, to = from) =>
  fingers(page, [
    [
      { x: from.x - 25, y: from.y },
      { x: to.x - 50, y: to.y },
    ],
    [
      { x: from.x + 25, y: from.y },
      { x: to.x + 50, y: to.y },
    ],
  ])

/** Deux doigts écartés de 100 px à 102 px autour d'un point : un pincement de ×1,02. */
const pinchSlightly = (page: Page, { x, y }: Point, end?: 'touchEnd' | 'touchCancel') =>
  fingers(
    page,
    [
      [
        { x: x - 50, y },
        { x: x - 51, y },
      ],
      [
        { x: x + 50, y },
        { x: x + 51, y },
      ],
    ],
    end,
  )

/** Deux touchers au même point, coup sur coup. */
async function doubleTap(page: Page, { x, y }: Point) {
  await page.touchscreen.tap(x, y)
  await page.touchscreen.tap(x, y)
}

/** Un cran de molette au point, vers le bas (`notches` positif) ou vers le haut, l'un après l'autre. */
async function wheel(page: Page, { x, y }: Point, notches: number) {
  await page.mouse.move(x, y)
  for (let notch = 0; notch < Math.abs(notches); notch++) {
    await page.mouse.wheel(0, Math.sign(notches) * NOTCH)
  }
}

/** Le toucher d'un pointeur à un point : un clic de la souris, ou un toucher du doigt. */
const TAPS = {
  souris: (page: Page, { x, y }: Point) => page.mouse.click(x, y),
  doigt: (page: Page, { x, y }: Point) => page.touchscreen.tap(x, y),
}

/** Attend deux images : React a rendu ce qu'un événement hors de ses gestionnaires a demandé. */
const nextFrames = (page: Page) =>
  page.evaluate(
    () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))),
  )

/** Où un geste du recensement se joue : le centre de l'image, un point du fond. */
type Places = { image: Point; background: Point }

/** Un point décalé de 30 px vers la droite et vers le bas : la fin d'un court glisser. */
const nudge = ({ x, y }: Point): Point => ({ x: x + 30, y: y + 30 })

/**
 * Les gestes du pointeur qui finissent dans la zone d'image, recensés : seize formes, souris puis
 * doigt, chacune avec le facteur qu'elle laisse, ou `null` si elle ferme la couche. Seul un clic ou
 * un toucher sur le fond, sans glisser, la ferme — un double clic ou un double tape sur le fond dès
 * son premier temps —, une fois passé le double clic qui l'a ouverte (`outlastOpening`). Un
 * glisser relâché sur le fond n'est pas un clic du fond, même si son `click` part de leur ancêtre
 * commun ; un clic droit non plus.
 */
const POINTER_GESTURES: [string, (page: Page, at: Places) => Promise<unknown>, number | null][] = [
  ['un clic sur l’image', (page, { image: { x, y } }) => page.mouse.click(x, y), 1],
  ['un clic sur le fond', (page, { background: { x, y } }) => page.mouse.click(x, y), null],
  [
    'un clic droit sur le fond',
    (page, { background: { x, y } }) => page.mouse.click(x, y, { button: 'right' }),
    1,
  ],
  ['un glisser sur l’image', (page, { image }) => mouseDrag(page, image, nudge(image)), 1],
  ['un glisser sur le fond', (page, { background }) => mouseDrag(page, background, nudge(background)), 1],
  ['un glisser de l’image au fond', (page, { image, background }) => mouseDrag(page, image, background), 1],
  ['un glisser du fond à l’image', (page, { image, background }) => mouseDrag(page, background, image), 1],
  ['un double clic sur l’image', (page, { image: { x, y } }) => page.mouse.dblclick(x, y), 2],
  ['un double clic sur le fond', (page, { background: { x, y } }) => page.mouse.dblclick(x, y), null],
  ['un toucher sur l’image', (page, { image: { x, y } }) => page.touchscreen.tap(x, y), 1],
  ['un toucher sur le fond', (page, { background: { x, y } }) => page.touchscreen.tap(x, y), null],
  ['un double tape sur l’image', (page, { image }) => doubleTap(page, image), 2],
  ['un double tape sur le fond', (page, { background }) => doubleTap(page, background), null],
  ['un doigt glissé de l’image au fond', (page, { image, background }) => fingers(page, [[image, background]]), 1],
  ['un doigt glissé du fond à l’image', (page, { image, background }) => fingers(page, [[background, image]]), 1],
  ['un pincement sur l’image', (page, { image }) => pinchOut(page, image), 2],
]

test.describe('les gestes du pointeur, recensés', () => {
  test('seize formes, dont quatre ferment la couche', () => {
    expect(POINTER_GESTURES).toHaveLength(16)
    expect(POINTER_GESTURES.filter(([, , scale]) => scale === null)).toHaveLength(4)
  })

  for (const [name, gesture, scale] of POINTER_GESTURES) {
    const outcome = scale === null ? 'ferme la couche seule' : `laisse la couche ouverte, à ×${scale}`
    test(`${name} ${outcome}`, async ({ page }) => {
      await openViewer(page)
      await outlastOpening(page)

      await gesture(page, { image: await imageCenter(page), background: await backgroundPoint(page) })

      if (scale === null) {
        await expect(viewer(page)).toHaveCount(0)
        await expect(panel(page)).toHaveAccessibleName('Fiche')
      } else {
        await settle(page)
        await expect(viewer(page)).toHaveAttribute('data-state', 'open')
        await expect.poll(async () => (await viewOf(page)).scale).toBeCloseTo(scale, 4)
      }
    })
  }
})

test.describe('le double clic et le double tape', () => {
  for (const [pointer, twice] of [
    ['à la souris', (page: Page, { x, y }: Point) => page.mouse.dblclick(x, y)],
    ['au doigt', doubleTap],
  ] as const) {
    test(`${pointer}, à ×1 : ×2 au point visé, qui reste sous le pointeur ; de tout zoom supérieur : ×1`, async ({
      page,
    }) => {
      await openViewer(page)
      const aim = await offCenter(page)
      const under = await imagePointAt(page, aim)

      await twice(page, aim)

      expect((await viewOf(page)).scale).toBe(2)
      await expectUnder(page, under, aim)

      await twice(page, aim)
      await settle(page)
      expect(await transformOf(page)).toBe(FIT)

      for (const key of ['+', '+']) await page.keyboard.press(key)
      await twice(page, aim)
      await settle(page)
      expect(await transformOf(page)).toBe(FIT)
    })
  }

  test('le double clic glisse en 240 ms, par la courbe --ease-out', async ({ page }) => {
    const [curve] = await resolveAll(page, [['transition-timing-function', 'var(--ease-out)']])
    await openViewer(page)
    const transitions = await watchTransitions(page)
    const { x, y } = await offCenter(page)

    await page.mouse.dblclick(x, y)
    await settle(page)

    expect(await transitions('image-viewer-image')).toEqual([
      { layer: 'image-viewer-image', property: 'transform', duration: '0.24s' },
    ])
    await expect(viewerImage(page)).toHaveCSS('transition-timing-function', curve)
  })
})

test.describe('le glisser', () => {
  test('zoomée, l’image suit la souris, bornée à l’image, sans transition', async ({ page }) => {
    await openViewer(page)
    await page.keyboard.press('+')
    await settle(page)
    const transitions = await watchTransitions(page)
    const bounds = await boundsAt(page, 2)
    const start = await imageCenter(page)
    const clamp = (value: number, bound: number) => Math.min(Math.max(value, -bound), bound)

    await page.mouse.move(start.x, start.y)
    await page.mouse.down()
    await page.mouse.move(start.x - 30, start.y - 20, { steps: 3 })
    await expect
      .poll(() => viewOf(page))
      .toEqual({ scale: 2, x: clamp(-30, bounds.x), y: clamp(-20, bounds.y) })

    await page.mouse.move(start.x - 2000, start.y - 2000, { steps: 3 })
    await page.mouse.up()

    await expect.poll(() => viewOf(page)).toEqual({ scale: 2, x: -bounds.x, y: -bounds.y })
    expect(await transitions('image-viewer-image')).toEqual([])
    await expect(viewer(page)).toHaveAttribute('data-state', 'open')
  })

  test('zoomée, l’image suit le doigt, et un balayage ne change pas d’image', async ({ page }) => {
    await openViewer(page)
    await page.keyboard.press('+')
    await settle(page)
    const bounds = await boundsAt(page, 2)
    const start = await imageCenter(page)

    await fingers(page, [[start, { x: start.x - 60, y: start.y }]])

    await expect.poll(() => viewOf(page)).toEqual({ scale: 2, x: -Math.min(60, bounds.x), y: 0 })
    await expect(viewerCounter(page)).toHaveText('1 / 3')
  })

  // Le doigt et le stylet balaient ; la souris, qui glisse, non (spec §1.10).
  for (const [pointer, drag, swipes] of [
    ['du doigt', (page: Page, from: Point, to: Point) => fingers(page, [[from, to]]), true],
    ['du stylet', penDrag, true],
    ['de la souris', mouseDrag, false],
  ] as const) {
    const outcome = swipes ? 'change d’image, dans les deux sens' : 'ne change pas d’image'
    test(`à ×1, un balayage ${pointer} ${outcome}`, async ({ page }) => {
      await openViewer(page)
      const start = await imageCenter(page)

      await drag(page, start, { x: start.x - 60, y: start.y })
      await expect(viewerCounter(page)).toHaveText(swipes ? '2 / 3' : '1 / 3')

      await drag(page, start, { x: start.x + 60, y: start.y })
      await expect(viewerCounter(page)).toHaveText('1 / 3')
      expect(await transformOf(page)).toBe(FIT)
    })
  }

  test('zoomée, l’image se saisit : grab, puis grabbing pendant le glisser', async ({
    page,
    isMobile,
  }) => {
    test.skip(isMobile, 'pas de curseur au doigt')
    await openViewer(page)
    const zone = page.locator('.image-viewer-zone')
    await expect(zone).toHaveCSS('cursor', 'auto')

    await page.keyboard.press('+')
    await expect(zone).toHaveCSS('cursor', 'grab')

    const { x, y } = await imageCenter(page)
    await page.mouse.move(x, y)
    await page.mouse.down()
    await expect(zone).toHaveCSS('cursor', 'grabbing')
    await page.mouse.up()
  })
})

/**
 * Les états des gestes de la couche, et ce qui doit les solder (passe 2 de relecture de #243) : le
 * dernier toucher, le pincement, la vue et son glissement. Un démontage ou un état neuf solde tout
 * à l'ouverture et à la fermeture, sauf le double clic que la galerie commence et qui ouvre la
 * couche à son premier temps ; le reste se rejoue ici, une forme par ligne, en quatre tables.
 */
test.describe('les états des gestes, soldés', () => {
  /** Les deux temps d'un double clic sur la galerie, à tant de ms : la couche paraît au premier. */
  const OPENING_DOUBLE_CLICKS = (['souris', 'doigt'] as const).flatMap((pointer) =>
    [60, 150, 300].map((gap) => [pointer, gap] as const),
  )

  /** Ce qui se joue au point d'un geste : le centre de l'image. */
  type Act = (page: Page, at: Point) => Promise<unknown>

  /**
   * Ce qui, entre deux touchers au même point, rompt le double toucher qu'ils feraient : un autre
   * geste, une molette, un changement d'image, une touche — la dernière sur la couche zoomée.
   */
  const TAP_BREAKS: [string, keyof typeof TAPS, Act, boolean][] = [
    ['un glisser de la souris', 'souris', (page, at) => mouseDrag(page, at, nudge(at)), false],
    [
      'un glisser du doigt, sans balayage',
      'doigt',
      (page, at) => fingers(page, [[at, { x: at.x, y: at.y + 30 }]]),
      false,
    ],
    [
      'un balayage du doigt',
      'doigt',
      (page, at) => fingers(page, [[at, { x: at.x - 60, y: at.y }]]),
      false,
    ],
    [
      'un geste du doigt interrompu',
      'doigt',
      (page, at) => fingers(page, [[at, at]], 'touchCancel'),
      false,
    ],
    ['un pincement', 'doigt', (page, at) => pinchOut(page, at), false],
    ['deux crans de molette', 'souris', (page, at) => wheel(page, at, -2), false],
    [
      '« Image suivante »',
      'souris',
      (page) => viewer(page).getByRole('button', { name: 'Image suivante' }).click(),
      false,
    ],
    ['la touche →', 'souris', (page) => page.keyboard.press('ArrowRight'), false],
    ['la touche +', 'souris', (page) => page.keyboard.press('+'), false],
    ['la touche ↓', 'souris', (page) => page.keyboard.press('ArrowDown'), true],
  ]

  /** Les zooms qui s'achèvent, et le facteur qu'ils laissent : sous ×1,05, l'image entière. */
  const ZOOM_ENDS: [string, Act, number][] = [
    ['un pincement de ×1,02', (page, at) => pinchSlightly(page, at), 1],
    [
      'un pincement de ×1,02 que le navigateur interrompt',
      (page, at) => pinchSlightly(page, at, 'touchCancel'),
      1,
    ],
    [
      'une molette fine, Ctrl enfoncé',
      async (page, { x, y }) => {
        await page.mouse.move(x, y)
        await page.keyboard.down('Control')
        await page.mouse.wheel(0, -2)
        await page.keyboard.up('Control')
      },
      1,
    ],
    [
      'deux pincements, qui doublent chacun',
      async (page, at) => {
        await pinchOut(page, at)
        await pinchOut(page, at)
      },
      4,
    ],
  ]

  /** Ce qui suit un pas qui glisse — la vue zoomée et déplacée à la touche — sans glisser. */
  const GLIDE_BREAKS: [string, Act][] = [
    ['un cran de molette', (page, at) => wheel(page, at, -1)],
    ['un pincement', (page, at) => pinchOut(page, at)],
    [
      'le redimensionnement',
      async (page) => {
        const before = await transformOf(page)
        await page.setViewportSize({ width: page.viewportSize()!.width, height: 400 })
        await expect.poll(() => transformOf(page)).not.toBe(before)
      },
    ],
  ]

  test('vingt-trois formes : six doubles clics d’ouverture, dix ruptures, quatre fins de zoom, trois pas', () => {
    const tables = [OPENING_DOUBLE_CLICKS, TAP_BREAKS, ZOOM_ENDS, GLIDE_BREAKS]

    expect(tables.map((forms) => forms.length)).toEqual([6, 10, 4, 3])
  })

  for (const [pointer, gap] of OPENING_DOUBLE_CLICKS) {
    const twice = pointer === 'souris' ? 'double clic' : 'double tape'
    test(`un ${twice} sur la galerie hors de l’image de la couche la laisse ouverte, ses temps à ${gap} ms`, async ({
      page,
    }) => {
      const frame = (await gallery(page).locator('.project-gallery-frame').boundingBox())!
      const at = { x: frame.x + 20, y: frame.y + 20 }

      await TAPS[pointer](page, at)
      await page.waitForTimeout(gap)
      await TAPS[pointer](page, at)

      await expect(viewer(page)).toHaveAttribute('data-state', 'open')
      // Le second temps est tombé sur le fond de la couche, hors de son image.
      const hit = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.className, at)
      expect(hit).toBe('image-viewer-zone')
    })
  }

  for (const [event, pointer, act, zoomed] of TAP_BREAKS) {
    test(`${event}${zoomed ? ', zoomée,' : ''} entre deux touchers rompt le double toucher`, async ({
      page,
    }) => {
      await openViewer(page)
      const at = await imageCenter(page)
      if (zoomed) await page.keyboard.press('+')
      await TAPS[pointer](page, at)
      await act(page, at)
      await nextFrames(page)
      const left = await viewOf(page)

      await TAPS[pointer](page, at)

      expect(await viewOf(page)).toEqual(left)
    })
  }

  for (const [name, gesture, scale] of ZOOM_ENDS) {
    test(`${name} laisse ×${scale}`, async ({ page }) => {
      await openViewer(page)

      await gesture(page, await imageCenter(page))

      await expect.poll(async () => (await viewOf(page)).scale).toBeCloseTo(scale, 4)
    })
  }

  for (const [event, act] of GLIDE_BREAKS) {
    test(`${event}, après un pas qui glisse, ne glisse pas`, async ({ page }) => {
      await openViewer(page)
      const at = await imageCenter(page)
      for (const key of ['+', 'ArrowRight', 'ArrowRight', 'ArrowRight']) {
        await page.keyboard.press(key)
      }
      await settle(page)
      const transitions = await watchTransitions(page)

      await act(page, at)
      await settle(page)

      expect(await transitions('image-viewer-image')).toEqual([])
    })
  }
})

test.describe('la molette', () => {
  /**
   * Consigne les molettes que la page reçoit à partir de maintenant, après la couche : leur `deltaY`,
   * et si la couche les a retenues.
   */
  async function watchWheels(page: Page) {
    const seen = await page.evaluateHandle(() => {
      const wheels: { deltaY: number; prevented: boolean }[] = []
      addEventListener('wheel', ({ deltaY, defaultPrevented: prevented }) =>
        wheels.push({ deltaY, prevented }),
      )
      return wheels
    })
    return () => seen.jsonValue()
  }

  test('zoome au point du curseur, qui reste sous lui, de ×1 à ×4 et retour, sans transition', async ({
    page,
  }) => {
    await openViewer(page)
    const transitions = await watchTransitions(page)
    const wheels = await watchWheels(page)
    const aim = await offCenter(page)
    const under = await imagePointAt(page, aim)

    await wheel(page, aim, -1)

    await expect.poll(async () => (await wheels()).length).toBe(1)
    const factor = wheelFactor((await wheels())[0].deltaY)
    await expect.poll(async () => (await viewOf(page)).scale).toBeCloseTo(factor, 4)
    await expectUnder(page, under, aim)

    // Assez de crans pour passer ×4 depuis ×1, puis pour revenir à ×1 depuis ×4.
    const toBound = Math.ceil(Math.log2(4) / Math.log2(factor))
    await wheel(page, aim, -toBound)
    await expect.poll(async () => (await viewOf(page)).scale).toBe(4)

    await wheel(page, aim, toBound + 1)
    await expect.poll(() => transformOf(page)).toBe(FIT)
    expect(await transitions('image-viewer-image')).toEqual([])
  })

  test('Ctrl et la molette — le pincement d’un pavé tactile — zooment l’image, et non la page', async ({
    page,
  }) => {
    await openViewer(page)
    const wheels = await watchWheels(page)
    const { x, y } = await imageCenter(page)

    await page.mouse.move(x, y)
    await page.keyboard.down('Control')
    await page.mouse.wheel(0, -10)
    await page.keyboard.up('Control')

    await expect.poll(async () => (await wheels()).length).toBe(1)
    const [{ deltaY, prevented }] = await wheels()
    expect(prevented).toBe(true)
    await expect.poll(async () => (await viewOf(page)).scale).toBeCloseTo(wheelFactor(deltaY, true), 4)
  })
})

test.describe('au doigt', () => {
  // Le milieu mené de 30 px vers la droite reste dans les bornes à ×2, aux deux largeurs : 44,5 px au
  // bureau, 200 px sur téléphone.
  for (const [name, shift] of [
    ['zoome au point milieu, qui reste sous les doigts', 0],
    ['entraîne l’image avec le milieu des doigts', 30],
  ] as const) {
    test(`le pincement ${name}, sans transition`, async ({ page }) => {
      await openViewer(page)
      const transitions = await watchTransitions(page)
      const from = await offCenter(page)
      const to = { x: from.x + shift, y: from.y }
      const under = await imagePointAt(page, from)

      await pinchOut(page, from, to)

      await expect.poll(async () => (await viewOf(page)).scale).toBeCloseTo(2, 4)
      await expectUnder(page, under, to)
      expect(await transitions('image-viewer-image')).toEqual([])
    })
  }

  test('la couche prend tous les gestes du doigt ; le cadre de la galerie laisse les siens au navigateur', async ({
    page,
  }) => {
    await openViewer(page)

    await expect(viewer(page)).toHaveCSS('touch-action', 'none')
    await expect(gallery(page).locator('.project-gallery-frame')).toHaveCSS(
      'touch-action',
      'pan-y pinch-zoom',
    )
  })
})

test.describe('en mouvement réduit', () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
  })

  test('la couche s’ouvre et se ferme par un fondu de 150 ms', async ({ page }) => {
    const [curve] = await resolveAll(page, [['animation-timing-function', 'var(--ease-out)']])
    const animations = await watchAnimations(page)

    await openViewer(page)
    await page.keyboard.press('Escape')
    await expect(viewer(page)).toHaveCount(0)

    expect(await animations()).toEqual([
      { name: 'project-in', duration: '0.15s', curve },
      { name: 'project-out', duration: '0.15s', curve },
    ])
  })

  test('le double clic et les touches zooment sans transition', async ({ page }) => {
    await openViewer(page)
    const transitions = await watchTransitions(page)
    const { x, y } = await offCenter(page)

    await page.mouse.dblclick(x, y)
    expect((await viewOf(page)).scale).toBe(2)
    await page.keyboard.press('+')
    expect((await viewOf(page)).scale).toBe(3)

    expect(await transitions('image-viewer-image')).toEqual([])
  })
})
