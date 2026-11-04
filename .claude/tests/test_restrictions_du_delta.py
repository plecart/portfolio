"""Tests de la passe « restrictions du delta »
(`.claude/skills/cycle-pr/scripts/restrictions-du-delta.py`).

Chaque cas bâtit un dépôt jetable dans `tmp_path`, la configuration git du poste écartée
(`GIT_CONFIG_GLOBAL` vers un fichier vide, `GIT_CONFIG_NOSYSTEM=1` : `cleanup-verbatim.md`,
« Comment l'appliquer »), y commite une base puis un delta, et lance le script sur `HEAD~1` par un
tube, comme la session le lit (`run_in_pipe`). Le cas d'origine est la mutation M5 de l'étude du
2026-11-04 (`docs/etudes/2026-11-04-etude-tests-de-la-pipeline.md` §2.4) : une moitié restrictive
retirée de `CLAUDE.md`, que la suite des phrases figées laissait verte. Les cas s'écrivent en
littéraux, jamais dérivés des constantes du script (`cycle-pr/references/tests.md`, « Le rouge se
constate, il ne se suppose pas »).
"""

import os
import subprocess
from pathlib import Path

import pytest
from conftest import load_script, run_in_pipe

restrictions = load_script("cycle-pr", "restrictions-du-delta")

# Chemin → lignes du fichier.
Fichiers = dict[str, tuple[str, ...]]


def git(*args: str) -> None:
    """`git <args>` dans le dossier courant ; une erreur lève : le dépôt témoin se construit, il ne
    se mesure pas."""
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], capture_output=True, check=True
    )


def commite(fichiers: Fichiers) -> None:
    """Écrit `fichiers` dans le dossier courant, fins de ligne LF, et les commite."""
    for nom, lignes in fichiers.items():
        chemin = Path(nom)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes("".join(f"{ligne}\n" for ligne in lignes).encode())
    git("add", "--all")
    git("commit", "-qm", "commit")


def lance(base: str = "HEAD~1") -> tuple[int, list[str]]:
    """La passe sur `base` depuis le dossier courant : son code de sortie et ses lignes, lues en
    UTF-8 — un script qui écrirait le tube en cp1252 y rougit."""
    done = run_in_pipe("cycle-pr", "restrictions-du-delta", base)
    return done.returncode, done.stdout.decode("utf-8").splitlines()


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un dépôt vide, dossier courant du test."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(tmp_path)
    git("init", "-q", "-b", "main")


M5_TETE = ("# Pipeline de développement", "", "## Observation continue (`task-observer`)", "")
M5_BASE: Fichiers = {
    "CLAUDE.md": (
        *M5_TETE,
        "**Ne jamais interrompre pour le journal.** Pas de proposition de revue spontanée.",
    )
}
M5_DELTA: Fichiers = {
    "CLAUDE.md": (
        *M5_TETE,
        "**Interrompre rarement pour le journal.** Pas de proposition de revue spontanée.",
    )
}
M5_LIGNE = (
    "CLAUDE.md § Observation continue (`task-observer`) : **Ne jamais interrompre pour le"
    " journal.** Pas de proposition de revue spontanée."
)


@pytest.mark.usefixtures("depot")
def test_une_restriction_retiree_de_claude_md_se_rend_avec_son_fichier_et_sa_section() -> None:
    """La mutation M5 de l'étude, §2.4 : « Ne jamais interrompre pour le journal » devenu
    « Interrompre rarement pour le journal » rend une ligne, code 0."""
    commite(M5_BASE)
    commite(M5_DELTA)

    assert lance() == (0, [M5_LIGNE])


BLOC_DE_CODE = ("## Étape", "", "```bash", "# un commentaire", "git status", "```", "")

