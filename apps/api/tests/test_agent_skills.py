"""Tests des skills (`.claude/skills/*/SKILL.md`) et des rôles (`.claude/agents/*.md`) de l'agent.

Claude Code lit le frontmatter YAML de chaque skill ; s'il ne parse pas, « the skill still loads
with no fields set » (doc « Extend Claude with skills ») : le skill reste invocable par `/<nom>`,
mais sa `description` ne sert plus au déclenchement automatique et son `argument-hint` disparaît —
sans erreur, nulle part. Mesuré le 2026-09-29 : trois skills maison sur treize étaient dans cet
état depuis leur création, listés par leur titre H1 au lieu de leur description, parce qu'un
« Déclencheurs : » sans guillemets fait d'un scalaire une clé de mapping.

Un rôle dont le frontmatter ne parse pas ne charge pas du tout : sans `name` lisible, Claude Code
le tient pour un document de référence rangé avec les rôles et le saute (`claude plugin validate`,
hors CI). Même cause possible — un « seulement : » sans guillemets dans la `description`.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import cast

import pytest
import yaml
from test_supply_chain import prose_citations, tracked_files

# `test_agent_skills.py` → `tests` → `api` → `apps` → racine du dépôt.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SKILLS = sorted(REPOSITORY_ROOT.glob(".claude/skills/*/SKILL.md"))
AGENTS = sorted(REPOSITORY_ROOT.glob(".claude/agents/*.md"))

# Le bloc entre les deux `---` de tête, quelle que soit la fin de ligne de la copie de travail.
FRONTMATTER = re.compile(r"\A---\r?\n(?P<yaml>.*?)\r?\n---\r?\n", re.DOTALL)

# Le champ sans lequel un skill ne se déclenche pas sur sa description — `name` est optionnel et
# vaut par défaut le nom du dossier.
REQUIRED_FIELDS = {"description"}


def label(path: Path) -> str:
    """Le nom que Claude Code donne au fichier : le dossier d'un skill, le nom d'un rôle."""
    return path.parent.name if path.name == "SKILL.md" else path.stem


def complaint(name: str, text: str) -> str | None:
    """Ce qui empêcherait Claude Code de charger ce skill ou ce rôle, ou `None` si rien.

    La garde est une **fonction sur du texte**, pas sur un chemin : c'est ce qui permet de la
    voir rouge sur un recueil de formes fautives construites en mémoire, sans jamais déposer de
    fichier fautif dans le dépôt (technique d'obs 53, modèle `WORKFLOW_FORMS` de
    `test_supply_chain.py`).

    Args:
        name: le nom que Claude Code donne au fichier, pour le message.
        text: le contenu du `SKILL.md` ou du `.md` du rôle.

    Returns:
        Le motif du refus, ou `None` si le fichier se charge avec tous ses champs.
    """
    match = FRONTMATTER.match(text)
    if not match:
        return f"{name} : aucun frontmatter en tête du fichier"
    try:
        fields: object = yaml.safe_load(match.group("yaml"))
    except yaml.YAMLError as error:
        return f"{name} : frontmatter illisible — {error}"
    if not isinstance(fields, dict):
        return f"{name} : le frontmatter n'est pas un mapping"
    present = cast(dict[str, object], fields)
    missing = REQUIRED_FIELDS - present.keys()
    if missing:
        return f"{name} : champs manquants {sorted(missing)}"
    description = present.get("description")
    if not (isinstance(description, str) and description.strip()):
        return f"{name} : description absente, vide ou non textuelle — Claude Code la jette"
    return None


# Le recueil : une forme fautive par classe, et le fragment de message qui doit la nommer. Les
# **deux premières** sont celles sur lesquelles `claude plugin validate` est muet — mesuré le
# 2026-10-09 sur v2.1.295, avec témoins —, c'est-à-dire exactement la classe qui a fait charger
# le rôle `relecteur` sans aucun champ. Cette table est la seule porte qui les attrape.
FRONTMATTER_FORMS = {
    "aucun frontmatter": ("# Un rôle sans frontmatter\n", "aucun frontmatter"),
    "deux-points non cités dans la description": (
        "---\nname: r\ndescription: Relecteur seulement : ne commit pas\n---\n\nCorps.\n",
        "frontmatter illisible",
    ),
    "frontmatter qui n'est pas un mapping": (
        "---\n- une\n- liste\n---\n\nCorps.\n",
        "n'est pas un mapping",
    ),
    "description absente": ("---\nname: r\n---\n\nCorps.\n", "champs manquants"),
    "description non textuelle": (
        "---\nname: r\ndescription:\n  - une\n  - liste\n---\n\nCorps.\n",
        "non textuelle",
    ),
    "description vide": ('---\nname: r\ndescription: "  "\n---\n\nCorps.\n', "vide"),
}


def test_les_dossiers_des_skills_et_des_roles_ne_sont_pas_vides() -> None:
    """Un motif qui n'apparie plus rien laisserait le test paramétré vert par absence."""
    assert SKILLS, (
        "aucun `SKILL.md` trouvé sous `.claude/skills/` — le motif a-t-il cessé de mordre ?"
    )
    assert AGENTS, "aucun `.md` trouvé sous `.claude/agents/` — le motif a-t-il cessé de mordre ?"


