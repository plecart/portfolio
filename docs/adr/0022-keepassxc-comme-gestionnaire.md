# 0022 — KeePassXC comme gestionnaire de mots de passe

- **Statut** : accepté
- **Date** : 2026-10-31
- **Décisions du cadrage** : D67 (`docs/cadrage-technique.md` §7) ; remplace la mention « Bitwarden
  ou 1Password » de l'ADR 0007 (§ Décision, point 2), qui reste accepté pour tout le reste

## Contexte

L'ADR 0007 gardait les secrets hors du serveur, dans un gestionnaire de mots de passe qu'il
nommait : Bitwarden ou 1Password. KeePassXC est celui que le mainteneur utilise déjà sur son poste,
et le premier déploiement (#25) y a rangé ses premiers secrets. Il ne garde qu'un fichier chiffré
local, sans copie en ligne : la clé privée `age`, qui seule ouvre les sauvegardes, n'existe ailleurs
que si ce fichier est copié.

## Facteurs de décision

- Le service rendu : des secrets hors du serveur, et la clé des sauvegardes jamais sur le seul VPS.
- Aucun compte ni abonnement de plus.
- La survie de la clé `age` à la perte du poste.

## Options considérées

1. **Bitwarden ou 1Password**, comme l'ADR 0007 le prévoyait : une copie en ligne, sans geste.
2. **KeePassXC**, avec une copie du fichier hors du poste.

## Décision

**Option 2.** La base KeePassXC est copiée hors du poste, sur un support distinct, dès sa création
et après chaque secret ajouté (`infra/RUNBOOK.md`, « Où vit chaque secret »).

## Conséquences

**Positives**

- Déjà installé, gratuit, aucun tiers ne détient la base.

**Négatives, assumées**

- La copie hors du poste est un geste à la main : oubliée, un poste perdu emporte les secrets ajoutés
  depuis, et la clé `age` si elle en fait partie — donc les sauvegardes.

## Comparaison des options

| | Bitwarden ou 1Password | KeePassXC |
|---|---|---|
| Copie hors du poste | automatique | à la main |
| Compte de plus | oui | non |
| Tiers détenant la base chiffrée | oui | non |
| Verdict | Écartée | **Retenue** |
