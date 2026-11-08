/**
 * Le zoom de la couche plein écran (issue #243), en logique pure : une zone d'image de 1000 × 800, où
 * une image carrée s'affiche en 800 × 800 à ×1.
 */
import { describe, expect, test } from 'vitest'
import { clampView, containedSize, FIT, panBy, toggleZoom, zoomAt } from '../src/project/zoom.ts'

const ZONE = { width: 1000, height: 800 }
const CENTER = { x: 500, y: 400 }
const SQUARE = { zone: ZONE, natural: { width: 2400, height: 2400 } }
const PORTRAIT = { zone: ZONE, natural: { width: 900, height: 1600 } }

describe('à ×1, l’image tient entière dans la zone, centrée', () => {
  test.each([
    ['carrée', { width: 2400, height: 2400 }, { width: 800, height: 800 }],
    ['en largeur', { width: 1600, height: 900 }, { width: 1000, height: 562.5 }],
    ['en hauteur', { width: 900, height: 1600 }, { width: 450, height: 800 }],
  ])('une image %s', (_, natural, shown) => {
    expect(containedSize(ZONE, natural)).toEqual(shown)
  })

  test('une petite image s’agrandit jusqu’à la zone', () => {
    expect(containedSize(ZONE, { width: 200, height: 100 })).toEqual({ width: 1000, height: 500 })
  })

  test('la translation reste nulle dans les deux axes, quelle que soit la demande', () => {
    expect(panBy(FIT, { x: 1000, y: -1000 }, SQUARE)).toEqual(FIT)
    expect(panBy(FIT, { x: -1000, y: 1000 }, SQUARE)).toEqual(FIT)
  })
})

describe('la translation est bornée à l’image', () => {
  test.each([
    [1000, 1000, 300, 400],
    [-1000, -1000, -300, -400],
    [120, -50, 120, -50],
  ])('à ×2, une demande de (%d, %d) rend (%d, %d)', (dx, dy, x, y) => {
    expect(panBy({ scale: 2, x: 0, y: 0 }, { x: dx, y: dy }, SQUARE)).toEqual({ scale: 2, x, y })
  })

  test('un déplacement s’ajoute à la translation en place', () => {
    expect(panBy({ scale: 2, x: 100, y: -100 }, { x: 100, y: -100 }, SQUARE)).toEqual({
      scale: 2,
      x: 200,
      y: -200,
    })
  })

  test('sur l’axe où l’image tient, la translation reste nulle', () => {
    expect(panBy({ scale: 2, x: 0, y: 0 }, { x: 1000, y: -1000 }, PORTRAIT)).toEqual({
      scale: 2,
      x: 0,
      y: -400,
    })
  })

  test('une zone agrandie ramène une vue dans ses nouvelles bornes', () => {
    const wider = { ...SQUARE, zone: { width: 1600, height: 800 } }

    expect(clampView({ scale: 2, x: -300, y: 400 }, wider)).toEqual({ scale: 2, x: 0, y: 400 })
  })
})

describe('le zoom', () => {
  test.each([
    [5, 4],
    [0.5, 1],
  ])('un facteur demandé de %d rend %d', (requested, scale) => {
    expect(zoomAt({ scale: 2, x: 0, y: 0 }, requested, CENTER, SQUARE).scale).toBe(scale)
  })

  test('revenu à ×1, l’image se recentre', () => {
    expect(zoomAt({ scale: 2, x: -300, y: 400 }, 1, CENTER, SQUARE)).toEqual(FIT)
  })

  test('de ×1 à ×2 au point (700, 400), ce point de l’image reste sous le pointeur', () => {
    expect(zoomAt(FIT, 2, { x: 700, y: 400 }, SQUARE)).toEqual({ scale: 2, x: -200, y: 0 })
  })

  test('de ×1 à ×2 au point (850, 400), la translation libre de −350 est bornée à −300', () => {
    expect(zoomAt(FIT, 2, { x: 850, y: 400 }, SQUARE)).toEqual({ scale: 2, x: -300, y: 0 })
  })

  test('le point visé déplacé entraîne l’image : (700, 400) amené en (650, 400), à ×2', () => {
    expect(zoomAt(FIT, 2, { x: 700, y: 400 }, SQUARE, { x: 650, y: 400 })).toEqual({
      scale: 2,
      x: -250,
      y: 0,
    })
  })

  test('au centre de la zone, la translation suit le facteur', () => {
    expect(zoomAt({ scale: 2, x: -200, y: 100 }, 3, CENTER, SQUARE)).toEqual({
      scale: 3,
      x: -300,
      y: 150,
    })
  })

  test('à sa borne, un facteur hors bornes ne change rien', () => {
    const view = { scale: 4, x: -500, y: 300 }

    expect(zoomAt(view, 5, { x: 900, y: 100 }, SQUARE)).toEqual(view)
  })
})

describe('le double clic', () => {
  test('à ×1, au point (700, 400) : ×2, et ce point de l’image reste sous le pointeur', () => {
    expect(toggleZoom(FIT, { x: 700, y: 400 }, SQUARE)).toEqual({ scale: 2, x: -200, y: 0 })
  })

  test('à ×1, au point (850, 400) : ×2, la translation bornée à −300', () => {
    expect(toggleZoom(FIT, { x: 850, y: 400 }, SQUARE)).toEqual({ scale: 2, x: -300, y: 0 })
  })

  test.each([1.15, 2, 4])('depuis ×%s : l’image entière, quel que soit le point', (scale) => {
    expect(toggleZoom({ scale, x: -50, y: 30 }, { x: 900, y: 100 }, SQUARE)).toEqual(FIT)
  })
})
