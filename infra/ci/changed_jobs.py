"""Ce que concerne un delta — les jobs `web`, `infra`, `avis`, et les tests de la pipeline —, en
`$GITHUB_OUTPUT`.

Lancé par le job `changes` de `.github/workflows/ci.yml`, sur le delta d'une PR, d'un push vers
`main` ou d'une release :

    git diff --name-only --no-renames "$BASE" HEAD | python3 infra/ci/changed_jobs.py >> "$GITHUB_OUTPUT"

`BASE` : sur une PR, `HEAD^1`, le trunk que le pas de fusion a combiné ; sur un push,
`github.event.before`, un push pouvant porter plusieurs commits ; sur une release, l'arbre vide —
le delta est l'arbre entier, et chaque réponse vaut `true` (ADR 0033). `--no-renames` : un
renommage y figure sous ses deux chemins, l'ancien et le nouveau — un fichier déplacé du front
vers `docs/` fait donc tourner `web`.

Lit sur l'entrée standard les chemins du delta, un par ligne, lignes vides ignorées, et écrit
`web=true|false`, `infra=true|false`, `avis=true|false`, puis `pipeline=true|false`. Les jobs
`web` et `mobile` — sur la réponse `web` —, `infra` et `avis`, et l'étape « Tests pipeline » du
job `api`, ne tournent que si leur réponse vaut `true` (ADR 0017, ADR 0019, ADR 0025,
ADR 0032) ; `api` tourne toujours. `avis` ne tourne ni sur un push ni sur une release, quelle
que soit sa réponse : la condition est dans `ci.yml`.

Règles, par motif `fnmatch` — où `*` traverse `/` :

- `web` : un chemin du front, ou le schéma de l'API, dont `make web-test` vérifie que les types
  générés du front sont à jour (`WEB`) ;
- `infra` : ce que les images définissent ou exécutent (`INFRA`, ADR 0031, décision 2), ou un
  module d'appui que `make image-test` charge (`IMAGE_TESTS`). Liste d'inclusion : le code du back
  et celui du front, que les images copient aussi, ont leurs jobs, `api` et `web` ;
- `avis` : une entrée des portes d'avis — ce que lisent `make audit`, `make web-audit` et
  `make scan`, et ce qui les définit (`AVIS`, ADR 0019, décision 2) ;
- `pipeline` : ce que la suite de la pipeline (`make test-pipeline`) lit, et ce qui la lance
  (`PIPELINE`) ; ou un module d'appui du back qu'elle importe (`PIPELINE_TESTS`) ;
- tous : un chemin de `ALL`, qui décide des jobs eux-mêmes, ou un chemin que `git` a mis
  entre guillemets (`QUOTED`) — il le fait pour tout chemin non ASCII, que plus aucun motif
  n'apparie ; un job sauté à tort cacherait un rouge, un job lancé pour rien ne coûte que des
  minutes. Les quatre les ajoutent à leurs motifs (`JOB_PATTERNS`).

Liste vide : aucun des quatre. Code de sortie 0 ; l'étape qui le lance tourne sous `pipefail`, et
un `git diff` en échec y fait rougir le job `changes` au lieu de rendre `false` en silence.
"""

import sys
from collections.abc import Iterable
from fnmatch import fnmatchcase

