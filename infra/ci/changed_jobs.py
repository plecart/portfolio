"""Ce que concerne un delta de PR — les jobs `web`, `infra`, `avis`, et les tests de la
pipeline —, en `$GITHUB_OUTPUT`.

Lancé par la première étape du job `api` de `.github/workflows/ci.yml`, sur le delta de la PR :

    git diff --name-only --no-renames HEAD^1 HEAD | python3 infra/ci/changed_jobs.py >> "$GITHUB_OUTPUT"

`--no-renames` : un renommage y figure sous ses deux chemins, l'ancien et le nouveau — un fichier
déplacé du front vers `docs/` fait donc tourner `web`.

Lit sur l'entrée standard les chemins du delta, un par ligne, lignes vides ignorées, et écrit
`web=true|false`, `infra=true|false`, `avis=true|false`, puis `pipeline=true|false`. Sur une PR,
les jobs `web`, `infra` et `avis`, et l'étape « Tests pipeline » du job `api`, ne tournent que si
leur réponse vaut `true` ; sur un push vers `main`, le workflow ne la lit pas et tout tourne
(ADR 0017, ADR 0019, ADR 0025). Le job `api` tourne sur chaque push.

Règles, par motif `fnmatch` — où `*` traverse `/` :

- `web` : un chemin du front, ou le schéma de l'API, dont `make web-test` vérifie que les types
  générés du front sont à jour (`WEB`) ;
- `infra` : un chemin hors du harnais (`HARNESS`). Liste d'exclusion, jamais d'inclusion : un
  fichier inconnu fait tourner le job. Les images copient `apps/api` et `apps/web/dist`
  (`infra/api/Dockerfile`, `infra/caddy/Dockerfile`), et les tests du back tournent dans `api` —
  sauf les modules d'appui que `make image-test` charge aussi (`IMAGE_TESTS`), qui le font tourner ;
- `avis` : une entrée des portes d'avis — ce que lisent `make audit`, `make web-audit` et
  `make scan`, et ce qui les définit (`AVIS`, ADR 0019, décision 2) ;
- `pipeline` : ce que la suite de la pipeline (`make test-pipeline`) lit, et ce qui la lance
  (`PIPELINE`) ; ou un module d'appui du back qu'elle importe (`PIPELINE_TESTS`) ;
- tous : un chemin de `ALL`, qui décide des jobs eux-mêmes, ou un chemin que `git` a mis
  entre guillemets (`QUOTED`) — il le fait pour tout chemin non ASCII, que plus aucun motif
  n'apparie ; un job sauté à tort cacherait un rouge, un job lancé pour rien ne coûte que des
  minutes. Ces chemins sont hors du harnais : `infra` les prend déjà, `web`, `avis` et
  `pipeline` les ajoutent.

Liste vide : aucun des quatre. Code de sortie 0 ; l'étape qui le lance tourne sous `pipefail`, et
un `git diff` en échec y fait rougir le job `api` au lieu de rendre `false` en silence.
"""

import sys
from collections.abc import Iterable
from fnmatch import fnmatchcase

WEB = ("apps/web/*", "apps/api/openapi.json")
HARNESS = (
    ".claude/*",
    "docs/*",
    "*.md",
    "apps/api/tests/*",
    ".github/dependabot.yml",
    ".github/workflows/avis.yml",
    ".github/workflows/restore.yml",
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
# scripts du harnais, et `.github/`, dont elle relit les renvois et les commandes ; puis ce qui la
# lance, le manifeste racine — son `pytest` et son `addopts` — et le verrou. `ALL` et `QUOTED`
# s'y ajoutent, comme pour `web` et `avis`.
PIPELINE = (".claude/*", "CLAUDE.md", "CONTRIBUTING.md", ".github/*", "pyproject.toml", "uv.lock")
# Les modules de `apps/api/tests/` que `make test-pipeline` charge : ce que `.claude/tests/`
# importe, directement ou non. Recalculés par `test_ci_declencheurs.py`, comme `IMAGE_TESTS`.
PIPELINE_TESTS = ("apps/api/tests/system_commands.py", "apps/api/tests/test_supply_chain.py")
# Ce qui décide des jobs eux-mêmes.
ALL = ("Makefile", ".github/workflows/ci.yml", "infra/ci/changed_jobs.py")
# Un chemin que `git` a mis entre guillemets : non ASCII, aucun autre motif ne l'apparie plus.
QUOTED = '"*'


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
        >>> jobs_for(["apps/api/content/models.py"])
        {'web': False, 'infra': True, 'avis': False, 'pipeline': False}
    """
    delta = [path for path in paths if path]
    return {
        "web": any(matches(path, (*WEB, *ALL, QUOTED)) for path in delta),
        "infra": any(path in IMAGE_TESTS or not matches(path, HARNESS) for path in delta),
        "avis": any(matches(path, (*AVIS, *ALL, QUOTED)) for path in delta),
        "pipeline": any(
            path in PIPELINE_TESTS or matches(path, (*PIPELINE, *ALL, QUOTED)) for path in delta
        ),
    }


def main() -> None:
    """Lit le delta sur l'entrée standard et écrit la réponse de chaque job sur la sortie."""
    for job, runs in jobs_for(sys.stdin.read().splitlines()).items():
        print(f"{job}={'true' if runs else 'false'}")


if __name__ == "__main__":
    main()
