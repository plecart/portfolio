# Finalisation, review et CI — détail de `cycle-pr`

Passages déplacés mot pour mot de `cycle-pr/SKILL.md` (issue #177), chacun sous le titre que
cite son renvoi. Les liens `references/…` qu'ils portent se lisent depuis le dossier du skill,
et leurs renvois de position (« ci-dessous », « plus bas ») depuis l'emplacement du renvoi.

## Preuves visuelles exigées par un HITL

**Preuves visuelles exigées par un HITL** : ni l'API GitHub ni `gh` ne savent joindre une image à
un body ou un commentaire. Le canal est une **branche orpheline `captures/pr-<n>`** poussée par
plomberie git (zéro fichier dans la PR), référencée par liens `?raw=true` dans le body, supprimée
à l'Étape 8.

## Un jeu de captures est jugé par comparaison, pas capture par capture

**Un jeu de captures est jugé par comparaison, pas capture par capture.** Quand des captures
s'ajoutent à un jeu déjà partiellement validé (reprise, autre session), **ouvrir une capture
validée avant d'en produire une nouvelle** et aligner sur elle les paramètres de rendu : mode de
compilation (le bandeau DEBUG), appareil et densité, résolution, thème, barre d'état. La consigne
écrite n'énumère que ce que son auteur a pensé à fixer ; l'artefact validé est complet.

## Jamais une fin de tour nue

Jamais une fin de tour nue : le moniteur de PR de l'application ne réveille que sur un échec, un
conflit ou un commentaire (description de `set_monitor`, lue le 2026-10-20), jamais sur un succès
— mesuré le même jour, PR #141 : run vert à 19:21:01Z, aucun réveil en 14 min. C'est la seule
surveillance de la CI que la session lance elle-même, le moniteur ne couvrant pas le succès ;
jamais une sonde planifiée. Le script ne couvre ni les autres workflows et événements, ni ce que le
run a combiné (paragraphe suivant), ni la page d'état et la réouverture, qui restent à la session
et au mainteneur (« Si aucun run n'apparaît »).

Ce run a tourné sur la référence de fusion calculée à son push, que GitHub ne recalcule ni à chaque
merge sur le trunk ni au passage en ready : il peut combiner la tête à un trunk vieux de plusieurs
merges — mesuré, 8 des 30 commits de `main` (obs 51). Ce qu'il prouve de l'état combiné se lit
dans les parents de cette référence, à l'Étape 7.

## Commentaire de répercussion

> **Commentaire de répercussion.** Un merge survenu ailleurs pendant que cette PR était ouverte a
> pu rendre sa spec fausse ; `repercussions` le signale ici même, par un commentaire sur la PR (le
> corps de l'issue n'est volontairement pas modifié tant que la PR est ouverte). L'instrument qui
> publie un tel commentaire puis le relit en entier est
> `python <répertoire de ce skill>/scripts/ecriture-relue.py comment <n> --body-file <fichier>`
> (Étape 8) ; `repercussions` le prescrit à son étape 5, « Issues en vol ». Un signalement
> **bloquant** se traite comme tel : intégrer la correction dans cette PR, ou remonter au
> mainteneur si cela déplace le périmètre — ne jamais merger par-dessus.
