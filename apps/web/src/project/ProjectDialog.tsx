import { Dialog, DialogClose, DialogContent, DialogPortal } from '@radix-ui/react-dialog'
import { useState } from 'react'
import type { Project } from '../api/projects.ts'
import { CloseIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { projectPath } from './project.ts'
import { ProjectContent } from './ProjectContent.tsx'
import { ProjectGallery } from './ProjectGallery.tsx'
import { useChoreography } from './useChoreography.ts'

/**
 * Le bouton de fermeture (spec §3.2) : 36 px, rond, papier, à 8 px du coin du panneau. Sur téléphone
 * il reste visible pendant que le panneau défile ; au-dessus de ce qui défile sous lui, y compris
 * des post-its et des rubans, que leur rotation fait peindre après lui.
 */
const CLOSE_CLASSES =
  'project-close fixed top-(--s-2) right-(--s-2) z-10 flex size-9 items-center justify-center rounded-full bg-(--paper) text-(--ink-2) transition-colors hover:text-(--ink) sm:absolute'

/**
 * Rend le focus à la carte d'un projet, que son `href` désigne (spec §3.2). Une carte encore dans la
 * fenêtre, même en partie, laisse la page où elle était ; seule une carte hors de la fenêtre, après
 * une arrivée directe, y vient.
 */
function focusCard(slug: string) {
  const card = document.querySelector<HTMLElement>(`.card[href="${projectPath(slug)}"]`)
  if (!card) return
  const { top, bottom } = card.getBoundingClientRect()
  card.focus({ preventScroll: bottom > 0 && top < innerHeight })
}

/**
 * La fiche d'un projet (spec §1.10, §3.2) : le dialogue modal de Radix, sans `DialogOverlay`, dont
 * le `RemoveScroll` poserait un `<style>` que la CSP de production bloque.
 *
 * Trois fermetures : le bouton, Échap et le retour du navigateur ; un clic hors du panneau n'en est
 * pas une. Ouverte depuis sa carte, elle en part et y revient (`useChoreography`, spec §4.6) : le
 * focus attend la pose sur le panneau, et la fiche reste ouverte pour Radix jusqu'à son retour,
 * quand le projet a déjà quitté l'adresse ; s'il y est revenu entre-temps, elle se rouvre alors par
 * son fondu. Sinon, deux fondus, et le bouton, premier du panneau, reçoit le focus de Radix à
 * l'ouverture. Le dernier projet montré reste rendu jusqu'au retrait du panneau ; une autre fiche
 * ouverte pendant le fondu de sortie trouve le panneau encore monté : sa galerie repart de la
 * première image.
 *
 * @param project Le projet à montrer ; `undefined`, fiche fermée.
 * @param origin La carte d'où la fiche s'ouvre, jusqu'à son retour ; `null` sans carte d'origine.
 * @param onClose La demande de fermeture : le bouton ou Échap.
 * @param onLanded La fiche est revenue à sa carte d'origine.
 */
export function ProjectDialog({
  project,
  origin,
  onClose,
  onLanded,
}: {
  project: Project | undefined
  origin: HTMLElement | null
  onClose: () => void
  onLanded: () => void
}) {
  const [shown, setShown] = useState(project)
  if (project && project !== shown) setShown(project)
  const [panel, setPanel] = useState<HTMLDivElement | null>(null)
  // Rouverte par l'adresse (« suivant ») pendant son retour, la fiche, revenue à sa carte, reprend un
  // panneau neuf, qui entre par son fondu : celui du vol ne sert qu'à lui.
  const [reopenings, setReopenings] = useState(0)
  const open = project !== undefined
  // Sur le retour à sa carte : le projet a déjà quitté l'adresse.
  const returning = !open && origin !== null
  useChoreography(panel, origin, open, () => {
    if (open) setReopenings((count) => count + 1)
    onLanded()
  })
  if (!shown) return null

  return (
    // Pendant le retour à la carte, le projet a quitté l'adresse : une seconde demande de fermeture
    // n'a plus rien à fermer.
    <Dialog open={open || returning} onOpenChange={() => open && onClose()}>
      <DialogPortal>
        <DialogContent
          key={reopenings}
          ref={setPanel}
          aria-modal="true"
          className="project-panel"
          // En vol, le panneau garde le focus jusqu'à la pose : laissé sur la carte cachée, Entrée
          // la rouvrirait.
          onOpenAutoFocus={(event) => {
            if (!origin) return
            event.preventDefault()
            panel?.focus()
          }}
          onInteractOutside={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            focusCard(shown.slug)
          }}
        >
          <div className="project-sheet" aria-hidden />
          <DialogClose aria-label={strings.closeProject} className={CLOSE_CLASSES}>
            <CloseIcon />
          </DialogClose>
          <ProjectGallery
            key={shown.slug}
            gallery={shown.gallery}
            rewound={returning}
          />
          <ProjectContent project={shown} />
        </DialogContent>
      </DialogPortal>
    </Dialog>
  )
}
