"""Tests de la sonde d'outillage (`.claude/skills/cycle-pr/scripts/sonde-outillage.py`).

La sonde éprouve, avant le briefing (`cycle-pr` Étape 1, « Éprouver les outils d'abord »), chaque
outil dont le cycle dépend, jusqu'à une écriture. Elle parle à `git`, à `gh` et aux commandes du
projet par une seule fonction, `run`, que ces tests remplacent par un poste témoin : une tête de
dépôt que le commit et le reset déplacent, un arbre propre ou sale, et des outils qui ne
répondent qu'à la **commande complète** attendue — toute autre lève (modèle :
`test_merge_lot.py`). Les commandes s'écrivent en littéraux, jamais dérivées des constantes du
script (`cycle-pr` 3.1, « la table de cas est dérivée de l'artefact sous test »). Les sondes `git`
se rejouent aussi sur un vrai dépôt jetable, et le lanceur par défaut, que le poste témoin
remplace partout ailleurs, sur un vrai processus.
"""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from conftest import load_script, run_in_pipe

sonde = load_script("cycle-pr", "sonde-outillage")

TETE = "a" * 40
SONDE = "c" * 40

# Les commandes que le script doit lancer pour `OPTIONS`, dans l'ordre.
STATUS = ("git", "status", "--porcelain", "--untracked-files=normal")
AUTH = ("gh", "auth", "status", "--active")
PUSH = ("gh", "api", "repos/{owner}/{repo}", "--jq", ".permissions.push")
HEAD = ("git", "rev-parse", "HEAD")
COMMIT = ("git", "commit", "--allow-empty", "-m", "chore: sonde outillage")
RESET = ("git", "reset", "--soft", "HEAD~1")
FORMAT = ("make", "format")
TEST = ("uv", "run", "pytest", "-k", "not lent")
OPTIONS = ("--format", "make format", "--test", 'uv run pytest -k "not lent"')
ORDRE = [STATUS, AUTH, PUSH, HEAD, COMMIT, HEAD, RESET, HEAD, FORMAT, STATUS, TEST]
NOMS = ["arbre propre", "gh auth status", "droit de push", "commit de sonde", "format", "test"]

Reponse = subprocess.CompletedProcess[str] | OSError


