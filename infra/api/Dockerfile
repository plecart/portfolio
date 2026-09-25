# Image de l'application `api` — la seule image Python du projet. #15 la publie sur GHCR sans
# en écrire une seconde, #12 la démarre avec une autre commande pour le worker (brief de #4).
#
# Contexte de build : la **racine du dépôt**, pas `infra/api`. L'espace de travail `uv` vit à la
# racine et `uv.lock` ne vaut que pour lui — un contexte réduit à `apps/api` ne pourrait pas
# être installé depuis le verrou.
#
# La version de Python apparaît ici, contrairement au `Makefile` et à la CI, parce qu'une image
# de base la porte dans son nom. Elle est tenue égale à `.python-version` de deux façons : par
# un test qui lit ce fichier (`apps/api/tests/test_infra.py`), et par `uv` lui-même, qui refuse
# de s'installer sur un interpréteur qui ne correspond pas à l'épingle (voir plus bas). C'est le
# traitement déjà retenu côté front pour `.nvmrc` et `engines`.

# Chaque image de base est épinglée par **empreinte**, derrière son étiquette la plus précise : une
# étiquette peut changer de contenu, une empreinte non (guide « Building best practices » de
# Docker). L'étiquette porte la version de correctif (`3.12.14`, pas `3.12`) parce que c'est elle
# qui fait avancer l'épingle : Dependabot (`.github/dependabot.yml`) propose chaque nouvelle
# version, étiquette et empreinte ensemble. La reconstruction d'une même étiquette — correctifs
# Debian seuls — peut ne pas être proposée ; le scan de l'image (#15) couvre ce cas. Les lignes
# `FROM` dépassent donc 100 colonnes : image et empreinte doivent tenir sur la première ligne de
# l'instruction, la seule que lise Dependabot.

# Nommée une fois et réutilisée par les deux étages : deux `FROM` littéraux finiraient par
# diverger, et l'étage d'exécution est justement celui qu'on relit le moins.
FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS base

# `uv` dans un étage à lui plutôt que dans un `COPY --from=<image>` : Dependabot ne lit que les
# lignes `FROM`, et une image citée seulement par `COPY --from` ne serait jamais mise à jour.
# Version figée, comme toutes les épingles du dépôt : `latest` ferait dépendre la
# reproductibilité de l'image de la date du build.
FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv


FROM base AS build

COPY --from=uv /uv /bin/uv

# UV_PYTHON_DOWNLOADS=0 : l'interpréteur de l'image de base suffit. Conséquence utile — combiné
#   au `.python-version` copié ci-dessous, `uv` échoue si l'image de base dérive de l'épingle,
#   au lieu de télécharger silencieusement la bonne version et de masquer l'écart.
# UV_COMPILE_BYTECODE=1 : les `.pyc` sont produits au build, pas au démarrage du conteneur.
#
# Pas de `UV_LINK_MODE` ici : ce réglage sert quand le cache `uv` est monté depuis un autre
# système de fichiers (`--mount=type=cache`), ce que cet étage ne fait pas — le cache vit dans
# la même couche que sa cible, et les liens physiques y fonctionnent.
ENV UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Les dépendances dans leur propre couche : elles changent rarement, le code à chaque commit.
# Seul un manifeste modifié invalide cette couche — c'est ce qui rend le cache de la CI utile.
#
# `--no-install-workspace` et non `--no-install-project` : c'est un espace de travail. `--frozen`
# ici et `--locked` à l'étape suivante, comme la documentation de `uv` le prescrit pour ce cas —
# le verrou ne peut être vérifié qu'une fois tous les manifestes des membres présents.
COPY .python-version pyproject.toml uv.lock ./
COPY apps/api/pyproject.toml apps/api/pyproject.toml
RUN uv sync --frozen --no-dev --no-install-workspace

COPY apps/api apps/api
RUN uv sync --locked --no-dev


FROM base AS runtime

# Rien de l'étage de build ne traverse, sinon l'environnement et le code : ni `uv`, ni son cache,
# ni les outils de développement, écartés par `--no-dev`.
#
# `apps/api` est copié parce que le membre est installé en mode éditable : l'environnement y
# renvoie au lieu d'en garder une copie. C'est aussi ce qui permet au Compose de développement de
# monter le code de l'hôte par-dessus et d'obtenir un rechargement à chaud.
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/apps/api /app/apps/api
COPY infra/api/entrypoint.sh /usr/local/bin/entrypoint.sh

# PYTHONUNBUFFERED : sans lui, les journaux de démarrage restent dans le tampon et n'apparaissent
# dans `docker logs` qu'après coup — donc jamais quand on en a besoin (cadrage §6.7).
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

# Utilisateur non root, sans shell de connexion. `media` est créé ici, et non par le volume :
# un volume nommé hérite du propriétaire du dossier qu'il recouvre dans l'image — créé par Docker
# à la volée, il appartiendrait à `root` et l'application ne pourrait pas y écrire.
RUN useradd --system --create-home --shell /usr/sbin/nologin api \
    && mkdir -p /app/media \
    && chown -R api:api /app \
    && chmod +x /usr/local/bin/entrypoint.sh

WORKDIR /app/apps/api
USER api

EXPOSE 8000

# `gunicorn` par défaut : l'image est déjà celle de la production (ADR 0001, « Serveur WSGI »).
# Le Compose de développement remplace cette commande par `runserver`, il ne change pas d'image.
ENTRYPOINT ["entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
