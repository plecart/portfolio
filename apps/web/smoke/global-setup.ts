/**
 * Le démarrage global de la fumée (#26) : la pile démarrée par `make smoke`, semée, puis rendue
 * dans l'ordre que l'épreuve du cache exige (brief de #26, critère du cache de #11).
 *
 * Le `worker` est arrêté avant la semence, et relancé après un premier appel de la liste : cet
 * appel voit donc, à coup sûr, la couverture « en attente », et la range dans le cache de l'API.
 * Puis l'attente, bornée, de l'état « prêt » en base. Ce que les scénarios lisent passe par
 * l'environnement, que Playwright transmet à ses workers : les adresses locales de la pile, le
 * projet semé, et l'état vu au premier appel.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { setTimeout as sleep } from 'node:timers/promises'
import { request } from '@playwright/test'
import { compose, servedCoverState } from './stack.ts'

/**
 * Le démarrage global entier, `worker` relancé et couverture traitée compris, prend de l'ordre de
 * dix secondes sur le poste (2026-11-05) : la borne n'est qu'un plafond, passé lequel le `worker`
 * ne traite plus.
 */
const READY_TIMEOUT_MS = 120_000

/** L'adresse locale qu'un port d'un service publie sur `127.0.0.1` (`docker compose port`). */
const published = (service: string, port: number) =>
  `http://${compose(['port', service, String(port)]).trim()}`

/** L'état de la couverture semée, lu dans la base par le conteneur `api`. */
const storedCoverState = () =>
  compose([
    'exec',
    '-T',
    'api',
    'python',
    'manage.py',
    'shell',
    '--no-imports',
    '--command',
    'from content.models import GalleryImage; print(GalleryImage.objects.get().state)',
  ]).trim()

export default async function globalSetup() {
  compose(['stop', 'worker'])
  const seed = readFileSync(join(import.meta.dirname, 'seed.py'), 'utf8')
  process.env.SMOKE_SEED = compose(['exec', '-T', 'api', 'python', '-'], seed)
  const { bucket } = JSON.parse(process.env.SMOKE_SEED) as { bucket: string }
  process.env.SMOKE_CADDY = published('caddy', 80)
  process.env.SMOKE_MEDIA = `${published('s3', 8080)}/${bucket}`

  const api = await request.newContext()
  process.env.SMOKE_FIRST_STATE = await servedCoverState(api)
  await api.dispose()

  compose(['start', 'worker'])
  const deadline = Date.now() + READY_TIMEOUT_MS
  for (let state = storedCoverState(); state !== 'ready'; state = storedCoverState()) {
    if (state === 'failed' || Date.now() > deadline) {
      throw new Error(`la couverture semée reste « ${state} » : le worker ne l'a pas rendue prête`)
    }
    await sleep(1000)
  }
}
