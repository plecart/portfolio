/**
 * Le clavier de la couche plein écran (issue #243, décision 6), en logique pure : chaque forme
 * d'une touche — une touche, ses modificateurs, l'état de la couche — commande la couche ou reste
 * au navigateur. Les formes se recensent ici, produit de trois listes écrites à la main ; celles qui
 * commandent la couche s'écrivent une à une, toute autre forme reste au navigateur.
 */
import { expect, test } from 'vitest'
import { type KeyCommand, keyCommand } from '../src/project/viewerKeys.ts'

/** Les touches de la couche, et une autre, qui la représente. */
const KEYS = ['+', '-', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Enter']

/** Aucun modificateur, puis chacun seul. */
const MODIFIERS = ['', 'Shift', 'Control', 'Alt', 'Meta']

/** Les états de la couche : zoomée ou non, à plusieurs images ou à une seule. */
const STATES = {
  '×1': { zoomed: false, navigable: true },
  '×1, une image': { zoomed: false, navigable: false },
  zoomé: { zoomed: true, navigable: true },
  'zoomé, une image': { zoomed: true, navigable: false },
}

type State = keyof typeof STATES

/** Une forme, telle que la table la nomme : « Maj + , zoomé ». */
type Form = { key: string; modifier: string; state: State }
const nameOf = ({ key, modifier, state }: Form) => `${modifier && `${modifier} `}${key}, ${state}`

const FORMS: Form[] = KEYS.flatMap((key) =>
  MODIFIERS.flatMap((modifier) =>
    (Object.keys(STATES) as State[]).map((state) => ({ key, modifier, state })),
  ),
)

/**
 * Les formes qui commandent la couche. + et − zooment d'une unité, avec ou sans Maj, dans tout
 * état ; zoomé, les flèches déplacent l'image de 100 px à l'opposé de leur sens ; à ×1, ← et →
 * changent d'image s'il y en a plusieurs.
 */
const COMMANDS = new Map<string, KeyCommand>([
  ['+, ×1', { zoom: 1 }],
  ['+, ×1, une image', { zoom: 1 }],
  ['+, zoomé', { zoom: 1 }],
  ['+, zoomé, une image', { zoom: 1 }],
  ['Shift +, ×1', { zoom: 1 }],
  ['Shift +, ×1, une image', { zoom: 1 }],
  ['Shift +, zoomé', { zoom: 1 }],
  ['Shift +, zoomé, une image', { zoom: 1 }],
  ['-, ×1', { zoom: -1 }],
  ['-, ×1, une image', { zoom: -1 }],
  ['-, zoomé', { zoom: -1 }],
  ['-, zoomé, une image', { zoom: -1 }],
  ['Shift -, ×1', { zoom: -1 }],
  ['Shift -, ×1, une image', { zoom: -1 }],
  ['Shift -, zoomé', { zoom: -1 }],
  ['Shift -, zoomé, une image', { zoom: -1 }],
  ['ArrowLeft, zoomé', { pan: { x: 100, y: 0 } }],
  ['ArrowLeft, zoomé, une image', { pan: { x: 100, y: 0 } }],
  ['ArrowRight, zoomé', { pan: { x: -100, y: 0 } }],
  ['ArrowRight, zoomé, une image', { pan: { x: -100, y: 0 } }],
  ['ArrowUp, zoomé', { pan: { x: 0, y: 100 } }],
  ['ArrowUp, zoomé, une image', { pan: { x: 0, y: 100 } }],
  ['ArrowDown, zoomé', { pan: { x: 0, y: -100 } }],
  ['ArrowDown, zoomé, une image', { pan: { x: 0, y: -100 } }],
  ['ArrowLeft, ×1', { step: -1 }],
  ['ArrowRight, ×1', { step: 1 }],
])

test('140 formes recensées, dont 26 commandent la couche, chacune une forme recensée', () => {
  const names = FORMS.map(nameOf)

  expect(names).toHaveLength(140)
  expect(COMMANDS.size).toBe(26)
  expect([...COMMANDS.keys()].filter((name) => !names.includes(name))).toEqual([])
})

test.each(FORMS.map((form) => [nameOf(form), form] as const))('%s', (name, form) => {
  const { key, modifier, state } = form
  const pressed = {
    key,
    shiftKey: modifier === 'Shift',
    ctrlKey: modifier === 'Control',
    altKey: modifier === 'Alt',
    metaKey: modifier === 'Meta',
  }

  expect(keyCommand(pressed, STATES[state])).toEqual(COMMANDS.get(name))
})
