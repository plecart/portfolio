# 0021 — Noms des buckets R2 préfixés par le projet

- **Statut** : accepté
- **Date** : 2026-10-30
- **Décisions du cadrage** : D66 (`docs/cadrage-technique.md` §7) ; remplace le nom `backups` de
  l'ADR 0004 (§ Décision) et de l'ADR 0007 (§ Décision, point 3), qui restent acceptés pour tout le
  reste

## Contexte

Les ADR 0004 et 0007 nommaient `backups` le bucket privé des sauvegardes ; le modèle
`infra/prod.env.example` portait `medias` et `backups`. R2 range tous les buckets d'un compte dans
une seule liste : un nom générique ne dit pas à quel projet un bucket appartient, dès que le compte
Cloudflare en porte un autre (premier déploiement, #25). Les deux buckets venaient d'être créés,
vides et sans jeton : le changement ne coûtait rien en console.

## Facteurs de décision

- Le repérage d'un bucket dans le tableau de bord, geste de `infra/RUNBOOK.md` (« Vérifier qu'une
  sauvegarde est arrivée »).
- Une erreur de bucket sur des sauvegardes se paie cher : le jeton de `backup` peut y supprimer.
- Aucun code ne porte le nom : il vient de `MEDIA_R2_BUCKET` et `BACKUP_R2_BUCKET`.

## Options considérées

1. **Garder `medias` et `backups`.**
2. **Préfixer par le projet** : `portfolio-<usage>`.
3. **Un compte Cloudflare par projet.**

## Décision

**Option 2.** Les buckets se nomment `portfolio-medias` et `portfolio-backups`. Tout bucket à venir
suit la même forme `portfolio-<usage>`.

## Conséquences

**Positives**

- Le projet d'un bucket se lit dans la liste, sans ouvrir ses jetons.

**Négatives, assumées**

- Les pages de la doc R2 lues le 2026-10-30 ne proposent aucun renommage de bucket : un changement
  ultérieur suppose de vider, recréer et reconfigurer.

## Comparaison des options

| | `medias`, `backups` | `portfolio-<usage>` | Un compte par projet |
|---|---|---|---|
| Projet lisible dans la liste | non | oui | oui |
| Geste à faire | aucun | recréer deux buckets vides | un compte de plus à tenir |
| Verdict | Écartée | **Retenue** | Écartée, disproportionnée |
