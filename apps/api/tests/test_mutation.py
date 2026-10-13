"""Tests du harnais de mutation `.claude/skills/cycle-pr/scripts/mutation.py`.

Le harnais est la preuve que les tests d'une PR *tiennent* : il casse ce qu'un test protège et
exige de le voir rougir. Un harnais qui se trompe mente toujours dans le même sens — il rend vert
un test jamais vu rouge (obs 37, deux défauts mesurés sur sept réécritures). D'où cette suite :
c'est la seule porte qui éprouve son comportement, `pyright` n'atteignant pas les dossiers cachés.
"""

import io
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from skill_scripts import load_script

mutation = load_script("cycle-pr", "mutation")

# La marge laissée aux bornes de temps : démarrage de l'interpréteur, ouverture des tubes. Les
# trois tests qui assèrent une borne la partagent — « le temps est la décision », et un nombre
# recopié trois fois se relâche une fois. Mesuré le 2026-10-10 sur ce poste : un délai de 2 s
# rend 2,09 s, un délai de 3 s avec petit-fils rend 3,1 s.
MARGE_SECONDS = 5

# Un extrait de « Commandes du projet » fidèle au vrai fichier : trois piles, des libellés qui se
# répètent d'une pile à l'autre, des commentaires alignés, un gabarit entre chevrons, un `n/a`.
CONFIG = """\
## Commandes du projet
Lues par `cycle-pr`, `execution-qa` et la génération de CI. `n/a` = étape absente du projet.

**Back (`apps/api/`)** — vérifiées le 2026-09-23 :
- install      : make install                     # uv sync
- test         : make test                        # suite complète ; exige Docker
- test ciblé   : uv run pytest <chemin|motif>     # une seule cible, pour la boucle TDD
- lint         : make lint                        # ruff check

**Front (`apps/web/`)** — vérifiées le 2026-09-23 :
- test ciblé   : cd apps/web && npm test -- <motif>
- format       : n/a                              # aucun formateur front installé
- e2e          : make web-e2e                     # Playwright + axe

## Qualité
- seuil de couverture : aucun
"""


def write_config(tmp_path: Path) -> Path:
    """Dépose l'extrait de configuration dans un dépôt jetable."""
    config = tmp_path / "pipeline.config.md"
    config.write_text(CONFIG, encoding="utf-8")
    return config


def test_la_commande_se_lit_dans_la_pile_demandee(tmp_path: Path) -> None:
    """Le libellé seul est ambigu : « test ciblé » existe dans les trois piles."""
    config = write_config(tmp_path)

    assert mutation.project_command(config, "test ciblé") == "uv run pytest"
    assert mutation.project_command(config, "test ciblé", stack="Front") == (
        "cd apps/web && npm test --"
    )
    assert mutation.project_command(config, "e2e", stack="Front") == "make web-e2e"


def test_une_etape_absente_ou_inconnue_arrete_au_lieu_de_deviner(tmp_path: Path) -> None:
    """Deviner une commande ferait rendre un verdict sur une suite qui n'a jamais tourné."""
    config = write_config(tmp_path)

    with pytest.raises(LookupError, match="n/a"):
        mutation.project_command(config, "format", stack="Front")
    with pytest.raises(LookupError, match="aucune commande"):
        mutation.project_command(config, "typecheck")
    # Un libellé d'une autre section ne répond pas à la place d'une commande. La pile demandée
    # est `Front` à dessein : c'est la dernière vue avant `## Qualité`, donc celle qu'une
    # recherche non bornée attribuerait à ses lignes. Mesuré sur le vrai fichier le 2026-10-09 :
    # 21 lignes en forme de commande vivent hors de la section, dont 15 sous cette pile.
    with pytest.raises(LookupError, match="aucune commande"):
        mutation.project_command(config, "seuil de couverture", stack="Front")


# --- Les rapports des trois lanceurs, mesurés le 2026-10-09 sur les versions du projet ---------

JUNIT_REPORT = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="3">
<testcase classname="apps.api.tests.test_x" name="test_passe" time="0.01" />
<testcase classname="apps.api.tests.test_x" name="test_echoue[cas: avec espace]" time="0.02">
<failure message="assert 1 == 2">E   assert 1 == 2</failure></testcase>
<testcase classname="apps.api.tests.test_x" name="test_en_erreur" time="0.00">
<error message="fixture introuvable">E   error</error></testcase>
<testcase classname="apps.api.tests.test_x" name="test_saute" time="0.00">
<skipped message="pas sur ce poste" /></testcase>
</testsuite></testsuites>
"""

VITEST_REPORT = """\
{"numTotalTests": 2, "success": false, "testResults": [
  {"name": "/w/tests/sonde.test.ts", "status": "failed", "assertionResults": [
    {"status": "passed", "fullName": "sonde passe", "title": "passe", "ancestorTitles": ["sonde"]},
    {"status": "failed", "fullName": "sonde echoue", "title": "echoue", "ancestorTitles": ["sonde"]}
  ]}]}
"""

# Un rapport Vitest réel, relevé le 2026-10-10 en jouant `it`, `it.skip` et `it.todo` sur le
# lanceur du dépôt (`npx vitest run --reporter=json`). C'est lui qui dit le vocabulaire des
# états « n'a pas tourné » — et qu'il vaut `skipped` et `todo`, jamais le `pending` de Jest.
VITEST_NOT_RUN_REPORT = """\
{"numTotalTests": 3, "success": true, "testResults": [
  {"name": "/w/tests/sonde-etats.test.ts", "status": "passed", "assertionResults": [
    {"status": "passed", "fullName": "sonde un test qui passe", "title": "un test qui passe"},
    {"status": "skipped", "fullName": "sonde un test saute", "title": "un test saute"},
    {"status": "todo", "fullName": "sonde un test a faire", "title": "un test a faire"}
  ]}]}
"""

PLAYWRIGHT_REPORT = """\
{"config": {}, "errors": [], "stats": {}, "suites": [
  {"title": "probe.spec.ts", "file": "probe.spec.ts", "specs": [
    {"title": "passe", "ok": true, "tests": [
      {"projectName": "desktop", "status": "expected", "results": [{"status": "passed"}]},
      {"projectName": "mobile", "status": "unexpected", "results": [{"status": "failed"}]}]}],
   "suites": [{"title": "un groupe", "specs": [
     {"title": "echoue", "ok": false, "tests": [{"status": "unexpected",
       "results": [{"status": "failed"}]}]},
     {"title": "instable", "ok": true, "tests": [{"status": "flaky",
       "results": [{"status": "failed"}, {"status": "passed"}]}]}]}]}]}