# Une ligne marquée retirée, et la ligne que la passe en rend. « section-de-la-base » : le delta
# insère une section plus haut et renomme celle de la ligne — son numéro et son titre diffèrent
# donc entre la base et la tête, et une section suit dans la base.
LIGNES_RENDUES: dict[str, tuple[Fichiers, Fichiers, list[str]]] = {
    "section-de-la-base": (
        {
            ".claude/rules/r.md": (
                "# Règle",
                "Intro.",
                "## Avant",
                "Ne jamais A.",
                "## Fin",
                "Fin.",
            )
        },
        {
            ".claude/rules/r.md": (
                "# Règle",
                "## Ajoutée",
                "Texte.",
                "Intro.",
                "## Après",
                "Rarement A.",
                "## Fin",
                "Fin.",
            )
        },
        [".claude/rules/r.md § Avant : Ne jamais A."],
    ),
    "commentaire-d-un-bloc-de-code": (
        {".claude/skills/s/SKILL.md": (*BLOC_DE_CODE, "Sans exception.")},
        {".claude/skills/s/SKILL.md": (*BLOC_DE_CODE, "Avec exceptions.")},
        [".claude/skills/s/SKILL.md § Étape : Sans exception."],
    ),
    "sans-titre-au-dessus": (
        {"CONTRIBUTING.md": ("Aucun titre ici.",)},
        {"CONTRIBUTING.md": ("Un titre ici.",)},
        ["CONTRIBUTING.md § — : Aucun titre ici."],
    ),
    "ligne-qui-commence-par-deux-tirets": (
        {"CLAUDE.md": ("# T", "-- Ne jamais X.")},
        {"CLAUDE.md": ("# T", "Rarement X.")},
        ["CLAUDE.md § T : -- Ne jamais X."],
    ),
    "chemin-a-espace-et-accent": (
        {".claude/a b/règle.md": ("# T", "Seul le lead.")},
        {".claude/a b/règle.md": ("# T", "Le lead.")},
        [".claude/a b/règle.md § T : Seul le lead."],
    ),
}


@pytest.mark.usefixtures("depot")
@pytest.mark.parametrize(
    ("base", "delta", "attendu"), LIGNES_RENDUES.values(), ids=LIGNES_RENDUES.keys()
)
def test_une_ligne_marquee_retiree_se_rend_sous_sa_section_de_la_base(
    base: Fichiers, delta: Fichiers, attendu: list[str]
) -> None:
    """La section est le dernier titre au-dessus de la ligne dans la base, hors des blocs de code,
    `—` sans titre ; une ligne retirée qui commence par `-- ` se lit `--- `, comme un en-tête de
    fichier ; le chemin se lit tel quel, espace et accent compris."""
    commite(base)
    commite(delta)

    assert lance() == (0, attendu)


# Le témoin de l'autre côté : un delta qui ne retire aucune ligne marquée d'un fichier normatif.
SANS_RESTRICTION_RETIREE: dict[str, tuple[Fichiers, Fichiers]] = {
    "restriction-ajoutee": (
        {"CLAUDE.md": ("## S", "Une règle.")},
        {"CLAUDE.md": ("## S", "Une règle.", "Ne jamais B.")},
    ),
    "ligne-sans-marque-modifiee": (
        {"CLAUDE.md": ("## S", "Une règle suit les ADR.")},
        {"CLAUDE.md": ("## S", "Une règle respecte les ADR.")},
    ),
    "hors-des-fichiers-normatifs": (
        {"docs/regle.md": ("## S", "Ne jamais A."), ".claude/notes.txt": ("Ne jamais A.",)},
        {"docs/regle.md": ("## S", "Rarement A."), ".claude/notes.txt": ("Rarement A.",)},
    ),
}


@pytest.mark.usefixtures("depot")
@pytest.mark.parametrize(
    ("base", "delta"), SANS_RESTRICTION_RETIREE.values(), ids=SANS_RESTRICTION_RETIREE.keys()
)
def test_un_delta_sans_restriction_retiree_rend_une_sortie_vide(
    base: Fichiers, delta: Fichiers
) -> None:
    """Une marque ajoutée, une ligne modifiée sans marque — « Une » ne porte pas « ne » —, une
    ligne marquée retirée hors de `.claude/**/*.md`, `CLAUDE.md` et `CONTRIBUTING.md` : rien."""
    commite(base)
    commite(delta)

    assert lance() == (0, [])


