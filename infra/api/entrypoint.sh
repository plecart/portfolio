#!/bin/sh
# Point d'entrée unique de l'image `api` : les étapes de démarrage, puis la commande reçue.
#
# Le même fichier sert en développement et en production (brief de #4). Les étapes sont une
# liste ordonnée de sous-commandes `manage.py`, lue dans `STARTUP_STEPS` : #6 y ajoutera la
# création du superutilisateur en allongeant la variable, sans toucher à ce fichier.
#
# `set -eu` : une étape qui échoue arrête le conteneur. Démarrer sur une base non migrée
# produirait des erreurs à la première requête, loin de la cause.
set -eu

# Absente, `migrate` ; **vide, aucune étape** — c'est ainsi que le `worker`, qui partage l'image,
# démarre sans migrer (brief de #12, décision 11). D'où `=` sans deux-points : `${VAR:=défaut}`
# traite une valeur vide comme une absence, et migrerait (mesuré à la clôture de #4) ; `${VAR-…}`,
# lui, substitue sans assigner, et la boucle ne verrait jamais `migrate`.
#
# ponytail: étapes sans argument — la boucle découpe sur les espaces. Le jour où une étape en
# réclame un, passer à un découpage sur les lignes (`IFS`) plutôt qu'à un format de configuration.
: "${STARTUP_STEPS=migrate}"

for step in $STARTUP_STEPS; do
    echo "démarrage : manage.py $step"
    python manage.py "$step"
done

# `exec` et non un appel simple : sans lui, le shell reste PID 1 et `docker stop` n'atteint
# jamais le serveur, qui est alors tué au bout du délai de grâce au lieu de s'arrêter proprement.
exec "$@"
