/**
 * L'entête au défilement, aux seuils exacts de la spec §3.3 : décollée dès 1 px ; au-delà de 56 px,
 * sortie après 8 px cumulés vers le bas, retour après 8 px cumulés vers le haut.
 */
import { describe, expect, test } from 'vitest'
import { headerAtTop, nextHeaderScroll, type HeaderScroll } from '../src/chrome/header-scroll.ts'

/** L'état de l'entête après une suite de positions de défilement, depuis le haut de page. */
function scrollThrough(...positions: number[]): HeaderScroll {
  return positions.reduce(nextHeaderScroll, headerAtTop)
}

describe("l'entête décollée", () => {
  test('reste transparente en haut de page', () => {
    expect(scrollThrough(0).detached).toBe(false)
  })

  test('prend son fond dès 1 px de défilement', () => {
    expect(scrollThrough(1).detached).toBe(true)
  })

  test('ne lit pas un rebond au-dessus du haut de page comme un défilement', () => {
    expect(scrollThrough(-12).detached).toBe(false)
  })
})

describe("l'entête qui sort et revient", () => {
  test('reste visible à 56 px et moins, quel que soit le cumul', () => {
    expect(scrollThrough(300, 56).hidden).toBe(false)
  })

  test('reste visible après 8 px vers le bas au-delà de 56 px', () => {
    expect(scrollThrough(56, 64).hidden).toBe(false)
  })

  test('sort au-delà de 8 px cumulés vers le bas', () => {
    expect(scrollThrough(56, 64, 65).hidden).toBe(true)
  })

  test('reste sortie après 8 px vers le haut', () => {
    expect(scrollThrough(300, 292).hidden).toBe(true)
  })

  test('revient au-delà de 8 px cumulés vers le haut', () => {
    expect(scrollThrough(300, 292, 291).hidden).toBe(false)
  })

  test('remet le cumul à zéro quand le sens change', () => {
    // Sans remise à zéro, 6 − 2 + 8 = 12 px la feraient sortir.
    expect(scrollThrough(56, 62, 60, 68).hidden).toBe(false)
  })
})
