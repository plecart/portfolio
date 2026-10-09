"""Tests du harnais de mutation `.claude/skills/cycle-pr/scripts/mutation.py`.

Le harnais est la preuve que les tests d'une PR *tiennent* : il casse ce qu'un test protège et
exige de le voir rougir. Un harnais qui se trompe mente toujours dans le même sens — il rend vert
un test jamais vu rouge (obs 37, deux défauts mesurés sur sept réécritures). D'où cette suite :
c'est la seule porte qui éprouve son comportement, `pyright` n'atteignant pas les dossiers cachés.
"""

import sys
from pathlib import Path

import pytest
from skill_scripts import load_script

mutation = load_script("cycle-pr", "mutation")

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
    assert "aucun rouge attendu" in verdicts[0].detail


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
    """
    root = build_repo(tmp_path)
    before = (root / "source.py").read_bytes()
    (root / ".claude" / "pipeline.config.md").write_text(
        "## Commandes du projet\n\n**Back (`.`)** — v :\n"
        f'- test ciblé   : "{sys.executable}" -c "import time; time.sleep(30)"\n',
        encoding="utf-8",
    )

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

    assert [v.verdict for v in verdicts] == ["PANNE"]
    assert "délai de 2 s dépassé" in verdicts[0].detail
    assert (root / "source.py").read_bytes() == before


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
    assert "aucune mutation" in verdicts[0].detail


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
