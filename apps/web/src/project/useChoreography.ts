import { useEffectEvent, useLayoutEffect, useRef } from 'react'
import {
  AT_REST,
  dimmedKeyframes,
  flightStart,
  milliseconds,
  NO_SHIFT,
  pivotIn,
  recoil,
  rolledStart,
  type Frame,
} from './choreography.ts'

/** Le cadre de la galerie, où vole la photo de la carte et se pose sa couverture (`coverTrip`). */
const FRAME = '.project-gallery-frame'

/**
 * Ce qui vole entre la carte et la fiche (spec §4.6) : chaque élément de la fiche, puis son
 * homologue sur la carte. La feuille en tête : sa fin est la pose. Les rubans à part (`RIBBON`).
 */
const TRAVELERS = [
  ['.project-sheet', '.card-face'],
  [FRAME, '.card-photo'],
  ['.project-title', '.card-postit'],
] as const

/**
 * Un ruban, sur la carte comme sur la fiche, par son identité : sa technologie, ou son état
 * (`TechnologyRibbon`, `StateRibbons`). Chaque ruban de la bande de la carte vole vers celui de la
 * fiche qui porte la même, dans la stack « Technologies » ou dans l'en-tête.
 */
const RIBBON = '[data-ribbon]'

/** La copie volante d'un ruban, par l'identité de son ruban (`flyerOf`). */
const FLYER = '[data-flyer]'

/** L'opacité du nom d'une technologie sur son ruban (`card.css`), qu'un ruban roulé efface. */
const RIBBON_NAME = '--card-ribbon-name'

/** La sangle d'un projet en cours (`Strap`), puis la boîte de ses rayures, qui y est. */
const STRAP = '.card-strap'
const STRIPES = '.card-strap-stripes'

/** La bande que porte chacune des deux boîtes de la sangle (`card.css`). */
const BAND = '::before'

/** La copie volante de la sangle (`strapFlyerOf`). */
const STRAP_FLYER = '[data-strap-flyer]'

/**
 * La photo de la carte, que copie la couverture volante (`coverTrip`), la piste de la galerie,
 * après laquelle elle se pose, et la classe de la copie.
 */
const PHOTO = '.card-photo img'
const TRACK = '.project-gallery-track'
const COVER = 'project-gallery-cover'

/**
 * Le reste de la fiche hors de la colonne défilante, qui apparaît à la pose et s'efface le premier
 * (spec §4.6) ; la colonne, `COLUMN`, en fait autant autour des rubans visés (`contentOf`).
 */
const CONTENT =
  '.project-close, .project-gallery-arrow, .project-gallery-expand, .project-gallery-bar, ' +
  '.project-link'
const COLUMN = '.project-scroll'

/** Les distances de spec §4.6, sans jeton : le recul des autres cartes, la montée du contenu. */
const RECOIL = 48
const CONTENT_RISE = '0px 8px'

/** Visible, effacé : les deux bouts d'un fondu. */
const SHOWN: Frame = { opacity: 1 }
const HIDDEN: Frame = { opacity: 0 }

/** Ce que montre le vol d'un ruban : sa copie (`flyerOf`), et non le ruban qu'elle remplace. */
const SEEN: Frame = { visibility: 'visible' }
const UNSEEN: Frame[] = [{ visibility: 'hidden' }, { visibility: 'hidden' }]

/**
 * Ce que change un vol : la translation et l'échelle ; d'un ruban, en plus, ce qu'il roule — sa
 * largeur, sa marge en ligne, son nom (`rollOf`) — et son opacité (spec §4.6).
 */
const FLIGHT = ['translate', 'scale']
const RIBBON_FLIGHT = [...FLIGHT, 'width', 'paddingInline', RIBBON_NAME, 'opacity']

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

/**
 * Un élément de la fiche qui vole : son homologue sur la carte et son retard. Un ruban vole par sa
 * copie (`flyerOf`), `element`, qui passe par le creux d'opacité, et reste caché tant qu'elle vole.
 */
type Leg = { element: HTMLElement; homologue: HTMLElement; delay: number; ribbon?: HTMLElement }

/** Une carte de la table : la couche qui s'efface, et son effacement, recul compris s'il y en a un. */
type Move = { layer: HTMLElement; keyframes: Keyframe[] }

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

