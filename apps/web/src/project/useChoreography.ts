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
 * Ce qui vole entre la carte et la fiche (spec §4.6) : chaque élément de la fiche, puis son
 * homologue sur la carte. La feuille en tête : sa fin est la pose.
 */
const TRAVELERS = [
  ['.project-sheet', '.card-face'],
  ['.project-gallery-frame', '.card-photo'],
  ['.project-title', '.card-postit'],
] as const

/** Les rubans de l'en-tête de la fiche, puis ceux de la bande de la carte, dans le même ordre. */
const RIBBONS = ['.project-head .card-ribbon', '.card-band .card-ribbon'] as const

/** Le reste de la fiche, qui apparaît à la pose et s'efface le premier (spec §4.6). */
const CONTENT =
  '.project-close, .project-gallery-arrow, .project-gallery-bar, .project-link, .project-scroll'

/** Les distances de spec §4.6, sans jeton : le recul des autres cartes, la montée du contenu. */
const RECOIL = 48
const CONTENT_RISE = '0px 8px'

/**
 * Le mouvement réduit (spec §6.3), et les durées et la courbe de spec §2.7, lues dans les jetons au
 * moment d'animer.
 */
function readMotion() {
  const tokens = getComputedStyle(document.documentElement)
  const time = (name: string) => milliseconds(tokens.getPropertyValue(name))
  return {
    reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
    open: time('--dur-open'),
    content: time('--dur-content'),
    fast: time('--dur-fast'),
    reducedFade: time('--dur-reduced'),
    ribbonDelay: time('--delay-ribbon'),
    easing: tokens.getPropertyValue('--ease-out').trim(),
  }
}

type Motion = ReturnType<typeof readMotion>

/** Un élément de la fiche en vol : l'image clé qui le pose sur son homologue, et son retard. */
type Leg = { element: HTMLElement; from: Frame; delay: number; dimmed: boolean }

/** Une carte de la table : sa couche d'entrée, et son effacement, recul compris s'il y en a un. */
type Move = { entry: HTMLElement; keyframes: Keyframe[] }

/** Le sens d'un mouvement : de la carte à la fiche, ou le retour. */
type Way = 'out' | 'back'

/** Les temps de la fiche, qu'elle vole ou qu'elle se fonde ; les cartes de la table à part. */
type Steps = {
  /** L'ouverture, dont la première animation finit quand la fiche devient active. */
  out: () => Animation[]
  /** Le premier temps du retour : ce qui s'efface d'abord. */
  clear: () => Animation[]
  /** Le second : ce qui revient à la carte, ou s'efface. */
  back: () => Animation[]
}

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

/**
 * Fait voler chaque élément de son homologue à sa place en `--dur-open` (spec §4.6), ou de sa place
 * à son homologue au retour, où il reste jusqu'au retrait du panneau.
 */
function fly(route: Leg[], { open, easing }: Motion, way: Way) {
  const back = way === 'back'
  return route.map(({ element, from, delay, dimmed }) => {
    const [start, end] = back ? [AT_REST, from] : [from, AT_REST]
    return element.animate(dimmed ? dimmedKeyframes(start, end) : [start, end], {
      duration: open,
      easing,
      delay,
      fill: back ? 'forwards' : 'backwards',
    })
  })
}

/**
 * Les cartes entrées de la table. Hors mouvement réduit, les autres que la carte ouverte (spec
 * §4.6) : celles de l'écran reculent à l'opposé de la carte ouverte en s'effaçant, celles hors de
 * l'écran s'effacent sans bouger. Le recul se pose sur la couche d'entrée, sous la cellule, que la
 * mesure des liens de l'auteur suit (`TABLE_CELL_SELECTOR`). En mouvement réduit (§6.3), toutes
 * s'effacent sans bouger, la carte ouverte comprise.
 */
function cardMoves(card: HTMLElement, reduced: boolean): Move[] {
  const opened = card.getBoundingClientRect()
  return [...document.querySelectorAll<HTMLElement>('.card[data-entered]')]
    .filter((cell) => reduced || cell !== card)
    .map((cell) => {
      const box = cell.getBoundingClientRect()
      const { x, y } = recoil(opened, box, RECOIL)
      const keyframes =
        !reduced && box.bottom > 0 && box.top < innerHeight
          ? [
              { opacity: 1, translate: NO_SHIFT },
              { opacity: 0, translate: `${x}px ${y}px` },
            ]
          : [{ opacity: 1 }, { opacity: 0 }]
      return { entry: cell.querySelector<HTMLElement>('.card-entry')!, keyframes }
    })
}

/**
 * Les cartes s'effacent, en `--dur-open`, ou en `--dur-fast` en mouvement réduit, et le restent ;
 * au retour, elles reviennent (spec §4.6, §6.3).
 */
function moveCards(moves: Move[], { reduced, open, fast, easing }: Motion, way: Way) {
  const back = way === 'back'
  return moves.map(({ entry, keyframes }) =>
    entry.animate(back ? [...keyframes].reverse() : keyframes, {
      duration: reduced ? fast : open,
      easing,
      fill: back ? 'none' : 'forwards',
    }),
  )
}

/**
 * La couche noir et blanc d'un projet en cours (spec §4.4, §4.6) : une copie grise de la première
 * image de la galerie, posée sur elle, qui s'efface pendant le vol, puis disparaît ; au retour, elle
 * revient, et part avec le panneau.
 *
 * @returns Son fondu ; aucun sans projet en cours ou sans image.
 */