def fini(code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    """Un processus terminé, sorties décodées, tel que le lanceur par défaut le rend."""
    return subprocess.CompletedProcess([], code, stdout=out, stderr=err)


class Poste:
    """Un poste témoin : un dépôt réduit à sa tête et à son arbre, et des outils qui ne répondent
    qu'à la commande complète attendue — toute autre lève.

    Le commit place la tête sur le commit de sonde, le reset la ramène, le format laisse l'arbre
    dans l'état `apres_format`. Chaque cas en change une chose.

    Args:
        sale: ce que `git status --porcelain` rend avant le format.
        apres_format: ce qu'il rend une fois le format passé.
        reset_sans_effet: le reset rend 0 sans ramener la tête.
        tete_illisible_apres_le_commit: la tête ne se lit plus une fois le commit de sonde en place.
        pannes: commande → la réponse qui remplace la nominale, sans effet sur le dépôt ; une
            exception y est levée, comme un programme introuvable.
    """

    def __init__(
        self,
        *,
        sale: str = "",
        apres_format: str = "",
        reset_sans_effet: bool = False,
        tete_illisible_apres_le_commit: bool = False,
        pannes: dict[tuple[str, ...], Reponse] | None = None,
    ) -> None:
        self.tete = TETE
        self.arbre = sale
        self.apres_format = apres_format
        self.reset_sans_effet = reset_sans_effet
        self.tete_illisible_apres_le_commit = tete_illisible_apres_le_commit
        self.pannes = pannes or {}
        self.appels: list[tuple[str, ...]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
        cmd = tuple(cmd)
        self.appels.append(cmd)
        if cmd in self.pannes:
            panne = self.pannes[cmd]
            if isinstance(panne, OSError):
                raise panne
            return panne
        if cmd == STATUS:
            return fini(out=self.arbre)
        if cmd == HEAD:
            if self.tete_illisible_apres_le_commit and self.tete == SONDE:
                return fini(128, err="fatal: bad revision 'HEAD'\n")
            return fini(out=f"{self.tete}\n")
        if cmd == COMMIT:
            self.tete = SONDE
            return fini(out="[feat/x ccccccc] chore: sonde outillage\n")
        if cmd == RESET:
            if not self.reset_sans_effet:
                self.tete = TETE
            return fini()
        if cmd == FORMAT:
            self.arbre = self.apres_format
            return fini(out="12 files left unchanged\n")
        if cmd == PUSH:
            return fini(out="true\n")
        if cmd in (AUTH, TEST):
            return fini()
        raise AssertionError(f"commande inattendue : {cmd}")


def lance(poste: Poste, *args: str) -> int:
    """Le script tel que la session l'appelle."""
    return sonde.main(list(args), run=poste)


def test_un_poste_en_etat_passe_les_six_sondes_dans_l_ordre(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Le témoin positif, et l'ordre : du moins cher au plus cher, la tête relue avant, entre et
    après l'écriture, l'arbre relu après le format. Sans lui, le KO de la première sonde pourrait
    venir d'un script qui échoue sur tout."""
    poste = Poste()

    assert lance(poste, *OPTIONS) == 0
    assert poste.appels == ORDRE
    assert capsys.readouterr().out.splitlines() == [f"OK   {nom}" for nom in NOMS]


# Un cas par garde : chacun change une seule chose à un poste en état, et nomme la sonde qui doit
# rendre KO, le nombre de commandes lancées — la fautive est la dernière, aucune ne la suit — et
# ce que la sortie doit en dire.
KO: dict[str, tuple[dict[str, Any], int, int, tuple[str, ...]]] = {
    "arbre-sale": ({"sale": "?? jetable.txt\n"}, 0, 1, ("pas propre", "?? jetable.txt")),
    "gh-non-authentifie": (
        {"pannes": {AUTH: fini(1, err="You are not logged into any GitHub hosts.\n")}},
        1,
        2,
        ("`gh auth status --active` a échoué (1)", "You are not logged into any GitHub hosts."),
    ),
    "push-refuse": ({"pannes": {PUSH: fini(out="false\n")}}, 2, 3, ("rend 'false'",)),
    # `gh api --jq` rend `null` quand le champ manque : seul `true` passe, pas tout sauf `false`.
    "push-absent": ({"pannes": {PUSH: fini(out="null\n")}}, 2, 3, ("rend 'null', pas 'true'",)),
    # Un dépôt sans commit : la tête ne se lit pas, et rien n'est écrit.
    "tete-illisible": (
        {"pannes": {HEAD: fini(128, err="fatal: ambiguous argument 'HEAD'\n")}},
        3,
        4,
        ("`git rev-parse HEAD` a échoué (128)", "ambiguous argument 'HEAD'"),
    ),
    "commit-refuse-par-un-hook": (
        {"pannes": {COMMIT: fini(1, out="commit-msg : type conventionnel manquant\n")}},
        3,
        5,
        ("a échoué (1)", "commit-msg : type conventionnel manquant"),
    ),
    # Le commit a réussi, la tête ne se relit pas : le reset n'est pas lancé, et le commit de sonde
    # reste peut-être en tête — le motif le dit.
    "tete-illisible-apres-le-commit": (
        {"tete_illisible_apres_le_commit": True},
        3,
        6,
        (
            "`git rev-parse HEAD` a échoué (128)",
            "bad revision 'HEAD'",
            "la tête porte peut-être encore le commit de sonde",
            "rien n'a été annulé",
            f"tête d'avant : {TETE}",
        ),
    ),
    "reset-en-echec": (
        {"pannes": {RESET: fini(128, err="fatal: Unable to create '.git/index.lock'\n")}},
        3,
        7,
        (f"le commit de sonde {SONDE} est encore en tête (tête d'avant : {TETE})", "index.lock"),
    ),
    "tete-deplacee-apres-le-reset": (
        {"reset_sans_effet": True},
        3,
        8,
        (f"la tête est {SONDE} après la sonde, pas {TETE}",),
    ),
    "format-qui-reecrit-l-arbre": (
        {"apres_format": " M apps/api/x.py\n"},
        4,
        10,
        ("pas formaté", "M apps/api/x.py"),
    ),
    "programme-introuvable": (
        {"pannes": {FORMAT: FileNotFoundError(2, "Le fichier spécifié est introuvable")}},
        4,
        9,
        ("`make` ne se lance pas", "Le fichier spécifié est introuvable"),
    ),
    "format-en-echec": (
        {"pannes": {FORMAT: fini(2, err="make: *** [Makefile:124: format] Error 2\n")}},
        4,
        9,
        ("`make format` a échoué (2)", "Error 2"),
    ),
    "test-en-echec": (
        {"pannes": {TEST: fini(1, out="FAILED test_x\n", err="make: *** Error 1\n")}},
        5,
        11,
        ("`uv run pytest -k 'not lent'` a échoué (1)", "FAILED test_x", "make: *** Error 1"),
    ),
}


@pytest.mark.parametrize(("etat", "sonde_ko", "lancees", "motifs"), KO.values(), ids=KO.keys())
def test_le_premier_ko_arrete_les_sondes_et_dit_sa_cause(
    etat: dict[str, Any],
    sonde_ko: int,
    lancees: int,
    motifs: tuple[str, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    poste = Poste(**etat)

    assert lance(poste, *OPTIONS) == 1
    assert poste.appels == ORDRE[:lancees]
    lignes = capsys.readouterr().out.splitlines()
    sondes = [ligne for ligne in lignes if not ligne.startswith(" ")]
    assert sondes == [f"OK   {nom}" for nom in NOMS[:sonde_ko]] + [f"KO   {NOMS[sonde_ko]}"]
    for motif in motifs:
        assert any(motif in ligne for ligne in lignes), f"{motif!r} absent de {lignes}"


def test_au_ko_la_sortie_fautive_se_borne_a_ses_vingt_dernieres_lignes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un rapport de test entier noierait la cause : la fin suffit à la nommer, et c'est là
    qu'un lanceur l'écrit — sortie d'erreur comprise, rendue après la sortie standard."""
    sortie = "".join(f"ligne {i:02}\n" for i in range(1, 46))
    poste = Poste(pannes={TEST: fini(1, out=sortie, err="ligne 46\n")})

    assert lance(poste, *OPTIONS) == 1
    rendues = [ligne.strip() for ligne in capsys.readouterr().out.splitlines()]
    assert [ligne for ligne in rendues if ligne.startswith("ligne")] == [
        f"ligne {i:02}" for i in range(27, 47)
    ]


SANS_FORMAT_NI_TEST = ORDRE[:8]
QUATRE_OK = [f"OK   {nom}" for nom in NOMS[:4]]
# Une option omise — `n/a` ou `# non vérifiée` dans `pipeline.config.md` : la session ne la passe
# pas — saute sa sonde, et la sortie le dit au lieu de se taire.
SAUTEES = {
    "sans-option": ((), SANS_FORMAT_NI_TEST, ["SAUTÉE format", "SAUTÉE test"]),
    "format-seul": (OPTIONS[:2], ORDRE[:10], ["OK   format", "SAUTÉE test"]),
    "test-seul": (OPTIONS[2:], [*SANS_FORMAT_NI_TEST, TEST], ["SAUTÉE format", "OK   test"]),
}


@pytest.mark.parametrize(("args", "appels", "fin"), SAUTEES.values(), ids=SAUTEES.keys())
def test_une_option_omise_saute_sa_sonde_et_le_dit(
    args: tuple[str, ...],
    appels: list[tuple[str, ...]],
    fin: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    poste = Poste()

    assert lance(poste, *args) == 0
    assert poste.appels == appels
    assert capsys.readouterr().out.splitlines() == [*QUATRE_OK, *fin]


# Chaque champ que la session saisit, balayé en une passe pour la présence et la forme : une
# commande vide ou mal citée ne se découpe en rien de lançable.
APPELS_MAL_FORMES = {
    "format-vide": ("--format", ""),
    "test-blanc": ("--test", "   "),
    "guillemet-non-ferme": ("--test", 'uv run pytest -k "lent'),
    "option-sans-valeur": ("--format",),
    "option-inconnue": ("--lint", "make lint"),
    "argument-positionnel": ("make test",),
    # `shlex.split` POSIX mange l'antislash : `apps\api` deviendrait `appsapi`.
    "chemin-a-antislash": ("--test", "uv run pytest apps\\api\\tests\\test_x.py"),
}


@pytest.mark.parametrize("args", APPELS_MAL_FORMES.values(), ids=APPELS_MAL_FORMES.keys())
def test_un_appel_mal_forme_sort_en_2_sans_rien_lancer(
    args: tuple[str, ...], capsys: pytest.CaptureFixture[str]
) -> None:
    poste = Poste()

    assert lance(poste, *args) == 2
    assert poste.appels == []
    assert "usage" in capsys.readouterr().err


def test_un_antislash_se_refuse_en_disant_d_ecrire_les_chemins_avec_des_barres_obliques(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert lance(Poste(), *APPELS_MAL_FORMES["chemin-a-antislash"]) == 2
    assert "écrire les chemins avec `/`" in capsys.readouterr().err


@pytest.fixture
def depot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Un vrai dépôt jetable à un commit, répertoire courant comme la racine d'où la session lance
    le script.

    Isolé de la configuration git du poste — un `core.hooksPath` ou un `commit.gpgsign` global
    s'y déclencherait au commit de sonde — et réglé pour cacher les fichiers non suivis
    (`status.showUntrackedFiles=no`) : la sonde doit les voir quand même.
    """
    configuration_vide = tmp_path / "gitconfig"
    configuration_vide.touch()
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(configuration_vide))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    depot = tmp_path / "depot"
    depot.mkdir()
    monkeypatch.chdir(depot)
    for args in (
        ("init", "-q"),
        ("config", "user.name", "t"),
        ("config", "user.email", "t@t"),
        ("config", "status.showUntrackedFiles", "no"),
        ("commit", "-q", "--allow-empty", "-m", "init"),
    ):
        subprocess.run(["git", *args], capture_output=True, check=True)
    return depot


def poste_reel(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Le lanceur par défaut pour `git`, sur le vrai dépôt ; les deux sondes `gh` répondent comme
    un compte authentifié qui peut pousser — la forge n'est jamais appelée."""
    cmd = tuple(cmd)
    if cmd == AUTH:
        return fini()
    if cmd == PUSH:
        return fini(out="true\n")
    if cmd[0] == "git":
        return sonde.default_run(cmd)
    raise AssertionError(f"commande inattendue : {cmd}")


def tete() -> str:
    """La tête du dépôt courant, lue par le vrai `git`."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_sur_un_vrai_depot_le_commit_de_sonde_rend_la_tete_d_avant(
    depot: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le commit et le reset joués par le vrai `git` : la tête revient au SHA d'avant."""
    avant = tete()

    assert sonde.main([], run=poste_reel) == 0
    assert capsys.readouterr().out.splitlines() == [*QUATRE_OK, "SAUTÉE format", "SAUTÉE test"]
    assert tete() == avant


def test_sur_un_vrai_depot_un_fichier_non_suivi_rend_l_arbre_sale(
    depot: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """La preuve sur le vrai `git` que la première sonde voit un fichier non suivi — même quand
    la configuration le cache à `git status`."""
    (depot / "jetable.txt").write_text("jetable\n", encoding="utf-8")

    assert sonde.main([], run=poste_reel) == 1
    lignes = capsys.readouterr().out.splitlines()
    assert lignes[0] == "KO   arbre propre"
    assert "     ?? jetable.txt" in lignes


@pytest.mark.parametrize(
    ("octets", "texte"),
    [("intégration".encode(), "intégration"), ("été".encode("cp1252"), "�t�")],
    ids=["utf-8", "octets-non-utf-8"],
)
def test_le_lanceur_par_defaut_decode_en_utf_8_sans_lever(octets: bytes, texte: str) -> None:
    """Le défaut réel du lanceur, que le poste témoin remplace ailleurs : décodée à la page de
    code de la console, une sortie accentuée arriverait de travers (obs 108) ; et une sortie qui
    n'est pas de l'UTF-8 — un lanceur de tests qui écrit en cp1252 — ne doit pas faire tomber la
    sonde qui la rapporte."""
    ecrit = f"import sys; sys.stdout.buffer.write({octets!r}); sys.stderr.buffer.write({octets!r})"

    done = sonde.default_run([sys.executable, "-c", ecrit])

    assert (done.stdout, done.stderr) == (texte, texte)


@pytest.mark.parametrize(
    ("args", "code", "flux", "texte"),
    [
        (["--help"], 0, "stdout", "SAUTÉE"),
        (["--test", 'make "test'], 2, "stderr", "commande mal citée"),
    ],
    ids=["aide-sur-stdout", "usage-sur-stderr"],
)
def test_la_sortie_du_script_lance_en_tube_est_en_utf_8(
    args: list[str], code: int, flux: str, texte: str
) -> None:
    """La session lit le script par un tube, où Python écrit dans la page de code du poste,
    cp1252, que `run_in_pipe` impose (`pipeline.config.md`, « Qualité ») — l'erreur
    d'argparse comprise, qui part sur la sortie d'erreur."""
    done = run_in_pipe("cycle-pr", "sonde-outillage", *args)

    assert done.returncode == code
    assert texte in getattr(done, flux).decode("utf-8")