/**
 * L'image clé qui pose `element`, au repos, sur `homologue`, mesurés à l'instant.
 *
 * @param start La pose, d'une boîte sur l'autre : `flightStart` par défaut.
 */
function startOn(element: HTMLElement, homologue: Element, start = flightStart): Frame {
  const style = getComputedStyle(element)
  const [x, y] = style.transformOrigin.split(' ').map(parseFloat)
  const matrix = new DOMMatrix(style.transform)
  const pivot = pivotIn(matrix, element.offsetWidth, element.offsetHeight, { x, y })
  return start(homologue.getBoundingClientRect(), element.getBoundingClientRect(), pivot)
}

/** La largeur d'un ruban et sa marge en ligne, mesurées : ce qu'un ruban roulé prend de l'autre. */
function rollOf(ribbon: HTMLElement) {
  return { width: `${ribbon.offsetWidth}px`, paddingInline: getComputedStyle(ribbon).paddingInline }
}

/**
 * L'image clé qui pose la copie d'un ruban, roulée, sur son homologue de la carte (spec §4.6) : à sa
 * largeur et à sa marge en ligne, son nom effacé, sous une échelle uniforme, le rapport de leurs
 * hauteurs (`rolledStart`). La translation se mesure sur la copie à cette largeur, que la mesure lui
 * rend aussitôt : le bout carte tombe sur le ruban de la carte, et ce qui dépasse de la copie est
 * coupé (`project.css`). Centrée sur le ruban tel qu'il est à l'écran, elle ne prend ni l'échelle de
 * la levée de la carte, ses mesures étant de mise en page, ni l'inclinaison de sa pose, gardant celle
 * de son ruban (`flyerOf`).
 */
function rolledOn(flyer: HTMLElement, homologue: HTMLElement): Frame {
  const roll = rollOf(homologue)
  const scale = homologue.offsetHeight / flyer.offsetHeight
  Object.assign(flyer.style, roll)
  const start = startOn(flyer, homologue, (from, to, pivot) => rolledStart(from, to, pivot, scale))
  Object.assign(flyer.style, { width: '', paddingInline: '' })
  return { ...start, ...roll, [RIBBON_NAME]: 0 }
}

/** Le bout carte d'un vol : l'élément posé sur son homologue ; la copie d'un ruban, roulée. */
const cardEnd = ({ element, homologue, ribbon }: Leg) =>
  ribbon ? rolledOn(element, homologue) : startOn(element, homologue)

/** Le bout fiche d'un vol : l'élément à sa place ; la copie d'un ruban, déroulée, son nom visible. */
const panelEnd = ({ element, ribbon }: Leg): Frame =>
  ribbon ? { ...AT_REST, ...rollOf(element), [RIBBON_NAME]: 1 } : AT_REST

/**
 * La copie volante d'un ruban de la fiche (spec §4.6) : fixe, elle vole hors de la colonne
 * défilante, qui couperait son vol, et ne la suit ni à son apparition ni à son effacement
 * (`contentOf`). Au bout de sa liste, elle ne déplace aucun ruban ; elle garde l'inclinaison du
 * sien, quel que soit son rang. Cachée hors de ses vols (`project.css`), qui la montrent (`fly`), et
 * des technologies d'assistance.
 */
function flyerOf(ribbon: HTMLElement): HTMLElement {
  const flyer = ribbon.cloneNode(true) as HTMLElement
  flyer.dataset.flyer = ribbon.dataset.ribbon
  delete flyer.dataset.ribbon
  flyer.ariaHidden = 'true'
  flyer.style.transform = getComputedStyle(ribbon).transform
  ribbon.parentElement!.append(flyer)
  return flyer
}

/**
 * Pose une copie volante sur son original, là où il est à l'instant, défilé hors de vue compris : sa
 * boîte, centrée sur celle qu'il occupe à l'écran, que son inclinaison fait tourner autour de son
 * centre, comme celle de la copie.
 */
function place(flyer: HTMLElement, original: HTMLElement) {
  const { left, top, width, height } = original.getBoundingClientRect()
  const layout = getComputedStyle(original)
  flyer.style.left = `${left + (width - parseFloat(layout.width)) / 2}px`
  flyer.style.top = `${top + (height - parseFloat(layout.height)) / 2}px`
}

