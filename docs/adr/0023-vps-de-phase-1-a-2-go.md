# 0023 — VPS de phase 1 : 1 vCPU et 2 Go au minimum

- **Statut** : accepté
- **Date** : 2026-10-31
- **Décisions du cadrage** : D68 (`docs/cadrage-technique.md` §7) ; remplace le point « Machine » de
  l'ADR 0002 pour la phase 1 (§ Décision) et son estimation de 4 à 8 € par mois (§ Conséquences),
  ainsi que le contexte « VPS de 4 Go » de l'ADR 0015 ; ces ADR restent acceptés pour tout le reste

## Contexte

L'ADR 0002 dimensionnait la phase 1 à 2 vCPU et 4 Go, sans mesure : la pile n'existait pas. Le
2026-10-31, au premier déploiement (#25), aucun VPS de cette taille n'était commandable en UE au
prix prévu : Hetzner CX23 en disponibilité limitée, OVH VPS-1 épuisé dans tous les centres
européens, Hetzner CPX22 à 23,99 € TTC par mois, Scaleway à partir de 24,53 € TTC hors disque.

La pile de production, sans `cloudflared`, mesurée le même jour (`docker stats` sous Docker Desktop,
base vide) : 262 Mio au repos — `api` 105, `worker` 101, `postgres` 33, `caddy` 12, `backup` 7,
`redis` 4 —, et 154 Mio de plus au pic pour une image de 24 Mpx passée par Pillow. `api` tourne sur
un worker `gunicorn` par défaut, `worker` sur une concurrence de 1.

## Facteurs de décision

- Le coût mensuel, cible de l'ADR 0002.
- Une marge de mémoire mesurée, `cloudflared`, le système et Docker en plus.
- Un changement de taille ou de fournisseur sans réécriture : le VPS se reconstruit depuis le dépôt
  et la dernière sauvegarde (ADR 0007).

## Options considérées

1. **Hetzner CPX22** : 2 vCPU, 4 Go, conforme à l'ADR 0002, 23,99 € TTC par mois.
2. **Hetzner CPX12** : 1 vCPU, 2 Go, x86, 14,39 € TTC par mois, IPv4 comprise.
3. **Attendre OVH VPS-1** : environ 5,39 € TTC par mois, retour en stock inconnu.

## Décision

**Option 2.** La phase 1 demande un VPS x86 — la CI ne construit que des images x86 — d'au moins
1 vCPU et 2 Go, en UE. La phase 2 reste à 8 Go.

## Conséquences

**Positives**

- 9,60 € par mois de moins que le CPX22. Marge mesurée sur le CPX12 le 2026-11-02, à vide, 19 h après
  le démarrage : 1 068 Mo disponibles, conteneurs à 679 Mio, dont `worker` 338 et `api` 207, plus
  que sur le poste. Le pic d'une image reste à mesurer sur cette machine.
- Facturation horaire avec plafond mensuel : un passage au VPS-1 d'OVH, revenu en stock, suit
  « Le VPS a disparu » (`infra/RUNBOOK.md`).

**Négatives, assumées**

- Au-dessus de l'estimation de l'ADR 0002 et de la cible de dix euros de #25.
- Un seul vCPU partagé entre sept services : démarrages et déploiements plus lents, non mesurés.
- Une base vide à la mesure : le cache de Postgres grandira avec le contenu.
- Sans `swap`, une saturation de la mémoire tue un processus plutôt que de ralentir la pile.

## Comparaison des options

| | CPX22 | CPX12 | OVH VPS-1 |
|---|---|---|---|
| Commandable le 2026-10-31 en UE | oui | oui | non |
| Prix TTC par mois | 23,99 € | 14,39 € | ~5,39 € |
| vCPU et mémoire | 2 vCPU, 4 Go | 1 vCPU, 2 Go | 2 vCores, 4 Go |
| Verdict | Écartée | **Retenue** | À reprendre au retour du stock |

## Conditions de réexamen

- Une mémoire proche de la saturation, ou une sonde qui tombe pendant un déploiement.
- Le VPS-1 d'OVH de nouveau commandable en UE.
- La phase 2, à 8 Go.
