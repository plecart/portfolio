/** Le repli d'un groupe de la stack à deux rangées (spec §4.3 ; issue #255), en logique pure. */
import { expect, test } from 'vitest'
import { stackFold, type Slot } from '../src/project/stackFold.ts'

/** Une liste de 440 px : quatre rubans de 100 px, à 8 px d'écart, y tiennent par rangée. */
const WIDTH = 440

/** Le ruban « +N » au bout d'une rangée : 8 px d'écart, puis 50 px. */
const MORE = 58

/** Des rubans de 100 px à 8 px d'écart, rangée par rangée, autant que chaque compte en donne. */
const rows = (...counts: number[]): Slot[] =>
  counts.flatMap((count, row) =>
    Array.from({ length: count }, (_, index) => ({ top: row * 36, right: index * 108 + 100 })),
  )

test.each([
  ['aucun ruban', 0, rows()],
  ['une rangée', 3, rows(3)],
  ['deux rangées pleines, sans débordement : tous, sans « +N »', 8, rows(4, 4)],
  ['un débordement : les deux rangées, le « +N » au bout de la deuxième', 6, rows(4, 2, 3)],
  ['un débordement, le « +N » qui repousse un ruban dans le repli', 7, rows(4, 4, 1)],
] as const)('%s : %i rubans montrés', (_, shown, slots) => {
  expect(stackFold(slots, MORE, WIDTH)).toBe(shown)
})

test('un ruban de toute la largeur sur la deuxième rangée : le « +N » le repousse et la prend seul', () => {
  const wide = (top: number) => ({ top, right: 430 })

  expect(stackFold([wide(0), wide(36), wide(72)], MORE, WIDTH)).toBe(1)
})
