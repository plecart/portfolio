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

/** La couche noir et blanc de la fiche, tant qu'elle vole (`fadeGrey`). */
const GREY = '.project-gallery-track > .card-photo-grey'

/** Les distances de spec §4.6, sans jeton : le recul des autres cartes, la montée du contenu. */
const RECOIL = 48
const CONTENT_RISE = '0px 8px'

/** Visible, effacé : les deux bouts d'un fondu. */
const SHOWN: Frame = { opacity: 1 }
const HIDDEN: Frame = { opacity: 0 }

/** Ce que change un vol : la translation et l'échelle, et l'opacité d'un ruban (spec §4.6). */
const FLIGHT = ['translate', 'scale']
const DIMMED_FLIGHT = [...FLIGHT, 'opacity']

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

/** Un élément de la fiche qui vole : son homologue sur la carte, son retard, son creux d'opacité. */
type Leg = { element: HTMLElement; homologue: Element; delay: number; dimmed: boolean }

/** Une carte de la table : sa couche d'entrée, et son effacement, recul compris s'il y en a un. */
type Move = { entry: HTMLElement; keyframes: Keyframe[] }

/**
 * Les temps de la fiche, qu'elle vole ou qu'elle se fonde ; les cartes de la table à part. Le retour
 * part toujours de ce que montre chaque élément (`relay`) : au repos, ou en plein mouvement quand la
 * fermeture interrompt l'ouverture (décision de #22).
 */
type Steps = {
  /** L'ouverture, dont la première animation finit quand la fiche devient active. */
  out: () => Animation[]
  /** Le premier temps du retour : ce qui s'efface d'abord. Pas encore apparu, il reste caché. */
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
  const travelers = TRAVELERS.map(([fiche, origin]) => ({
    element: panel.querySelector<HTMLElement>(fiche)!,
    homologue: card.querySelector(origin)!,
    delay: 0,
    dimmed: false,
  }))
  const [fiche, origin] = RIBBONS
  const homologues = card.querySelectorAll(origin)
  const ribbons = [...panel.querySelectorAll<HTMLElement>(fiche)].map((element, index) => ({
    element,
    homologue: homologues[index],
    delay: index * ribbonDelay,
    dimmed: true,
  }))
  return [...travelers, ...ribbons]
}

/** Ce que montre `element` à l'instant dans ces propriétés, animations comprises. */
function shown(element: Element, properties: readonly string[]): Frame {
  const style = getComputedStyle(element)
  return Object.fromEntries(
    properties.map((property) => [property, style.getPropertyValue(property)]),
  )
}

/**
 * Relaie des animations sans saut (décision de #22) : les suivantes partent de ce que montraient les
 * éléments, relevé en argument, avant que les animations relayées ne soient retirées ; une mesure que
 * prend `next` ne voit plus que le repos.
 *
 * @param from Ce que montre chaque élément (`shown`), au repos ou en plein mouvement.
 * @param next Les animations suivantes, depuis ces relevés, dans leur ordre.
 */
function relay(relayed: Animation[], from: Frame[], next: (from: Frame[]) => Animation[]) {
  for (const animation of relayed) animation.cancel()
  return next(from)
}

/**
 * Le vol d'un élément de `start` à `end` en `--dur-open`, après son retard (spec §4.6) ; un ruban
 * passe par son creux d'opacité.
 */
function fly(
  { element, delay, dimmed }: Leg,
  start: Frame,
  end: Frame,
  { open, easing }: Motion,
  fill: FillMode,
) {
  return element.animate(dimmed ? dimmedKeyframes(start, end) : [start, end], {
    duration: open,
    easing,
    delay,
    fill,
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
          : [SHOWN, HIDDEN]
      return { entry: cell.querySelector<HTMLElement>('.card-entry')!, keyframes }
    })
}

/** Le temps d'un mouvement des cartes : `--dur-open`, ou `--dur-fast` en mouvement réduit (§6.3). */
const cardTiming = ({ reduced, open, fast, easing }: Motion) => ({
  duration: reduced ? fast : open,
  easing,
})

/** Les cartes s'effacent, et le restent tant que la fiche est ouverte (spec §4.6, §6.3). */
function recede(moves: Move[], motion: Motion) {
  return moves.map(({ entry, keyframes }) =>
    entry.animate(keyframes, { ...cardTiming(motion), fill: 'forwards' }),
  )
}

