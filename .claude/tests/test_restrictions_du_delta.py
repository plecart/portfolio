"""Tests de la passe « restrictions du delta »
(`.claude/skills/cycle-pr/scripts/restrictions-du-delta.py`).

Chaque cas bâtit un dépôt jetable dans `tmp_path` — la table de configuration en partage un, bâti
une fois par module —, la configuration git du poste écartée (`isole_git`), y commite une base
puis un delta, et lance le script sur `HEAD~1` par un tube, comme la session le lit
(`run_in_pipe`). Les marques et les clôtures de bloc de code se lisent sans dépôt.

Le cas d'origine est la mutation M5 de l'étude du 2026-11-04
(`docs/etudes/2026-11-04-etude-tests-de-la-pipeline.md` §2.4) : une moitié restrictive retirée de
`CLAUDE.md`, que la suite des phrases figées laissait verte. Les cas s'écrivent en littéraux,
jamais dérivés des constantes du script (`cycle-pr/references/tests.md`, « Le rouge se constate,
il ne se suppose pas »).
"""

from pathlib import Path

import pytest
from conftest import git_temoin, isole_git, load_script, run_in_pipe

restrictions = load_script("cycle-pr", "restrictions-du-delta")

# Chemin → lignes du fichier.
Fichiers = dict[str, tuple[str, ...]]


def commite(fichiers: Fichiers) -> None:
    """Écrit `fichiers` dans le dossier courant, fins de ligne LF, et les commite."""
    for nom, lignes in fichiers.items():
        chemin = Path(nom)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes("".join(f"{ligne}\n" for ligne in lignes).encode())
    git_temoin("add", "--all")
    git_temoin("commit", "-qm", "commit")