"""


def test_le_rapport_junit_rend_un_etat_par_test_sans_tronquer_son_identifiant() -> None:
    """Un identifiant paramétré tronqué à la première espace a rendu seize rouges « VERT »."""
    outcomes = mutation.REPORTERS["junit"].outcomes(JUNIT_REPORT)

    assert outcomes["apps.api.tests.test_x::test_passe"] == "passed"
    assert outcomes["apps.api.tests.test_x::test_echoue[cas: avec espace]"] == "failed"
    assert outcomes["apps.api.tests.test_x::test_en_erreur"] == "failed"
    assert outcomes["apps.api.tests.test_x::test_saute"] == "skipped"


def test_le_rapport_vitest_rend_un_etat_par_assertion() -> None:
    """Forme mesurée : `testResults[].assertionResults[]`, `fullName` et `status`."""
    outcomes = mutation.REPORTERS["vitest"].outcomes(VITEST_REPORT)

    assert outcomes == {"sonde passe": "passed", "sonde echoue": "failed"}


def test_le_rapport_playwright_rend_un_etat_par_spec_et_par_projet() -> None:
    """Deux projets jouent chaque spec : sans leur nom dans la clé, la moitié disparaît.

    Forme mesurée : les `describe` imbriquent des `suites`, et le vocabulaire d'un `test` est
    `expected` / `unexpected`, distinct du `passed` / `failed` de ses `results`.

    `flaky` n'est pas traduit en `failed` : un test qui n'a rougi qu'à un essai sur deux n'a pas
    *attrapé* la mutation, et le compter rouge ferait mentir le harnais dans le sens qui
    l'arrange. Le verdict n'accepte que `failed`, donc un `flaky` laisse la mutation VERTE.
    """
    outcomes = mutation.REPORTERS["playwright"].outcomes(PLAYWRIGHT_REPORT)

    assert outcomes == {
        "probe.spec.ts > passe [desktop]": "passed",
        "probe.spec.ts > passe [mobile]": "failed",
        "probe.spec.ts > un groupe > echoue": "failed",
        "probe.spec.ts > un groupe > instable": "flaky",
    }


# --- La boucle de mutation, sur un dépôt jetable ----------------------------------------------

SOURCE = """\
def positive(n):
    if n < 0:
        raise ValueError("négatif")
    return n


def doubled(n):
    return n * 2
"""

SUITE = """\
import pytest

from source import positive


def test_refuse_un_negatif():
    with pytest.raises(ValueError):
        positive(-1)


def test_rend_un_positif():
    assert positive(2) == 2
"""


def build_repo(tmp_path: Path, suite: str = SUITE) -> Path:
    """Un dépôt jetable : une configuration, une source, une suite. Aucune infrastructure."""
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "pipeline.config.md").write_text(
        "## Commandes du projet\n\n"
        "**Back (`.`)** — vérifiées :\n"
        f'- test ciblé   : "{sys.executable}" -m pytest -p no:cacheprovider\n',
        encoding="utf-8",
    )
    (tmp_path / "source.py").write_text(SOURCE, encoding="utf-8")
    (tmp_path / "test_source.py").write_text(suite, encoding="utf-8")
    return tmp_path


def spec(**mutation: object) -> dict[str, object]:
    """Un fichier de mutations à une seule mutation, valeurs par défaut comprises."""
    return {"targets": ["test_source.py"], "mutations": [{"expect": [], **mutation}]}


def test_une_mutation_attrapee_est_rouge_et_le_fichier_revient_octet_pour_octet(
    tmp_path: Path,
) -> None:
    """Le cœur du contrat : la garde retirée, le test qui la protège doit rougir."""
    root = build_repo(tmp_path)
    before = (root / "source.py").read_bytes()

    verdicts = mutation.play(
        root,
        spec(
            name="garde du négatif retirée",
            file="source.py",
            old="if n < 0:",
            new="if False:",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["ROUGE"]
    assert (root / "source.py").read_bytes() == before


def test_un_test_qui_ne_tient_pas_est_vert(tmp_path: Path) -> None:
    """Muter ce qu'aucun test n'observe doit rendre VERT, jamais ROUGE."""
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        spec(
            name="doublement cassé",
            file="source.py",
            old="return n * 2",
            new="return n * 3",
            expect=["test_rend_un_positif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["VERT"]


def test_le_rouge_d_un_autre_test_ne_vaut_pas_le_rouge_attendu(tmp_path: Path) -> None:
    """Mesuré le 2026-10-04 : une mutation a compté ROUGE sur l'échec d'un *autre* test.

    Ici la mutation fait rougir `test_rend_un_positif` mais pas `test_refuse_un_negatif`, qu'on
    prétend éprouver. Un verdict pris sur le code de sortie dirait ROUGE.
    """
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        spec(
            name="retour faussé",
            file="source.py",
            old="    return n\n",
            new="    return n + 1\n",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["VERT"]
    assert "test_rend_un_positif" in verdicts[0].detail


def test_un_old_absent_ou_multiple_est_une_panne_et_ne_touche_rien(tmp_path: Path) -> None:
    """Un remplacement non unique muterait autre chose que ce que la mutation prétend."""
    root = build_repo(tmp_path)
    before = (root / "source.py").read_bytes()

    attendu = ["test_refuse_un_negatif"]
    absent = mutation.play(
        root, spec(name="absent", file="source.py", old="zzz", new="y", expect=attendu)
    )
    multiple = mutation.play(
        root, spec(name="multiple", file="source.py", old="n", new="m", expect=attendu)
    )

    assert [v.verdict for v in absent] == ["PANNE"]
    assert [v.verdict for v in multiple] == ["PANNE"]
    assert "0 fois" in absent[0].detail
    assert (root / "source.py").read_bytes() == before


def test_une_mutation_qui_ne_mute_rien_est_une_panne(tmp_path: Path) -> None:
    """`new` identique à `old` réécrit le fichier à l'identique : le test visé reste vert, et ce
    VERT se lit « l'invariant n'est pas gardé » alors que rien n'a été muté (obs 77). Mesuré au
    lot 2 de #77 : une ancre choisie par sous-chaîne avait pris le commentaire qui citait le code,
    et son remplacement ne trouvait rien."""
    root = build_repo(tmp_path)
    before = (root / "source.py").read_bytes()

    verdicts = mutation.play(
        root,
        spec(
            name="sans effet",
            file="source.py",
            old="if n < 0:",
            new="if n < 0:",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "ne mute rien" in verdicts[0].detail
    assert (root / "source.py").read_bytes() == before


def test_les_fins_de_ligne_du_fichier_mute_sont_respectees(tmp_path: Path) -> None:
    """Les worktrees sont extraits en CRLF, l'arbre de l'auteur en LF : un `old` en LF n'y est
    jamais trouvé (obs 37, complément du 2026-09-27)."""
    root = build_repo(tmp_path)
    crlf = SOURCE.replace("\n", "\r\n")
    (root / "source.py").write_bytes(crlf.encode("utf-8"))

    verdicts = mutation.play(
        root,
        spec(
            name="garde retirée dans un fichier CRLF",
            file="source.py",
            old="if n < 0:\n        raise ValueError",
            new="if False:\n        raise ValueError",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["ROUGE"]
    assert (root / "source.py").read_bytes() == crlf.encode("utf-8")


def test_un_temoin_rouge_arrete_avant_toute_mutation(tmp_path: Path) -> None:
    """Sans témoin vert, un rouge de mutation ne prouve rien : il était peut-être déjà là."""
    root = build_repo(tmp_path, suite=SUITE + "\n\ndef test_deja_rouge():\n    assert False\n")
    before = (root / "source.py").read_bytes()

    verdicts = mutation.play(
        root, spec(name="jamais jouée", file="source.py", old="if n < 0:", new="if False:")
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "témoin" in verdicts[0].detail
    assert "test_deja_rouge" in verdicts[0].detail
    assert (root / "source.py").read_bytes() == before


SECURITY_MUTATIONS = {
    "exception de scanner": {"file": ".trivyignore.yaml", "old": "a", "new": "b"},
    "porte de CI": {"file": ".github/workflows/ci.yml", "old": "a", "new": "b"},
    "permission d'agent": {"file": ".claude/settings.json", "old": "a", "new": "b"},
    "option de blocage": {"file": "Makefile", "old": "--exit-code 1", "new": ""},
    "épingle d'empreinte": {
        "file": "infra/api/Dockerfile",
        "old": "python:3.12@sha256:" + "0" * 64,
        "new": "python:3.12",
    },
    # Formes de chemin repliables : mesurées en relecture, `//` et `./` traversaient le refus,
    # qui appariait la chaîne déclarée sans la normaliser. La classe se traite entière.
    "porte de CI, double barre": {
        "file": ".github//workflows/ci.yml",
        "old": "a",
        "new": "b",
    },
    "réglages de l'application, double barre": {
        "file": "apps/api/config//settings.py",
        "old": "a",
        "new": "b",
    },
    "permission d'agent, préfixe point-barre": {
        "file": "./.claude/settings.json",
        "old": "a",
        "new": "b",
    },
}


@pytest.mark.parametrize(
    ("label", "candidate"), SECURITY_MUTATIONS.items(), ids=SECURITY_MUTATIONS.keys()
)
def test_une_mutation_d_un_reglage_de_securite_est_refusee(
    label: str, candidate: dict[str, str]
) -> None:
    """Le classifieur du mode auto refuse de lancer une suite sur un dépôt affaibli (obs 53).

    Le harnais n'essaie donc pas : il refuse et renvoie à la forme qui prouve autant sans
    toucher au dépôt — la garde écrite en fonction sur du texte, éprouvée sur un recueil de
    formes fautives construites en mémoire.
    """
    refusal = mutation.security_refusal(candidate)

    assert refusal, f"« {label} » devrait être refusée"
    assert "recueil de formes fautives" in refusal


def test_une_mutation_sans_rouge_attendu_est_une_panne(tmp_path: Path) -> None:
    """« Le rouge attendu nommé » est tout le propos : sans nom, il n'y a rien à conclure."""
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root, spec(name="sans attendu", file="source.py", old="if n < 0:", new="if False:")
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "`expect` est vide" in verdicts[0].detail


