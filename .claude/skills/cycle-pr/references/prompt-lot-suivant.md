# Gabarit — le prompt du lot suivant

Écrit par la **session sortante**, après sa passe `repercussions` (Étape 8, « Cas découpé »), et
remis au mainteneur — qui le colle dans une session neuve. Pas par le lead : sur une vague de cinq
lots, chaque frontière passée par lui lui coûte un brief relu et un prompt écrit, et son contexte
a grossi jusqu'à devoir être relayé (obs 62). La session sortante, elle, connaît son lot.

**Ce gabarit ne porte que des pointeurs.** Jamais une règle recopiée. Une consigne tirée d'une
mémoire de phase, d'une passation ou d'un tableau de bord hérite des erreurs de son auteur tout en
empruntant la crédibilité de la source qu'elle cite : mesuré, un prompt de relais a énoncé la règle
qu'un correctif avait **retirée**, en citant ce correctif par son SHA, et quatre artefacts en aval
l'ont reprise sur trois sessions (obs 52). Un pointeur se relit sur disque au moment où il sert ;
un énoncé, non.

Les crochets sont à remplir ; **tout le reste se recopie tel quel**. Une ligne qu'on ne peut pas
remplir est une ligne qui manque à la passation, pas une ligne à supprimer : la mettre à
« <rien> » est une information.

---

Tu réalises le **lot \<k>/\<n>** de l'issue #\<N> — « \<titre du lot> ». Les lots \<…> sont
mergés ; c'est ton tour.

Tu travailles dans \<le clone principal `\<chemin>` | le worktree `\<chemin absolu>`>. Branche
neuve depuis `origin/\<trunk>` = `\<SHA complet>` (vérifié à l'instant).

\<Si worktree : crée ta branche toi-même — `git checkout -b \<type>/\<slug>`, derrière la porte de
fraîcheur de `cycle-pr` Étape 1 —, puis supprime la branche du lot précédent, locale **et**
distante : sous un trunk fusionné par rebase ou squash, la branche mergée ne continue jamais, ses
commits réécrits doubleraient dans ta PR. Rejoue la commande `install` des piles que ton lot touche
si un verrou a bougé, puis la commande de fumée.>

\<Si vague `pr-paralleles` : \<adresse du lead>, et « réponds toujours au `from` de ce message ».
Le lead n'est pas le mainteneur : c'est ton interlocuteur pour la vérification d'avant-go, et lui
seul ne donne **jamais** de « go ».>

Charge le skill `task-observer` (session longue ; le journal est **hors du dépôt**, chemin dans
`CLAUDE.md`). Lis `CLAUDE.md` et `.claude/pipeline.config.md`. Puis invoque le skill `cycle-pr`
(outil Skill) avec \<N>.

**Ton brief est le bloc « \<titre du lot> » du corps de #\<N>**, plus le brief d'agent en
commentaire (`gh issue view \<N> --comments`). En cas d'écart entre le brief d'agent et le
« Journal de spec » du corps, **le journal l'emporte** : il porte sa date et il est adossé aux
sources de vérité. \<Si lot intermédiaire : ta PR ne porte **pas** `Closes` ; son corps ouvre par
« En vol pour #\<N> (lot \<k>/\<n>) ».>

Tu es autorisé à lancer l'équipier `relecteur` de l'Étape 4.2 — **un seul pour toute la PR**, à qui
reviennent la seconde passe et la relance par `SendMessage`. Cette invocation de `cycle-pr` vaut
demande de l'utilisateur.

**Ce que mon lot a payé et que le tien n'a pas à re-dériver** — un point par ligne, chacun avec
l'artefact qui le porte, jamais l'énoncé seul :

- \<pièges d'outillage payés : une forme refusée par le garde de permissions, un argument réécrit
  par le shell, un résumeur qui a masqué un rouge, une ancre de mutation sans effet…>
- \<chiffres du bilan, en **coût par contact** — jamais un total : un total suit la taille du delta
  relu et ne se compare pas d'un lot à l'autre>
- \<ambiguïtés de critère levées, chacune avec la ligne du « Journal de spec » qui la porte>
- \<état du seed à ton entrée : population nommée et dénombrement>

**Ce que je n'ai pas fait, et pourquoi** : \<… | rien>.

Préviens \<le mainteneur | le lead> quand tu as fini, ou si tu trouves un bloquant qui dépasse ton
périmètre.
