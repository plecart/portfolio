/** L'adresse d'une fiche (spec §3.2 ; issue #170), en logique pure. */
import { expect, test } from 'vitest'
import { projectPath, slugFromPath } from '../src/project/project.ts'

test.each([
  ['/', null],
  ['/projets/x', 'x'],
  ['/projets/x/', 'x'],
  ['/projets/', null],
  ['/projets/a/b', null],
])('le chemin %s désigne le slug %s', (pathname, slug) => {
  expect(slugFromPath(pathname)).toBe(slug)
})

test('le chemin d’une fiche se relit en son slug', () => {
  expect(slugFromPath(projectPath('atelier'))).toBe('atelier')
})