@pytest.mark.parametrize("path", SKILLS + AGENTS, ids=[label(path) for path in SKILLS + AGENTS])
def test_le_frontmatter_de_chaque_skill_et_role_parse_et_porte_ses_champs(path: Path) -> None:
    """Un frontmatter illisible ne rougit nulle part : skill muet, rôle sauté."""
    found = complaint(label(path), path.read_text(encoding="utf-8-sig"))

    assert found is None, found


@pytest.mark.parametrize(
    ("text", "expected"), FRONTMATTER_FORMS.values(), ids=FRONTMATTER_FORMS.keys()
)
def test_chaque_forme_fautive_de_frontmatter_est_refusee(text: str, expected: str) -> None:
    """La garde doit mordre sur chaque classe, pas seulement sur celle d'un incident passé.

    Un pin écrit après un incident couvre la population de l'incident, pas celle de la règle :
    le test des skills, né d'un défaut sur trois `SKILL.md`, ne paramétrait pas les rôles.
    """
    found = complaint("témoin", text)

    assert found is not None, "cette forme devrait être refusée"
    assert expected in found, f"message inattendu : {found}"


# La prose du harnais : skills, rôles, règles, et les deux fichiers de tête du dépôt. Un script
# déplacé ou renommé y laisse des renvois entrants qu'aucune porte ne voit — la prose se lit
# comme juste et n'échoue que pour celui qui suit le chemin, c'est-à-dire pendant la passe de
# relecture que le script devait outiller.
# La population est exactement celle que `cleanup-verbatim.md` prescrit pour balayer les renvois
# entrants d'une édition : `.claude/`, `CLAUDE.md`, `CONTRIBUTING.md`, `.github/`. La faire plus
# étroite que la règle qui la nomme laisserait un trou dont rien ne dirait le motif — aucun renvoi
# `scripts/*.py` n'y vit aujourd'hui hors de `.claude/`, le trou était donc latent, pas actuel.
#
# Deux bornes volontaires. `.claude/` est borné aux `.md` : l'élargir y ferait entrer les scripts
# eux-mêmes, donc les renvois de docstring que la porte écarte à dessein (voir son docstring).
# `.github/` ne l'est pas, parce qu'un renvoi y vivrait aussi bien dans un workflow `.yml` que
# dans un gabarit `.md`, et qu'aucun `.py` n'y est suivi.
#
# Ces globs sont consommés par `Path.glob`, où `**` admet zéro composant : `.claude/**/*.md`
# apparie donc `.claude/pipeline.config.md`. Transposée telle quelle en pathspec git, la liste
# n'y arriverait pas — voir `prose_citations`, et la commande citée par la porte ci-dessous.
HARNESS_PROSE_GLOBS = [".claude/**/*.md", "CLAUDE.md", "CONTRIBUTING.md", ".github/**/*"]

# Le dossier qui porte les scripts d'un skill. Nommé une fois : il entre à la fois dans le motif
# qui apparie les renvois et dans les chemins que `script_target` reconstruit, et deux littéraux
# qui divergeraient laisseraient la porte apparier une forme pour en résoudre une autre — la
# classe de défaut que cette porte existe précisément pour attraper.
SCRIPTS_DIRECTORY = "scripts"

