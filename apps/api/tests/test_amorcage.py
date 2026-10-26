"""Tests des gestes de dépôt locaux d'`init-projet`
(`.claude/skills/init-projet/scripts/amorcage.py`).

`depot init`, `ignore` et `commit` tournent contre le vrai `git`, `copie` sur le vrai système de
fichiers, dans le dossier jetable d'un projet que `GIT_CEILING_DIRECTORIES` isole de tout dépôt
parent, et `GIT_CONFIG_GLOBAL` et `GIT_CONFIG_NOSYSTEM` des configurations git globale et
système du poste. Une relecture non conforme s'y provoque en remplaçant une commande du geste par
une autre (`substitue`) — pour `copie`, sa copie par une copie vide — : le geste ne fait pas ce
qu'il dit, et la relecture doit le voir. `claude`, `uvx` et `pipx` sont joués par un lanceur
simulé (`Lanceur`) : le vrai `claude mcp add` écrirait dans `~/.claude.json` du poste ;
`ssh-keygen`, réel, signe les commits d'un cas. Les cas s'écrivent en littéraux.
"""

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest
from command_doubles import Reply, failure, sortie_d_echec, success
from skill_scripts import load_script, run_in_pipe

amorcage = load_script("init-projet", "amorcage")

Run = Callable[[Sequence[str]], subprocess.CompletedProcess[bytes]]


class Lanceur:
    """Un lanceur simulé : chaque programme rend, dans l'ordre, les réponses qu'on lui donne —
    une `OSError` se lève, comme un exécutable introuvable ; une commande de plus lève
    `IndexError`, un programme sans réponses `KeyError`. Il garde chaque commande reçue."""

    def __init__(self, **reponses: list[Reply]) -> None:
        self.reponses = reponses
        self.appels: list[tuple[str, ...]] = []

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        self.appels.append(tuple(cmd))
        reponse = self.reponses[cmd[0]].pop(0)
        if isinstance(reponse, OSError):
            raise reponse
        return reponse


@pytest.fixture
def projet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Le dossier du projet, répertoire courant, hors de tout dépôt : `git` ne remonte pas
    au-dessus de `tmp_path`, et ne lit ni la configuration globale ni celle du système : un
    `commit.gpgsign` du poste sans clé y ferait échouer chaque commit (mesuré le 2026-10-26,
    git 2.47.1) ; un cas qui éprouve une clé la pose en configuration locale. L'identité de
    l'auteur passe par l'environnement : elle ne dépend ni de la configuration git du poste ni de
    celle de la CI."""
    dossier = tmp_path / "projet"
    dossier.mkdir()
    monkeypatch.chdir(dossier)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Amorce")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "amorce@example.invalid")
    return dossier


def git(*args: str) -> str:
    """La sortie du vrai `git` dans le répertoire courant, qui doit réussir."""
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout.decode()


def lance(*args: str, run: Run | None = None) -> int:
    """Le script tel que la session l'appelle — avec le lanceur réel, sauf `run`."""
    return amorcage.main(list(args), run=run or amorcage.default_run)


