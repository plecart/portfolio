/**
 * La pile de la fumée vue de Playwright (#26) : les commandes Compose de `make smoke`, et le relais
 * qui sert les trois origines de production depuis la pile.
 *
 * Le front publié est compilé avec l'API de production : le navigateur voit les vrais noms d'hôte,
 * et chaque requête vers l'un d'eux part en HTTP vers la pile — à `caddy` sous son en-tête `Host`,
 * comme `cloudflared` la lui transmet en production, ou au témoin S3 pour les médias ; rien ne sort
 * vers la production (brief de #26, décision 5). Le relais passe par le client HTTP de Playwright,
 * qui envoie l'en-tête `Host` qu'on lui donne ; celui de Node (`fetch`) le remplace par l'adresse
 * jointe (mesuré le 2026-11-05, Playwright 1.64.1, Node 24). `route.fetch` n'en tient pas lieu : il
 * refuse de changer le schéma d'une adresse (doc Playwright, `Route.fetch`, option `url`).
 */
import { execFileSync } from 'node:child_process'
import { join } from 'node:path'
import type { APIRequestContext, APIResponse } from '@playwright/test'

/** La racine du dépôt, d'où `make smoke` mène Compose : les chemins de sa commande en partent. */
const REPOSITORY_ROOT = join(import.meta.dirname, '..', '..', '..')

/** La borne d'une commande Compose : au-delà, la fumée échoue au lieu d'attendre. */
const COMPOSE_TIMEOUT_MS = 120_000

/**
 * Une variable que `make smoke` exporte, ou que le démarrage global pose pour les scénarios.
 *
 * @throws Si elle manque : la fumée se lance par `make smoke`, jamais par Playwright seul.
 */
export function env(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`${name} manque : la fumée se lance par « make smoke »`)
  return value
}

/** L'origine de production d'un des trois noms d'hôte que `make smoke` exporte. */
export const origin = (host: 'SITE_HOST' | 'API_HOST' | 'MEDIA_HOST') => `https://${env(host)}`

/**
 * Lance une commande Compose sur la pile de la fumée, celle que `make smoke` a démarrée.
 *
 * @param args La sous-commande et ses arguments, par exemple `['stop', 'worker']`.
 * @param input Ce que la commande lit sur son entrée standard.
 * @returns Sa sortie standard ; sa sortie d'erreur passe à celle du lanceur.
 * @throws Si elle sort en erreur ou dépasse `COMPOSE_TIMEOUT_MS`.
 */
export function compose(args: string[], input?: string): string {
  const [command, ...options] = env('SMOKE_COMPOSE').split(' ')
  return execFileSync(command, [...options, ...args], {
    cwd: REPOSITORY_ROOT,
    encoding: 'utf8',
    input,
    timeout: COMPOSE_TIMEOUT_MS,
  })
}

/**
 * L'adresse dans la pile d'une adresse des trois origines, et l'hôte sous lequel la demander : à
 * `caddy`, qui route par nom d'hôte, le site et l'API ; au témoin S3, la base des médias dans son
 * bucket. Les deux adresses locales viennent du démarrage global.
 *
 * @returns `undefined` hors des trois origines.
 */
export function inStack(url: string): { url: string; host?: string } | undefined {
  const { origin: requested, host, pathname, search } = new URL(url)
  const path = `${pathname}${search}`
  if (requested === origin('MEDIA_HOST')) return { url: `${env('SMOKE_MEDIA')}${path}` }
  if ([origin('SITE_HOST'), origin('API_HOST')].includes(requested)) {
    return { url: `${env('SMOKE_CADDY')}${path}`, host }
  }
}

/** Les options d'une requête relayée : celles du client HTTP de Playwright. */
type RelayOptions = NonNullable<Parameters<APIRequestContext['fetch']>[1]>

/**
 * Relaie une requête vers l'une des trois origines à la pile. Une redirection est rendue telle
 * quelle, jamais suivie : l'appelant voit la réponse même de la pile.
 *
 * @param api Le client HTTP de Playwright.
 * @param url L'adresse de production demandée.
 * @param options Méthode, en-têtes et corps de la requête.
 * @throws Si `url` est hors des trois origines.
 */
export async function relay(
  api: APIRequestContext,
  url: string,
  options: RelayOptions = {},
): Promise<APIResponse> {
  const target = inStack(url)
  if (!target) throw new Error(`hors des trois origines relayées : ${url}`)
  const headers = target.host ? { ...options.headers, host: target.host } : options.headers
  return api.fetch(target.url, { ...options, headers, maxRedirects: 0 })
}

/** L'adresse de la liste des projets, celle que le front compilé appelle. */
export const projectsUrl = () => `${origin('API_HOST')}/api/projets`

/** L'état de la couverture du projet semé, tel que la liste de l'API le sert. */
export async function servedCoverState(api: APIRequestContext): Promise<string> {
  const projects = (await (await relay(api, projectsUrl())).json()) as {
    gallery: { state: string }[]
  }[]
  return projects[0].gallery[0].state
}