# Les **deux** formes sous lesquelles un script de skill se cite, et elles seules :
#
# 1. **relative** (`<répertoire de ce skill>/scripts/x.py`, ou `scripts/x.py` nu) — la forme des
#    fichiers d'un skill, qui est recopié dans le seed où son chemin absolu diffère ; elle se
#    résout contre le dossier du skill qui porte le fichier citant ;
# 2. **depuis la racine** (`.claude/skills/<skill>/scripts/x.py`) — la forme d'un rôle ou d'une
#    règle, qui vit hors de l'arborescence des skills et n'a donc pas de dossier de référence.
#
# Un renvoi relatif porté par un fichier qui ne vit **pas** sous un skill ne se résout contre
# rien : il est rendu tel quel, donc introuvable. C'est un défaut, pas un cas à ignorer — c'est
# exactement la forme qu'un rôle prendrait s'il recopiait la phrase d'un skill.
# L'ancrage à gauche n'est pas décoratif : sans lui, le motif apparie `scripts/<x>.py` **au
# milieu** de n'importe quel chemin et jette son préfixe réel. `infra/scripts/deploy.py` se
# résolvait alors en `scripts/deploy.py`, introuvable — un renvoi juste rendait la porte rouge —,
# et pire sous un skill, où il se résolvait en `.claude/skills/<ce skill>/scripts/deploy.py`, une
# cible fausse qu'un homonyme aurait rendue verte. `[\w/-]` interdit la lettre, le chiffre, le
# tiret et le slash juste avant le motif ; un espace, un backtick ou un début de ligne les
# laissent passer, donc les trois formes canoniques sont intactes.
SCRIPT_REFERENCE = re.compile(
    r"(?<![\w/-])(?:\.claude/skills/(?P<skill>[\w-]+)/|<répertoire de ce skill>/)?"
    rf"{SCRIPTS_DIRECTORY}/(?P<script>[\w.-]+\.py)"
)

# Les préfixes de chemin qui ne sont pas ceux d'un script de skill, et qu'aucune résolution ne
# doit tenter. Dénombrement : 2 formes mesurées — un chemin d'infrastructure et un chemin
# applicatif —, les deux appariées avant l'ancrage, les deux refusées après.
FOREIGN_PREFIXES = {
    "chemin d-infrastructure": "voir infra/scripts/deploy.py pour le détail",
    "chemin applicatif": "lance apps/api/scripts/seed.py",
}


def script_target(root: Path, citing: Path, reference: re.Match[str]) -> str:
    """Le chemin, relatif à `root` et en POSIX, du script que ce renvoi désigne.

    Args:
        root: la racine du dépôt.
        citing: le fichier de prose qui porte le renvoi.
        reference: l'appariement de `SCRIPT_REFERENCE`.

    Returns:
        Le chemin visé. Pour un renvoi **relatif**, il est résolu contre le dossier du skill qui
        contient `citing` ; faute d'un tel dossier, le renvoi est rendu sans base — il ne
        désigne alors aucun fichier, et la porte le rapporte introuvable.
    """
    script = reference.group("script")
    if skill := reference.group("skill"):
        return f".claude/skills/{skill}/{SCRIPTS_DIRECTORY}/{script}"
    # La base se dérive de `root`, jamais d'une constante de module : la porte est appelée sur le
    # dépôt **et** sur des témoins en répertoire temporaire, et une base figée sur le dépôt rend
    # la branche relative muette chez le témoin — la seule qui l'éprouve.
    skills = root / ".claude" / "skills"
    own = next((parent for parent in citing.parents if parent.parent == skills), None)
    if own is None:
        return f"{SCRIPTS_DIRECTORY}/{script}"
    return f"{own.relative_to(root).as_posix()}/{SCRIPTS_DIRECTORY}/{script}"


def cited_scripts(root: Path, population: Iterable[str]) -> dict[str, set[str]]:
    """Les scripts que la prose du harnais désigne, chacun avec les fichiers qui le citent.

    Args:
        root: la racine à parcourir.
        population: les chemins relatifs, en POSIX, que l'appelant a le droit de lire. Tout
            fichier présent sur le disque mais absent de cette liste est ignoré — le choix de la
            population appartient donc à l'appelant, comme pour la porte des renvois de
            `test_infra.py`.

    Returns:
        Le chemin visé par chaque renvoi → le nom des fichiers qui le portent.
    """
    cited: dict[str, set[str]] = {}
    for citing, reference in prose_citations(
        root, population, HARNESS_PROSE_GLOBS, SCRIPT_REFERENCE
    ):
        cited.setdefault(script_target(root, citing, reference), set()).add(citing.name)
    return cited


