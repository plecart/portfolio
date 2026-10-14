/**
 * Le placement des liens de l'auteur, aux seuils exacts de la spec §3.4 et §6.1 (brief de #18,
 * décision 1) : sous 600 px de large, toujours le pied de page ; à partir de 600 px, la colonne
 * fixe sans cellule ou dès 76 px de marge.
 */
import { describe, expect, test } from 'vitest'
import {
  authorLinksPlacement,
  nearestCellMargin,
} from '../src/chrome/author-links-placement.ts'

describe("la forme des liens de l'auteur", () => {
  test('pied de page à 599 px de large, même sans cellule', () => {
    expect(authorLinksPlacement(599, null)).toBe('footer')
  })

  test('pied de page à 599 px de large, même avec une marge large', () => {
    expect(authorLinksPlacement(599, 200)).toBe('footer')
  })

  test('colonne à 600 px de large sans cellule', () => {
    expect(authorLinksPlacement(600, null)).toBe('column')
  })

  test('pied de page devant une marge de 75 px', () => {
    expect(authorLinksPlacement(600, 75)).toBe('footer')
  })

  test('colonne dès une marge de 76 px', () => {
    expect(authorLinksPlacement(600, 76)).toBe('column')
  })
})

describe('la marge à côté de la table', () => {
  /** Une fenêtre sans barre de défilement : la largeur visible est celle de la fenêtre. */
  const noScrollbar = (width: number) => ({ windowWidth: width, viewportWidth: width })

  test('aucune sans cellule', () => {
    expect(nearestCellMargin([], noScrollbar(1280))).toBeNull()
  })

  test("celle d'une table centrée : 118 px à 1280 px (spec §3.1)", () => {
    expect(nearestCellMargin([{ left: 118, right: 1162 }], noScrollbar(1280))).toBe(118)
  })

  test('le bord le plus proche, à droite comme à gauche', () => {
    expect(nearestCellMargin([{ left: 200, right: 1250 }], noScrollbar(1280))).toBe(30)
    expect(nearestCellMargin([{ left: 30, right: 1000 }], noScrollbar(1280))).toBe(30)
  })

  test('la cellule la plus proche du bord, parmi plusieurs', () => {
    const cells = [
      { left: 400, right: 640 },
      { left: 668, right: 1200 },
      { left: 100, right: 340 },
    ]

    expect(nearestCellMargin(cells, noScrollbar(1280))).toBe(80)
  })

  test('hors barre de défilement : 78 px à 1200 px, barre de 10 px comprise (spec §3.4)', () => {
    // La grille de 1044 px, centrée dans les 1190 px visibles, recule de 5 px.
    const cells = [{ left: 73, right: 1117 }]

    expect(nearestCellMargin(cells, { windowWidth: 1200, viewportWidth: 1190 })).toBe(78)
  })

  test('une cellule masquée, de largeur nulle, ne compte pas', () => {
    const cells = [
      { left: 370, right: 730 },
      { left: 0, right: 0 },
    ]

    expect(nearestCellMargin(cells, noScrollbar(1100))).toBe(370)
  })

  test('aucune quand toutes les cellules sont masquées', () => {
    expect(nearestCellMargin([{ left: 0, right: 0 }], noScrollbar(1100))).toBeNull()
  })
})