/**
 * Les cartes reviennent à leur place en réapparaissant (spec §4.6, §6.3), d'où elles sont : effacées,
 * ou en route quand la fermeture interrompt l'ouverture.
 */
function comeBack(moves: Move[], receding: Animation[], motion: Motion) {
  return relay(
    receding,
    moves.map(({ entry, keyframes: [rest] }) => shown(entry, Object.keys(rest))),
    (froms) =>
      moves.map(({ entry, keyframes: [rest] }, index) =>
        entry.animate([froms[index], rest], cardTiming(motion)),
      ),
  )
}

/**
 * La couche noir et blanc d'un projet en cours (spec §4.4, §4.6) : une copie grise de la première
 * image de la galerie, posée sur elle, qui s'efface pendant le vol puis disparaît ; au retour, elle
 * revient depuis `from`, et part avec le panneau. Annulée, elle disparaît.
 *
 * @returns Son fondu ; aucun sans projet en cours ou sans image.
 */
function fadeGrey(
  panel: HTMLElement,
  card: HTMLElement,
  { open, easing }: Motion,
  way: 'out' | 'back',
  from = HIDDEN,
) {
  const image = panel.querySelector('.project-gallery-image')
  if (!image || !card.querySelector('.card-photo-grey')) return []
  const grey = image.cloneNode() as HTMLImageElement
  grey.classList.add('card-photo-grey')
  grey.alt = ''
  grey.ariaHidden = 'true'
  image.after(grey)
  const out = way === 'out'
  const fade = grey.animate(out ? [SHOWN, HIDDEN] : [from, SHOWN], { duration: open, easing })
  const remove = () => grey.remove()
  if (out) fade.addEventListener('finish', remove)
  fade.addEventListener('cancel', remove)
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
 * Le reste de la fiche, qui s'efface le premier à la fermeture (spec §4.6), depuis ce qu'il montre,
 * jusqu'au retrait : pas encore apparu, il reste caché.
 */
function hideContent(panel: HTMLElement, reveals: Animation[], { fast, easing }: Motion) {
  const content = [...panel.querySelectorAll<HTMLElement>(CONTENT)]
  return relay(
    reveals,
    content.map((element) => shown(element, ['opacity', 'translate'])),
    (froms) =>
      content.map((element, index) =>
        element.animate([froms[index], HIDDEN], { duration: fast, easing, fill: 'forwards' }),
      ),
  )
}

/**
 * Le vol (spec §4.6) : à l'ouverture, le panneau, transparent, montre sa feuille posée sur la carte,
 * et la photo, le post-it et les rubans posés sur leurs homologues ; la carte se cache d'un coup, et
 * tout part ensemble, la feuille en tête. Au retour, le contenu s'efface ; puis le panneau redevient
 * transparent sur sa feuille, et tout repart vers la carte, mesurée de nouveau.
 */
function flying(panel: HTMLElement, card: HTMLElement, motion: Motion): Steps {
  const route = legs(panel, card, motion)
  let outbound: Animation[] = []
  let reveals: Animation[] = []
  return {
    out: () => {
      panel.setAttribute('data-flight', '')
      const starts = route.map(({ element, homologue }) => startOn(element, homologue))
      card.setAttribute('data-origin', '')
      outbound = [
        ...route.map((leg, index) => fly(leg, starts[index], AT_REST, motion, 'backwards')),
        ...fadeGrey(panel, card, motion, 'out'),
      ]
      reveals = revealContent(panel, motion)
      return [...outbound, ...reveals]
    },
    clear: () => hideContent(panel, reveals, motion),
    back: () => {
      panel.setAttribute('data-flight', '')
      // La couche qui s'efface encore, quand la fermeture interrompt l'ouverture.
      const fading = panel.querySelector(GREY)
      const grey = fading ? shown(fading, ['opacity']) : HIDDEN
      return [
        ...relay(
          outbound,
          route.map(({ element, dimmed }) => shown(element, dimmed ? DIMMED_FLIGHT : FLIGHT)),
          (froms) =>
            route.map((leg, index) =>
              fly(leg, froms[index], startOn(leg.element, leg.homologue), motion, 'both'),
            ),
        ),
        ...fadeGrey(panel, card, motion, 'back', grey),
      ]
    },
  }
}

/**
 * Le mouvement réduit (spec §6.3) : des fondus seuls, sans feuille ni vol. La fiche apparaît en
 * `--dur-fast` et devient active à `--dur-reduced`, la fin de son fondu, attente comprise ; au
 * retour, son contenu s'efface en `--dur-reduced`, puis elle-même.
 */
function fading(panel: HTMLElement, { fast, reducedFade, easing }: Motion): Steps {
  let appearing: Animation[] = []
  const fadeOut = (element: Element, from: Frame) =>
    element.animate([from, HIDDEN], { duration: reducedFade, easing, fill: 'forwards' })
  const fadeAllOut = (relayed: Animation[], elements: Element[]) =>
    relay(
      relayed,
      elements.map((element) => shown(element, ['opacity'])),
      (froms) => elements.map((element, index) => fadeOut(element, froms[index])),
    )
  return {
    out: () => {
      appearing = [
        panel.animate([HIDDEN, SHOWN], { duration: fast, endDelay: reducedFade - fast, easing }),
      ]
      return appearing
    },
    clear: () => fadeAllOut([], [...panel.children]),
    back: () => fadeAllOut(appearing, [panel]),
  }
}

/**
 * La fin de toutes ces animations, qu'elles aillent à leur terme ou qu'on les annule en route : une
 * annulation rejette `finished`, et ce qui attend la fin n'arriverait jamais.
 */
const allSettled = (animations: Animation[]) =>
  Promise.allSettled(animations.map(({ finished }) => finished))

/**
 * Fait décoller une fiche de sa carte (spec §4.6, §6.3) — un vol, ou des fondus en mouvement réduit
 * —, mesurée avant d'être peinte, pendant que les cartes de la table s'effacent. Quand elle devient
 * active, « Fermer la fiche » prend le focus, et le panneau en vol reprend son papier. Une animation
 * annulée en route ne retient ni la pose ni le retour : chacun attend la fin des siennes, quelle
 * qu'elle soit (`allSettled`). Le panneau et ses ancêtres ne se transforment jamais : sous 600 px,
 * le bouton Fermer y est fixe.
 *
 * @returns L'atterrissage, qui ramène la fiche à sa carte, et l'abandon, qui retire tout sans
 *   mouvement.
 */
function takeOff(panel: HTMLElement, card: HTMLElement) {
  const motion = readMotion()
  const steps = motion.reduced ? fading(panel, motion) : flying(panel, card, motion)
  panel.setAttribute('data-choreography', '')
  const moves = cardMoves(card, motion.reduced)
  const receding = recede(moves, motion)
  const flights = steps.out()
  // En vol, posée, sur le retour, ou partie : revenue à sa carte, ou abandonnée.
  let phase: 'flight' | 'posed' | 'return' | 'gone' = 'flight'

  // La pose, au bout du premier vol, même annulé en route par un tiers ; jamais une fois le retour
  // parti, qui l'annule.
  void allSettled([flights[0]]).then(() => {
    if (phase !== 'flight') return
    phase = 'posed'
    panel.removeAttribute('data-flight')
    panel.querySelector<HTMLElement>('.project-close')?.focus()
  })

  const abort = () => {
    if (phase === 'gone') return
    phase = 'gone'
    for (const animation of [...flights, ...receding]) animation.cancel()
    card.removeAttribute('data-origin')
    panel.removeAttribute('data-flight')
    panel.removeAttribute('data-choreography')
  }

  /**
   * Le retour à la carte (spec §4.6, §6.3) : ce qui s'efface d'abord, puis le reste, pendant que les
   * cartes de la table reviennent. Une fermeture en plein vol repart de là où est chaque élément, et
   * n'attend pas le contenu, qui n'est pas apparu (décision de #22). Au bout du dernier, la carte
   * réapparaît d'un coup sous la photo posée. Une carte sortie du document n'a plus de place où
   * revenir : la fiche se retire alors par le fondu de sortie.
   */
  const land = async () => {
    if (!card.isConnected) {
      abort()
      return
    }
    const posed = phase === 'posed'
    phase = 'return'
    const clearing = steps.clear()
    if (posed) await allSettled(clearing)
    await allSettled([...steps.back(), ...comeBack(moves, receding, motion)])
    card.removeAttribute('data-origin')
    phase = 'gone'
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