def test_chaque_script_cite_par_la_prose_du_harnais_existe() -> None:
    """Un script renommé laisse derrière lui des renvois que rien ne suit.

    **Dénombrement de la classe, écrit avant le premier correctif** (`cycle-pr` Étape 4.2,
    cliquet). Les renvois vers un script se répartissent en **3 formes**, dont `script_target`
    résout les 2 **canoniques** et laisse la 3ᵉ introuvable :

    1. **relative**, dans les fichiers d'un skill (`<répertoire de ce skill>/scripts/x.py`, ou
       `scripts/x.py` nu) — résolue contre le dossier du skill qui porte le fichier citant ;
    2. **depuis la racine** (`.claude/skills/<skill>/scripts/x.py`) — la forme d'un rôle ou
       d'une règle, qui vit hors de l'arborescence des skills ;
    3. **orpheline** : une forme relative portée par un fichier qui n'est pas sous un skill —
       `cycle-pr/scripts/mutation.py` dans `pipeline.config.md`, relative à `.claude/skills/`
       sans le dire. Elle ne se résout contre rien, et elle a été **normalisée** en forme 2 par
       le commit qui ouvre ce lot, non appariée par un motif de plus : une porte qui gagne un
       motif par occurrence hérite de toutes les formes qu'on n'a pas prévues (obs 28).

       La forme 3 n'est un défaut **que tant qu'aucun `scripts/` ne vit à la racine du dépôt** :
       `python scripts/foo.py` relatif à la racine est la convention d'un workflow, et la
       population inclut `.github/`. Condition vérifiée le 2026-10-12 —
       `git ls-files "scripts/"` rend vide, et `ci.yml` ne cite que des modules de
       `apps/api/tests/`, qui relèvent de l'autre porte. Le jour où un `scripts/` racine
       apparaît, cette porte rougira sur un renvoi juste : la sortie est alors de résoudre la
       forme 3 contre la racine en dernier recours, pas d'écarter le fichier citant.

    Population recensée le 2026-10-12 sur `228d820`, avant que ce lot n'écrive une ligne de
    prose : **2 renvois, dont 1 cassé** — un de forme 1, un de forme 3, aucun de forme 2. La
    commande qui les rend, et qui doit rendre 2 :

        git grep -n "scripts/[a-z-]*\\.py" 228d820 -- \\
            ".claude/*.md" ".claude/**/*.md" "CLAUDE.md" "CONTRIBUTING.md" ".github/**/*"

    Le pathspec `".claude/*.md"` y est **en plus** de `HARNESS_PROSE_GLOBS` : le `**` de git
    exige au moins un composant et n'apparie pas `.claude/pipeline.config.md`, là où celui de
    `Path.glob` admet zéro composant et l'apparie (mesuré — voir `prose_citations`). Sans ce
    pathspec, la commande rend 1 et rate précisément le renvoi cassé qui motive la
    normalisation. Les trois formes sont éprouvées sur témoins par
    `test_chaque_forme_de_renvoi_vers_un_script_se_resout` : une porte dont une branche n'a
    jamais tourné ne garde rien, et la forme 2 n'avait aucune occurrence avant ce lot.

    **Ce que cette porte ne couvre pas**, et pourquoi on ne l'a pas élargie : elle apparie un
    chemin de *script*. Un renvoi vers un script écrit sans son dossier `scripts/` — « le
    harnais de mutation », « le bilan » — n'est gardé par rien, et aucun motif simple ne
    distingue une telle prose d'une phrase ordinaire. `HARNESS_PROSE_GLOBS` ne contient aucun
    glob de source Python, donc les renvois qui vivent dans les docstrings échappent à cette
    porte-ci, par le même arbitrage que la porte des renvois de `test_infra.py` — dont les globs
    en appariaient trois, par `infra/**/*`, sans que la phrase qui les décrivait le dise.

    La population est celle que le dépôt **contient** (`tracked_files()`), jamais celle du
    disque : un brouillon non suivi suffirait sinon à faire rougir chez une personne seule.
    """
    cited = cited_scripts(REPOSITORY_ROOT, tracked_files())

    assert cited, "aucun renvoi vers un script trouvé — le motif a-t-il cessé de mordre ?"
    missing = {
        target: sorted(where)
        for target, where in cited.items()
        if not (REPOSITORY_ROOT / target).exists()
    }
    assert not missing, f"{len(cited)} scripts cités, introuvables : {missing}"