WEB = ("apps/web/*", "apps/api/openapi.json")
# Ce que les images définissent ou exécutent : `infra/` — Dockerfiles, fichiers Compose, ce que les
# images copient, leurs tests ; ce que l'image `api` copie avant son code — manifestes, verrou,
# `.python-version` — et les manifestes du front, dont `make build` compile `dist` ; les migrations
# du back, que l'image `api` joue à son démarrage, et la chaîne de sauvegarde des tests des images
# avec elle.
INFRA = (
    "infra/*",
    "pyproject.toml",
    "apps/api/pyproject.toml",
    "uv.lock",
    ".python-version",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "apps/api/*/migrations/*",
    ".dockerignore",  # ce que porte le contexte de build, dont les images copient des dossiers
    ".env.example",  # copié en `.env` par le job `infra` : `compose.dev.yml` le cite
)
# Les modules de `apps/api/tests/` que `make image-test` (job `infra`) charge : son greffon
# `process_environment` et ce que `infra/tests/` importe, directement ou non. Recalculés par
# `test_ci_declencheurs.py`, qui rougit sur un import ajouté sans eux.
IMAGE_TESTS = (
    "apps/api/tests/call_witness.py",
    "apps/api/tests/process_environment.py",
    "apps/api/tests/system_commands.py",
    "apps/api/tests/test_env.py",
    "apps/api/tests/test_infra.py",
    "apps/api/tests/test_supply_chain.py",
)
# Les entrées des portes d'avis : manifestes et verrous, Dockerfiles, exceptions datées, la porte
# de `pip-audit` et le workflow qui les joue. Le `Makefile`, qui définit leurs cibles, en est une
# aussi : `ALL` le porte déjà.
AVIS = (
    "pyproject.toml",
    "apps/api/pyproject.toml",
    "uv.lock",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "infra/*/Dockerfile",
    ".trivyignore.yaml",
    "infra/ci/pip-audit-exceptions.toml",
    "infra/ci/pip_audit_gate.py",
    ".github/workflows/avis.yml",
)
# Ce que lit la suite de la pipeline, `.claude/tests` (ADR 0025) : la prose, les réglages et les
# scripts du harnais, `.github/`, dont elle relit les renvois et les commandes, et la description
# du schéma d'architecture, que le skill `schema-architecture` valide et dessine ; puis ce qui la
# lance, le manifeste racine — son `pytest` et son `addopts` —, le verrou, et `.python-version`,
# l'interpréteur que `uv` lui donne (doc uv, « Project structure »). `ALL` et `QUOTED` s'y
# ajoutent, comme pour `web` et `avis`.
PIPELINE = (
    ".claude/*",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    ".github/*",
    "docs/schema/*",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
)
# Les modules de `apps/api/tests/` que `make test-pipeline` charge : ce que `.claude/tests/`
# importe, directement ou non. Recalculés par `test_ci_declencheurs.py`, comme `IMAGE_TESTS`.
PIPELINE_TESTS = ("apps/api/tests/system_commands.py", "apps/api/tests/test_supply_chain.py")
# Ce qui décide des jobs eux-mêmes.
ALL = ("Makefile", ".github/workflows/ci.yml", "infra/ci/changed_jobs.py")
# Un chemin que `git` a mis entre guillemets : non ASCII, aucun autre motif ne l'apparie plus.
QUOTED = '"*'
# Les motifs propres à chaque job, dans l'ordre de la réponse ; `ALL` et `QUOTED` s'ajoutent à
# chacun. Un module d'appui est un chemin sans joker, que `fnmatchcase` n'apparie qu'à lui-même.
JOB_PATTERNS = {
    "web": WEB,
    "infra": (*INFRA, *IMAGE_TESTS),
    "avis": AVIS,
    "pipeline": (*PIPELINE, *PIPELINE_TESTS),
}


def matches(path: str, patterns: Iterable[str]) -> bool:
    """Vrai si `path` apparie l'un des `patterns`, à la casse près (`fnmatchcase`) : les chemins de
    `git` sont sensibles à la casse, quel que soit le système qui lance le script."""
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def jobs_for(paths: Iterable[str]) -> dict[str, bool]:
    """Les jobs que le delta `paths` concerne.

    Args:
        paths: les chemins du delta, relatifs à la racine du dépôt, tels que `git diff --name-only`
            les écrit sous `--no-renames` ; une chaîne vide est ignorée.

    Returns:
        `{"web": …, "infra": …, "avis": …, "pipeline": …}`, dans cet ordre ; `False` pour les
        quatre sur un delta vide.

    Example:
        >>> jobs_for(["apps/api/content/migrations/0001_initial.py"])
        {'web': False, 'infra': True, 'avis': False, 'pipeline': False}
    """
    delta = [path for path in paths if path]
    return {
        job: any(matches(path, (*patterns, *ALL, QUOTED)) for path in delta)
        for job, patterns in JOB_PATTERNS.items()
    }


def main() -> None:
    """Lit le delta sur l'entrée standard et écrit la réponse de chaque job sur la sortie."""
    for job, runs in jobs_for(sys.stdin.read().splitlines()).items():
        print(f"{job}={'true' if runs else 'false'}")


if __name__ == "__main__":
    main()