@pytest.mark.usefixtures("depot")
@pytest.mark.parametrize(
    ("cle", "valeur"),
    [("color.ui", "always"), ("diff.external", "false"), ("diff.relative", "true")],
    ids=["couleur-forcee", "diff-externe", "diff-relatif"],
)
def test_la_configuration_git_du_depot_ne_change_pas_la_ligne_rendue(
    cle: str, valeur: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Trois clés qui changent ce que `git diff` rend (mesuré le 2026-11-04, git 2.47.1) : la
    couleur forcée préfixe chaque ligne d'un échappement, un diff externe qui échoue fait sortir
    `git` en 128, un diff relatif le borne au dossier courant — d'où la passe lancée depuis un
    sous-dossier."""
    commite(M5_BASE)
    commite(M5_DELTA)
    git("config", cle, valeur)
    Path("apps").mkdir()
    monkeypatch.chdir("apps")

    assert lance() == (0, [M5_LIGNE])


@pytest.mark.usefixtures("depot")
def test_une_base_qui_a_avance_se_lit_depuis_le_point_de_depart_commun() -> None:
    """`<base>...HEAD` part de `git merge-base <base> HEAD` : `main` a avancé depuis — une section
    insérée au-dessus de la ligne, une restriction ajoutée — sans que ni sa section ni son ajout
    n'entrent dans la passe de `pr`."""
    commite({"CLAUDE.md": ("## Avant", "Ne jamais A.")})
    git("checkout", "-q", "-b", "pr")
    commite({"CLAUDE.md": ("## Avant", "Rarement A.")})
    git("checkout", "-q", "main")
    commite({"CLAUDE.md": ("## Insérée", "## Avant", "Ne jamais A.", "Seul B.")})
    git("checkout", "-q", "pr")

    assert lance("main") == (0, ["CLAUDE.md § Avant : Ne jamais A."])


@pytest.mark.usefixtures("depot")
def test_un_fichier_renomme_se_lit_sous_son_chemin_de_la_base() -> None:
    """Renommé et retouché, le fichier se diffe contre son ancien chemin : seule la ligne retouchée
    est retirée — lu comme une suppression, il rendrait aussi « Seul B. », que le delta garde. Sous
    `diff.renames=false` : sans elle, `git diff` suit déjà les renommages, et la mutation qui retire
    `--find-renames` restait verte (mesuré le 2026-11-04, git 2.47.1)."""
    lignes = ("# T", "Seul B.", "Ligne un.", "Ligne deux.")
    commite({".claude/a.md": (*lignes, "Ne jamais A.")})
    git("mv", ".claude/a.md", ".claude/b.md")
    commite({".claude/b.md": (*lignes, "Rarement A.")})
    git("config", "diff.renames", "false")

    assert lance() == (0, [".claude/a.md § T : Ne jamais A."])


@pytest.mark.usefixtures("depot")
def test_une_base_inconnue_sort_en_2_avec_le_motif_de_git_sur_la_sortie_d_erreur() -> None:
    """`git` en échec : rien sur la sortie standard, le motif sur la sortie d'erreur."""
    commite(M5_BASE)

    done = run_in_pipe("cycle-pr", "restrictions-du-delta", "inconnue")

    assert (done.returncode, done.stdout) == (2, b"")
    assert b"inconnue" in done.stderr


# Chaque marque seule dans sa phrase, puis un mot qui en contient une sans l'être.
FORMES_DE_MARQUE = {
    "jamais": ("Jamais d'auto-merge.", True),
    "seule": ("Une seule voie.", True),
    "seul": ("Le seul cas.", True),
    "seulement": ("Seulement sur verdict vert.", True),
    "reste-a": ("La décision reste à la session.", True),
    "ne": ("On ne merge pas.", True),
    "n-apostrophe": ("Il n'existe pas.", True),
    "ni": ("Ni push, ni force.", True),
    "sans": ("Sans exception.", True),
    "aucun": ("Aucun commit cassé.", True),
    "aucune": ("Aucune issue.", True),
    "ne-en-fin-de-mot": ("Une donnée.", False),
    "ni-en-tete-de-mot": ("Un nid.", False),
    "aucun-en-tete-de-mot": ("Aucunement.", False),
    "reste-sans-a": ("Il reste du texte.", False),
}


@pytest.mark.parametrize(
    ("texte", "marquee"), FORMES_DE_MARQUE.values(), ids=FORMES_DE_MARQUE.keys()
)
def test_une_marque_restrictive_se_reconnait_en_mot_entier_sans_la_casse(
    texte: str, marquee: bool
) -> None:
    """Le témoin des deux côtés de `MARQUE_RESTRICTIVE`, sans dépôt."""
    assert bool(restrictions.MARQUE_RESTRICTIVE.search(texte)) is marquee