/**
 * Ce que la copie de la sangle tient de sa carte, hors de laquelle elle vole : son cadre, d'où vient
 * son angle, et sa place au coin sur une intention (`card.css`).
 */
const STRAP_STATE = ['--card-frame', '--strap-cornered']

/**
 * La copie volante de la sangle d'une carte (spec §4.6), `aria-hidden` comme elle : fixe, dans le
 * panneau, au-dessus de la feuille et de la photo volante par sa place, la dernière du panneau, comme
 * par son `z-index` (`card.css`) — chacun y suffit. Posée sur la sangle telle qu'elle est à l'instant
 * — centrée sur sa boîte (`place`), à sa taille de mise en page, dans l'état qu'elle tient de sa
 * carte — avant d'entrer dans le document, elle y entre d'emblée dans cet état. Elle ne prend donc ni
 * l'inclinaison de la pose de la carte ni l'échelle de sa levée : plus petite de 2 % qu'une sangle
 * levée (`--card-lift-scale`), quand la photo part de sa boîte englobante, non tournée mais levée.
 * Hors de son vol, ôtée de sa boîte et cachée (`project.css`).
 */
function strapFlyerOf(strap: HTMLElement, panel: HTMLElement): HTMLElement {
  const flyer = strap.cloneNode(true) as HTMLElement
  flyer.dataset.strapFlyer = ''
  place(flyer, strap)
  const style = getComputedStyle(strap)
  Object.assign(flyer.style, { width: style.width, height: style.height })
  for (const name of STRAP_STATE) flyer.style.setProperty(name, style.getPropertyValue(name))
  panel.append(flyer)
  return flyer
}

/** La transformation que montre à l'instant la bande d'une boîte de la sangle, carte ou copie. */
const bandOf = (box: Element) => getComputedStyle(box, BAND).transform

/**
 * Les trajets de la fiche (spec §4.6) : la feuille, la photo, le post-it, puis chaque ruban de la
 * bande de la carte vers celui de la fiche de même identité (`RIBBON`), le i-ème de la bande avec
 * `i` retards. Un ruban dont la fiche ne rend pas l'homologue, replié, n'a pas de trajet.
 */
function legs(panel: HTMLElement, card: HTMLElement, { ribbonDelay }: Motion): Leg[] {
  const travelers = TRAVELERS.map(([inPanel, onCard]) => ({
    element: panel.querySelector<HTMLElement>(inPanel)!,
    homologue: card.querySelector<HTMLElement>(onCard)!,
    delay: 0,
  }))
  const panelRibbons = new Map(
    [...panel.querySelectorAll<HTMLElement>(RIBBON)].map((ribbon) => [ribbon.dataset.ribbon, ribbon]),
  )
  const ribbons = [...card.querySelectorAll<HTMLElement>(`.card-band ${RIBBON}`)].flatMap(
    (homologue, index) => {
      const ribbon = panelRibbons.get(homologue.dataset.ribbon)
      if (!ribbon) return []
      return [{ element: flyerOf(ribbon), homologue, delay: index * ribbonDelay, ribbon }]
    },
  )
  return [...travelers, ...ribbons]
}

/**
 * Ce que montre `element` à l'instant dans ces propriétés, animations comprises, chacune sous son nom
 * d'image clé : `paddingInline` se lit `padding-inline`.
 */
function shown(element: Element, properties: readonly string[]): Frame {
  const style = getComputedStyle(element)
  const cssName = (property: string) =>
    property.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)
  return Object.fromEntries(
    properties.map((property) => [property, style.getPropertyValue(cssName(property))]),
  )
}

/**
 * Relaie des animations sans saut (décision de #22) : les suivantes partent de ce que montraient les
 * éléments, relevé en argument, avant que les animations relayées ne soient retirées ; une mesure que
 * prend `next` ne voit plus que le repos.
 *
 * @param relayed Les animations en cours, annulées une fois `from` relevé.
 * @param from Ce que montre chaque élément (`shown`), au repos ou en plein mouvement.
 * @param next Les animations suivantes, depuis ces relevés, dans leur ordre.
 */
function relay(relayed: Animation[], from: Frame[], next: (from: Frame[]) => Animation[]) {
  for (const animation of relayed) animation.cancel()
  return next(from)
}

/**
 * Le vol d'un élément de `start` à `end` en `--dur-open`, après son retard (spec §4.6). Un ruban vole
 * par sa copie, montrée le temps du vol, retard compris, qui se roule et passe par son creux
 * d'opacité ; le ruban reste caché autant.
 */