# Le recueil de la classe : un témoin par **forme** de renvoi et par **glob** de la population,
# chacun (fichier citant, prose, chemin attendu). Ajouter une forme ou un glob, c'est ajouter une
# ligne — la porte s'étend, elle ne se modifie pas.
#
# Les clés sont en **ASCII** parce qu'elles deviennent des identifiants de cas pytest : un tiret
# cadratin ou un accent y est échappé en `—` dans le nom de nœud, et un `expect` de
# `mutation.py` — qui exige d'apparier exactement un test — devient alors impossible à écrire de
# mémoire. C'est la seule place du dépôt où un identifiant de test renonce à sa forme naturelle,
# et c'est l'outil qui l'impose, pas le style.
#
# Chaque témoin porte la profondeur et l'extension **réelles** de ce qu'il représente, pas un
# représentant commode : le glob `.github/**/*` existe pour les workflows `.yml` en profondeur 2,
# et un témoin `.md` en profondeur 1 le laissait vert quand on le restreignait aux `.md` (mutation
# vue VERTE). Un glob représenté par un fichier qui n'a ni sa profondeur ni son extension n'est
# pas représenté.
SCRIPT_REFERENCE_WITNESSES = {
    "forme-1-relative-dans-un-skill": (
        ".claude/skills/cycle-pr/SKILL.md",
        "python <répertoire de ce skill>/scripts/x.py",
        ".claude/skills/cycle-pr/scripts/x.py",
    ),
    "forme-2-depuis-la-racine-dans-un-role": (
        ".claude/agents/relecteur.md",
        "lance .claude/skills/cycle-pr/scripts/y.py",
        ".claude/skills/cycle-pr/scripts/y.py",
    ),
    "forme-3-orpheline-hors-skill": (
        ".claude/agents/orphelin.md",
        "lance scripts/z.py",
        "scripts/z.py",
    ),
    "glob-claude-md-a-la-racine": (
        ".claude/pipeline.config.md",
        "voir .claude/skills/cycle-pr/scripts/config.py",
        ".claude/skills/cycle-pr/scripts/config.py",
    ),
    "glob-CLAUDE.md": (
        "CLAUDE.md",
        "voir .claude/skills/cycle-pr/scripts/tete.py",
        ".claude/skills/cycle-pr/scripts/tete.py",
    ),
    "glob-CONTRIBUTING.md": (
        "CONTRIBUTING.md",
        "voir .claude/skills/cycle-pr/scripts/contrib.py",
        ".claude/skills/cycle-pr/scripts/contrib.py",
    ),
    "glob-github-yml-profondeur-2": (
        ".github/workflows/ci.yml",
        "run: python .claude/skills/cycle-pr/scripts/forge.py",
        ".claude/skills/cycle-pr/scripts/forge.py",
    ),
}


@pytest.mark.parametrize(
    ("citing", "prose", "expected"),
    SCRIPT_REFERENCE_WITNESSES.values(),
    ids=SCRIPT_REFERENCE_WITNESSES.keys(),
)
def test_chaque_forme_de_renvoi_vers_un_script_se_resout(
    tmp_path: Path, citing: str, prose: str, expected: str
) -> None:
    """**Dénombrement de la classe** : 3 formes de renvoi, 4 globs de population, 7 témoins.

    Une porte qui n'apparie qu'une forme laisse les autres vertes par absence : c'est la classe
    d'obs 63 — une règle formulée dans le vocabulaire de son premier domaine ne se déclenche pas
    sur la même forme ailleurs. Les trois formes sont donc éprouvées ici, sur témoins, et non
    sur le dépôt, où la forme 2 n'existait pas avant ce lot et où aucun renvoi ne vit hors de
    `.claude/`.

    Le dénombrement vit dans ce recueil et non dans une phrase : chaque ligne de
    `SCRIPT_REFERENCE_WITNESSES` est un cas exécutable, et retirer un glob de
    `HARNESS_PROSE_GLOBS` ou une branche de `script_target` rougit le cas qui lui correspond.
    C'est ce que la règle de `cleanup-verbatim.md` demande d'un dénombrement : épinglé dans
    l'artefact, pas déclaré à côté.

    **Ce que ce test ne dit pas** : combien de renvois vivent dans le dépôt. Ce recensement-là
    est une population **vivante** — il grossit à chaque lot qui cite un script —, donc il se
    date et se re-dérive par la commande que porte la porte, jamais par une assertion qui
    rougirait au prochain renvoi légitime.
    """
    path = tmp_path / citing
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prose, encoding="utf-8")

    assert cited_scripts(tmp_path, [citing]) == {expected: {path.name}}


