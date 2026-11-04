# 0025 — Les tests de la pipeline vivent avec elle et tournent sur son delta

- **Statut** : accepté
- **Date** : 2026-11-04
- **Décisions du cadrage** : D69 (`docs/cadrage-technique.md` §7) ; remplace le point « la suite
  du back porte aussi les tests de la pipeline » de l'ADR 0017 (§ Décision), qui reste accepté pour
  tout le reste ; décisions de l'interrogatoire de #225 (2026-11-04)

## Contexte

Les tests de la pipeline — skills, règles, rôles et leurs scripts — vivaient dans la suite du back,
`apps/api/tests/`, et tournaient à chaque push du job `api` : « la suite du back porte aussi les
tests de la pipeline » (ADR 0017, § Décision). L'étude du 2026-11-04
(`docs/etudes/2026-11-04-etude-tests-de-la-pipeline.md`) en a fait l'inventaire : 15 fichiers,
2 870 cas, près de 80 s en local (§1.1), et un couplage au back réduit à une fixture et trois aides
(§3).

Le plus gros fichier, `test_agent_skills.py`, figeait la prose normative mot pour mot : 12 224 de ses
15 333 lignes, la catégorie (d) de l'étude (§1.2). Ces phrases figées n'ont attrapé aucune
régression, ont coûté un double entretien à 37 PR sur 149 (§2.3), et laissaient la suite verte
quand on retirait une restriction de `CLAUDE.md` (mutation M5, §2.4).

## Facteurs de décision

- Un test se paie à chaque PR qui touche ce qu'il fige : il garde ce qu'aucune autre porte ne voit.
- La pipeline est découplée du projet (étude §5.4) : ses tests ne dépendent ni de Django ni du
  `conftest.py` du back.
- Le quota d'Actions reste serré (ADR 0017) : une suite qui tourne pour rien coûte des minutes, un
  job de plus une minute facturée par run.
- Le rouge propre au runner Linux reste vu avant le merge.

## Options considérées

Où (étude §6.1) :

1. **Rester dans `apps/api/tests/`.**
2. **`.claude/tests/`**, avec son propre `conftest.py`.
3. **`.claude/skills/<skill>/tests/`**, un dossier par skill.

Quand (étude §6.2) :

1. **À chaque push du job `api`**, dans `make test`.
2. **Une étape du job `api`, sur le delta de la pipeline** ; toujours sur un push vers `main`.
3. **Un hook pre-commit**, ou une commande locale seule.

Ce qui remplace une phrase figée (étude §6.3) :

1. **Garder les phrases figées.**
2. **Les retirer** : la relecture et la passe « restrictions du delta » prennent le relais.

## Décision

**Option 2 pour chacune des trois questions.**

- **Les tests de la pipeline vivent dans `.claude/tests/`.** Son `conftest.py` ne porte que des
  aides que chaque test importe, aucune fixture : la suite tourne sous `--noconftest`, sans Django
  ni le `conftest.py` du back. Les aides que le back partage avec elle gardent leur seule définition
  dans des modules de `apps/api/tests/` sans Django, que ce `conftest.py` réexporte. `make test` ne
  lance plus que `apps` ; `make test-pipeline` lance `.claude/tests`. Le projet pyright
  `.claude/pyrightconfig.json`, en mode strict, couvre les scripts des skills et ces tests.
- **En CI, une étape « Tests pipeline » du job `api`** lance `make test-pipeline`, après la suite
  du back : sur une PR, quand la sortie `pipeline` d'`infra/ci/changed_jobs.py` vaut `true` ; sur
  un push vers `main`, toujours. Aucun job neuf. La règle vit dans le script : ce que la suite lit
  et ce qui la lance (`PIPELINE`), ce qui décide des jobs (`ALL`), un chemin que `git` met entre
  guillemets, et les modules du back que la suite importe (`PIPELINE_TESTS`).
- **Les phrases figées sont retirées, pas corrigées.** Une restriction retirée ou modifiée de la
  prose normative se lit sur le diff : le script `cycle-pr/scripts/restrictions-du-delta.py` rend
  chacune, et la session de relecture le joue à chaque passe.

**La barre : ce qu'un test de la pipeline peut être.** Il lit l'une de ces choses :

- un **format** qu'une machine lit — le frontmatter d'un skill ou d'un rôle, `settings.json` ;
- un **chemin ou un titre cité** par la prose, qui doit résoudre ;
- un **code de sortie d'un outil**, mesuré sur un dépôt témoin ;
- le **comportement d'un script** ;
- la **forme d'une commande** écrite dans la prose.

Jamais une phrase de comportement. Une classe de prose se relit par la passe « restrictions du
delta », elle ne s'épingle pas.

Le retrait s'est fait par la nature de ce que chaque test lit, cette barre à la main, et non par le
classement manuel de l'étude (§1.2 : 62 tests conservés, 35 retirés), qui ne se reproduit pas : de
`test_agent_skills.py`, 67 tests et 418 cas sont conservés, 30 tests et 1 381 cas retirés. Les 5 de
plus que l'étude sont des gardes de forme de commande ou de format (journal « Décisions » de
l'issue #225, 2026-11-04). Le point de l'ADR 0017 remplacé : le job `api` tourne sur chaque
push ; la suite de la pipeline, `.claude/tests/`, y tourne quand le delta la concerne, et sur
chaque push vers `main`.

## Conséquences

**Positives**

- Une PR d'application ne paie plus la suite de la pipeline, et l'étape qui la lance ne charge ni
  Django ni les fixtures du back.
- La suite ne dépend plus de Django : `pytest`, `pyyaml`, et deux modules d'appui du back qui n'en
  importent pas.
- Plus aucun double entretien : reformuler une règle ne demande plus de recopier sa phrase dans un
  test.

**Négatives, assumées**

- Une reformulation de prose ne produit plus de second diff : la passe « restrictions du delta »
  et la relecture le remplacent. Une restriction qui disparaît par réécriture d'un paragraphe
  entier n'est rendue que comme ligne modifiée ; sa lecture reste humaine.
- Un rouge de la suite du back saute l'étape « Tests pipeline » du même run : le rouge de la
  pipeline se voit au push suivant.
- Les deux suites ne se collectent pas dans une même session : les deux `conftest.py` portent le
  même nom de module.
- La suite ne voyage pas encore seule : `test_supply_chain.py` et `system_commands.py`, que le back
  emploie aussi, restent dans `apps/api/tests/`, et un changement de l'un d'eux fait tourner
  l'étape.

## Comparaison des options

| | Où | Quand | Phrases figées |
|---|---|---|---|
| Option 1 | les fixtures Django tournent pour rien ; ne voyage pas avec `.claude/` | ≈ 75 s par run du job `api`, PR d'application comprise | 12 224 lignes, 37 doubles entretiens, M5 verte |
| **Option 2** | **un dossier, un `conftest.py`** | **une étape, 0 minute facturée de plus** | **retirées ; la passe lit chaque ligne retirée du diff** |
| Option 3 | deux emplacements : 4 des 15 fichiers ne sont d'aucun skill | hook : contredit `CONTRIBUTING.md` ; commande locale : perd le rouge Linux | — |

## Conditions de réexamen

- Un défaut de prose passe que ni la passe « restrictions du delta » ni la relecture n'ont vu.
- Un skill est publié seul : l'option 3 du « Où » redevient la bonne.