function fadeGrey(panel: HTMLElement, card: HTMLElement, { open, easing }: Motion, way: Way) {
  const back = way === 'back'
  const image = panel.querySelector('.project-gallery-image')
  if (!image || !card.querySelector('.card-photo-grey')) return []
  const grey = image.cloneNode() as HTMLImageElement
  grey.classList.add('card-photo-grey')
  grey.alt = ''
  grey.ariaHidden = 'true'
  image.after(grey)
  const keyframes = [{ opacity: 1 }, { opacity: 0 }]
  const fade = grey.animate(back ? keyframes.reverse() : keyframes, {
    duration: open,
    easing,
    fill: back ? 'forwards' : 'none',
  })
  if (!back) fade.addEventListener('finish', () => grey.remove())
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

/** Le reste de la fiche, qui s'efface le premier à la fermeture (spec §4.6), jusqu'au retrait. */
function hideContent(panel: HTMLElement, { fast, easing }: Motion) {
  return [...panel.querySelectorAll<HTMLElement>(CONTENT)].map((element) =>
    element.animate([{ opacity: 0 }], { duration: fast, easing, fill: 'forwards' }),
  )
}

/**
 * Le vol (spec §4.6) : à l'ouverture, le panneau, transparent, montre sa feuille posée sur la carte,
 * et la photo, le post-it et les rubans posés sur leurs homologues ; la carte se cache d'un coup, et
 * tout part ensemble, la feuille en tête. Au retour, le contenu s'efface ; puis le panneau redevient
 * transparent sur sa feuille, et tout repart vers la carte, mesuré de nouveau.
 */
function flying(panel: HTMLElement, card: HTMLElement, motion: Motion): Steps {
  return {
    out: () => {
      panel.setAttribute('data-flight', '')
      const route = legs(panel, card, motion)
      card.setAttribute('data-origin', '')
      return [
        ...fly(route, motion, 'out'),
        ...fadeGrey(panel, card, motion, 'out'),
        ...revealContent(panel, motion),
      ]
    },
    clear: () => hideContent(panel, motion),
    back: () => {
      panel.setAttribute('data-flight', '')
      const route = legs(panel, card, motion)
      return [...fly(route, motion, 'back'), ...fadeGrey(panel, card, motion, 'back')]
    },
  }
}

/**
 * Le mouvement réduit (spec §6.3) : des fondus seuls, sans feuille ni vol. La fiche apparaît en
 * `--dur-fast` et devient active à `--dur-reduced`, la fin de son fondu, attente comprise ; au
 * retour, son contenu s'efface en `--dur-reduced`, puis elle-même.
 */
function fading(panel: HTMLElement, { fast, reducedFade, easing }: Motion): Steps {
  const fadeOut = (element: Element) =>
    element.animate([{ opacity: 0 }], { duration: reducedFade, easing, fill: 'forwards' })
  return {
    out: () => [
      panel.animate([{ opacity: 0 }, { opacity: 1 }], {
        duration: fast,
        endDelay: reducedFade - fast,
        easing,
      }),
    ],
    clear: () => [...panel.children].map(fadeOut),
    back: () => [fadeOut(panel)],
  }
}

/** La fin de toutes ces animations. */
const allFinished = (animations: Animation[]) =>
  Promise.all(animations.map(({ finished }) => finished))

/**
 * Fait décoller une fiche de sa carte (spec §4.6, §6.3) — un vol, ou des fondus en mouvement réduit
 * —, mesurée avant d'être peinte, pendant que les cartes de la table s'effacent. Quand elle devient
 * active, « Fermer la fiche » prend le focus, et le panneau en vol reprend son papier. Le panneau et
 * ses ancêtres ne se transforment jamais : sous 600 px, le bouton Fermer y est fixe.
 *
 * @returns L'atterrissage, qui ramène la fiche à sa carte, et l'abandon, qui retire tout sans
 *   mouvement.
 */
function takeOff(panel: HTMLElement, card: HTMLElement) {
  const motion = readMotion()
  const steps = motion.reduced ? fading(panel, motion) : flying(panel, card, motion)
  panel.setAttribute('data-choreography', '')
  const moves = cardMoves(card, motion.reduced)
  const receding = moveCards(moves, motion, 'out')
  const flights = steps.out()
  flights[0].addEventListener('finish', () => {
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

  /**
   * Le retour à la carte (spec §4.6, §6.3) : ce qui s'efface d'abord, puis le reste, pendant que les
   * cartes de la table reviennent. Au bout du dernier, la carte réapparaît d'un coup sous la photo
   * posée. Une carte sortie du document n'a plus de place où revenir : la fiche se retire alors par
   * le fondu de sortie.
   */
  const land = async () => {
    if (!card.isConnected) {
      abort()
      return
    }
    // ponytail: fermée en vol, la fiche se pose d'abord d'un coup ; le retour depuis la position
    // courante de chaque élément (décision de #22) remplacera ce saut.
    for (const animation of flights) animation.finish()
    await allFinished(steps.clear())
    const back = steps.back()
    for (const animation of receding) animation.cancel()
    await allFinished([...back, ...moveCards(moves, motion, 'back')])
    card.removeAttribute('data-origin')
    landed = true
  }

  return { land, abort }
}

/**
 * La chorégraphie d'une fiche ouverte depuis sa carte (spec §4.6, §6.3) : le décollage dès que le
 * panneau est rendu, l'atterrissage quand la fiche quitte l'adresse. Une fiche sans carte d'origine
 * — arrivée directe, historique — garde ses fondus.
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
