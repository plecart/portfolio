import { Dialog, DialogClose, DialogContent, DialogPortal } from '@radix-ui/react-dialog'
import { useState } from 'react'
import type { Project } from '../api/projects.ts'
import { CloseIcon } from '../chrome/icons.tsx'
import { strings } from '../strings.ts'
import { projectPath } from './project.ts'
import { ProjectContent } from './ProjectContent.tsx'

/**
 * Le bouton de fermeture (spec §3.2) : 36 px, rond, papier, à 8 px du coin du panneau. Sur téléphone
 * il reste visible pendant que le panneau défile ; au-dessus de ce qui défile sous lui, y compris
 * des post-its et des rubans, que leur rotation fait peindre après lui.
 */
const CLOSE_CLASSES =
  'fixed top-(--s-2) right-(--s-2) z-10 flex size-9 items-center justify-center rounded-full bg-(--paper) text-(--ink-2) transition-colors hover:text-(--ink) sm:absolute'

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
 * pas une. Le bouton, premier du panneau, reçoit le focus de Radix à l'ouverture. Pendant le fondu
 * de sortie, le projet a déjà quitté l'adresse : le dernier montré reste donc rendu.
 *
 * @param project Le projet à montrer ; `undefined`, fiche fermée.
 * @param onClose La demande de fermeture : le bouton ou Échap.
 */
export function ProjectDialog({
  project,
  onClose,
}: {
  project: Project | undefined
  onClose: () => void
}) {
  const [shown, setShown] = useState(project)
  if (project && project !== shown) setShown(project)
  if (!shown) return null

  return (
    <Dialog open={project !== undefined} onOpenChange={onClose}>
      <DialogPortal>
        <DialogContent
          aria-modal="true"
          className="project-panel"
          onInteractOutside={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            focusCard(shown.slug)
          }}
        >
          <DialogClose aria-label={strings.closeProject} className={CLOSE_CLASSES}>
            <CloseIcon />
          </DialogClose>
          <ProjectContent project={shown} />
        </DialogContent>
      </DialogPortal>
    </Dialog>
  )
}