def test_un_repertoire_dans_la_population_n_est_pas_lu(tmp_path: Path) -> None:
    """Le garde `is_file()` du collecteur partagé, et pourquoi il n'est pas mort.

    Sous la population que les portes emploient — `tracked_files()`, qui ne liste jamais de
    répertoire — ce garde est inatteignable, et la mutation qui le retire reste **VERTE**. Il
    redevient nécessaire dès qu'un glob apparie autre chose que des fichiers : `.github/**/*`
    apparie `.github/workflows`, et un appelant qui écrit sa population à la main y ferait
    lever `read_text`. Ce témoin est ce qui distingue un garde vivant d'un garde mort.
    """
    (tmp_path / ".github" / "workflows").mkdir(parents=True)

    assert cited_scripts(tmp_path, [".github/workflows"]) == {}


def test_le_relecteur_ne_declare_aucun_outil_d_ecriture_de_fichier() -> None:
    """Le rôle `relecteur` dit à son lecteur « tu n'as pas de `Write` » : la liste doit le tenir.

    Ce n'est pas qu'une phrase à garder vraie. Le mandat du rôle est de ne rien changer — « ne
    commit pas, ne pousse pas, ne corrige pas » —, et il en tire une conséquence pratique : un
    fichier de travail s'écrit par redirection, parce que le garde d'isolation refuse un
    heredoc. Ajouter `Write` à la liste rendrait la consigne fausse **en silence**, exactement
    la classe d'obs 50 : rien dans le harnais ne relit la prose d'un rôle contre son frontmatter.

    `Edit` reste : une mutation modifie un fichier existant, elle n'en crée pas.
    """
    frontmatter = FRONTMATTER.match(
        (REPOSITORY_ROOT / ".claude" / "agents" / "relecteur.md").read_text(encoding="utf-8-sig")
    )

    assert frontmatter, "le frontmatter de `relecteur` ne parse plus — voir la porte voisine"
    declared = cast(dict[str, object], yaml.safe_load(frontmatter.group("yaml"))).get("tools")
    assert isinstance(declared, str), f"`tools` absent ou non textuel : {declared!r}"
    assert "Write" not in declared, (
        f"`relecteur` déclare `Write` ({declared}) — son texte dit à son lecteur le contraire"
    )


@pytest.mark.parametrize("prose", FOREIGN_PREFIXES.values(), ids=FOREIGN_PREFIXES.keys())
def test_un_prefixe_de_chemin_etranger_n_est_pas_pris_pour_un_script_de_skill(
    tmp_path: Path, prose: str
) -> None:
    """Un renvoi juste vers un script qui n'est pas celui d'un skill ne doit rien déclencher.

    Sans ancrage à gauche, le motif appariait `scripts/<x>.py` au milieu du chemin et en jetait
    le préfixe : la porte rougissait sur `infra/scripts/deploy.py`, c'est-à-dire sur un renvoi
    correct. Le mode d'échec est le pire des deux possibles — une porte qui bloque la CI sur du
    travail juste est une porte qu'on apprend à contourner.

    Ce test est la face négative de `SCRIPT_REFERENCE_WITNESSES` : celui-là dit ce que la porte
    doit voir, celui-ci ce qu'elle doit ignorer. Une porte qui n'a que la face positive s'élargit
    sans fin, puisque rien ne mesure ce qu'elle attrape de trop.
    """
    citing = tmp_path / "CONTRIBUTING.md"
    citing.write_text(prose, encoding="utf-8")

    assert cited_scripts(tmp_path, ["CONTRIBUTING.md"]) == {}
