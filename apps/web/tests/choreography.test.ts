/** La géométrie de la chorégraphie d'une fiche (spec §2.7, §4.6 ; issue #22), en logique pure. */
import { describe, expect, test } from 'vitest'
import {
  AT_REST,
  type Frame,
  dimmedKeyframes,
  flightStart,
  milliseconds,
  pivotIn,
  recoil,
} from '../src/project/choreography.ts'

/** Une boîte de `getBoundingClientRect`, par ses quatre nombres. */
const box = (left: number, top: number, width: number, height: number) => ({
  left,
  top,
  width,
  height,
})

/** La matrice d'une rotation de `degrees`, telle que `DOMMatrix` la lit sur `rotate()`. */
function rotation(degrees: number) {
  const radians = (degrees * Math.PI) / 180
  return { a: Math.cos(radians), b: Math.sin(radians), c: -Math.sin(radians), d: Math.cos(radians) }
}

const IDENTITY = rotation(0)

type Box = ReturnType<typeof box>
type Matrix = ReturnType<typeof rotation>
type Point = { x: number; y: number }

/**
 * La boîte englobante d'un élément au repos, de boîte de mise en page `layout` et tourné de
 * `matrix` autour de `origin`, après `translate` et `scale` autour du même pivot : ce que le
 * navigateur rend au premier instant d'un vol.
 */
function boxInFlight(layout: Box, matrix: Matrix, origin: Point, keyframe: Frame) {
  const [x, y] = String(keyframe.translate).split(' ').map(parseFloat)
  const [sx, sy] = String(keyframe.scale).split(' ').map(Number)
  const pivot = { x: layout.left + origin.x, y: layout.top + origin.y }
  const corners = [
    [0, 0],
    [layout.width, 0],
    [0, layout.height],
    [layout.width, layout.height],
  ].map(([cx, cy]) => {
    const [dx, dy] = [cx - origin.x, cy - origin.y]
    const [rx, ry] = [matrix.a * dx + matrix.c * dy, matrix.b * dx + matrix.d * dy]
    return [pivot.x + x + sx * rx, pivot.y + y + sy * ry]
  })
  const xs = corners.map(([cx]) => cx)
  const ys = corners.map(([, cy]) => cy)
  return box(Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))
}

/** La boîte englobante au repos : le vol au point de départ, sans translation ni échelle. */
const boxAtRest = (layout: Box, matrix: Matrix, origin: Point) =>
  boxInFlight(layout, matrix, origin, AT_REST)

/** Deux boîtes égales au millième de pixel. */
function expectSameBox(actual: Box, expected: Box) {
  for (const key of ['left', 'top', 'width', 'height'] as const) {
    expect(actual[key]).toBeCloseTo(expected[key], 3)
  }
}

describe('la durée d’un jeton', () => {
  test.each([
    ['280ms', 280],
    [' 150ms', 150],
    ['1.8s', 1800],
    ['0.2s', 200],
  ])('« %s » vaut %d ms', (token, expected) => {
    expect(milliseconds(token)).toBe(expected)
  })
})

describe('le pivot d’un élément dans sa boîte englobante', () => {
  test('sans rotation, c’est son origine de transformation', () => {
    expect(pivotIn(IDENTITY, 200, 40, { x: 100, y: 20 })).toEqual({ x: 100, y: 20 })
  })

  test('tourné de −2° autour de son coin haut gauche, le coin descend sous le haut de la boîte', () => {
    const pivot = pivotIn(rotation(-2), 200, 40, { x: 0, y: 0 })

    expect(pivot.x).toBeCloseTo(0, 6)
    expect(pivot.y).toBeCloseTo(200 * Math.sin((2 * Math.PI) / 180), 6)
  })
})