def test_depot_init_cree_le_depot_sur_main_puis_le_relit(
    projet: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance("depot", "init") == 0
    assert git("symbolic-ref", "--short", "HEAD") == "main\n"
    assert capsys.readouterr().out == "initialisé et relu — dépôt git sur main\n"


def test_depot_init_n_a_rien_a_faire_dans_un_depot_sur_main(
    projet: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git("init", "-b", "main")

    assert lance("depot", "init") == 0
    assert capsys.readouterr().out == "rien à faire — dépôt git déjà sur main\n"


def test_depot_init_refuse_un_depot_sur_une_autre_branche_sans_la_renommer(
    projet: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git("init", "-b", "master")

    assert lance("depot", "init") == 1
    assert git("symbolic-ref", "--short", "HEAD") == "master\n"
    assert capsys.readouterr().out == (
        "refus — le dépôt est sur la branche master, pas main : rien n'est renommé\n"
    )


def substitue(avant: Sequence[str], apres: Sequence[str]) -> Run:
    """Le lanceur réel, qui lance `apres` quand on lui demande `avant`."""

    def run(cmd: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        return amorcage.default_run(apres if tuple(cmd) == tuple(avant) else cmd)

    return run


@pytest.mark.parametrize(
    ("apres", "motif"),
    [
        (("git", "init", "-b", "autre"), "branche relue autre, attendu main"),
        (("git", "--version"), "`git symbolic-ref --short HEAD` a échoué (128)"),
    ],
    ids=["autre-branche", "sans-depot"],
)
def test_depot_init_sort_en_1_si_la_relecture_ne_trouve_pas_le_depot_sur_main(
    apres: tuple[str, ...], motif: str, projet: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un dépôt absent se voit par l'échec de la lecture de sa branche, qui suit le geste : c'est
    une relecture non conforme, pas un refus."""
    run = substitue(("git", "init", "-b", "main"), apres)

    assert lance("depot", "init", run=run) == 1
    assert motif in sortie_d_echec(capsys, "relecture non conforme")


# Un boilerplate au layout réel, réduit : chaque fichier relatif à sa racine, et ses octets.
BOILERPLATE = {
    "template/CLAUDE.md": b"# Pipeline\n",
    "template/.claude/rules/contraintes.md": b"# Contraintes\r\n",
    "template/.github/workflows/ci.yml": b"name: {{NOM}}\n",
    "skills/cycle-pr/SKILL.md": b"---\nname: cycle-pr\n---\n",
    "skills/cycle-pr/scripts/merge-lot.py": b"print('lot')\n",
}


def garnit(racine: Path, fichiers: dict[str, bytes]) -> Path:
    """Le dossier `racine`, garni de `fichiers`."""
    for chemin, octets in fichiers.items():
        (racine / chemin).parent.mkdir(parents=True, exist_ok=True)
        (racine / chemin).write_bytes(octets)
    return racine


def contenu(dossier: Path) -> dict[str, bytes]:
    """Chaque fichier sous `dossier`, relatif à lui, et ses octets."""
    return {
        chemin.relative_to(dossier).as_posix(): chemin.read_bytes()
        for chemin in dossier.rglob("*")
        if chemin.is_file()
    }


def test_copie_copie_le_template_hors_github_et_les_skills_puis_les_relit(
    projet: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`template/.github/` porte des modèles à trous, générés à l'étape 7 : jamais copiés."""
    source = garnit(tmp_path / "boilerplate", BOILERPLATE)

    assert lance("copie", str(source)) == 0
    assert contenu(projet) == {
        "CLAUDE.md": b"# Pipeline\n",
        ".claude/rules/contraintes.md": b"# Contraintes\r\n",
        ".claude/skills/cycle-pr/SKILL.md": b"---\nname: cycle-pr\n---\n",
        ".claude/skills/cycle-pr/scripts/merge-lot.py": b"print('lot')\n",
    }
    assert capsys.readouterr().out == "copié et relu — fichiers copiés : 4, déjà identiques : 0\n"


def test_copie_n_a_rien_a_faire_quand_chaque_cible_est_identique(
    projet: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = garnit(tmp_path / "boilerplate", BOILERPLATE)
    assert lance("copie", str(source)) == 0
    capsys.readouterr()

    assert lance("copie", str(source)) == 0
    assert capsys.readouterr().out == "rien à faire — fichiers déjà identiques : 4\n"


def test_copie_refuse_sans_rien_ecrire_et_nomme_chaque_conflit(
    projet: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Tout ou rien : la fusion d'une cible qui diffère — `settings.json` — reste à la main."""
    source = garnit(tmp_path / "boilerplate", BOILERPLATE)
    deja_la = {"CLAUDE.md": b"# Projet\n", ".claude/skills/cycle-pr/SKILL.md": b"local\n"}
    garnit(projet, deja_la)

    assert lance("copie", str(source)) == 1
    assert contenu(projet) == deja_la
    assert capsys.readouterr().out == (
        "refus — cibles différentes de leur source (2), rien n'est copié :"
        " CLAUDE.md, .claude/skills/cycle-pr/SKILL.md\n"
    )


def test_copie_refuse_un_boilerplate_sans_skills(
    projet: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = garnit(tmp_path / "boilerplate", {"template/CLAUDE.md": b"# Pipeline\n"})

    assert lance("copie", str(source)) == 1
    assert contenu(projet) == {}
    assert capsys.readouterr().out == f"refus — {source} n'a pas skills/\n"


def test_copie_sort_en_1_si_une_copie_differe_de_sa_source(
    projet: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Une copie tronquée — le geste ne fait pas ce qu'il dit — : la relecture nomme chaque
    fichier."""
    source = garnit(tmp_path / "boilerplate", BOILERPLATE)

    def copie_vide(_source: Path, cible: Path) -> None:
        cible.touch()

    monkeypatch.setattr(amorcage.shutil, "copyfile", copie_vide)

    assert lance("copie", str(source)) == 1
    assert capsys.readouterr().out == (
        "relecture non conforme — copie différente de sa source : .claude/rules/contraintes.md,"
        " CLAUDE.md, .claude/skills/cycle-pr/SKILL.md,"
        " .claude/skills/cycle-pr/scripts/merge-lot.py\n"
    )


def test_valide_lance_check_jsonschema_sur_une_copie_yml_retiree_ensuite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sans l'extension `.yml`, l'outil lit du JSON (mesuré le 2026-10-26, check-jsonschema
    0.38.2) : un brouillon sans extension se valide sous une copie qui la porte."""
    brouillon = tmp_path / "brouillon-ci"
    brouillon.write_bytes(b"on: push\n")
    vus: list[tuple[tuple[str, ...], Path, bytes]] = []

    def run(cmd: Sequence[str]) -> subprocess.CompletedProcess[bytes]:
        copie = Path(cmd[-1])
        vus.append((tuple(cmd[:-1]), copie, copie.read_bytes()))
        return success(b"ok -- validation done\n")

    assert lance("valide", str(brouillon), "--schema", "vendor.github-workflows", run=run) == 0
    [(commande, copie, octets)] = vus
    assert commande == ("uvx", "check-jsonschema", "--builtin-schema", "vendor.github-workflows")
    assert (copie.name, octets) == ("brouillon-ci.yml", b"on: push\n")
    assert not copie.parent.exists()
    assert capsys.readouterr().out == f"valide — {brouillon} (vendor.github-workflows)\n"


@pytest.fixture
def dependabot(tmp_path: Path) -> Path:
    """Un `dependabot.yml` à valider ; l'outil, simulé, ne le lit pas."""
    fichier = tmp_path / "dependabot.yml"
    fichier.write_bytes(b"version: 2\n")
    return fichier


def test_valide_refuse_un_fichier_invalide_avec_les_cinq_premieres_lignes_de_l_outil(
    dependabot: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """L'outil écrit ses erreurs sur sa sortie standard, `uvx` son installation sur la sortie
    d'erreur (mesuré le 2026-10-26) ; au-delà de cinq lignes, le reste est tu."""
    erreurs = (
        b"Schema validation errors were encountered.\n"
        b"  a.yml::$.updates[0]: 'schedule' is a required property\n"
        b"  a.yml::$.updates[1]: 'schedule' is a required property\n"
        b"  a.yml::$.updates[2]: 'schedule' is a required property\n"
        b"  a.yml::$.updates[3]: 'schedule' is a required property\n"
        b"  a.yml::$.updates[4]: 'schedule' is a required property\n"
    )
    invalide = subprocess.CompletedProcess([], 1, erreurs, b"Installed 14 packages in 183ms\n")

    lanceur = Lanceur(uvx=[invalide])

    assert lance("valide", str(dependabot), "--schema", "vendor.dependabot", run=lanceur) == 1
    assert capsys.readouterr().out == (
        f"refus — {dependabot} invalide (vendor.dependabot) : Schema validation errors were"
        " encountered. ; a.yml::$.updates[0]: 'schedule' is a required property ;"
        " a.yml::$.updates[1]: 'schedule' is a required property ;"
        " a.yml::$.updates[2]: 'schedule' is a required property ;"
        " a.yml::$.updates[3]: 'schedule' is a required property\n"
    )


def test_valide_passe_par_pipx_quand_uvx_ne_se_lance_pas(dependabot: Path) -> None:
    lanceur = Lanceur(uvx=[FileNotFoundError("uvx")], pipx=[success(b"ok -- validation done\n")])

    assert lance("valide", str(dependabot), "--schema", "vendor.dependabot", run=lanceur) == 0
    assert [appel[:-1] for appel in lanceur.appels] == [
        ("uvx", "check-jsonschema", "--builtin-schema", "vendor.dependabot"),
        ("pipx", "run", "check-jsonschema", "--builtin-schema", "vendor.dependabot"),
    ]


def test_valide_refuse_quand_ni_uvx_ni_pipx_ne_se_lancent(
    dependabot: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le refus sort du dossier temporaire par une exception : il est retiré quand même."""
    lanceur = Lanceur(uvx=[FileNotFoundError("uvx")], pipx=[FileNotFoundError("pipx")])

    assert lance("valide", str(dependabot), "--schema", "vendor.dependabot", run=lanceur) == 1
    assert not Path(lanceur.appels[0][-1]).parent.exists()
    assert capsys.readouterr().out == "refus — ni uvx ni pipx ne se lancent\n"


@pytest.fixture
def depot_ignorant(projet: Path) -> Path:
    """Le projet en dépôt git, sous un `.gitignore` qui exclut journaux, verrous et dépendances."""
    git("init", "-b", "main")
    (projet / ".gitignore").write_bytes(b"*.log\n*.lock\nnode_modules/\n")
    return projet


def test_ignore_confirme_les_chemins_exclus_et_suivis(
    depot_ignorant: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("--exclus", "app.log", "node_modules/paquet/index.js", "--suivis", "src/main.py")

    assert lance("ignore", *args) == 0
    assert capsys.readouterr().out == "conforme — exclus : 2, suivis : 1\n"


def test_ignore_refuse_et_nomme_chaque_chemin_en_defaut(
    depot_ignorant: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ("--exclus", "src/main.py", "app.log", "--suivis", "README.md", "debug.log")

    assert lance("ignore", *args) == 1
    assert capsys.readouterr().out == (
        "refus — devrait être exclu : src/main.py ; devrait rester suivi : debug.log\n"
    )


def test_ignore_voit_le_motif_qui_exclut_un_fichier_deja_suivi(
    depot_ignorant: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un fichier suivi n'est jamais dit ignoré par `git check-ignore` sans `--no-index` : le
    `uv.lock` suivi masquerait le motif `*.lock`, qui l'exclurait d'un clone neuf
    (git-check-ignore(1), « --no-index » ; mesuré le 2026-10-26, git 2.47.1)."""
    (depot_ignorant / "uv.lock").write_bytes(b"version = 1\n")
    git("add", "-f", "uv.lock")

    assert lance("ignore", "--exclus", "app.log", "--suivis", "uv.lock") == 1
    assert capsys.readouterr().out == "refus — devrait rester suivi : uv.lock\n"


def test_ignore_refuse_hors_d_un_depot_git(
    projet: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`git check-ignore` y sort en 128 : ni « ignoré » (0) ni « non ignoré » (1)."""
    assert lance("ignore", "--exclus", "app.log", "--suivis", "src/main.py") == 1
    assert "`git check-ignore --no-index -q app.log` a échoué (128)" in sortie_d_echec(
        capsys, "refus"
    )


CONTEXT7 = "https://mcp.context7.com/mcp"
LISTE = ("claude", "mcp", "list")
AJOUT = ("claude", "mcp", "add", "--scope", "user", "--transport", "http", "context7", CONTEXT7)
# `claude mcp list`, tel qu'il se lit (mesuré le 2026-10-26, Claude Code 2.1.295).
LISTE_AVEC_CONTEXT7 = success(
    "Checking MCP server health…\n\n"
    "context7: https://mcp.context7.com/mcp (HTTP) - ✔ Connected\n".encode()
)


def test_mcp_n_a_rien_a_faire_quand_le_serveur_est_liste(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lanceur = Lanceur(claude=[LISTE_AVEC_CONTEXT7])

    assert lance("mcp", "context7", CONTEXT7, run=lanceur) == 0
    assert lanceur.appels == [LISTE]
    assert capsys.readouterr().out == "rien à faire — serveur MCP context7 déjà listé\n"


def test_mcp_ajoute_le_serveur_en_portee_utilisateur_puis_relit_la_liste(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un serveur se reconnaît à son nom entier : `context7-local` n'est pas `context7`."""
    autre = success(b"Checking MCP server health\n\ncontext7-local: npx (stdio) - Connected\n")
    lanceur = Lanceur(claude=[autre, success(b"Added HTTP MCP server\n"), LISTE_AVEC_CONTEXT7])

    assert lance("mcp", "context7", CONTEXT7, run=lanceur) == 0
    assert lanceur.appels == [LISTE, AJOUT, LISTE]
    assert capsys.readouterr().out == f"ajouté et relu — serveur MCP context7 ({CONTEXT7})\n"


VIDE = success(b"No MCP servers configured.\n")


@pytest.mark.parametrize(
    ("apres_la_lecture", "ecart"),
    [
        ([success(b""), VIDE], "context7 absent de `claude mcp list` après son ajout"),
        (
            [failure(b"Error: config illisible\n")],
            f"`{' '.join(AJOUT)}` a échoué (1) : Error: config illisible",
        ),
    ],
    ids=["liste-sans-le-serveur", "ajout-en-echec"],
)
def test_mcp_sort_en_1_si_l_ajout_n_est_pas_relu(
    apres_la_lecture: list[Reply], ecart: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un ajout en échec a pu écrire : c'est une relecture non conforme, pas un refus."""
    lanceur = Lanceur(claude=[VIDE, *apres_la_lecture])

    assert lance("mcp", "context7", CONTEXT7, run=lanceur) == 1
    assert capsys.readouterr().out == f"relecture non conforme — {ecart}\n"


def test_mcp_refuse_quand_claude_ne_se_lance_pas(capsys: pytest.CaptureFixture[str]) -> None:
    lanceur = Lanceur(claude=[FileNotFoundError("introuvable")])

    assert lance("mcp", "context7", CONTEXT7, run=lanceur) == 1
    assert capsys.readouterr().out == "refus — `claude` ne se lance pas : introuvable\n"


TITRE = "chore: amorçage pipeline de dev"


@pytest.fixture
def depot_a_commiter(projet: Path) -> Path:
    """Le projet en dépôt git sans commit : un `.gitignore`, un fichier à suivre, un exclu."""
    git("init", "-b", "main")
    garnit(projet, {".gitignore": b"*.log\n", "README.md": b"# Vitrine\n", "debug.log": b""})
    return projet


def test_commit_commite_le_projet_hors_exclus_puis_relit_le_commit(
    depot_a_commiter: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance("commit") == 0
    assert git("log", "-1", "--format=%s") == f"{TITRE}\n"
    assert git("ls-files") == ".gitignore\nREADME.md\n"
    assert capsys.readouterr().out == f"commité et relu — {TITRE}\n"


def test_commit_n_a_rien_a_faire_sur_un_arbre_propre(
    depot_a_commiter: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert lance("commit") == 0
    capsys.readouterr()

    assert lance("commit") == 0
    assert capsys.readouterr().out == "rien à faire — rien à commiter\n"


def test_commit_refuse_un_fichier_suivi_que_les_regles_d_ignore_excluent(
    depot_a_commiter: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un `.gitignore` n'agit pas sur ce qui est déjà suivi. Le nom se lit tel quel, accents
    compris — sans `-z`, `git ls-files` l'écrirait entre guillemets, en octal."""
    (depot_a_commiter / "brouillon-été.log").write_bytes(b"")
    git("add", "-f", "brouillon-été.log")

    assert lance("commit") == 1
    assert git("rev-list", "--all") == ""
    assert capsys.readouterr().out == (
        "refus — fichiers suivis que les règles d'ignore excluent, à retirer par"
        " `git rm --cached` : brouillon-été.log\n"
    )


def signe_par_ssh(depot: Path) -> None:
    """Chaque commit signé par une clé SSH jetable, sans phrase de passe, rangée hors du dépôt ;
    `ssh-keygen` doit être sur le `PATH`."""
    cle = depot.parent / "cle"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(cle)], check=True)
    git("config", "gpg.format", "ssh")
    git("config", "user.signingKey", str(cle))
    git("config", "commit.gpgsign", "true")


def commite_un_depot_imbrique() -> None:
    """Tout le projet commité, dont le dépôt imbriqué `module`, à un commit."""
    git("init", "-b", "main", "module")
    git("-C", "module", "commit", "--allow-empty", "-m", "un")
    git("add", "-A")
    git("commit", "-m", "initial")


def avance_un_depot_imbrique(_depot: Path) -> None:
    """Tout est commité, sauf le pointeur d'un dépôt imbriqué, avancé d'un commit : la seule
    chose que `git add -A` ait à commiter."""
    commite_un_depot_imbrique()
    git("-C", "module", "commit", "--allow-empty", "-m", "deux")


# Chaque clé éprouvée — l'id de son cas —, sa valeur, et ce qui prépare le dépôt pour qu'elle
# y ait prise.
CONFIGURATIONS: dict[str, tuple[str, Callable[[Path], None] | None]] = {
    "status.showUntrackedFiles": ("no", None),
    "diff.ignoreSubmodules": ("all", avance_un_depot_imbrique),
    "i18n.logOutputEncoding": ("ISO-8859-1", None),
    "log.showSignature": ("true", signe_par_ssh),
}


@pytest.mark.parametrize("cle", CONFIGURATIONS)
def test_commit_commite_et_relit_quelle_que_soit_la_configuration_git(
    cle: str, depot_a_commiter: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Une clé de configuration git, posée en configuration locale, ne change pas ce que les
    lectures de `commit` concluent.

    Dénombré avant le correctif, sur les deux scripts du lot — `amorcage.py`, et ce que le lot
    ajoute à `ecriture-relue.py` : 11 appels `git`, 8 lectures et 3 gestes ; 2 lectures fuyaient,
    par 4 clés, une par cas. Provenance : « mesuré » par sonde le 2026-10-26, git 2.47.1 ; « lu »
    dans la page de manuel de la commande ; sinon « non vérifié ».

    - `git status --porcelain` (`commit`, avant le geste et à sa relecture) : fuite, mesuré.
      `status.showUntrackedFiles=no` cache les fichiers non suivis, `diff.ignoreSubmodules=all`
      le pointeur avancé d'un dépôt imbriqué que `git add -A` commite quand même : « rien à
      faire », sans commit. `--porcelain` fixe le format, pas le contenu ; `core.quotePath` ne
      change que l'écriture d'un chemin dans le motif (lu). `--ignore-submodules=dirty` l'emporte
      sur la clé et est voulu, pas `none` : le contenu interne d'un dépôt imbriqué ne se commite
      pas par `git add -A`, et l'option se choisit sur ce que le geste peut écrire, pas au plus
      strict (mesuré).
    - `git log -1 --format=%s` (relecture de `commit`) : fuite, mesuré. `i18n.logOutputEncoding`
      réencode le sujet, `log.showSignature` le fait précéder d'une ligne de vérification sur un
      commit signé : relecture non conforme d'un commit conforme.
    - `git ls-files -i -c --exclude-standard -z` (`commit`), `git check-ignore --no-index -q`
      (`ignore`) : `core.excludesFile` et `core.ignoreCase` y changent la réponse (mesuré), et
      c'est l'intention — les règles d'ignore de ce poste valent ; `core.quotePath` est tenu par
      `-z`, et `-q` n'écrit rien (lu).
    - `git rev-parse --is-inside-work-tree` (`depot init`, `depot create`), `git symbolic-ref
      --short HEAD` (`depot init`) : aucune clé recensée qui change leur réponse (non vérifié).
    - `git remote get-url origin` (`depot create`) : `url.<base>.insteadOf` y est appliqué (lu) ;
      tenu entre les formes HTTPS et SSH, toutes deux comparées (non vérifié).
    - Les gestes `git init -b main`, `git add -A`, `git commit -m` : `init.defaultBranch` est tenu
      par `-b` (lu) ; un `commit.gpgsign` sans clé fait échouer le commit, `i18n.commitEncoding`
      étiquette son message sans le réencoder, que `git log` relit mal en UTF-8 (mesuré), un
      hook peut le refuser ou changer son sujet (lu) — la relecture le dit.
    """
    valeur, prepare = CONFIGURATIONS[cle]
    if prepare:
        prepare(depot_a_commiter)
    git("config", cle, valeur)

    assert lance("commit") == 0
    assert capsys.readouterr().out == f"commité et relu — {TITRE}\n"
    assert (
        git("status", "--porcelain", "--untracked-files=normal", "--ignore-submodules=none") == ""
    )


def test_commit_n_a_rien_a_faire_quand_seul_l_interieur_d_un_depot_imbrique_change(
    depot_a_commiter: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un fichier non suivi **dans** un dépôt imbriqué n'est pas à la portée de `git add -A`, qui
    n'en commite que le pointeur : compté comme un changement, il lancerait un `git commit` qui
    n'a rien à écrire, et sortirait en relecture non conforme (mesuré le 2026-10-26,
    git 2.47.1)."""
    commite_un_depot_imbrique()
    (depot_a_commiter / "module" / "brouillon.txt").write_bytes(b"")

    assert lance("commit") == 0
    assert capsys.readouterr().out == "rien à faire — rien à commiter\n"
    assert git("rev-list", "--count", "HEAD") == "1\n"


@pytest.mark.parametrize(
    ("avant", "apres", "ecart"),
    [
        (
            ("git", "commit", "-m", TITRE),
            ("git", "commit", "-m", "autre titre"),
            f"dernier commit « autre titre », attendu « {TITRE} »",
        ),
        (
            ("git", "add", "-A"),
            ("git", "add", ".gitignore"),
            "arbre non propre après le commit : ?? README.md",
        ),
        (
            ("git", "commit", "-m", TITRE),
            ("git", "commit", "--option-inconnue"),
            f"`git commit -m {TITRE}` a échoué (129)",
        ),
    ],
    ids=["autre-sujet", "arbre-non-propre", "commit-en-echec"],
)
def test_commit_sort_en_1_si_le_commit_relu_n_est_pas_l_amorcage(
    avant: tuple[str, ...],
    apres: tuple[str, ...],
    ecart: str,
    depot_a_commiter: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un commit en échec suit `git add -A`, qui a écrit l'index : c'est une relecture non
    conforme, pas un refus."""
    assert lance("commit", run=substitue(avant, apres)) == 1
    assert ecart in sortie_d_echec(capsys, "relecture non conforme")


def test_un_appel_mal_forme_sort_en_2_sans_rien_lancer() -> None:
    assert lance("valide", "ci.yml", "--schema", "vendor.autre", run=Lanceur()) == 2


def test_l_aide_lancee_en_tube_est_en_utf_8() -> None:
    """La session lit le script par un tube, où Python écrit dans la page de code du poste,
    cp1252, que `run_in_pipe` impose (`pipeline.config.md`, « Qualité »)."""
    done = run_in_pipe("init-projet", "amorcage", "--help")

    assert done.returncode == 0
    assert "gestes de dépôt locaux" in done.stdout.decode("utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="un `.cmd` ne se lance que sous Windows")
def test_le_lanceur_reel_trouve_un_programme_cmd_sous_son_nom_nu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sous Windows, `claude` est un `claude.cmd` que `CreateProcess` ne trouve pas sous son nom
    nu — `[WinError 2]`, mesuré le 2026-10-26 — ; `shutil.which` le trouve, par `PATHEXT`."""
    (tmp_path / "outil.cmd").write_bytes(b"@echo %1\r\n")
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    assert amorcage.default_run(("outil", "bonjour")).stdout == b"bonjour\r\n"
