/** Les barres de la colonne de lecture (spec §5.1) : 100 %, 85 % et 60 % de sa largeur. */
const BAR_WIDTHS = ['w-full', 'w-[85%]', 'w-3/5']

/** La pulsation des cadres de la table (§5.1), jamais en mouvement réduit (§6.3). */
const PULSE = 'animate-frame-pulse motion-reduce:animate-none'

/**
 * Le cadre de fiche (spec §5.1, « À l'adresse d'une fiche ») : la boîte du panneau (§3.2), là où la
 * fiche va paraître, droite et sans contenu — le carré de la photo en `--line`, puis, dans la
 * colonne de lecture, le bloc du post-it du titre et trois barres de 10 px. Caché des technologies
 * d'assistance, inerte, sans bouton ; son contenu pulse comme les cadres de la table, son papier et
 * son ombre restant opaques. Rendu hors du portail de la fiche, dans la même couche qu'elle et
 * avant elle : la fiche le recouvre.
 */
export function ProjectFrame() {
  return (
    <div data-project-frame aria-hidden inert className="project-frame">
      <div className={`aspect-square bg-(--line) ${PULSE}`} />
      <div className={`project-frame-reading ${PULSE}`}>
        <div className="postit project-frame-title" />
        <div className="flex flex-col gap-(--s-3)">
          {BAR_WIDTHS.map((width) => (
            <div key={width} className={`h-[10px] rounded-full bg-(--line) ${width}`} />
          ))}
        </div>
      </div>
    </div>
  )
}
