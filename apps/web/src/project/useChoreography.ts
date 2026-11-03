import { useEffectEvent, useLayoutEffect, useRef } from 'react'
import {
  AT_REST,
  dimmedKeyframes,
  flightStart,
  milliseconds,
  NO_SHIFT,
  pivotIn,
  recoil,
  type Frame,
} from './choreography.ts'

/**
 * Ce qui vole de la carte à la fiche (spec §4.6) : chaque élément de la fiche, puis son homologue
 * sur la carte. La feuille en tête : sa fin est la pose.
 */
const TRAVELERS = [
  ['.project-sheet', '.card-face'],
  ['.project-gallery-frame', '.card-photo'],
  ['.project-title', '.card-postit'],
] as const

/** Les rubans de l'en-tête de la fiche, puis ceux de la bande de la carte, dans le même ordre. */
const RIBBONS = ['.project-head .card-ribbon', '.card-band .card-ribbon'] as const

/** Le reste de la fiche, qui apparaît à la pose (spec §4.6). */
const CONTENT =
  '.project-close, .project-gallery-arrow, .project-gallery-bar, .project-link, .project-scroll'

/** Les distances de spec §4.6, sans jeton : le recul des autres cartes, la montée du contenu. */
const RECOIL = 48
const CONTENT_RISE = '0px 8px'

/** Les durées et la courbe de spec §2.7, lues dans les jetons au moment d'animer. */
function readMotion() {
  const tokens = getComputedStyle(document.documentElement)
  const time = (name: string) => milliseconds(tokens.getPropertyValue(name))
  return {
    open: time('--dur-open'),
    content: time('--dur-content'),
    ribbonDelay: time('--delay-ribbon'),
    easing: tokens.getPropertyValue('--ease-out').trim(),
  }
}

type Motion = ReturnType<typeof readMotion>

/** Un élément de la fiche en vol : l'image clé qui le pose sur son homologue, et son retard. */
type Leg = { element: HTMLElement; from: Frame; delay: number; dimmed: boolean }

/** L'image clé qui pose `element`, au repos, sur `homologue`, mesurés à l'instant. */
function startOn(element: HTMLElement, homologue: Element): Frame {
  const style = getComputedStyle(element)
  const [x, y] = style.transformOrigin.split(' ').map(parseFloat)
  const matrix = new DOMMatrix(style.transform)
  const pivot = pivotIn(matrix, element.offsetWidth, element.offsetHeight, { x, y })
  return flightStart(homologue.getBoundingClientRect(), element.getBoundingClientRect(), pivot)
}

/** Les trajets de la fiche (spec §4.6) : la feuille, la photo, le post-it, puis chaque ruban. */
function legs(panel: HTMLElement, card: HTMLElement, { ribbonDelay }: Motion): Leg[] {
  const travelers = TRAVELERS.map(([fiche, origin]) => {
    const element = panel.querySelector<HTMLElement>(fiche)!
    return { element, from: startOn(element, card.querySelector(origin)!), delay: 0, dimmed: false }
  })
  const [fiche, origin] = RIBBONS
  const homologues = card.querySelectorAll(origin)
  const ribbons = [...panel.querySelectorAll<HTMLElement>(fiche)].map((element, index) => ({
    element,
    from: startOn(element, homologues[index]),
    delay: index * ribbonDelay,
    dimmed: true,
  }))
  return [...travelers, ...ribbons]
}

/** Fait voler chaque élément de son homologue à sa place, en `--dur-open` (spec §4.6). */
function flyOut(route: Leg[], { open, easing }: Motion) {
  return route.map(({ element, from, delay, dimmed }) =>
    element.animate(dimmed ? dimmedKeyframes(from, AT_REST) : [from, AT_REST], {
      duration: open,
      easing,
      delay,
      fill: 'backwards',
    }),
  )
}

/**
 * Les autres cartes entrées (spec §4.6) : celles de l'écran reculent à l'opposé de la carte ouverte
 * en s'effaçant, celles hors de l'écran s'effacent sans bouger. Le recul se pose sur la couche
 * d'entrée, sous la cellule, que la mesure des liens de l'auteur suit (`TABLE_CELL_SELECTOR`).
 * Les cartes restent effacées jusqu'au retour.
 */
function recede(card: HTMLElement, { open, easing }: Motion) {
  const opened = card.getBoundingClientRect()
  return [...document.querySelectorAll<HTMLElement>('.card[data-entered]')]
    .filter((cell) => cell !== card)
    .map((cell) => {
      const box = cell.getBoundingClientRect()
      const onScreen = box.bottom > 0 && box.top < innerHeight
      const { x, y } = recoil(opened, box, RECOIL)
      const keyframes = onScreen
        ? [
            { opacity: 1, translate: NO_SHIFT },
            { opacity: 0, translate: `${x}px ${y}px` },
          ]
        : [{ opacity: 1 }, { opacity: 0 }]
      return cell.querySelector('.card-entry')!.animate(keyframes, {
        duration: open,
        easing,
        fill: 'forwards',
      })
    })
}