function fly(
  { element, delay, ribbon }: Leg,
  start: Frame,
  end: Frame,
  { open, easing }: Motion,
  fill: FillMode,
) {
  const timing = { duration: open, easing, delay, fill }
  if (!ribbon) return [element.animate([start, end], timing)]
  return [
    element.animate(dimmedKeyframes({ ...start, ...SEEN }, { ...end, ...SEEN }), timing),
    ribbon.animate(UNSEEN, timing),
  ]
}

/**
 * Les cartes entrées de la table. Hors mouvement réduit, les autres que la carte ouverte (spec
 * §4.6) : celles de l'écran reculent à l'opposé de la carte ouverte en s'effaçant, celles hors de
 * l'écran s'effacent sans bouger. Le recul se pose sur la couche d'entrée, sous la cellule, que la
 * mesure des liens de l'auteur suit (`TABLE_CELL_SELECTOR`). En mouvement réduit (§6.3), toutes
 * s'effacent sans bouger, la carte ouverte comprise, par sa face.
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
      const layer = cell.querySelector<HTMLElement>(cell === card ? '.card-face' : '.card-entry')!
      return { layer, keyframes }
    })
}

/** Le temps d'un mouvement des cartes : `--dur-open`, ou `--dur-fast` en mouvement réduit (§6.3). */
const cardTiming = ({ reduced, open, fast, easing }: Motion) => ({
  duration: reduced ? fast : open,
  easing,
})

/** Les cartes s'effacent, et le restent tant que la fiche est ouverte (spec §4.6, §6.3). */
function recede(moves: Move[], motion: Motion) {
  return moves.map(({ layer, keyframes }) =>
    layer.animate(keyframes, { ...cardTiming(motion), fill: 'forwards' }),
  )
}

/**
 * Les cartes reviennent à leur place en réapparaissant (spec §4.6, §6.3), d'où elles sont : effacées,
 * ou en route quand la fermeture interrompt l'ouverture.
 */
function comeBack(moves: Move[], receding: Animation[], motion: Motion) {
  return relay(
    receding,
    moves.map(({ layer, keyframes: [rest] }) => shown(layer, Object.keys(rest))),
    (froms) =>
      moves.map(({ layer, keyframes: [rest] }, index) =>
        layer.animate([froms[index], rest], cardTiming(motion)),
      ),
  )
}

/** Les éléments de `root` qui ne contiennent rien de `kept`, chacun au plus haut. */
function around(root: Element, kept: readonly Element[]): Element[] {
  return [...root.children].flatMap((child) => {
    if (kept.includes(child)) return []
    return kept.some((element) => child.contains(element)) ? around(child, kept) : [child]
  })
}

/**
 * La couverture volante (spec §4.6) : une copie de la photo de la carte, déjà chargée — mêmes
 * sources, à la même taille : complète dès son insertion, sans requête, différée ou non (Chromium
 * 156, sonde du 2026-11-25) —, `aria-hidden`, posée dans le cadre de la galerie juste après sa
 * piste : au-dessus des images, sous les flèches et la loupe, sur tout le cadre, avec lequel elle
 * vole, et effacée au repos (`project.css`). À l'ouverture, elle s'efface en `--dur-open`, sans
 * retard : le cadre part avec la couverture et arrive avec la première image que montre la galerie.
 * Au retour, elle revient de ce qu'elle montre (`relay`) et reparaît en `--dur-open` sur l'image
 * montrée, quelle qu'elle soit, jusqu'au retrait du panneau.
 *
 * @returns Ses deux fondus ; `null` sans photo sur la carte, ou quand la galerie ne montre que la
 *   couverture (`data-cover`, `ProjectGallery`) : rien ne change alors dans le cadre.
 */
function coverTrip(panel: HTMLElement, card: HTMLElement, { open, easing }: Motion) {
  const photo = card.querySelector<HTMLImageElement>(PHOTO)
  const frame = panel.querySelector(FRAME)!
  if (!photo || frame.hasAttribute('data-cover')) return null
  const cover = photo.cloneNode() as HTMLImageElement
  cover.className = COVER
  cover.alt = ''
  cover.ariaHidden = 'true'
  frame.querySelector(TRACK)!.after(cover)
  const timing = { duration: open, easing }
  let fading: Animation[] = []
  return {
    out: () => (fading = [cover.animate([SHOWN, HIDDEN], timing)]),
    back: () =>
      relay(fading, [shown(cover, ['opacity'])], ([from]) => [
        cover.animate([from, SHOWN], { ...timing, fill: 'forwards' }),
      ]),
  }
}