def lance(base: str = "HEAD~1") -> tuple[int, list[str]]:
    """La passe sur `base` depuis le dossier courant : son code de sortie et ses lignes, lues en
    UTF-8 — un script qui écrirait le tube en cp1252 y rougit."""
    done = run_in_pipe("cycle-pr", "restrictions-du-delta", base)
    return done.returncode, done.stdout.decode("utf-8").splitlines()


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Un dépôt vide, dossier courant du test."""
    isole_git(monkeypatch)
    monkeypatch.chdir(tmp_path)
    git_temoin("init", "-q", "-b", "main")


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


# Le dépôt de la table de configuration : un fichier par effet, chacun rendant une ligne que la
# clé qui le vise change sans son option (mesuré le 2026-11-04, git 2.47.1).
CONFIGURATION_TETE = ("# Pipeline", "", "## Observation continue (`task-observer`)", "")
CONFIGURATION_RENOMME = ("# T", "Seul B.", "Ligne un.", "Ligne deux.")
CONFIGURATION_BASE: Fichiers = {
    # Deux retraits proches, puis un retrait dans le fichier suivant : sous
    # `diff.interHunkContext`, les deux blocs fusionnent autour de leur ligne de contexte, que le
    # compte du bloc ne décompte pas, et ce compte déborde sur l'en-tête du fichier suivant.
    "CLAUDE.md": (*CONFIGURATION_TETE, "**Ne jamais interrompre.**", "Une ligne.", "Sans revue."),
    "CONTRIBUTING.md": ("## Démarrer", "Seul le mainteneur merge."),
    # `diff.algorithm=patience` garde « Sans B. » et retire les « y ».
    ".claude/algorithme.md": ("Sans B.", "  y", "  y"),
    # Sans l'heuristique d'indentation, le bloc retiré glisse sous « ## S ».
    ".claude/indentation.md": ("Ne jamais A.", "  y", "## S", "Ne jamais A.", ""),
    # Deux fichiers renommés et retouchés : lus comme des suppressions — `diff.renames=false`, ou
    # deux renommages au-delà de `diff.renameLimit=1` —, ils rendraient aussi « Seul B. » et
    # « Aucun C. », que le delta garde.
    ".claude/a.md": (*CONFIGURATION_RENOMME, "Ne jamais A."),
    ".claude/c.md": ("# U", "Aucun C.", "Ligne trois.", "Ligne quatre.", "Ne jamais D."),
}
CONFIGURATION_DELTA: Fichiers = {
    "CLAUDE.md": (*CONFIGURATION_TETE, "**Interrompre rarement.**", "Une ligne.", "Avec revue."),
    "CONTRIBUTING.md": ("## Démarrer", "Le mainteneur merge."),
    ".claude/algorithme.md": ("  y", "Sans B."),
    ".claude/indentation.md": ("Ne jamais A.", ""),
    ".claude/b.md": (*CONFIGURATION_RENOMME, "Rarement A."),
    ".claude/d.md": ("# U", "Aucun C.", "Ligne trois.", "Ligne quatre.", "Rarement D."),
    # Une copie retouchée de `CLAUDE.md` : sous `diff.renames=copies`, elle se diffe contre lui,
    # et la restriction qu'il retire se rend deux fois.
    ".claude/copie.md": (*CONFIGURATION_TETE, "**Rarement.**", "Une ligne.", "Sans revue."),
}
CONFIGURATION_LIGNES = [
    ".claude/algorithme.md § — : Sans B.",
    ".claude/a.md § T : Ne jamais A.",
    ".claude/c.md § U : Ne jamais D.",
    ".claude/indentation.md § — : Ne jamais A.",
    "CLAUDE.md § Observation continue (`task-observer`) : **Ne jamais interrompre.**",
    "CLAUDE.md § Observation continue (`task-observer`) : Sans revue.",
    "CONTRIBUTING.md § Démarrer : Seul le mainteneur merge.",
]
# Les fichiers d'attributs que `core.attributesFile` désigne, rangés dans le `.git` du dépôt.
ATTRIBUTS = {"pilote": "* diff=p\n", "binaire": "* binary\n"}

# Une ligne par clé que la docstring du script dit neutralisée par une option, avec la valeur qui
# change la sortie sans elle ; `{pilote}` et `{binaire}` valent les fichiers d'`ATTRIBUTS`.
CONFIGURATIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "sans-configuration": (),
    "couleur-forcee": (("color.ui", "always"),),
    "couleur-du-diff": (("color.diff", "always"),),
    # `git` sort en 128 : le diff externe échoue.
    "diff-externe": (("diff.external", "false"),),
    "pilote-externe": (("core.attributesFile", "{pilote}"), ("diff.p.command", "false")),
    "conversion-de-texte": (
        ("core.attributesFile", "{pilote}"),
        ("diff.p.textconv", "sed s/jamais/souvent/"),
    ),
    # Un fichier lu binaire ne rend aucune ligne.
    "pilote-binaire": (("core.attributesFile", "{pilote}"), ("diff.p.binary", "true")),
    "attribut-binaire": (("core.attributesFile", "{binaire}"),),
    "seuil-des-gros-fichiers": (("core.bigFileThreshold", "1"),),
    # Lancée depuis un sous-dossier, la passe n'y verrait que lui.
    "diff-relatif": (("diff.relative", "true"),),
    "contexte-entre-blocs": (("diff.interHunkContext", "3"),),
    "renommages-coupes": (("diff.renames", "false"),),
    "copies-cherchees": (("diff.renames", "copies"),),
    "limite-de-renommage": (("diff.renameLimit", "1"),),
    "algorithme-patience": (("diff.algorithm", "patience"),),
    "sans-heuristique-d-indentation": (("diff.indentHeuristic", "false"),),
}


@pytest.fixture(scope="module")
def depot_de_configuration(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Le dépôt de la table de configuration, bâti une fois : chaque ligne n'y change que
    l'environnement de la passe, jamais le dépôt."""
    racine = tmp_path_factory.mktemp("configuration")
    with pytest.MonkeyPatch.context() as monkeypatch:
        isole_git(monkeypatch)
        monkeypatch.chdir(racine)
        git_temoin("init", "-q", "-b", "main")
        commite(CONFIGURATION_BASE)
        for renomme in (".claude/a.md", ".claude/c.md"):
            Path(renomme).unlink()
        commite(CONFIGURATION_DELTA)
    (racine / "apps").mkdir()
    for nom, contenu in ATTRIBUTS.items():
        (racine / ".git" / nom).write_text(contenu, encoding="utf-8")
    return racine