describe('le vol d’un élément depuis son homologue', () => {
  const CARD = box(40, 300, 220, 220)
  const LAYOUT = box(600, 100, 594, 594)

  for (const [name, matrix, origin] of [
    ['sans rotation, pivot haut gauche', IDENTITY, { x: 0, y: 0 }],
    ['sans rotation, pivot au centre', IDENTITY, { x: 297, y: 297 }],
    ['tourné de −2°, pivot haut gauche', rotation(-2), { x: 0, y: 0 }],
    ['tourné de 1°, pivot au centre', rotation(1), { x: 297, y: 297 }],
  ] as const) {
    test(`${name} : le premier instant le pose exactement sur l’homologue`, () => {
      const atRest = boxAtRest(LAYOUT, matrix, origin)
      const pivot = pivotIn(matrix, LAYOUT.width, LAYOUT.height, origin)

      const keyframe = flightStart(CARD, atRest, pivot)

      expectSameBox(boxInFlight(LAYOUT, matrix, origin, keyframe), CARD)
    })
  }

  test('à mi-trajet, un même point passe au même endroit quel que soit le pivot', () => {
    const halfway = (origin: Point) => {
      const start = flightStart(CARD, LAYOUT, pivotIn(IDENTITY, LAYOUT.width, LAYOUT.height, origin))
      const [x, y] = String(start.translate).split(' ').map(parseFloat)
      const [sx, sy] = String(start.scale).split(' ').map(Number)
      return boxInFlight(LAYOUT, IDENTITY, origin, {
        translate: `${x / 2}px ${y / 2}px`,
        scale: `${(1 + sx) / 2} ${(1 + sy) / 2}`,
      })
    }

    expectSameBox(halfway({ x: 297, y: 297 }), halfway({ x: 0, y: 0 }))
  })

  test('l’échelle est non uniforme : chaque axe suit le sien', () => {
    expect(flightStart(box(0, 0, 100, 50), box(0, 0, 200, 200), { x: 0, y: 0 }).scale).toBe('0.5 0.25')
  })

  test('au repos, ni translation ni échelle', () => {
    expect(AT_REST).toEqual({ translate: '0px 0px', scale: '1 1' })
  })
})

describe('le recul d’une carte (spec §4.6)', () => {
  const OPENED = box(100, 100, 200, 200)

  test.each([
    ['à droite', box(400, 100, 200, 200), { x: 48, y: 0 }],
    ['au-dessous, sur une table à une colonne', box(100, 400, 200, 200), { x: 0, y: 48 }],
    ['en haut à gauche', box(-200, -200, 200, 200), { x: -48 / Math.SQRT2, y: -48 / Math.SQRT2 }],
  ])('une carte %s recule à l’opposé de la carte ouverte, de 48 px', (_, card, expected) => {
    const { x, y } = recoil(OPENED, card, 48)

    expect(x).toBeCloseTo(expected.x, 6)
    expect(y).toBeCloseTo(expected.y, 6)
  })

  test('deux centres confondus : aucune direction, aucun recul', () => {
    expect(recoil(OPENED, box(150, 150, 100, 100), 48)).toEqual({ x: 0, y: 0 })
  })
})

describe('les images clés d’un ruban en vol (spec §4.6)', () => {
  const START = { translate: '10px 20px', scale: '0.5 0.5' }

  test('à 35 % d’opacité entre 30 % et 70 % du trajet, pleins aux deux bouts', () => {
    expect(dimmedKeyframes(START, AT_REST)).toEqual([
      { ...START, opacity: 1 },
      { offset: 0.3, opacity: 0.35 },
      { offset: 0.7, opacity: 0.35 },
      { ...AT_REST, opacity: 1 },
    ])
  })

  test('au retour, le même creux, du repos vers la carte', () => {
    expect(dimmedKeyframes(AT_REST, START).at(-1)).toEqual({ ...START, opacity: 1 })
  })

  test('un départ relevé en plein creux garde son opacité : le retour d’une ouverture interrompue', () => {
    expect(dimmedKeyframes({ ...START, opacity: '0.5' }, AT_REST)[0]).toEqual({ ...START, opacity: '0.5' })
  })
})