/**
 * Le reste de la fiche (spec §4.6) : `CONTENT`, puis la colonne défilante, élément par élément autour
 * de ce que le vol y garde — les rubans visés et leurs copies volantes —, qui ne suit ni son
 * apparition ni son effacement. La colonne elle-même ne s'efface pas : elle les contient.
 */
function contentOf(panel: HTMLElement, kept: readonly Element[]): Element[] {
  return [...panel.querySelectorAll(CONTENT), ...around(panel.querySelector(COLUMN)!, kept)]
}

/** Le reste (`contentOf`), invisible jusqu'à la pose, puis montant de 8 px (spec §4.6). */
function revealContent(elements: Element[], { open, content, easing }: Motion) {
  return elements.map((element) =>
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
 * Le reste de la fiche (`contentOf`), qui s'efface le premier à la fermeture (spec §4.6), depuis ce
 * qu'il montre, jusqu'au retrait : pas encore apparu, il reste caché.
 */
function hideContent(elements: Element[], reveals: Animation[], { fast, easing }: Motion) {
  return relay(
    reveals,
    elements.map((element) => shown(element, ['opacity', 'translate'])),
    (froms) =>
      elements.map((element, index) =>
        element.animate([froms[index], HIDDEN], { duration: fast, easing, fill: 'forwards' }),
      ),
  )
}

/**
 * La sangle ôtée de sa carte (spec §4.6). Sa copie volante (`strapFlyerOf`) prend la bande que la
 * carte montre à l'instant, transition comprise, avant de l'ôter (`data-origin`, `card.css`) ; à
 * l'ouverture, ses deux bandes, la tranche et les rayures, glissent ensemble perpendiculairement à
 * leur axe, vers le coin haut-gauche, jusqu'à quitter leur boîte, où la copie se tient ôtée
 * (`project.css`), en `--dur-open`, sans retard ; la copie s'efface en `--dur-fast` pendant qu'elle
 * glisse, comme le trombone qui monte. Au retour, en plein vol comme posée, la copie est retirée : la
 * carte réapparue fait glisser sa propre sangle en place.
 */
function strapTrip(panel: HTMLElement, strap: HTMLElement, { open, fast, easing }: Motion) {
  const start = bandOf(strap)
  const flyer = strapFlyerOf(strap, panel)
  return {
    out: () => {
      const keyframes = [
        { ...SEEN, transform: start },
        { ...SEEN, transform: bandOf(flyer) },
      ]
      return [
        ...[flyer, flyer.querySelector(STRIPES)!].map((box) =>
          box.animate(keyframes, { duration: open, easing, pseudoElement: BAND }),
        ),
        flyer.animate([SHOWN, HIDDEN], { duration: fast, easing, fill: 'forwards' }),
      ]
    },
    back: () => flyer.remove(),
  }
}

/**
 * Le vol (spec §4.6) : à l'ouverture, le panneau, transparent, montre sa feuille posée sur la carte,
 * et la photo, le post-it et les rubans posés sur leurs homologues ; la carte se cache d'un coup, sa
 * sangle passant à sa copie (`strapTrip`), et tout part ensemble, la feuille en tête. Au retour, le
 * contenu s'efface ; puis le panneau redevient transparent sur sa feuille, et tout repart vers la
 * carte, mesurée de nouveau, sauf la sangle, que la carte remet elle-même. Chaque ruban part de sa
 * place à l'instant, défilée hors de vue ou non : aucun test de visibilité. La photo vole avec le
 * cadre de la galerie, sa couverture s'y effaçant à l'aller et y reparaissant au retour
 * (`coverTrip`).
 */
function flying(panel: HTMLElement, card: HTMLElement, motion: Motion): Steps {
  const route = legs(panel, card, motion)
  const strap = card.querySelector<HTMLElement>(STRAP)
  const strapFlight = strap && strapTrip(panel, strap, motion)
  const coverFlight = coverTrip(panel, card, motion)
  const kept = route.flatMap(({ element, ribbon }) => (ribbon ? [element, ribbon] : []))
  // Au départ d'un vol, chaque copie volante sur son ruban.
  const placeFlyers = () => {
    for (const { element, ribbon } of route) if (ribbon) place(element, ribbon)
  }
  let outbound: Animation[] = []
  let reveals: Animation[] = []
  return {
    out: () => {
      panel.setAttribute('data-flight', '')
      card.setAttribute('data-origin', '')
      placeFlyers()
      const [starts, rests] = [route.map(cardEnd), route.map(panelEnd)]
      outbound = route.flatMap((leg, index) =>
        fly(leg, starts[index], rests[index], motion, 'backwards'),
      )
      reveals = revealContent(contentOf(panel, kept), motion)
      return [
        ...outbound,
        ...(strapFlight?.out() ?? []),
        ...(coverFlight?.out() ?? []),
        ...reveals,
      ]
    },
    clear: () => hideContent(contentOf(panel, kept), reveals, motion),
    back: () => {
      panel.setAttribute('data-flight', '')
      strapFlight?.back()
      placeFlyers()
      return [
        ...relay(
          outbound,
          route.map(({ element, ribbon }) => shown(element, ribbon ? RIBBON_FLIGHT : FLIGHT)),
          (froms) =>
            route.flatMap((leg, index) => fly(leg, froms[index], cardEnd(leg), motion, 'both')),
        ),
        ...(coverFlight?.back() ?? []),
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
 * active, elle réagit au pointeur, « Fermer la fiche » prend le focus, et le panneau en vol reprend
 * son papier ; sa fermeture demandée, elle n'y réagit plus. Une animation annulée en route ne
 * retient ni la pose ni le retour : chacun attend la fin des siennes, quelle qu'elle soit
 * (`allSettled`). Le panneau et ses ancêtres ne se transforment jamais : sous 600 px, le bouton
 * Fermer y est fixe.
 *
 * @returns L'atterrissage, qui ramène la fiche à sa carte, et l'abandon, qui retire tout sans
 *   mouvement.
 */
function takeOff(panel: HTMLElement, card: HTMLElement) {
  const motion = readMotion()
  const steps = motion.reduced ? fading(panel, motion) : flying(panel, card, motion)
  panel.setAttribute('data-choreography', '')
  panel.setAttribute('data-inactive', '')
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
    panel.removeAttribute('data-inactive')
    panel.removeAttribute('data-flight')
    panel.querySelector<HTMLElement>('.project-close')?.focus()
  })

  const abort = () => {
    if (phase === 'gone') return
    phase = 'gone'
    for (const animation of [...flights, ...receding]) animation.cancel()
    // Les copies volantes des rubans, de la sangle et de la couverture, que la fiche abandonnée ne
    // fera plus voler.
    const flyers = panel.querySelectorAll(`${FLYER}, ${STRAP_FLYER}, .${COVER}`)
    for (const flyer of flyers) flyer.remove()
    card.removeAttribute('data-origin')
    for (const attribute of ['data-inactive', 'data-flight', 'data-choreography']) {
      panel.removeAttribute(attribute)
    }
  }

  /**
   * Le retour à la carte (spec §4.6, §6.3) : ce qui s'efface d'abord, puis le reste, pendant que les
   * cartes de la table reviennent. Une fermeture en plein vol repart de là où est chaque élément, et
   * n'attend pas le contenu, qui n'est pas apparu (décision de #22). Au bout du dernier, la carte
   * réapparaît d'un coup sous la photo posée, et sa sangle y glisse en place (`card.css`). Une carte
   * sortie du document n'a plus de place où revenir : la fiche se retire alors par le fondu de sortie.
   */
  const comeHome = async () => {
    if (!card.isConnected) {
      abort()
      return
    }
    const posed = phase === 'posed'
    phase = 'return'
    panel.setAttribute('data-inactive', '')
    const clearing = steps.clear()
    if (posed) await allSettled(clearing)
    await allSettled([...steps.back(), ...comeBack(moves, receding, motion)])
    card.removeAttribute('data-origin')
    phase = 'gone'
  }

  // Un seul retour, même demandé deux fois : l'adresse peut encore changer pendant qu'il vole.
  let landing: Promise<void> | undefined
  const land = () => (landing ??= comeHome())

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