/**
 * La couche noir et blanc d'un projet en cours (spec §4.4, §4.6) : une copie grise de la première
 * image de la galerie, posée sur elle, qui s'efface pendant le vol puis disparaît.
 *
 * @returns Son fondu ; aucun sans projet en cours ou sans image.
 */
function fadeGrey(panel: HTMLElement, card: HTMLElement, { open, easing }: Motion) {
  const image = panel.querySelector('.project-gallery-image')
  if (!image || !card.querySelector('.card-photo-grey')) return []
  const grey = image.cloneNode() as HTMLImageElement
  grey.classList.add('card-photo-grey')
  grey.alt = ''
  grey.ariaHidden = 'true'
  image.after(grey)
  const fade = grey.animate([{ opacity: 1 }, { opacity: 0 }], { duration: open, easing })
  fade.addEventListener('finish', () => grey.remove())
  fade.addEventListener('cancel', () => grey.remove())
  return [fade]
}

/** Le reste de la fiche, invisible jusqu'à la pose, puis montant de 8 px (spec §4.6). */
function revealContent(panel: HTMLElement, { open, content, easing }: Motion) {
  return [...panel.querySelectorAll<HTMLElement>(CONTENT)].map((element) =>
    element.animate(
      [
        { opacity: 0, translate: CONTENT_RISE },
        { opacity: 1, translate: NO_SHIFT },
      ],
      { duration: content, delay: open, easing, fill: 'backwards' },
    ),
  )
}

/**
 * Fait décoller une fiche de sa carte (spec §4.6). La fiche, rendue, est mesurée avant d'être
 * peinte : le panneau, transparent, montre sa feuille posée sur la carte, et la photo, le post-it et
 * les rubans posés sur leurs homologues ; la carte se cache d'un coup, et tout part ensemble. À la
 * pose, au bout de la feuille, le panneau reprend son papier et « Fermer la fiche » le focus.
 *
 * Le panneau et ses ancêtres ne se transforment jamais : sous 600 px, le bouton Fermer y est fixe.
 *
 * @returns L'atterrissage, qui rend la carte, et l'abandon, qui retire tout sans mouvement.
 */
function takeOff(panel: HTMLElement, card: HTMLElement) {
  const motion = readMotion()
  panel.setAttribute('data-choreography', '')
  panel.setAttribute('data-flight', '')
  const route = legs(panel, card, motion)
  const receding = recede(card, motion)
  card.setAttribute('data-origin', '')
  const flights = [
    ...flyOut(route, motion),
    ...fadeGrey(panel, card, motion),
    ...revealContent(panel, motion),
  ]
  // La pose, au bout de la feuille, premier des trajets.
  const [sheet] = flights
  sheet.addEventListener('finish', () => {
    panel.removeAttribute('data-flight')
    panel.querySelector<HTMLElement>('.project-close')?.focus()
  })
  let landed = false

  const abort = () => {
    if (landed) return
    for (const animation of [...flights, ...receding]) animation.cancel()
    card.removeAttribute('data-origin')
    panel.removeAttribute('data-flight')
    panel.removeAttribute('data-choreography')
  }

  // ponytail: fermeture par le fondu de #170, le temps que le retour à la carte arrive.
  const land = () => {
    abort()
    landed = true
    return Promise.resolve()
  }

  return { land, abort }
}

/**
 * La chorégraphie d'une fiche ouverte depuis sa carte (spec §4.6) : le décollage dès que le panneau
 * est rendu, l'atterrissage quand la fiche quitte l'adresse. Une fiche sans carte d'origine —
 * arrivée directe, historique — garde ses fondus.
 *
 * @param panel Le panneau de la fiche, une fois rendu.
 * @param card La carte d'origine ; `null`, pas de chorégraphie.
 * @param open La fiche est à l'adresse.
 * @param onLanded La fiche est revenue à sa carte : elle peut quitter le document.
 */
export function useChoreography(
  panel: HTMLElement | null,
  card: HTMLElement | null,
  open: boolean,
  onLanded: () => void,
) {
  const trip = useRef<ReturnType<typeof takeOff>>(null)
  const landed = useEffectEvent(onLanded)

  useLayoutEffect(() => {
    if (!panel || !card) return
    const current = takeOff(panel, card)
    trip.current = current
    return () => {
      current.abort()
      trip.current = null
    }
  }, [panel, card])

  useLayoutEffect(() => {
    if (!open) trip.current?.land().then(landed)
  }, [open])
}
