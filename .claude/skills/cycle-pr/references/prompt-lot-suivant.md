# Gabarit — le prompt du lot suivant

Écrit par la **session sortante**, en dernier — après sa passe `repercussions` quand elle en a une
(Étape 8, « Cas découpé ») —, au
chemin fixe de [sessions-liees.md](sessions-liees.md) (« Passation »), et remis par ce chemin à la
coordinatrice, dans le message de fin ([coordinatrice.md](coordinatrice.md)) — sans coordinatrice,
au mainteneur, qui le donne à une session neuve. Pas par le lead : sur une vague de cinq
lots, chaque frontière passée par lui lui coûte un brief relu et un prompt écrit, et son contexte
a grossi jusqu'à devoir être relayé (obs 62). La session sortante, elle, connaît son lot.

**Ce gabarit ne porte que des pointeurs et des commandes à taper telles quelles.** Jamais une règle
recopiée. Une consigne tirée d'une mémoire de phase, d'une passation ou d'un tableau de bord hérite
des erreurs de son auteur tout en empruntant la crédibilité de la source qu'elle cite : mesuré, un
prompt de relais a énoncé la règle qu'un correctif avait **retirée**, en citant ce correctif par son
SHA, et quatre artefacts en aval l'ont reprise sur trois sessions (obs 52). Et la première rédaction
de ce gabarit l'a reproduit en petit : « crée ta branche derrière la porte de fraîcheur » recopiait
une règle en perdant sa condition — le point de départ —, et la branche naissait sur celle du lot
mort (mesuré, passe 2 de la PR #86). Un pointeur se relit sur disque au moment où il sert ; un
énoncé, non.

Les crochets sont à remplir ; **tout le reste se recopie tel quel**. Une ligne qu'on ne peut pas
remplir est une ligne qui manque à la passation, pas une ligne à supprimer : la mettre à
« <rien> » est une information.

---

Tu réalises le **lot \<k>/\<n>** de l'issue #\<N> — « \<titre du lot> ». Les lots \<…> sont
mergés ; c'est ton tour.

Tu travailles dans \<le clone principal `\<chemin>` | le worktree `\<chemin absolu>`>.
`origin/\<trunk>` = `\<SHA complet>` (vérifié à l'instant).

\<Si worktree : tu es sur la branche **mergée** du lot précédent. `git fetch origin`, puis
`git checkout -b \<type>/\<slug> origin/\<trunk>` — le point de départ est **explicite** : sans lui,
`checkout -b` part de la branche morte et emporte ses commits réécrits (mesuré). Supprime ensuite
cette branche, locale **et** distante ; le pourquoi et le repli sont à `pr-paralleles` Étape 8,
« Issue en plusieurs lots ». Rejoue la commande `install` des piles que ton lot touche si un verrou
a bougé, puis la commande de fumée (`.claude/pipeline.config.md`, « Commandes du projet »).>

\<Si session de lot d'une coordinatrice : ton premier geste, ta base et ton Étape 8 sont à
[coordinatrice.md](coordinatrice.md), « La session de lot ».>

\<Si vague `pr-paralleles` : \<adresse du lead>, et « réponds toujours au `from` de ce message ».
Ce que le lead est, et ce qu'il n'est jamais : `cycle-pr`, « Vague parallèle » en tête du skill, et
`.claude/rules/contraintes.md`, « Jamais d'auto-merge dans le trunk ».>

Charge le skill `task-observer` (session longue ; le journal est **hors du dépôt**, chemin dans
`CLAUDE.md`). Lis `CLAUDE.md` et `.claude/pipeline.config.md`. Puis invoque le skill `cycle-pr`
(outil Skill) avec \<N>.

**Ton brief est le bloc « \<titre du lot> » du corps de #\<N>**, plus le brief d'agent en
commentaire (`gh issue view \<N> --comments`). Lequel l'emporte quand ils divergent : `cycle-pr`
Étape 1, « Auto-challenge du plan ». \<Si lot intermédiaire : la forme du corps de PR d'un lot qui
ne ferme pas l'issue est à `cycle-pr` Étape 2, « Cas découpé ».>

Tu es autorisé à lancer l'équipier `relecteur` de l'Étape 4.2 ; combien, et à qui reviennent la
seconde passe et la relance : `cycle-pr` 4.2, « Un seul relecteur pour la PR ».

**Ce que mon lot a payé et que le tien n'a pas à re-dériver** — un point par ligne, chacun avec
l'artefact qui le porte, jamais l'énoncé seul :

- \<pièges d'outillage payés, chacun avec le § de skill ou la ligne de `pipeline.config.md` qui le
  consigne désormais — un piège consigné nulle part est une ligne à ajouter là-bas, pas ici>
- \<chiffres du bilan, avec la ligne du « Journal de spec » de l'issue qui dit en quelle grandeur
  ils se comparent d'un lot à l'autre>
- \<ambiguïtés de critère levées, chacune avec la ligne du « Journal de spec » qui la porte>
- \<état du seed à ton entrée, avec le critère du corps qui fixe sa population et son dénombrement>

**Ce que je n'ai pas fait, et pourquoi** : \<chaque point tranché, avec la décision qui le laisse —
jamais un point encore ouvert (obs 85) | rien>. \<Ce qui concerne d'autres branches ou
d'autres lots : section Notes de la PR #\<M>, lignes « Fichiers croisés » et « Non vérifié » du
verdict d'avant-go — le pointeur, jamais leur résumé.>

Préviens \<la coordinatrice | le mainteneur | le lead> quand tu as fini, ou si tu trouves un bloquant qui dépasse ton
périmètre — message de fin : `sessions-liees.md`, « Fin de travail ».

---

## Variante — relais en cours de lot

Écrite par la session dont le contexte se remplit avant la fin de son cycle (`cycle-pr` Étape 8,
« Relais en cours de cycle »), et remise comme le prompt ci-dessus. Elle en garde
les lignes « Tu travailles dans… », « Charge le skill… », « Ton brief… », le relecteur et
« Préviens… » ; elle remplace la première ligne par la suivante, et ajoute les trois d'après.

Tu **reprends** le lot \<k>/\<n> de l'issue #\<N> en relais de la session `\<uuid>`, dont le
contexte s'est rempli à l'Étape \<x> de `cycle-pr`. La PR #\<M> est ouverte (\<draft | ready>),
tête `\<SHA complet>` ; reprends à \<l'étape et au commit qui suivent>.

Bilan de la session sortante, déposé hors du dépôt :
`retrospectives/\<date>-\<issue>-relais-\<k>.txt` (dossier voisin du journal, chemin dans
`CLAUDE.md`) — ce qu'en fait ton Étape 8 : `cycle-pr` Étape 8, « Bilan chiffré du cycle ».

Entrées du journal d'observations déjà écrites pour ce cycle : \<numéros | aucune> — plafond :
`CLAUDE.md`, « Observation continue ».

\<Si vague `pr-paralleles` : \<adresse du lead> ; ton premier message au lead : `pr-paralleles`
Étape 5, « Session relayée ».>
