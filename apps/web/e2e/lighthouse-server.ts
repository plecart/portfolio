/**
 * Le serveur de la collecte Lighthouse (`lighthouserc.json`, docs/frontend-outillage.md §2.4) : la
 * version compilée, repli SPA compris, la liste des douze projets et leurs fichiers, tous sur son
 * origine. La donnée appartient au test : rien n'entre dans l'application pour cela.
 *
 * `dist` porte l'origine de l'API en dur : le JS servi la remplace par celle de ce serveur, sans
 * second build, pour que l'artefact mesuré reste celui de la production (spec §1.16 ; issue #168).
 * Le texte part compressé, comme le faisait `staticDistDir`.
 *
 * Lancé par Node, types effacés : `node e2e/lighthouse-server.ts`, depuis `apps/web`.
 */
import { readFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { extname, join } from 'node:path'
import { gzipSync } from 'node:zlib'
import lighthouse from '../lighthouserc.json' with { type: 'json' }
import { API_ORIGIN } from './api.ts'
import { FILES_ORIGIN, fixturePath, PROJECT_SETS } from './projects.ts'

const { origin: ORIGIN, port: PORT } = new URL(lighthouse.ci.collect.url[0])

const DIST = join(import.meta.dirname, '..', 'dist')

const CONTENT_TYPES: Record<string, string> = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.txt': 'text/plain',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
}

/** Les types déjà compressés, que `gzip` ne ferait qu'alourdir. */
const COMPRESSED = ['.webp', '.woff2']

/** Une réponse : l'extension qui en donne le type, et son corps. */
type Answer = { extension: string; body: Buffer }

/** Un fichier de `dist`, l'origine de l'API remplacée dans le JS ; l'index pour une autre adresse. */
async function distFile(pathname: string): Promise<Answer> {
  const path = join(DIST, pathname)
  const body = await readFile(path).catch(() => null)
  if (body === null) return { extension: '.html', body: await readFile(join(DIST, 'index.html')) }

  const extension = extname(path)
  if (extension !== '.js') return { extension, body }
  return { extension, body: Buffer.from(body.toString('utf8').replaceAll(API_ORIGIN, ORIGIN)) }
}

/** La réponse à une adresse : la liste, un fichier de `fixtures/`, ou un fichier de `dist`. */
async function answer(pathname: string): Promise<Answer> {
  if (pathname === '/api/projets') {
    const projects = JSON.stringify(PROJECT_SETS.twelveWithShowcase).replaceAll(FILES_ORIGIN, ORIGIN)
    return { extension: '.json', body: Buffer.from(projects) }
  }
  if (pathname.startsWith('/images/') || pathname.startsWith('/icones/')) {
    return { extension: extname(pathname), body: await readFile(fixturePath(pathname)) }
  }
  return distFile(pathname)
}

createServer(async (request, response) => {
  const { extension, body } = await answer(new URL(request.url!, ORIGIN).pathname)
  const compressed = !COMPRESSED.includes(extension)
  response.writeHead(200, {
    'content-type': CONTENT_TYPES[extension] ?? 'application/octet-stream',
    ...(compressed && { 'content-encoding': 'gzip' }),
  })
  response.end(compressed ? gzipSync(body) : body)
}).listen(PORT, () => console.log(`listening on ${ORIGIN}`))
