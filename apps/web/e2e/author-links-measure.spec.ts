/**
 * La mesure qui choisit la forme des liens de l'auteur, sur la page servie (spec §3.4 ; brief de
 * #18, décision 1) : la marge relue à chaque voie qui la change, avant la première peinture.
 *
 * Les seuils exacts sont prouvés en Vitest (`tests/author-links-placement.test.ts`) ; la marge sous
 * une barre de défilement visible, dans `author-links-scrollbar.spec.ts`.
 */
import { expect, test } from '@playwright/test'
import { COLUMN_VIEWPORT, expectPlacement, placeCells } from './table.ts'

test.skip(({ isMobile }) => isMobile, 'largeurs de bureau : le projet desktop les porte')

test('sans cellule, les liens sont en colonne dès 600 px de large, en pied de page en dessous', async ({
  page,
}) => {
  await page.setViewportSize({ width: 600, height: 800 })
  await page.goto('/')
  await expectPlacement(page, 'column')

  await page.setViewportSize({ width: 599, height: 800 })
  await expectPlacement(page, 'footer')

  await page.setViewportSize({ width: 600, height: 800 })
  await expectPlacement(page, 'column')
})

test('devant des cellules, la marge mesurée décide, et se relit au redimensionnement comme au changement de cellules', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1100, height: 800 })
  await page.goto('/')
  await expectPlacement(page, 'column')

  // Un bloc de 1044 px, quatre colonnes : 28 px de marge à 1100 px (spec §3.4).
  await placeCells(page, [1044])
  await expectPlacement(page, 'footer')

  // Une carte seule de 360 px (spec §4.1) : 370 px de marge.
  await placeCells(page, [360])
  await expectPlacement(page, 'column')

  await placeCells(page, [1044])
  await expectPlacement(page, 'footer')

  // 118 px de marge à 1280 px (spec §3.1), puis de nouveau 28 à 1100.
  await page.setViewportSize({ width: 1280, height: 800 })
  await expectPlacement(page, 'column')
  await page.setViewportSize({ width: 1100, height: 800 })
  await expectPlacement(page, 'footer')

  await placeCells(page, [])
  await expectPlacement(page, 'column')
})

/**
 * Chaque voie qui change la marge la fait relire. Dénombrées avant correctif, le 2026-10-14
 * (première relecture de la PR #93) : sept voies.
 *
 * - relues : la fenêtre redimensionnée (test ci-dessus) ; un élément ajouté ou retiré ;
 * - fuyaient : un attribut changé sur un élément en place — `data-table-cell` posé ou retiré,
 *   `style`, `hidden` ou `class` qui redimensionne ou masque la cellule — ; une cellule masquée,
 *   mesurée comme une marge nulle ;
 * - neutralisée : une barre de défilement qui apparaît ou disparaît, la marge se comptant hors
 *   barre (`author-links-scrollbar.spec.ts`) ;
 * - hors portée, à la charge de la table (`TABLE_CELL_SELECTOR`) : une taille changée par une
 *   feuille sans mutation ; une transformation posée sur un ancêtre de la cellule.
 *
 * Les cas partent d'une cellule de 360 px à 1100 px — colonne, 370 px de marge — et passent la
 * page en pied de page par leur voie, ou l'inverse depuis une cellule de 1044 px.
 */
const CELL_ENTRIES: [string, (cell: HTMLElement) => void][] = [
  [
    'une cellule de 1044 px ajoutée',
    (cell) => {
      const wide = document.createElement('div')
      wide.setAttribute('data-table-cell', '')
      wide.style.cssText = 'width: 1044px; height: 10px; margin: 0 auto'
      cell.after(wide)
    },
  ],
  ['la cellule élargie par `style`', (cell) => (cell.style.width = '1044px')],
  [
    "l'attribut posé sur un élément large déjà en place",
    (cell) => {
      const wide = document.createElement('div')
      wide.style.cssText = 'width: 1044px; height: 10px; margin: 0 auto'
      cell.after(wide)
      // Une image plus tard : l'ajout et l'attribut, lus ensemble, ne prouveraient que l'ajout.
      requestAnimationFrame(() => wide.setAttribute('data-table-cell', ''))
    },
  ],
]