# --- Ce que la première passe de relecture a trouvé (2026-10-09) -------------------------------


def test_un_rouge_attendu_ambigu_est_une_panne_pas_un_rouge(tmp_path: Path) -> None:
    """Le défaut d'obs 37, rouvert d'un cran plus étroit : apparié en sous-chaîne, `expect`
    accepte le rouge d'un **frère de préfixe** pendant que le test visé reste vert.

    Mesuré : une suite portant `test_refuse_un_negatif` et
    `test_refuse_un_negatif_et_double_le_reste` rendait ROUGE pour le premier sur le rouge du
    second. Désormais un fragment doit désigner **un** test de la suite témoin — la symétrie de
    l'unicité exigée de `old`.
    """
    root = build_repo(
        tmp_path,
        suite=SUITE + "\n\ndef test_refuse_un_negatif_et_double_le_reste():\n    assert True\n",
    )

    verdicts = mutation.play(
        root,
        spec(
            name="retour faussé",
            file="source.py",
            old="    return n\n",
            new="    return n + 1\n",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "apparie 2 tests" in verdicts[0].detail


def test_un_rouge_attendu_introuvable_est_une_panne(tmp_path: Path) -> None:
    """Une faute de frappe dans `expect`, ou un identifiant que le lanceur échappe — pytest
    échappe les non-ASCII des cas paramétrés —, rendait VERT : un verdict sur un test jamais
    nommé. Zéro appariement est une panne, pas un test qui ne tient pas."""
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        spec(
            name="attendu mal orthographié",
            file="source.py",
            old="if n < 0:",
            new="if False:",
            expect=["test_refuse_un_negatiff"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "apparie 0 tests" in verdicts[0].detail


# Des chemins **neutres** à dessein : un chemin absolu de réglage de sécurité serait arrêté par
# le refus de sécurité, et le test prouverait l'autre garde. Ici seule la borne peut mordre.
HORS_RACINE = {
    "chemin absolu": "{anchor}hors-du-depot-sonde.txt",
    "remontée par deux points": "../../hors-du-depot-sonde.txt",
    "remontée déguisée": "sous/../../../hors-du-depot-sonde.txt",
}


@pytest.mark.parametrize("declared", HORS_RACINE.values(), ids=HORS_RACINE.keys())
def test_un_fichier_hors_de_la_racine_est_refuse(tmp_path: Path, declared: str) -> None:
    """`Path` ne borne rien : joint à un chemin absolu, il le rend tel quel.

    Un `file` qui sort de la racine fait muter — et restaurer — hors du worktree isolé, donc
    dans le clone principal où l'auteur travaille au même moment. C'est la rupture d'isolation
    que la vérification de `git rev-parse --show-toplevel` existe pour empêcher, et elle
    contourne au passage le refus de sécurité, qui n'apparie que le chemin **déclaré**.
    """
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        spec(
            name="évasion",
            file=declared.format(anchor=tmp_path.anchor.replace("\\", "/")),
            old="quoi que ce soit",
            new="",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "sort de la racine" in verdicts[0].detail


def test_un_rapport_illisible_est_une_panne(tmp_path: Path) -> None:
    """Le docstring promettait PANNE ; l'exception du lecteur s'échappait et emportait les
    mutations suivantes du lot avec une trace au lieu d'un verdict.

    Le rapporteur de ce test écrit la sortie de la commande à la place du rapport : c'est la
    forme d'un lanceur tué en cours d'écriture, ou d'une sortie mêlée au rapport.
    """
    root = build_repo(tmp_path)
    garbled = mutation.Reporter(' > "{report}"', mutation.junit_outcomes)

    with pytest.raises(mutation.Unusable, match="illisible"):
        mutation.Suite(root, "echo pas du xml", garbled, []).outcomes()


def test_un_lanceur_qui_ne_demarre_pas_est_une_panne_d_outil(tmp_path: Path) -> None:
    """La troisième des « trois états » du critère : ni ROUGE ni VERT, et qui dit pourquoi.

    Le message nomme la cause la plus fréquente — les options du rapport sont ajoutées à la
    commande, et une cible `make` ou `just` les refuse.
    """
    root = build_repo(tmp_path)
    (root / ".claude" / "pipeline.config.md").write_text(
        "## Commandes du projet\n\n**Back (`.`)** — v :\n"
        "- test ciblé   : binaire-absent-pour-la-sonde --run\n",
        encoding="utf-8",
    )

    verdicts = mutation.play(
        root,
        spec(
            name="jamais jouée",
            file="source.py",
            old="if n < 0:",
            new="if False:",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "aucun rapport produit" in verdicts[0].detail
    assert "invoque le lanceur directement" in verdicts[0].detail


def test_un_delai_depasse_est_une_panne_et_restaure_le_fichier(tmp_path: Path) -> None:
    """Une mutation fabrique des boucles sans fin : la condition d'arrêt est ce qu'on casse.

    Sans délai, le harnais se bloque **le fichier muté**, et un arrêt brutal laisse le dépôt
    affaibli — le `finally` ne tourne pas sous un signal non rattrapable.

    Le temps écoulé est asséré, parce que **le temps est la décision** : le verdict et la
    restauration tiennent aussi quand la borne ne borne rien. Mesuré en relecture : `/T` retiré
    du `taskkill`, la suite restait verte et ce test mettait **30,08 s** pour un délai de 2 s
    (2,08 s sur l'arbre propre). La marge est celle du second recours borné, pas une tolérance
    de confort : au-delà, c'est que l'arbre a survécu.
    """
    root = build_repo(tmp_path)
    before = (root / "source.py").read_bytes()
    (root / ".claude" / "pipeline.config.md").write_text(
        "## Commandes du projet\n\n**Back (`.`)** — v :\n"
        f'- test ciblé   : "{sys.executable}" -c "import time; time.sleep(30)"\n',
        encoding="utf-8",
    )
    started = time.monotonic()

    verdicts = mutation.play(
        root,
        {
            "targets": [],
            "timeout": 2,
            "mutations": [
                {
                    "name": "boucle sans fin",
                    "file": "source.py",
                    "old": "if n < 0:",
                    "new": "if False:",
                    "expect": ["test_refuse_un_negatif"],
                }
            ],
        },
    )
    elapsed = time.monotonic() - started

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "délai de 2 s dépassé" in verdicts[0].detail
    assert (root / "source.py").read_bytes() == before
    assert elapsed < 2 + MARGE_SECONDS, f"la borne n'a pas tenu : {elapsed:.2f} s"


def test_un_rapporteur_inconnu_est_une_panne(tmp_path: Path) -> None:
    """Une clé écrite à la main doit rendre un verdict, jamais une `KeyError` nue."""
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        {
            "targets": [],
            "reporter": "jupiter",
            "mutations": [{"name": "x", "file": "source.py", "old": "a", "new": "b"}],
        },
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "inconnu" in verdicts[0].detail


def test_un_fichier_de_mutations_sans_mutation_est_une_panne(tmp_path: Path) -> None:
    """Zéro mutation jouée ne doit pas se lire « toutes attrapées »."""
    verdicts = mutation.play(build_repo(tmp_path), {"targets": [], "mutations": []})

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "`mutations` est vide" in verdicts[0].detail


ORDINAIRES = {
    "le propre test de refus du harnais": {
        "file": "apps/api/tests/test_mutation.py",
        "old": '"old": "--exit-code 1"',
        "new": '"old": ""',
    },
    "le recueil de motifs du harnais": {
        "file": ".claude/skills/cycle-pr/scripts/mutation.py",
        "old": "--ignore-unfixed|--exit-code",
        "new": "--ignore-unfixed",
    },
    "une épingle de digest dans un module de support de test": {
        "file": "apps/api/tests/containers.py",
        "old": "postgres@sha256:" + "0" * 64,
        "new": "postgres@sha256:" + "1" * 64,
    },
    "un dict produit portant une clé allow": {
        "file": "apps/api/content/models.py",
        "old": '"allow": True',
        "new": '"allow": False',
    },
    "une option de saut de lanceur": {
        "file": "apps/api/tests/test_project.py",
        "old": "--skip-slow",
        "new": "",
    },
    "une garde ordinaire": {"file": "source.py", "old": "if n < 0:", "new": ""},
}


@pytest.mark.parametrize("candidate", ORDINAIRES.values(), ids=ORDINAIRES.keys())
def test_une_mutation_ordinaire_n_est_jamais_refusee(candidate: dict[str, str]) -> None:
    """Un refus qui mord sur le travail ordinaire est un refus qu'on apprend à contourner.

    Mesuré en relecture : les motifs de contenu, appliqués à tout fichier, refusaient 5 cas sur
    6 — dont le propre recueil de ce script et son propre test de refus, donc le harnais ne
    pouvait pas éprouver son critère de sécurité par mutation. Ils sont maintenant bornés aux
    fichiers de configuration.
    """
    assert mutation.security_refusal(candidate) is None


# La casse d'un chemin de réglage de sécurité : les systèmes de fichiers du poste et de la CI
# sont insensibles à la casse — NTFS, APFS par défaut —, donc `.github/WORKFLOWS/ci.yml`
# **est** `.github/workflows/ci.yml` et passait le refus. Une forme par appariement insensible :
# les 10 motifs de chemin, et le test de fichier de configuration qui borne ceux de contenu.
CASSES = {
    "porte de CI en majuscules": {"file": ".github/WORKFLOWS/ci.yml", "old": "a", "new": "b"},
    "permission d'agent en majuscules": {
        "file": ".CLAUDE/settings.json",
        "old": "a",
        "new": "b",
    },
    "propriétaires du code en minuscules": {"file": "codeowners", "old": "a", "new": "b"},
    "composition de production en capitales": {
        "file": "COMPOSE.PROD.YAML",
        "old": "a",
        "new": "b",
    },
    "suffixe de configuration en majuscules": {
        "file": "infra/ci/scan.YML",
        "old": "trivy image",
        "new": "trivy image --exit-code 0",
    },
    "nom de configuration en minuscules": {
        "file": "makefile",
        "old": "trivy image",
        "new": "trivy image --severity HIGH",
    },
}


@pytest.mark.parametrize("candidate", CASSES.values(), ids=CASSES.keys())
def test_la_casse_du_chemin_ne_contourne_pas_le_refus(candidate: dict[str, str]) -> None:
    """Un refus qu'une majuscule contourne n'est pas un refus.

    Mesuré en relecture sur `.github/WORKFLOWS/ci.yml`. Les deux derniers cas visent le second
    appariement, celui qui décide si les motifs de **contenu** s'appliquent : un suffixe ou un
    nom de fichier en majuscules sortait le fichier du périmètre de configuration, donc aucune
    option de scanner n'y était cherchée.
    """
    assert mutation.security_refusal(candidate), "la casse a contourné le refus"


def test_les_motifs_de_contenu_restent_sensibles_a_la_casse() -> None:
    """Le troisième appariement est volontairement sensible, et le dénombrement le dit.

    `--SEVERITY` n'est pas une option, `@SHA256:` n'est pas une empreinte, et les clés JSON que
    cherche la règle de permission sont elles-mêmes sensibles à la casse. Les rendre insensibles
    élargirait le refus sans fermer aucune voie réelle.
    """
    assert (
        mutation.security_refusal(
            {"file": "infra/ci/scan.yml", "old": "trivy image", "new": "trivy image --SEVERITY"}
        )
        is None
    )


def test_un_attendu_saute_est_une_panne_pas_un_vert(tmp_path: Path) -> None:
    """Un test sauté n'a pas tourné : le même état qu'un attendu absent du rapport.

    Il rendait VERT — « le test ne tient pas » — pour un test que personne n'a joué, et c'est
    l'erreur qui coûte le plus : elle envoie renforcer une garde qui tenait déjà. `flaky` reste
    hors de cette classe, lui : il a tourné, et n'a pas attrapé la mutation de façon fiable.
    """
    root = build_repo(
        tmp_path,
        suite=(
            "import pytest\n\nfrom source import positive\n\n\n"
            '@pytest.mark.skip(reason="sauté à dessein")\n'
            "def test_refuse_un_negatif():\n"
            "    with pytest.raises(ValueError):\n        positive(-1)\n"
        ),
    )

    verdicts = mutation.play(
        root,
        spec(
            name="garde du négatif retirée",
            file="source.py",
            old="if n < 0:",
            new="if False:",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "n'ont pas tourné" in verdicts[0].detail


def test_un_refus_de_securite_arrete_la_mutation_dans_play(tmp_path: Path) -> None:
    """La garde vivait en deux endroits qui se masquaient : retirer l'un laissait l'autre rendre
    le même verdict, donc aucun test ne pouvait épingler ni l'un ni l'autre. Il n'en reste
    qu'un, et ce test l'éprouve au niveau où il agit."""
    root = build_repo(tmp_path)
    (root / "compose.yml").write_text("services:\n  api:\n    image: x\n", encoding="utf-8")

    verdicts = mutation.play(
        root,
        spec(
            name="composition affaiblie",
            file="compose.yml",
            old="image: x",
            new="image: y",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "réglage de sécurité" in verdicts[0].detail
    assert "recueil de formes fautives" in verdicts[0].detail


# --- Ce que les sondes de la passe 2 ont trouvé (2026-10-09) -----------------------------------
#
# Ces quatre gardes viennent de sondes écrites par un relecteur interrompu par une limite
# d'usage avant d'avoir pu rendre son rapport. Ses fichiers de sonde sont restés dans son
# worktree ; les relire et les jouer a coûté moins que de redécouvrir ce qu'il avait vu.


def test_un_expect_ecrit_en_chaine_est_refuse_avant_toute_resolution(tmp_path: Path) -> None:
    """Une chaîne est itérable : chaque **lettre** deviendrait un fragment de `expect`.

    Mesuré le 2026-10-09 : sur une suite témoin à un seul test, chaque lettre s'y résolvait, et
    `"expect": "un"` rendait **ROUGE** — comme `"expect": "test_refuse_un_negatiff"`, un nom mal
    orthographié. C'est le défaut que `resolve` ferme, rouvert par une erreur de type : le refus
    doit donc venir **avant** la résolution.
    """
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        spec(
            name="expect mal typé",
            file="source.py",
            old="if n < 0:",
            new="if False:",
            expect="test_refuse_un_negatif",
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "`expect` est une chaîne" in verdicts[0].detail


# Une suite témoin dont le cas paramétré porte un accent, comme près de trois dixièmes de ceux
# du dépôt — dénombrement et commande dans
# `test_un_identifiant_accentue_se_nomme_dans_sa_forme_naturelle`.
SUITE_ACCENTUEE = """\
import pytest

from source import positive


@pytest.mark.parametrize("valeur", [-1], ids=["à la borne"])
def test_refuse_un_negatif(valeur):
    with pytest.raises(ValueError):
        positive(valeur)
"""


def test_un_identifiant_accentue_se_nomme_dans_sa_forme_naturelle(tmp_path: Path) -> None:
    """`expect` nomme un cas paramétré accentué comme on l'écrit, pas comme pytest l'échappe.

    pytest échappe les non-ASCII des identifiants paramétrés : `à la borne` devient le littéral
    `\\xe0 la borne`, dans le rapport comme sur la ligne de commande. Un harnais qui ne sait
    nommer que l'ASCII laisse hors de sa portée la part de la suite qui en porte, et rend PANNE
    « apparie 0 tests » sur un test qui existe, ce qui se lit comme une faute de frappe.

    **Ce test est le seul endroit où ce chiffre vit**, et c'est le dénombrement qui bouge, pas
    l'invariant : ce qui rougit ici est la résolution de la forme échappée, qui ne dépend
    d'aucun décompte. Avec `test_un_identifiant_accentue_se_nomme_aussi_dans_la_forme_du_lanceur`,
    les **deux** branches de l'union sont couvertes — retirer l'une ou l'autre fait rougir.

    Relevé du **2026-10-12 sur `ee21cb5`**, par `uv run pytest --collect-only -q` sur les
    identifiants collectés portant un échappement non-ASCII : **302 des 1041 tests, sur
    19 fichiers** — soit 29,0 %, dont 280 en `\\x` et 22 en `\\u` seulement
    (`test_image_scan.py`, des bornes du type
    `[infra \\u2014 sans scan]`). Compter la seule forme `\\x` sous-décrit la population que
    `resolve` doit couvrir, puisque `encode("unicode_escape")` rend les deux. La population est
    figée par un commit, donc reproductible à SHA égal ; elle grossit à chaque lot, donc le
    couple 302/1041 se relit, jamais se recopie.
    """
    root = build_repo(tmp_path, suite=SUITE_ACCENTUEE)

    verdicts = mutation.play(
        root,
        spec(
            name="garde du négatif retirée",
            file="source.py",
            old="if n < 0:",
            new="if False:",
            expect=["test_refuse_un_negatif[à la borne]"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["ROUGE"]


def test_un_identifiant_accentue_se_nomme_aussi_dans_la_forme_du_lanceur(tmp_path: Path) -> None:
    """La forme échappée, celle que le rapport affiche, reste acceptée : les deux mènent au test.

    C'est ce que la PANNE donne à lire à qui l'a rencontrée ; la refuser l'obligerait à
    deviner laquelle des deux formes le harnais attend.
    """
    root = build_repo(tmp_path, suite=SUITE_ACCENTUEE)

    verdicts = mutation.play(
        root,
        spec(
            name="garde du négatif retirée",
            file="source.py",
            old="if n < 0:",
            new="if False:",
            expect=["test_refuse_un_negatif[\\xe0 la borne]"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["ROUGE"]


CLES_OBLIGATOIRES = ("file", "old", "new")


@pytest.mark.parametrize("missing", CLES_OBLIGATOIRES)
def test_une_cle_obligatoire_absente_est_une_panne(tmp_path: Path, missing: str) -> None:
    """Le fichier de mutations s'écrit à la main : une clé oubliée rendait une `KeyError` nue,
    qui abandonnait les mutations suivantes du lot avec une trace au lieu d'un verdict."""
    root = build_repo(tmp_path)
    entry = {
        "name": "clé manquante",
        "file": "source.py",
        "old": "if n < 0:",
        "new": "if False:",
        "expect": ["test_refuse_un_negatif"],
    }
    del entry[missing]

    verdicts = mutation.play(root, {"targets": ["test_source.py"], "mutations": [entry]})

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert f"clé « {missing} » absente" in verdicts[0].detail


MAUVAIS_DELAIS = {
    "texte": "beaucoup",
    "zéro": 0,
    "négatif": -5,
    "booléen": True,
    "nul": None,
}


@pytest.mark.parametrize("value", MAUVAIS_DELAIS.values(), ids=MAUVAIS_DELAIS.keys())
def test_un_delai_qui_n_est_pas_un_nombre_positif_est_une_panne(
    tmp_path: Path, value: object
) -> None:
    """`int("beaucoup")` levait une `ValueError` nue depuis la construction de la suite.

    `True` est refusé aussi : il vaudrait une seconde, et toute suite dépasserait ce délai —
    une PANNE généralisée qui se lirait comme un environnement cassé.
    """
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        {
            "targets": ["test_source.py"],
            "timeout": value,
            "mutations": [
                {
                    "name": "délai absurde",
                    "file": "source.py",
                    "old": "if n < 0:",
                    "new": "if False:",
                    "expect": ["test_refuse_un_negatif"],
                }
            ],
        },
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "`timeout`" in verdicts[0].detail


def test_un_lien_dur_vers_un_fichier_hors_racine_est_refuse(tmp_path: Path) -> None:
    """`resolve()` ne suit pas un lien **dur** : ce n'est pas un lien dans le chemin, c'est le
    même fichier sous un autre nom.

    Mesuré le 2026-10-09 : un lien dur créé dans la racine vers un fichier extérieur passait la
    borne, et l'écriture atteignait bien le fichier extérieur — la jonction NTFS, le lien
    symbolique et le chemin UNC, eux, étaient déjà refusés. Les 239 fichiers suivis du dépôt ont
    tous exactement un lien, donc la garde ne refuse aucun travail ordinaire.
    """
    root = tmp_path / "depot"
    root.mkdir()
    outside = tmp_path / "hors.txt"
    outside.write_text("secret\n", encoding="utf-8")
    inside = root / "innocent.txt"
    try:
        os.link(outside, inside)
    except (OSError, NotImplementedError) as refus:  # pragma: no cover — selon le système
        pytest.skip(f"liens durs indisponibles ici : {refus}")

    with pytest.raises(mutation.Unusable, match="liens durs"):
        mutation.within(root, "innocent.txt")

    assert outside.read_text(encoding="utf-8") == "secret\n"


def test_une_jonction_vers_l_exterieur_est_refusee_par_la_borne(tmp_path: Path) -> None:
    """Un répertoire de la racine qui *pointe* ailleurs, et dont la cible **existe**.

    Première écriture de ce test : il nommait un chemin UNC et une jonction **inexistants**, et
    assertait seulement « ça lève ». Mesuré par mutation : la borne retirée, il restait vert —
    `is_file()` refusait les deux pour une tout autre raison. Un test d'évasion doit donc porter
    sur une cible qui existe, et asserter **le motif**, pas le seul fait qu'on a refusé.

    Dénombrement de la classe, 4 formes recensées : jonction et lien symbolique refusés par
    `resolve()` + `is_relative_to`, chemin absolu et remontée par `..` de même, lien dur refusé
    par le compte de liens — qu'aucun des deux mécanismes précédents n'aurait attrapé.
    """
    root = tmp_path / "depot"
    root.mkdir()
    elsewhere = tmp_path / "ailleurs"
    elsewhere.mkdir()
    (elsewhere / "hors.txt").write_text("secret\n", encoding="utf-8")
    try:
        made = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(root / "pont"), str(elsewhere)],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError) as absent:  # pragma: no cover — hors Windows
        pytest.skip(f"`mklink` indisponible ici : {absent}")
    if not (root / "pont").exists():  # pragma: no cover — selon le système de fichiers
        pytest.skip(f"jonctions indisponibles ici : {made.stdout or made.stderr}")

    with pytest.raises(mutation.Unusable, match="sort de la racine"):
        mutation.within(root, "pont/hors.txt")

    assert (elsewhere / "hors.txt").read_text(encoding="utf-8") == "secret\n"


# Les **trois** champs de liste du fichier de mutations. Un constat sur l'un d'eux est un
# échantillon, pas un inventaire : `expect` a été trouvé par une sonde de relecture, `targets` et
# `mutations` le partageaient sans que personne les ait regardés.
CHAMPS_DE_LISTE = {
    "expect": {"expect": "test_refuse_un_negatif"},
    "targets": {"targets": "test_source.py"},
    "mutations": {"mutations": "une mutation"},
}


@pytest.mark.parametrize("surcharge", CHAMPS_DE_LISTE.values(), ids=CHAMPS_DE_LISTE.keys())
def test_aucun_champ_de_liste_n_accepte_une_chaine(
    tmp_path: Path, surcharge: dict[str, str]
) -> None:
    """Une chaîne est itérable : écrite là où une liste est attendue, elle est lue lettre par
    lettre, et chaque lettre devient un élément.

    Mesuré sur `expect` : `"un"` rendait ROUGE. La même forme sur `targets` aurait envoyé une
    lettre par argument au lanceur, et sur `mutations` aurait fait appeler `.get` sur une lettre.
    Dénombrement de la classe : **3 champs de liste recensés, 3 refusés.**
    """
    root = build_repo(tmp_path)
    entry: dict[str, Any] = {
        "name": "sonde",
        "file": "source.py",
        "old": "if n < 0:",
        "new": "if False:",
        "expect": ["test_refuse_un_negatif"],
    }
    base: dict[str, Any] = {"targets": ["test_source.py"], "mutations": [entry]}
    if "expect" in surcharge:
        entry["expect"] = surcharge["expect"]
    else:
        base.update(surcharge)

    verdicts = mutation.play(root, base)

    assert [v.verdict for v in verdicts] == ["PANNE"]
    # Le message **spécifique**, pas le repli générique « au lieu d'une liste » : une assertion
    # jointe par `or` ne distingue pas quelle branche a mordu, et la mutation qui retire la
    # garde de la chaîne la laisse verte. Mesuré — trois fois, sur trois tests différents.
    assert "est une chaîne" in verdicts[0].detail


def test_un_petit_fils_en_boucle_sans_fin_ne_bloque_pas_le_harnais(tmp_path: Path) -> None:
    """Le délai doit porter sur **l'arbre entier**, pas sur l'enfant direct.

    `shell=True` fait de l'enfant direct un interpréteur de commandes : pytest, node ou make
    sont donc **toujours** des petits-fils. `subprocess.run(timeout=…)` ne tue que l'enfant
    direct, puis attend la fermeture des tubes hérités — qu'un petit-fils survivant tient
    ouverts. Mesuré le 2026-10-09 : un petit-fils en boucle sans fin laissait `judge()` bloqué
    bien au-delà du délai, **le fichier muté sur disque pendant tout ce temps**.

    Le test précédent ne l'attrapait pas : `time.sleep(30)` n'a pas d'enfant.
    """
    root = build_repo(tmp_path)
    before = (root / "source.py").read_bytes()
    marker = tmp_path / "le-petit-fils-vit.txt"
    # Le petit-fils **écrit** en boucle : c'est ce qui rend le test décisif. Un test qui
    # n'assérerait que le message et une borne de temps passerait même si la descendance
    # survivait, la grâce bornée rendant PANNE de toute façon.
    # Borné à 20 s : s'il survit, il écrit bien au-delà de la fenêtre d'observation — donc
    # l'assertion le voit —, mais il meurt seul, et une régression de la garde ne laisse pas un
    # processus immortel derrière chaque exécution de la suite.
    (root / "petit_fils.py").write_text(
        "import sys, time, pathlib\n"
        "marque = pathlib.Path(sys.argv[1])\n"
        "fin = time.monotonic() + 20\n"
        "while time.monotonic() < fin:\n"
        "    marque.write_text(str(time.time()))\n"
        "    time.sleep(0.02)\n",
        encoding="utf-8",
    )
    (root / "lanceur.py").write_text(
        "import subprocess, sys\nsubprocess.run([sys.executable, 'petit_fils.py', sys.argv[1]])\n",
        encoding="utf-8",
    )
    (root / ".claude" / "pipeline.config.md").write_text(
        "## Commandes du projet\n\n**Back (`.`)** — v :\n"
        f'- test ciblé   : "{sys.executable}" lanceur.py "{marker}"\n',
        encoding="utf-8",
    )
    started = time.monotonic()

    verdicts = mutation.play(
        root,
        {
            "targets": [],
            "timeout": 3,
            "mutations": [
                {
                    "name": "petit-fils immortel",
                    "file": "source.py",
                    "old": "if n < 0:",
                    "new": "if False:",
                    "expect": ["test_refuse_un_negatif"],
                }
            ],
        },
    )
    elapsed = time.monotonic() - started

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "descendance tués" in verdicts[0].detail
    assert elapsed < 3 + MARGE_SECONDS, f"le délai n'a pas borné l'arbre : {elapsed:.2f} s"
    assert (root / "source.py").read_bytes() == before

    # La preuve que le petit-fils est bien mort : son marqueur cesse de bouger.
    assert marker.exists(), "le petit-fils n'a jamais tourné — le montage ne prouve rien"
    first = marker.read_text(encoding="utf-8")
    time.sleep(1)
    assert marker.read_text(encoding="utf-8") == first, "le petit-fils écrit encore"


def casse_le_tueur_d_arbre(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rend indisponible le tueur d'arbre de **cette** plateforme.

    `taskkill` hors du `PATH` sous Windows, groupe de processus hors de portée ailleurs : les
    deux formes de la même panne. Les deux voies de `terminate_tree` sont donc éprouvées, une
    par plateforme — un test qui n'en couvrirait qu'une passerait pour rien sur l'autre.

    Le remplacement ne délègue rien : `subprocess.run` n'a **qu'un seul** appel dans le harnais,
    celui du tueur d'arbre, donc le neutraliser entier ne masque aucun autre travail. Si un jour
    un second appel apparaît, c'est ce test qui le dira.
    """
    if os.name == "nt":

        def sans_taskkill(*_: Any, **__: Any) -> None:
            raise FileNotFoundError(2, "introuvable", "taskkill")

        monkeypatch.setattr(subprocess, "run", sans_taskkill)
    else:  # pragma: no cover — ce poste est Windows ; la CI emprunte cette branche

        def sans_killpg(*_: Any) -> None:
            raise PermissionError("groupe de processus hors de portée")

        monkeypatch.setattr(os, "killpg", sans_killpg)


def test_un_tueur_d_arbre_indisponible_laisse_la_borne_et_le_lot_intacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un tueur d'arbre absent coûte une descendance survivante, jamais la borne ni le lot.

    Mesuré en relecture : avec un `taskkill` introuvable, l'`OSError` sortait de
    `terminate_tree` — dont le contrat est pourtant de ne jamais lever. Elle sautait le `kill()`
    qui suit, puis le `raise Unusable` qui borne, et la sortie du `with Popen(…)` attendait les
    tubes **sans délai** : un délai de 2 s dépassé de 23 s, et le lot entier abandonné sur une
    trace nue — la classe même que `text_field` et `positive_seconds` ferment.

    Les deux pièces sont éprouvées d'un coup : un verdict rendu prouve que rien n'a levé, et le
    temps écoulé prouve qu'aucune attente n'est restée sans borne. La borne admet ici le second
    recours en entier : le tueur absent, la descendance tient les tubes jusqu'au bout de la
    grâce — c'est le prix voulu, et il est fini.
    """
    root = build_repo(tmp_path)
    before = (root / "source.py").read_bytes()
    (root / ".claude" / "pipeline.config.md").write_text(
        "## Commandes du projet\n\n**Back (`.`)** — v :\n"
        f'- test ciblé   : "{sys.executable}" -c "import time; time.sleep(30)"\n',
        encoding="utf-8",
    )
    casse_le_tueur_d_arbre(monkeypatch)
    started = time.monotonic()

    verdicts = mutation.play(
        root,
        {
            "targets": [],
            "timeout": 2,
            "mutations": [
                {
                    "name": "boucle sans fin, tueur d'arbre absent",
                    "file": "source.py",
                    "old": "if n < 0:",
                    "new": "if False:",
                    "expect": ["test_refuse_un_negatif"],
                }
            ],
        },
    )
    elapsed = time.monotonic() - started

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "délai de 2 s dépassé" in verdicts[0].detail
    assert (root / "source.py").read_bytes() == before
    assert elapsed < 2 + mutation.GRACE_SECONDS + MARGE_SECONDS, (
        f"la borne n'a pas tenu : {elapsed:.2f} s"
    )


def test_terminate_tree_ne_leve_pas_quand_son_tueur_manque(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le contrat de `terminate_tree` — « sans lever » — pris au mot, sur un processus vivant.

    Le test ci-dessus l'éprouve à travers `play` ; celui-ci nomme la fonction, pour que le
    constat se lise à l'endroit du contrat plutôt qu'à travers trois couches.
    """
    casse_le_tueur_d_arbre(monkeypatch)
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # Accepté et ignoré sous Windows (vérifié) ; ailleurs, c'est le groupe que tue le signal.
        start_new_session=True,
    )
    try:
        mutation.terminate_tree(process)
    finally:
        process.kill()
        process.wait(timeout=mutation.GRACE_SECONDS)


def test_un_attendu_absent_du_rapport_mute_est_une_panne_pas_un_vert(tmp_path: Path) -> None:
    """Une mutation qui empêche la **collecte** fait disparaître le test visé du rapport.

    Il n'a alors ni rougi ni tenu : il n'a pas tourné. Mesuré en relecture — il était compté
    « survivant », donc VERT, ce qui condamne un test que personne n'a éprouvé. C'est
    exactement la distinction que `Unusable` existe pour tenir.
    """
    root = build_repo(tmp_path)

    verdicts = mutation.play(
        root,
        spec(
            name="collecte impossible",
            file="source.py",
            old="def positive(n):",
            new="def renommee(n):",
            expect=["test_refuse_un_negatif"],
        ),
    )

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "n'ont pas tourné" in verdicts[0].detail


def test_une_mutation_de_meme_longueur_change_la_date_du_fichier(tmp_path: Path) -> None:
    """Sinon un cache de compilation sert la version témoin, et le verdict est faux.

    `__pycache__` s'invalide sur (date, taille) : une mutation de même longueur écrite dans la
    même seconde ne change ni l'un ni l'autre. Mesuré en **CI Linux** le 2026-10-09 — deux
    mutations de longueur identique rendaient VERT un test qui tient. Invisible sur le poste
    Windows, dont l'horodatage de fichier est plus fin : c'est une règle sensible à la
    plateforme, inscrite comme telle dans `pipeline.config.md`.
    """
    cible = tmp_path / "source.py"
    cible.write_bytes(b"if n < 0:")
    avant = cible.stat()

    mutation.rewrite(cible, b"if False:", avant.st_mtime + 1)
    apres = cible.stat()

    assert apres.st_size == avant.st_size, "le montage ne vaut que pour une longueur identique"
    assert apres.st_mtime != avant.st_mtime


def test_le_vocabulaire_des_etats_qui_nont_pas_tourne_couvre_les_trois_rapporteurs() -> None:
    """Le dénombrement de `NOT_RUN`, éprouvé sur les rapports des trois lanceurs.

    Le constat est né sur un `skipped` de pytest ; le fermer là aurait laissé Vitest rendre
    VERT sur un `todo`. Les trois vocabulaires sont donc lus dans un rapport de chaque
    rapporteur : **JUnit `skipped`, Vitest `skipped` et `todo`, Playwright `skipped`** — et le
    `pending` de Jest, qu'aucun des trois n'émet, reste dehors.
    """
    junit = mutation.REPORTERS["junit"].outcomes(
        '<testsuites><testsuite><testcase classname="m" name="saute">'
        '<skipped message="x"/></testcase></testsuite></testsuites>'
    )
    vitest = mutation.REPORTERS["vitest"].outcomes(VITEST_NOT_RUN_REPORT)
    playwright = mutation.REPORTERS["playwright"].outcomes(
        '{"suites": [{"title": "s.spec.ts", "specs": [{"title": "saute", "ok": true, '
        '"tests": [{"status": "skipped", "results": [{"status": "skipped"}]}]}]}]}'
    )

    assert junit == {"m::saute": "skipped"}
    assert set(vitest.values()) == {"passed", "skipped", "todo"}
    assert playwright == {"s.spec.ts > saute": "skipped"}
    assert {state for state in vitest.values() if state != "passed"} <= mutation.NOT_RUN
    assert "skipped" in mutation.NOT_RUN and "pending" not in mutation.NOT_RUN


class _VerdictAvecFleche:
    """Un verdict factice dont le texte porte un caractère hors cp1252, comme un vrai nom."""

    verdict = "ROUGE"

    def __str__(self) -> str:
        return "ROUGE  flèche → absente : rouges : ['test_x']"


def test_les_verdicts_s_impriment_sur_une_console_cp1252(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mesuré à la relance de la PR #86 : une mutation nommée avec `→`, console cp1252 →
    `UnicodeEncodeError` au premier `print(verdict)`, **après** que toutes les mutations ont tourné
    — fichiers restaurés, mais tous les verdicts perdus. Ce dépôt a 279 identifiants de test
    accentués (journal de spec de #77, 2026-10-12) ; les accents passent en cp1252, les flèches
    et les emojis non.

    Le mécanisme est rejoué en processus : `sys.stdout` est un flux texte encodé en cp1252 sur un
    tampon d'octets, et `play()` rend un verdict dont le texte porte `→`. Le harnais doit écrire
    ses verdicts en octets UTF-8 sur le tampon, sans dépendre de l'encodage de la couche texte.
    """
    spec = tmp_path / "mutations.json"
    spec.write_text("{}", encoding="utf-8")
    tampon = io.BytesIO()

    def play_factice(_racine: Path, _spec: object) -> list[_VerdictAvecFleche]:
        return [_VerdictAvecFleche()]

    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(tampon, encoding="cp1252"))
    monkeypatch.setattr(mutation, "play", play_factice)

    code = mutation.main([str(tmp_path), str(spec)])

    assert code == 0
    assert "flèche → absente" in tampon.getvalue().decode("utf-8")
