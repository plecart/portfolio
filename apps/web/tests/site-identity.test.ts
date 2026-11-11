/**
 * L'identité du site dans le gabarit `index.html` (#265) : le JSON-LD `Person` et `WebSite` qu'un
 * robot lit sur chaque page, et que Django relit comme seule source (`apps/api/content/site.py`).
 * Ses liens et son adresse sont des copies, chacune tenue égale à sa vérité.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from 'vitest'
import { APP_ROOT } from './app-files.ts'

const TEMPLATE = readFileSync(join(APP_ROOT, 'index.html'), 'utf8')

/** Les liens de l'auteur, que le site affiche (spec §1.13, §3.4). */
const AUTHOR_LINKS = readFileSync(join(APP_ROOT, 'src/chrome/AuthorLinks.tsx'), 'utf8')

/** Les nœuds du JSON-LD du gabarit, par type. */
function graph(): Record<string, Record<string, unknown>> {
  const [, json] = TEMPLATE.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/) ?? []
  const nodes = (JSON.parse(json) as { '@graph': Record<string, unknown>[] })['@graph']
  return Object.fromEntries(nodes.map((node) => [node['@type'], node]))
}

test('le JSON-LD du site lie les profils des liens de l’auteur, dans leur ordre', () => {
  const hrefs = [...AUTHOR_LINKS.matchAll(/href: '([^']+)'/g)].map(([, href]) => href)

  expect(graph().Person.sameAs).toEqual(hrefs)
})

test('l’adresse de l’accueil est la même dans le canonical et dans le JSON-LD', () => {
  const [, canonical] = TEMPLATE.match(/<link rel="canonical" href="([^"]+)"/) ?? []
  const { Person, WebSite } = graph()

  expect([Person.url, WebSite.url]).toEqual([canonical, canonical])
})