for (const [entry, apply] of CELL_ENTRIES) {
  test(`la marge se relit quand une cellule large entre — ${entry}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 800 })
    await page.goto('/')
    await placeCells(page, [360])
    await expectPlacement(page, 'column')

    await page.locator('[data-table-cell]').evaluate(apply)

    await expectPlacement(page, 'footer')
  })
}

const CELL_EXITS: [string, (cell: HTMLElement) => void][] = [
  ['retirée du DOM', (cell) => cell.remove()],
  ["l'attribut retiré", (cell) => cell.removeAttribute('data-table-cell')],
  ['masquée par `hidden`', (cell) => (cell.hidden = true)],
  ['masquée par `style`', (cell) => (cell.style.display = 'none')],
  [
    'masquée par `class`',
    (cell) => {
      const sheet = document.createElement('style')
      sheet.textContent = '.probe-hidden { display: none }'
      document.head.append(sheet)
      cell.classList.add('probe-hidden')
    },
  ],
]

for (const [exit, apply] of CELL_EXITS) {
  test(`la marge se relit quand la cellule large sort — ${exit}`, async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 800 })
    await page.goto('/')
    await placeCells(page, [360, 1044])
    await expectPlacement(page, 'footer')

    await page.locator('[data-table-cell]').nth(1).evaluate(apply)

    await expectPlacement(page, 'column')
  })
}

test('la marge se relit quand un attribut de la grille déplace ses cellules', async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 800 })
  await page.goto('/')
  await placeCells(page, [360])
  await expectPlacement(page, 'column')

  // La cellule, centrée dans 400 px de contenu après 700 px de marge, finit à 20 px du bord.
  await page.getByRole('main').evaluate((table) => (table.style.paddingLeft = '700px'))

  await expectPlacement(page, 'footer')
})

test("la pose d'une cellule, sur son élément enfant, ne relit pas la marge", async ({ page }) => {
  // Compte les lectures de boîte des cellules : chacune force une mise en page.
  await page.addInitScript(() => {
    const read = Element.prototype.getBoundingClientRect
    let cellReads = 0
    Element.prototype.getBoundingClientRect = function (this: Element) {
      if (this.matches('[data-table-cell]')) cellReads += 1
      return read.call(this)
    }
    Object.defineProperty(window, 'cellReads', { get: () => cellReads })
  })
  const cellReads = () => page.evaluate(() => (window as unknown as { cellReads: number }).cellReads)
  await page.setViewportSize({ width: 1100, height: 800 })
  await page.goto('/')
  await placeCells(page, [360])
  await page.locator('[data-table-cell]').evaluate(async (cell) => {
    cell.append(document.createElement('div'))
    await new Promise((resolve) => requestAnimationFrame(resolve))
  })
  await expectPlacement(page, 'column')
  const before = await cellReads()

  // Une inclinaison écrite à chaque image, comme un survol qui suit le pointeur (#20, #22).
  await page.locator('[data-table-cell] > div').evaluate(async (pose) => {
    for (const angle of [1, -1, 2]) {
      pose.style.rotate = `${angle}deg`
      pose.classList.toggle('lifted')
      await new Promise((resolve) => requestAnimationFrame(resolve))
    }
  })

  expect(await cellReads()).toBe(before)
})

test('la forme est posée avant la première peinture', async ({ page }) => {
  // Relevée dans la tâche même qui insère le `<footer>` : aucune peinture ne la précède.
  await page.addInitScript(() => {
    const inserted = new MutationObserver(() => {
      const footer = document.querySelector('footer')
      if (!footer) return
      inserted.disconnect()
      document.documentElement.dataset.firstPosition = getComputedStyle(footer).position
    })
    inserted.observe(document, { childList: true, subtree: true })
  })
  await page.setViewportSize(COLUMN_VIEWPORT)
  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('data-first-position', 'fixed')
})