@pytest.mark.parametrize("cles", CONFIGURATIONS.values(), ids=CONFIGURATIONS.keys())
def test_la_configuration_git_ne_change_pas_les_lignes_rendues(
    cles: tuple[tuple[str, str], ...],
    depot_de_configuration: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chaque clé que la docstring du script neutralise par une option change la sortie sans elle
    (mesuré le 2026-11-04, git 2.47.1) ; le témoin sans configuration rend les mêmes lignes. La
    clé passe par `GIT_CONFIG_COUNT`, que `git` ajoute à sa configuration, au-dessus des fichiers
    (`git-config`, « ENVIRONMENT ») ; la passe part d'un sous-dossier, que `diff.relative`
    borne."""
    isole_git(monkeypatch)
    fichiers = {nom: str(depot_de_configuration / ".git" / nom) for nom in ATTRIBUTS}
    monkeypatch.setenv("GIT_CONFIG_COUNT", str(len(cles)))
    for rang, (cle, valeur) in enumerate(cles):
        monkeypatch.setenv(f"GIT_CONFIG_KEY_{rang}", cle)
        monkeypatch.setenv(f"GIT_CONFIG_VALUE_{rang}", valeur.format(**fichiers))
    monkeypatch.chdir(depot_de_configuration / "apps")

    assert lance() == (0, CONFIGURATION_LIGNES)


def test_l_environnement_git_diff_opts_ne_change_pas_les_lignes_rendues(
    depot_de_configuration: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`GIT_DIFF_OPTS=--unified=3` passe devant `-U0` (mesuré le 2026-11-04, git 2.47.1) : ses
    lignes de contexte fusionnent les blocs voisins, comme `diff.interHunkContext`."""
    isole_git(monkeypatch)
    monkeypatch.setenv("GIT_DIFF_OPTS", "--unified=3")
    monkeypatch.chdir(depot_de_configuration)

    assert lance() == (0, CONFIGURATION_LIGNES)


@pytest.mark.usefixtures("depot")
def test_une_base_qui_a_avance_se_lit_depuis_le_point_de_depart_commun() -> None:
    """`<base>...HEAD` part de `git merge-base <base> HEAD` : `main` a avancé depuis — une section
    insérée au-dessus de la ligne, une restriction ajoutée — sans que ni sa section ni son ajout
    n'entrent dans la passe de `pr`."""
    commite({"CLAUDE.md": ("## Avant", "Ne jamais A.")})
    git_temoin("checkout", "-q", "-b", "pr")
    commite({"CLAUDE.md": ("## Avant", "Rarement A.")})
    git_temoin("checkout", "-q", "main")
    commite({"CLAUDE.md": ("## Insérée", "## Avant", "Ne jamais A.", "Seul B.")})
    git_temoin("checkout", "-q", "pr")

    assert lance("main") == (0, ["CLAUDE.md § Avant : Ne jamais A."])


@pytest.mark.usefixtures("depot")
def test_une_base_inconnue_sort_en_2_avec_le_motif_de_git_sur_la_sortie_d_erreur() -> None:
    """`git` en échec : rien sur la sortie standard, le motif sur la sortie d'erreur."""
    commite(M5_BASE)

    done = run_in_pipe("cycle-pr", "restrictions-du-delta", "inconnue")

    assert (done.returncode, done.stdout) == (2, b"")
    assert b"inconnue" in done.stderr


# Chaque forme de marque seule dans sa phrase — une par marque et par flexion en genre et en
# nombre, la règle de fin de mot refusant toute autre forme —, puis un mot qui en contient une
# sans l'être.
FORMES_DE_MARQUE = {
    "jamais": ("Jamais d'auto-merge.", True),
    "toujours": ("Toujours un brief.", True),
    "seul": ("Le seul cas.", True),
    "seule": ("Une seule voie.", True),
    "seuls": ("Les seuls cas.", True),
    "seules": ("Les seules voies.", True),
    "seulement": ("Seulement sur verdict vert.", True),
    "uniquement": ("Uniquement sur verdict vert.", True),
    "reste-a": ("La décision reste à la session.", True),
    "restent-a": ("Les décisions restent à la session.", True),
    "ne": ("On ne merge pas.", True),
    "n-apostrophe": ("Il n'existe pas.", True),
    "ni": ("Ni push, ni force.", True),
    "pas-nominal": ("Pas de proposition de revue.", True),
    "sans": ("Sans exception.", True),
    "aucun": ("Aucun commit cassé.", True),
    "aucune": ("Aucune issue.", True),
    "aucuns": ("Aucuns frais.", True),
    "aucunes": ("Aucunes données.", True),
    "interdit": ("Le force-push est interdit.", True),
    "interdite": ("Une écriture interdite.", True),
    "interdits": ("Des pushs interdits.", True),
    "interdites": ("Des écritures interdites.", True),
    "ne-en-fin-de-mot": ("Une donnée.", False),
    "ni-en-tete-de-mot": ("Un nid.", False),
    "pas-en-tete-de-mot": ("Il passe.", False),
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


# Une clôture de bloc de code (CommonMark 0.31.2, §4.5) : même caractère que l'ouvrante, au moins
# aussi longue, suivie de blancs seuls ; une ouvrante à accents graves n'en porte pas dans son
# info. Chaque cas : les lignes, et la section de la dernière.
CLOTURES = {
    "accents-graves-dans-un-bloc-tilde": (
        ("# Avant", "~~~", "```", "# Dedans", "~~~", "x"),
        "Avant",
    ),
    "cloture-plus-courte": (("# Avant", "````", "```", "# Dedans", "````", "x"), "Avant"),
    "cloture-suivie-d-un-texte": (("# Avant", "```", "```bash", "# Dedans", "```", "x"), "Avant"),
    "accent-grave-dans-l-info": (("# Avant", "```a`b", "# Après", "x"), "Après"),
    "cloture-plus-longue": (("# Avant", "~~~", "# Dedans", "~~~~", "# Après", "x"), "Après"),
}


@pytest.mark.parametrize(("lignes", "attendue"), CLOTURES.values(), ids=CLOTURES.keys())
def test_un_bloc_de_code_ne_se_ferme_que_sur_une_cloture_de_son_caractere(
    lignes: tuple[str, ...], attendue: str
) -> None:
    """Un titre dans un bloc de code n'est pas une section : la clôture qui le ferme à tort fait
    lire comme titre ce qui le suit, et le témoin d'une clôture plus longue garde l'autre côté."""
    assert restrictions.section(lignes, len(lignes)) == attendue
