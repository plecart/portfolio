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

import ast
import re
import shlex
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import cast

import pytest
import yaml
from skill_scripts import load_script
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

# Les **trois** formes sous lesquelles un renvoi vers un script de skill apparaît :
#
# 1. **relative** (`<répertoire de ce skill>/scripts/x.py`, ou `scripts/x.py` nu) — la forme des
#    fichiers d'un skill, qui est recopié dans le seed où son chemin absolu diffère ; elle se
#    résout contre le dossier du skill qui porte le fichier citant, ou du skill voisin qu'elle
#    nomme (`<répertoire de ce skill>/../<skill>/scripts/x.py`) : l'amorçage d'`init-projet`
#    tourne avant que les skills soient copiés dans le projet ;
# 2. **depuis la racine** (`.claude/skills/<skill>/scripts/x.py`) — la forme d'un rôle ou d'une
#    règle, qui vit hors de l'arborescence des skills et n'a donc pas de dossier de référence ;
# 3. **préfixée par un nom de skill** (`cycle-pr/scripts/x.py`) — relative à `.claude/skills/`
#    sans le dire. C'est un défaut, et le seul qui se soit produit dans ce dépôt.
#
# Le motif capture le segment qui précède (`prefix`) **sans décider** : c'est `script_target` qui
# tranche, par `(.claude/skills/<prefix>).is_dir()`. Deux raisons. D'abord `cycle-pr/scripts/x.py`
# et `infra/scripts/x.py` ont **exactement la même forme** — aucun motif ne les distingue, et un
# ancrage qui refuse le premier refuse le second : mesuré, un ancrage `(?<![\w/-])` tuait la
# détection de la forme 3 dans sa seule orthographe réelle. Ensuite la distinction *est* décidable
# — par l'arborescence, c'est-à-dire par « la règle exacte de l'outil que la garde protège » que
# `cleanup-verbatim.md` prescrit au lieu d'un motif plus large (obs 28).
#
# L'ancrage qui reste, `(?<![\w-])`, empêche seulement d'apparier le milieu d'un segment
# (`monscripts/x.py`). Il laisse passer un `/`, donc un chemin absolu vers la forme 2 reste
# détecté.
SCRIPT_REFERENCE = re.compile(
    r"(?<![\w-])"
    r"(?:\.claude/skills/(?P<skill>[\w-]+)/"
    r"|<répertoire de ce skill>/(?:\.\./(?P<sibling>[\w-]+)/)?"
    r"|(?P<prefix>[\w.-]+)/)?"
    rf"{SCRIPTS_DIRECTORY}/(?P<script>[\w.-]+\.py)"
)

# Les préfixes qui ne nomment pas un skill : le renvoi ne concerne alors pas cette porte et
# s'ignore, au lieu de rougir sur un chemin juste. Dénombrement : 2 formes mesurées — un chemin
# d'infrastructure et un chemin applicatif. Noter que `[\w.-]+` s'arrête au `/`, donc
# `apps/api/scripts/seed.py` rend `prefix = "api"` : c'est sans effet, aucun skill ne s'appelle
# ainsi, et le jour où l'un s'appellerait `api` ce renvoi deviendrait un défaut à signaler.
FOREIGN_PREFIXES = {
    "chemin d-infrastructure": "voir infra/scripts/deploy.py pour le détail",
    "chemin applicatif": "lance apps/api/scripts/seed.py",
    # Ce qu'il reste à l'ancrage, et lui seul : `scripts/` au milieu d'un segment. Mesuré —
    # sans `(?<![\w-])`, `monscripts/x.py` rend `scripts/x.py`, introuvable, donc un rouge sur
    # un chemin qui n'a rien à voir. Les deux cas ci-dessus, eux, sont désormais écartés par
    # `is_dir()` et non par l'ancrage : sans ce troisième témoin, retirer l'ancrage ne faisait
    # plus rien rougir (mutation vue VERTE).
    "segment-englobant": "voir monscripts/x.py",
}


def script_target(root: Path, citing: Path, reference: re.Match[str]) -> str | None:
    """Le chemin, relatif à `root` et en POSIX, du script que ce renvoi désigne.

    Args:
        root: la racine du dépôt.
        citing: le fichier de prose qui porte le renvoi.
        reference: l'appariement de `SCRIPT_REFERENCE`.

    Returns:
        Le chemin visé, ou `None` si l'appariement ne concerne pas un script de skill — un
        préfixe qui ne nomme aucun dossier de `.claude/skills/`. Un renvoi de forme 3, ou un
        renvoi relatif porté par un fichier qui ne vit pas sous un skill, est rendu **sans
        base** : il ne désigne alors aucun fichier, et la porte le rapporte introuvable, ce qui
        est le but — c'est ainsi que la forme 3 se fait normaliser en forme 2.
    """
    script = reference.group("script")
    # La base se dérive de `root`, jamais d'une constante de module : la porte est appelée sur le
    # dépôt **et** sur des témoins en répertoire temporaire, et une base figée sur le dépôt rend
    # les branches relatives muettes chez le témoin — les seules qui les éprouvent.
    skills = root / ".claude" / "skills"
    if skill := reference.group("skill") or reference.group("sibling"):
        return f".claude/skills/{skill}/{SCRIPTS_DIRECTORY}/{script}"
    if prefix := reference.group("prefix"):
        if not (skills / prefix).is_dir():
            return None
        return f"{SCRIPTS_DIRECTORY}/{script}"
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
        if (target := script_target(root, citing, reference)) is not None:
            cited.setdefault(target, set()).add(citing.name)
    return cited


def test_chaque_script_cite_par_la_prose_du_harnais_existe() -> None:
    """Un script renommé laisse derrière lui des renvois que rien ne suit.

    **Dénombrement de la classe, écrit avant le premier correctif** (`cycle-pr` Étape 4.2,
    cliquet). Les renvois vers un script se répartissent en **3 formes**, dont `script_target`
    résout les 2 **canoniques** et laisse la 3ᵉ introuvable :

    1. **relative**, dans les fichiers d'un skill (`<répertoire de ce skill>/scripts/x.py`, ou
       `scripts/x.py` nu) — résolue contre le dossier du skill qui porte le fichier citant, ou
       du skill voisin qu'elle nomme (`<répertoire de ce skill>/../<skill>/scripts/x.py`) ;
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
# Chaque témoin porte l'**orthographe réelle** de ce qu'il représente, pas un représentant
# commode. Mesuré deux fois, dans les deux directions : le glob `.github/**/*` existe pour les
# workflows `.yml` en profondeur 2, et un témoin `.md` en profondeur 1 le laissait vert quand on
# le restreignait aux `.md` ; la forme 3 ne s'est produite que **préfixée par un nom de skill**
# (`cycle-pr/scripts/x.py`), et un témoin qui l'écrivait nue (`scripts/z.py`) a laissé un ancrage
# tuer sa détection sans rien faire rougir. Les deux orthographes de la forme 3 sont donc des cas
# distincts. Un témoin qui n'a ni la profondeur, ni l'extension, ni l'orthographe de ce qu'il
# représente ne le représente pas.
SCRIPT_REFERENCE_WITNESSES = {
    "forme-1-relative-dans-un-skill": (
        ".claude/skills/cycle-pr/SKILL.md",
        "python <répertoire de ce skill>/scripts/x.py",
        ".claude/skills/cycle-pr/scripts/x.py",
    ),
    "forme-1-vers-un-skill-voisin": (
        ".claude/skills/init-projet/SKILL.md",
        "python <répertoire de ce skill>/../cycle-pr/scripts/v.py",
        ".claude/skills/cycle-pr/scripts/v.py",
    ),
    "forme-2-depuis-la-racine-dans-un-role": (
        ".claude/agents/relecteur.md",
        "lance .claude/skills/cycle-pr/scripts/y.py",
        ".claude/skills/cycle-pr/scripts/y.py",
    ),
    "forme-2-precedee-d-un-chemin": (
        "CONTRIBUTING.md",
        "python E:/Projets/Portfolio/.claude/skills/cycle-pr/scripts/abs.py",
        ".claude/skills/cycle-pr/scripts/abs.py",
    ),
    "forme-3-prefixee-par-un-nom-de-skill": (
        ".claude/pipeline.config.md",
        "(`cycle-pr/scripts/mutation.py`, fonction `rewrite`)",
        "scripts/mutation.py",
    ),
    "forme-3-orpheline-sans-prefixe": (
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
    """**Dénombrement de la classe** : 3 formes en 6 orthographes, 4 globs, 10 témoins.

    Une porte qui n'apparie qu'une orthographe laisse les autres vertes par absence : c'est la
    classe d'obs 63 — une règle formulée dans le vocabulaire de son premier domaine ne se
    déclenche pas sur la même forme ailleurs. Toutes sont donc éprouvées ici, sur témoins, et non
    sur le dépôt, où la forme 2 n'existait pas avant ce lot et où aucun renvoi ne vit hors de
    `.claude/`.

    Le dossier `.claude/skills/cycle-pr/` est créé dans chaque cas, vide : c'est lui qui rend la
    forme 3 décidable. `script_target` ne tranche pas sur l'orthographe du préfixe mais sur son
    existence comme dossier de skill — sans ce dossier, le même texte serait un préfixe étranger
    et s'ignorerait (voir `FOREIGN_PREFIXES`).

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
    (tmp_path / ".claude" / "skills" / "cycle-pr").mkdir(parents=True)
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


def role_frontmatter(role: str) -> dict[str, object]:
    """Le frontmatter d'un rôle de `.claude/agents/`, parsé.

    Args:
        role: le nom du fichier du rôle, sans son extension.

    Returns:
        Les champs que ce rôle déclare.

    Raises:
        AssertionError: le fichier est absent, ou son frontmatter ne parse pas — les deux états
            où une affirmation sur ce frontmatter passerait pour une raison étrangère à elle.
    """
    path = REPOSITORY_ROOT / ".claude" / "agents" / f"{role}.md"
    assert path.is_file(), f"rôle introuvable : {path}"
    frontmatter = FRONTMATTER.match(path.read_text(encoding="utf-8-sig"))
    assert frontmatter, f"le frontmatter de `{role}` ne parse plus — voir la porte voisine"
    fields: object = yaml.safe_load(frontmatter.group("yaml"))
    assert isinstance(fields, dict), f"le frontmatter de `{role}` n'est pas un mapping"
    return cast(dict[str, object], fields)


# Ce que la **prose** d'un rôle affirme de son propre frontmatter — et que rien ne relit (obs 50) :
# `claude plugin validate` est muet sur le frontmatter d'un rôle (mesuré le 2026-10-09 sur
# v2.1.295), et aucune porte ne confronte le texte d'un rôle aux champs qu'il déclare.
#
# Une ligne par affirmation : le rôle, le champ, et le fragment que ce champ ne doit **pas**
# porter — `None` quand c'est le champ entier qui doit être absent ou nul. Ajouter une
# affirmation, c'est ajouter une ligne : la porte s'étend, elle ne se modifie pas.
#
# Deux provenances, à ne pas mélanger. La **population** est mécanique : les rôles **suivis** que
# `git ls-files ".claude/agents/*.md"` rend — 4 au 2026-10-13, le quatrième étant `verificateur`.
# La commande compte l'index, pas le disque : lancée avant le `git add` du rôle qu'on ajoute, elle
# rend un de moins, et c'est la bonne population (celle du dépôt, comme `tracked_files()`).
# Les **affirmations**, elles, se *lisent* — aucune commande ne distingue « ma prose affirme un
# champ » d'une phrase ordinaire —, donc chacune ci-dessous est citée par sa phrase, **verbatim**
# du fichier nommé. C'est la seule provenance que cette table accepte, et une citation reformulée
# y est un défaut au même titre qu'un champ faux : mesuré, la première rédaction attribuait au
# `verificateur` une phrase (« Tu ne travailles pas dans un worktree ») qui n'existait nulle part.
ROLE_FRONTMATTER_CLAIMS: list[tuple[str, str, str | None]] = [
    # « Le sous-agent n'a pas de `Write` » (`relecteur.md`) — et `Edit` reste : une mutation
    # modifie un fichier existant, elle n'en crée pas. La session de relecture a `Write` : elle
    # n'écrit aucun fichier du dépôt, tenue par son texte.
    ("relecteur", "tools", "Write"),
    # « tu n'écris rien » (`verificateur.md`) : le mandat est un verdict, pas un correctif.
    ("verificateur", "tools", "Write"),
    # « Tu n'as **pas** de worktree » (`verificateur.md`) : c'est ce qui le garde bon marché, et un
    # `isolation` déclaré en ferait créer un à chaque (PR, go).
    ("verificateur", "isolation", None),
    # « Tu n'as pas `Write` : la sortie y va par redirection » (`releveur.md`).
    ("releveur", "tools", "Write"),
    # « Tu n'as pas d'accès web » (`releveur.md`, « Lectures bornées ») : une page arbitraire est
    # une entrée non fiable pour un rôle qui a `Bash` et `Edit` (relecture de la PR #151, I4).
    ("releveur", "tools", "WebFetch"),
    ("releveur", "tools", "WebSearch"),
    # « Tes outils sont `Bash, Read, Grep, Glob, Edit, Write` et les deux de `context7` : ni `Skill`
    # ni `playwright` » (`developpeur.md`) — sans liste, il recevrait tous les outils, `playwright`
    # compris.
    ("developpeur", "tools", "playwright"),
    # Même phrase : `ponytail` se lit par `Read`, la liste des skills ne pèse pas sur son plancher.
    ("developpeur", "tools", "Skill"),
]


# Les identifiants de cas se **dérivent** des valeurs, jamais d'une clé saisie à la main : sous une
# clé écrite à part, remplacer `("verificateur", "isolation", None)` par un autre rôle laissait le
# cas vert sous un nom qui annonçait toujours `verificateur` (mesuré, mutation VERTE). Un
# identifiant qui ne dérive pas de ce qu'il nomme est un commentaire, pas une étiquette.
@pytest.mark.parametrize(
    ("role", "field", "forbidden"),
    ROLE_FRONTMATTER_CLAIMS,
    ids=[f"{role}-{field}-{forbidden}" for role, field, forbidden in ROLE_FRONTMATTER_CLAIMS],
)
def test_le_frontmatter_d_un_role_tient_ce_que_sa_prose_affirme(
    role: str, field: str, forbidden: str | None
) -> None:
    """Une affirmation qu'un rôle fait sur son propre frontmatter doit rougir quand elle devient
    fausse.

    Ce n'est pas qu'une phrase à garder vraie. Chaque rôle tire de son frontmatter une
    conséquence pratique que son lecteur applique sans la revérifier — le `relecteur` écrit ses
    fichiers de travail par redirection *parce qu'il* n'a pas de `Write` ; le `verificateur`
    n'écrit rien et ne se détache sur aucune tête *parce qu'il* partage l'arbre vivant de la
    session, n'ayant pas de worktree. Changer le champ rendrait la consigne fausse **en
    silence**, exactement la classe d'obs 50.

    La table est paramétrée, et non répliquée en un test par rôle : l'affirmation de frontmatter
    est une **classe**, pas la propriété d'un rôle. Née sur le seul `relecteur`, elle a eu son
    deuxième et son troisième membre dès le rôle suivant.
    """
    declared = role_frontmatter(role).get(field)

    if forbidden is None:
        assert declared is None, (
            f"`{role}` déclare `{field}: {declared!r}` — sa prose dit le contraire"
        )
        return
    assert isinstance(declared, str), (
        f"`{field}` absent ou non textuel chez `{role}` : {declared!r}"
    )
    assert forbidden not in declared, (
        f"`{role}` déclare `{field}: {declared}` — son texte dit à son lecteur le contraire"
    )


# L'autre sens : un outil que la prose d'un rôle lui fait employer, et que sa liste `tools:` doit
# donc nommer. Même provenance que la table précédente, citation verbatim du fichier nommé.
ROLE_REQUIRED_TOOLS: list[tuple[str, str]] = [
    # « par `context7` ou les sources du paquet » (`developpeur.md`, « Frontières tierces »).
    ("developpeur", "mcp__context7__resolve-library-id"),
    ("developpeur", "mcp__context7__query-docs"),
    # « lu dans sa documentation à jour (`context7`) » (`relecteur.md`, point 3).
    ("relecteur", "mcp__context7__resolve-library-id"),
    ("relecteur", "mcp__context7__query-docs"),
    # « une question sur une bibliothèque, écrite par ton appelant, posée à `context7` »
    # (`releveur.md`, « Ce que tu fais »).
    ("releveur", "mcp__context7__resolve-library-id"),
    ("releveur", "mcp__context7__query-docs"),
]


@pytest.mark.parametrize(
    ("role", "tool"),
    ROLE_REQUIRED_TOOLS,
    ids=[f"{role}-{tool}" for role, tool in ROLE_REQUIRED_TOOLS],
)
def test_la_liste_d_outils_d_un_role_nomme_ceux_que_sa_prose_emploie(role: str, tool: str) -> None:
    """Une liste `tools:` fermée retire **en silence** tout outil qu'elle ne nomme pas.

    Le rôle lit alors une consigne qu'il ne peut plus suivre, et se rabat sur une autre voie sans
    le savoir. Relevé à la passe 2 de la PR #136 : la liste posée au `developpeur` pour borner son
    plancher lui retirait `context7`, que `CLAUDE.md` met en priorité pour toute question de
    bibliothèque — aucune porte ne le voyait.

    Dénombré le 2026-10-20 sur les cinq rôles (`grep` de `^tools:` puis des outils nommés par la
    prose) : deux rôles se font prescrire un outil absent de leur liste, `developpeur` et
    `relecteur`, tous deux pour `context7` — 2 fuyaient sur 2. Un rôle neuf qui en prescrit un
    s'ajoute à `ROLE_REQUIRED_TOOLS` : le `releveur`, à qui `triage` délègue une question de
    bibliothèque depuis le lot 6a2 de #134 (2026-10-23) — 3 rôles, 6 couples.
    """
    declared = role_frontmatter(role).get("tools")
    assert isinstance(declared, str), f"`tools` absent ou non textuel chez `{role}` : {declared!r}"

    assert tool in [name.strip() for name in declared.split(",")], (
        f"`{role}` ne déclare pas `{tool}` — sa prose le lui fait employer"
    )


def test_seul_le_releveur_demarre_sans_claude_md() -> None:
    """« Ces textes ne te sont pas chargés » (`releveur.md`, « Ce que tu n'appliques pas ») et
    « Le `releveur`, seul rôle à porter `omitClaudeMd: true` » (`CLAUDE.md`, « Orchestration »).

    `omitClaudeMd: true` retire au sous-agent `CLAUDE.md` et les règles inconditionnelles de
    `.claude/rules/` (code.claude.com/docs/en/sub-agents, lu le 2026-10-28) : son corps reprend ce
    qu'il en tirait (« Lire borné »). Le champ retiré, la phrase deviendrait fausse en silence et
    `CLAUDE.md` et les règles reviendraient dans son contexte au premier appel (lot 3 de #177) ;
    posé sur un autre rôle, il lui retirerait des règles que son corps ne reprend pas. Un rôle qui
    le reçoit à dessein s'ajoute à l'ensemble attendu.
    """
    assert {
        path.stem for path in AGENTS if role_frontmatter(path.stem).get("omitClaudeMd") is True
    } == {"releveur"}


# Le modèle et l'effort d'un rôle s'écrivent à trois endroits : son frontmatter, sa ligne de la
# table « Orchestration » de `CLAUDE.md`, et la première ligne de son corps, qui dit si son mandat
# contient des décisions — le critère d'éligibilité au modèle le moins cher (obs 66). Aucune des
# trois ne se dérive d'une autre ici : c'est leur **accord** qui est sous test. Mesuré à la passe 1
# de la PR #87 : rôle repassé en `effort: low`, rôle d'Opus passé sur Sonnet, table repassée en
# effort `low` — trois mutations VERTES sur toute cette suite, alors que l'incohérence que le lot 4
# de #77 a corrigée à la main était exactement la première.
ORCHESTRATION_ROW = re.compile(
    r"^\| `(?P<role>[a-z]+)` \| (?P<model>[A-Za-z]+)(?:, effort `(?P<effort>[a-z]+)`)? \|",
    re.MULTILINE,
)
MANDATE_LINE = re.compile(
    r"\A\*\*Ton mandat (?P<verdict>ne contient aucune décision|contient des décisions)"
)
# Le seul modèle d'un mandat qui tranche, écrit en littéral. Tout autre est moins cher, donc
# réservé au mandat sans décision : comparer au modèle le moins cher de la table laissait passer
# un rôle qui tranche, déplacé sur un modèle plus modeste encore (sonde `haiku` VERTE, passe 2 de
# la PR #87).
DECIDING_MODEL = "opus"


def orchestration_table() -> dict[str, tuple[str, str | None]]:
    """Le couple (modèle, effort) que la table « Orchestration » de `CLAUDE.md` donne à chaque rôle.

    Le modèle est rendu en minuscules, comme le frontmatter l'écrit ; l'effort vaut `None` quand
    la ligne n'en porte pas, comme un frontmatter qui ne déclare pas le champ.
    """
    text = (REPOSITORY_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    return {
        row["role"]: (row["model"].lower(), row["effort"])
        for row in ORCHESTRATION_ROW.finditer(text)
    }


def role_body(role: str) -> str:
    """Le corps d'un rôle, frontmatter retiré et blancs de tête ôtés."""
    text = (REPOSITORY_ROOT / ".claude" / "agents" / f"{role}.md").read_text(encoding="utf-8-sig")
    frontmatter = FRONTMATTER.match(text)
    assert frontmatter, f"le frontmatter de `{role}` ne parse plus — voir la porte voisine"
    return text[frontmatter.end() :].lstrip()


def test_la_table_d_orchestration_couvre_exactement_les_roles_du_depot() -> None:
    """Une ligne de table sans rôle, ou un rôle sans ligne, sort des deux tests suivants en silence.

    Les cas de ceux-là se tirent des fichiers de rôle ; c'est ce test-ci qui garde l'autre sens.
    """
    assert set(orchestration_table()) == {path.stem for path in AGENTS}


@pytest.mark.parametrize("path", AGENTS, ids=[label(path) for path in AGENTS])
def test_la_table_d_orchestration_et_le_frontmatter_d_un_role_disent_le_meme_modele(
    path: Path,
) -> None:
    """La table de `CLAUDE.md` choisit l'équipier ; le frontmatter le fait tourner.

    Qu'ils divergent, et le lead délègue en croyant un effort que le rôle n'applique pas, ou un
    modèle que le rôle ne porte pas — sans qu'aucune des deux lectures ne paraisse fausse seule.
    """
    fields = role_frontmatter(path.stem)
    declared = (str(fields.get("model")).lower(), fields.get("effort"))
    listed = orchestration_table().get(path.stem)

    assert listed == declared, (
        f"`CLAUDE.md` donne à `{path.stem}` {listed}, son frontmatter {declared}"
    )


@pytest.mark.parametrize("path", AGENTS, ids=[label(path) for path in AGENTS])
def test_un_role_dit_en_tete_s_il_tranche_et_son_modele_le_suit(path: Path) -> None:
    """« Chaque rôle dit en tête de son fichier s'il tranche » (`CLAUDE.md`, critère d'éligibilité).

    Et ce qu'il en dit commande son modèle : un mandat qui tranche reste sur Opus, un mandat sans
    décision va à un modèle moins cher. Un rôle qui change de modèle sans que sa première ligne
    suive — ou l'inverse — rend fausse la seule phrase que son lecteur lit d'abord.
    """
    head = MANDATE_LINE.match(role_body(path.stem))
    assert head, (
        f"`{path.stem}` ne dit pas en tête de son corps si son mandat contient des décisions"
    )
    model = str(role_frontmatter(path.stem).get("model")).lower()

    assert (head["verdict"] == "ne contient aucune décision") == (model != DECIDING_MODEL), (
        f"`{path.stem}` est sur `{model}` et dit « {head['verdict']} »"
    )


# Un rôle n'existe que là où une étape le nomme (D5 de #134, obs 119) : `executant`, né à
# l'amorçage, n'avait jamais été lancé — 0 sur 89 sous-agents relevés le 2026-10-19 —, et
# `developpeur` n'avait aucun déclencheur écrit. La table « Orchestration » gardée ci-dessus décrit
# une intention ; les tests qui suivent gardent le branchement.
SKILL_PROSE = ".claude/skills/**/*.md"
ROLE_NAMES = [path.stem for path in AGENTS]

# La seule mention de rôles qui n'est pas une délégation : l'entrée `.claude/agents/` de la liste
# des fichiers qu'`init-projet` copie. Elle se retire du texte lu, et nulle part ailleurs.
ROLE_FILE_LIST = re.compile(r"^- `\.claude/agents/` \([^)]*\)", re.MULTILINE)

# Le paragraphe « Maison » de `.claude/pipeline.config.md`, « Skills du projet ».
HOUSE_SKILLS_PARAGRAPH = re.compile(r"^\*\*Maison\*\*.*?\n\n", re.MULTILINE | re.DOTALL)

# Les treize skills maison, en littéral ; un test garde l'égalité avec la config.
HOUSE_SKILLS = (
    "init-projet",
    "vers-prd",
    "vers-issues",
    "triage",
    "interroge-moi",
    "cycle-pr",
    "contradiction",
    "repercussions",
    "pr-paralleles",
    "plan-qa",
    "execution-qa",
    "bug-vers-issue",
    "audit-spec-ui",
)


def cites_role(text: str, role: str) -> bool:
    """Vrai si `text` nomme `role` entre accents graves, sous son nom exact (`` `releveur` ``)."""
    return f"`{role}`" in text


def cites_an_executor(text: str, roles: Iterable[str]) -> bool:
    """Vrai si `text` nomme l'un des `roles` entre accents graves ou renvoie à un script de skill.

    Le renvoi de script se lit par `SCRIPT_REFERENCE` et se résout par `script_target`, comme dans
    la porte des scripts cités : un préfixe qui ne nomme aucun skill (`infra/scripts/x.py`) ne
    désigne pas un script de skill, donc pas un exécutant.
    """
    return any(cites_role(text, role) for role in roles) or any(
        script_target(REPOSITORY_ROOT, REPOSITORY_ROOT, reference) is not None
        for reference in SCRIPT_REFERENCE.finditer(text)
    )


def delegating_text(path: Path) -> str:
    """Le texte d'un fichier de skill, la liste de fichiers d'`init-projet` retirée."""
    return ROLE_FILE_LIST.sub("", path.read_text(encoding="utf-8"))


def skills_citing(role: str) -> list[str]:
    """Les fichiers de skill qui nomment `role` hors liste de fichiers — chemins depuis la racine."""
    return [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in sorted(REPOSITORY_ROOT.glob(SKILL_PROSE))
        if cites_role(delegating_text(path), role)
    ]


def skill_prose(skill: str) -> str:
    """Le `SKILL.md` d'un skill et ses références, mis bout à bout, liste de fichiers retirée."""
    files = sorted((REPOSITORY_ROOT / ".claude/skills" / skill).glob("**/*.md"))
    assert files, f"`{skill}` n'a aucun fichier Markdown — le nom est-il juste ?"
    return "\n".join(delegating_text(path) for path in files)


@pytest.mark.parametrize("path", AGENTS, ids=[label(path) for path in AGENTS])
def test_chaque_role_est_nomme_par_un_skill(path: Path) -> None:
    """D5 : chaque rôle de `.claude/agents/` est nommé par au moins un fichier de skill.

    Dénombrement au 2026-10-20 sur `e70e279` (avant le lot 2a) : 5 rôles, 3 nommés (`relecteur`,
    `verificateur` et `executant`, ce dernier par la seule ligne des mineurs de `cycle-pr` 4.2),
    2 jamais (`developpeur`, `releveur`). Le témoin d'un rôle fictif est le test suivant.
    """
    assert skills_citing(path.stem), f"`{path.stem}` n'est nommé par aucun skill : rien ne le lance"


def test_ni_un_role_fictif_ni_la_liste_d_init_projet_ne_comptent_pour_une_citation() -> None:
    """Témoins du précédent, sur la prose réelle : un rôle fictif ne trouve aucun fichier, et la
    liste de fichiers d'`init-projet`, qui nomme tous les rôles, n'est jamais comptée — l'entrée
    entière, jusqu'à l'entrée suivante, ne cite plus aucun exécutant une fois retirée."""
    assert skills_citing("fantome") == []
    # `init-projet` ne nomme `verificateur` que dans sa liste de fichiers.
    assert INIT_PROJET_SKILL not in skills_citing("verificateur")
    init_projet = (REPOSITORY_ROOT / INIT_PROJET_SKILL).read_text(encoding="utf-8")
    liste = ROLE_FILE_LIST.search(init_projet)
    assert liste, (
        "la liste de fichiers d'`init-projet` a changé de forme : `ROLE_FILE_LIST` ne la voit plus"
    )
    assert all(cites_role(liste.group(0), role) for role in ROLE_NAMES)
    entree = init_projet[liste.start() : init_projet.index("\n- ", liste.start())]
    assert not cites_an_executor(ROLE_FILE_LIST.sub("", entree), ROLE_NAMES)


# Le recueil de `cites_an_executor`, des deux côtés.
EXECUTOR_CITATION_FORMS = {
    "rôle entre accents graves": ("lancer un `releveur` par porte", True),
    "rôle fictif": ("lancer un `fantome` par porte", False),
    "nom nu": ("lancer un releveur par porte", False),
    "nom d'un fichier de rôle": ("lire `releveur.md` d'abord", False),
    "renvoi de script": ("python <répertoire de ce skill>/scripts/merge-lot.py <n>", True),
    "script étranger aux skills": ("voir infra/scripts/deploy.py pour le détail", False),
}


@pytest.mark.parametrize(
    ("text", "expected"),
    EXECUTOR_CITATION_FORMS.values(),
    ids=EXECUTOR_CITATION_FORMS.keys(),
)
def test_une_citation_d_executant_se_reconnait(text: str, expected: bool) -> None:
    assert cites_an_executor(text, ROLE_NAMES) is expected


def test_les_skills_maison_du_test_sont_ceux_de_la_config() -> None:
    """Un skill maison ajouté à la config sans l'être ici échapperait au second paramétrage."""
    config = (REPOSITORY_ROOT / ".claude/pipeline.config.md").read_text(encoding="utf-8")
    paragraph = HOUSE_SKILLS_PARAGRAPH.search(config)
    assert paragraph, "le paragraphe « Maison » de `pipeline.config.md` a changé de forme"

    assert set(re.findall(r"`([a-z-]+)`", paragraph.group(0))) == set(HOUSE_SKILLS)


@pytest.mark.parametrize("skill", HOUSE_SKILLS)
def test_chaque_skill_maison_nomme_ses_executants(skill: str) -> None:
    """Second paramétrage de D5 : un skill maison nomme un rôle ou un script.

    Au 2026-10-20 sur `e70e279`, deux sur treize (`cycle-pr`, `pr-paralleles`) ; trois au
    2026-10-23 sur `34604c7` avec `triage` (lot 6a2, bloc 1), six au commit suivant avec
    `interroge-moi`, `vers-prd` et `vers-issues` (bloc 2), sept le 2026-10-23 avec `repercussions`
    (lot 6b, bloc 1), neuf le 2026-10-25 avec `bug-vers-issue` et `contradiction` (lot 6b2), dix
    le 2026-10-26 avec `plan-qa` (lot 7a), onze le même jour avec `execution-qa` (lot 7b2), douze
    le même jour avec `audit-spec-ui` (lot 8b), treize sur treize avec `init-projet` (lot 8b) : la
    liste d'attente qui exemptait les autres, vide, est retirée avec son cliquet.
    """
    assert cites_an_executor(skill_prose(skill), ROLE_NAMES), (
        f"`{skill}` ne nomme aucun rôle ni aucun script"
    )


# Les skills dont la prose n'écrit plus sur la forge que par l'écriture distante relue (#134,
# lot 4) : chaque lot de #134 y ajoute les siens — le lot 6a2 `triage`, `interroge-moi`, `vers-prd`
# et `vers-issues` ; le lot 6b `repercussions` (bloc 1) ; le lot 6b2 `bug-vers-issue` et
# `contradiction` ; le lot 7a `plan-qa` ; le lot 7b2 `execution-qa` ; le lot 8b `audit-spec-ui`
# et `init-projet`.
SKILLS_SANS_ECRITURE_GH_DIRECTE = (
    "triage",
    "interroge-moi",
    "vers-prd",
    "vers-issues",
    "repercussions",
    "bug-vers-issue",
    "contradiction",
    "plan-qa",
    "execution-qa",
    "audit-spec-ui",
    "init-projet",
)
ECRITURE_RELUE = ".claude/skills/cycle-pr/scripts/ecriture-relue.py"
# Les skills de la table précédente qui n'écrivent sur aucune issue, chacun avec sa raison : le
# renvoi au script y serait sans objet (lot 6b2 de #134, 2026-10-25 ; lot 8b, 2026-10-26).
ECRITURE_RELUE_SANS_OBJET = {
    "contradiction": (
        "n'écrit sur aucune issue : ses PR d'amendement suivent les étapes 5 et 6 de"
        " `triage/hors-scope.md`, et la propagation aux issues passe par `repercussions`"
    ),
    "audit-spec-ui": "n'écrit sur aucune issue : ses corrections partent par une PR (D-12)",
}

# Une commande `gh` citée, jusqu'à son accent grave fermant ou sa fin de ligne.
GH_COMMAND = re.compile(r"(?<![\w-])gh\s+(?P<group>[a-z][\w-]*)(?P<args>[^`\n]*)")
# Les verbes tenus pour une lecture ; tout autre verbe d'un groupe de `gh` est tenu pour une
# écriture : un faux positif rougit, une écriture manquée se tairait.
GH_READ_VERBS = frozenset({"view", "list"})
GH_API_METHOD = re.compile(r"(?:-X|--method)[\s=]*(?P<method>[A-Za-z]+)")
# Ce qui fait passer `gh api` en POST sans `--method` : un champ ou un corps — « if
# !opts.RequestMethodPassed && (len(params) > 0 || opts.RequestInputFile != "") { method = "POST" »
# (`apiRun`, cli/cli `pkg/cmd/api/api.go`, lu par `context7` le 2026-10-23 ; `gh api --help`,
# gh 2.94.0). Une requête GraphQL passe en POST de même : elle n'écrit que par une `mutation`.
GH_API_PAYLOAD = re.compile(r"(?<![\w-])(?:-[fF]|--raw-field|--field|--input)(?![\w-])")
# Un merge n'écrit pas de contenu à relire : `--match-head-commit` fait vérifier la tête par la
# forge avant d'agir (`gh pr merge --help`, gh 2.94.0), la garde de `cycle-pr` Étape 7.
GH_GUARDED_MERGE = re.compile(r"^\s*merge\b.*--match-head-commit\b")


def gh_command_writes(group: str, args: str) -> bool:
    """Vrai si la commande `gh <group><args>` écrit sur la forge sans garde."""
    if group == "pr" and GH_GUARDED_MERGE.search(args):
        return False
    if group != "api":
        return next(iter(args.split()), "") not in GH_READ_VERBS
    if "graphql" in args.split():
        return "mutation" in args
    if method := GH_API_METHOD.search(args):
        return method["method"].upper() != "GET"
    return GH_API_PAYLOAD.search(args) is not None


def gh_writes(text: str) -> list[str]:
    """Les commandes `gh` d'écriture que `text` cite, une ligne continuée par `\\` rejointe."""
    return [
        command.group(0).strip()
        for command in GH_COMMAND.finditer(text.replace("\\\n", " "))
        if gh_command_writes(command["group"], command["args"])
    ]


# Le recueil de `gh_writes`, des deux côtés.
GH_COMMAND_FORMS = {
    "issue create": ("`gh issue create --title A --body-file corps.md`", True),
    "issue edit": ('`gh issue edit <n> --milestone "A"`', True),
    "issue close": ("`gh issue close <n>`", True),
    "issue comment": ("`gh issue comment <n> --body-file notes.md`", True),
    "issue reopen": ("`gh issue reopen <n>`", True),
    "label create": ("`gh label create needs-triage`", True),
    "label edit": ("`gh label edit bug --color f00`", True),
    "pr comment": ("`gh pr comment <n> --body-file notes.md`", True),
    "pr edit": ("`gh pr edit <n> --add-label bug`", True),
    "pr merge sans garde": ("`gh pr merge <n> --rebase`", True),
    "pr merge garde": ("`gh pr merge <n> --rebase --match-head-commit <SHA relu>`", False),
    "api avec champ": ('gh api "repos/{owner}/{repo}/milestones" -f title="A"', True),
    "api avec methode": ("`gh api -X PATCH repos/{owner}/{repo}/issues/<n>`", True),
    "api avec corps": ("`gh api repos/{owner}/{repo}/issues/<n> --input -`", True),
    "api mutation": ("`gh api graphql -f query='mutation { addComment }'`", True),
    "ligne continuee": ('gh api "repos/{owner}/{repo}/issues/<n>" \\\n  -X PATCH', True),
    "issue view": ("`gh issue view <n> --json state`", False),
    "issue list": ("`gh issue list --label needs-triage`", False),
    "api lecture": ("`gh api \"repos/{owner}/{repo}/milestones\" --jq '.[]'`", False),
    "api graphql lecture": ("`gh api graphql -f query='{ repository { … } }'`", False),
    "api GET avec champ": ("`gh api -X GET search/issues -f q=x`", False),
    "pr list": ("`gh pr list`", False),
    "pr view": ("`gh pr view`", False),
    "gh nu": ("publié par `gh`", False),
    "mot en gh": ("les ghosts du dépôt", False),
}


@pytest.mark.parametrize(
    ("text", "expected"), GH_COMMAND_FORMS.values(), ids=GH_COMMAND_FORMS.keys()
)
def test_une_ecriture_gh_se_reconnait(text: str, expected: bool) -> None:
    assert bool(gh_writes(text)) is expected


@pytest.mark.parametrize("skill", SKILLS_SANS_ECRITURE_GH_DIRECTE)
def test_un_skill_sans_ecriture_gh_directe_n_en_cite_aucune(skill: str) -> None:
    """Une écriture `gh` directe n'est pas relue (`contraintes.md`, « Écritures sur un artefact
    distant ») : au 2026-10-23 sur `aba63e1`, `triage` en portait quatre, toutes dans
    `themes-milestones.md`, `vers-issues` une (`gh issue edit <n> --milestone`), `interroge-moi`
    et `vers-prd` aucune — leurs écritures n'y étaient décrites qu'en prose. Le 2026-10-23 (lot 6b,
    bloc 1), `repercussions` une : le `gh api -X PATCH` de son brief. Le 2026-10-25 (lot 6b2),
    `bug-vers-issue` deux (`gh issue create`, `gh label create`), `contradiction` aucune. Le
    2026-10-26 (lot 7a), `plan-qa` trois (`gh issue create` ×2, `gh label create`) ; le même jour
    (lot 7b2), `execution-qa` trois sur `ffbe52e` — `gh issue comment` de
    `gabarit-commentaire-phase.md`, `gh issue edit --body-file` et la mention `gh issue edit` de
    `patch-checkbox-gh.md` —, rendus par `gh_writes` sur les cinq fichiers à ce commit. Le même
    jour (lot 8b), `audit-spec-ui` aucune sur `0c408db`, `init-projet` quatre — `gh repo create`,
    `gh label create`, les deux `gh pr ready` —, rendues par `gh_writes`.

    **Population** : `SKILLS_SANS_ECRITURE_GH_DIRECTE`, le `SKILL.md` et les références de chacun.
    **Ce que le détecteur ne voit pas** : une écriture décrite sans commande (« publie un
    commentaire ») — le dénombrement de la PR la couvre, une entrée par geste prescrit — et une
    commande dont ce qui écrit, drapeau ou `mutation`, tient sur une ligne suivante sans `\\` final.
    """
    writes = gh_writes(skill_prose(skill))

    assert not writes, f"`{skill}` écrit par `gh` : {writes}"


def cites_ecriture_relue(skill: str) -> bool:
    """Vrai si la prose de `skill` cite `ECRITURE_RELUE`, résolu depuis son `SKILL.md`."""
    citing = REPOSITORY_ROOT / ".claude/skills" / skill / "SKILL.md"
    return ECRITURE_RELUE in {
        script_target(REPOSITORY_ROOT, citing, reference)
        for reference in SCRIPT_REFERENCE.finditer(skill_prose(skill))
    }


@pytest.mark.parametrize(
    "skill",
    [skill for skill in SKILLS_SANS_ECRITURE_GH_DIRECTE if skill not in ECRITURE_RELUE_SANS_OBJET],
)
def test_un_skill_sans_ecriture_gh_directe_cite_l_ecriture_relue(skill: str) -> None:
    """Le revers du précédent : ses écritures nomment le script qui les relit."""
    assert cites_ecriture_relue(skill), f"`{skill}` ne cite pas `{ECRITURE_RELUE}`"


@pytest.mark.parametrize("skill", ECRITURE_RELUE_SANS_OBJET)
def test_une_exemption_du_renvoi_a_l_ecriture_relue_reste_sans_objet(skill: str) -> None:
    """Le cliquet de l'exemption : elle ne vaut que pour un skill de la table, qui ne cite pas le
    script — le jour où il le cite, l'exemption tombe."""
    assert skill in SKILLS_SANS_ECRITURE_GH_DIRECTE, f"`{skill}` est exempté hors de la table"
    assert not cites_ecriture_relue(skill), (
        f"`{skill}` cite `{ECRITURE_RELUE}` : retire-le d'`ECRITURE_RELUE_SANS_OBJET`"
    )


# `git diff A..B` compare deux **arbres** ; ce n'est pas une plage de commits. Entre le trunk et la
# tête, il compte donc en sens inverse tout ce que le trunk a reçu depuis le point de fork — le
# gabarit d'une PR franchit alors ses seuils à tort dès que `main` avance. La forme qui mesure la
# branche est à **trois** points, `main...HEAD`, qui part de la base de fusion. Mesuré à la passe 2
# de la PR #87 : `446a3a6` dans le rôle d'un `main` avancé, `e89e19b` dans celui de la branche —
# deux points rendent 6 fichiers et 173 suppressions, trois points rendent un diff vide.
#
# La classe est la **plage adossée au nom du trunk**, pas la commande : une plage nue remise à un
# relecteur, qui la diffe, fuit autant que le `git diff` du gabarit. Seul `git log` la lit juste
# (les commits de la branche) ; trois points y seraient faux à leur tour (différence symétrique),
# d'où, pour une plage qui sert aux deux, `<base>..HEAD` avec `<base>` le point de fork.
# Dénombrement, sur la prose du harnais au 2026-10-14 : **5** plages à deux points adossées au
# trunk, **5** fuyaient — les 2 `git diff` du gabarit (`cycle-pr` 3.5, `taille-pr.md`, passe 2),
# et 3 plages nues de `cycle-pr` 4.1 et 4.2 que le premier motif, limité au préfixe `git diff`, ne
# voyait pas (relance). Justes et hors classe : 2 croisements déjà à trois points
# (`verificateur.md`, `pr-paralleles`), 1 diff depuis un SHA **ancêtre** de la tête.
# Borne déclarée : le motif lit les plages **entre accents graves**, la forme de toute commande de
# cette prose ; une plage écrite hors code lui échappe.
TRUNK_TWO_DOTS = re.compile(
    r"`(?!git log\b)[^`\n]*?(?<![\w/<>.-])(?:origin/)?(?:main|<trunk>)\.\.(?!\.)"
)

TRUNK_TWO_DOTS_FORMS = {
    "gabarit à deux points": ("`git diff --stat main..HEAD`", True),
    "trunk distant à deux points": ("`git diff origin/main..HEAD`", True),
    "trunk générique à deux points": ("`git diff --stat origin/<trunk>..HEAD`", True),
    "plage nue remise au relecteur": ("la plage `main..HEAD` et le SHA", True),
    "plage nue du trunk distant": ("(`origin/<trunk>..HEAD`)", True),
    "gabarit à trois points": ("`git diff --stat main...HEAD`", False),
    "plage de commits de git log": ("`git log --oneline main..HEAD`", False),
    "diff depuis un ancêtre de la tête": ("`git diff <sha de la vérification>..HEAD`", False),
    "plage depuis le point de fork": ("la plage `<base>..HEAD`", False),
}


@pytest.mark.parametrize(
    ("prose", "flagged"), TRUNK_TWO_DOTS_FORMS.values(), ids=TRUNK_TWO_DOTS_FORMS
)
def test_le_motif_des_plages_du_trunk_ne_vise_que_les_deux_points(
    prose: str, flagged: bool
) -> None:
    """Le motif mord sur les cinq écritures fautives, et sur aucune voisine juste.

    Les voisines comptent autant que les fautives : `git log main..HEAD` **est** la plage de
    commits de la branche, un diff depuis un ancêtre de la tête n'a pas de base de fusion à
    prendre, et `<base>..HEAD` est la forme prescrite — rougir sur l'une d'elles ferait corriger
    un texte juste.
    """
    assert bool(TRUNK_TWO_DOTS.search(prose)) is flagged


def test_aucune_plage_adossee_au_trunk_ne_s_ecrit_a_deux_points() -> None:
    """La prose du harnais prescrit des commandes et des plages qu'un agent tape telles quelles."""
    found = [
        f"{path.relative_to(REPOSITORY_ROOT).as_posix()} : {match.group(0)}"
        for path, match in prose_citations(
            REPOSITORY_ROOT, tracked_files(), HARNESS_PROSE_GLOBS, TRUNK_TWO_DOTS
        )
    ]

    assert not found, (
        f"plage du trunk à deux points — `main...HEAD` pour un diff, `<base>..HEAD` pour une "
        f"plage remise : {found}"
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

    Le dossier `.claude/skills/cycle-pr/` existe ici aussi, et c'est le cœur du cas : la prose
    `infra/scripts/deploy.py` a **exactement la même forme** que `cycle-pr/scripts/mutation.py`,
    que le témoin positif exige de voir. Seule l'existence du dossier les distingue — un ancrage,
    lui, les refuse ou les accepte ensemble, et c'est mesuré : un ancrage qui fermait ce faux
    rouge a tué du même coup la détection de la forme 3.
    """
    (tmp_path / ".claude" / "skills" / "cycle-pr").mkdir(parents=True)
    citing = tmp_path / "CONTRIBUTING.md"
    citing.write_text(prose, encoding="utf-8")

    assert cited_scripts(tmp_path, ["CONTRIBUTING.md"]) == {}


def test_plusieurs_fichiers_citant_une_meme_cible_sont_tous_rapportes(tmp_path: Path) -> None:
    """La carte « cible → fichiers citants » agrège, elle n'écrase pas.

    Le dépôt a une cible citée par trois fichiers, et c'est cette carte qui fait le message
    d'échec de la porte : écrasée, elle ne nommerait qu'un seul coupable sur trois. Le recueil
    paramétré ne peut pas l'épingler — un cas y vaut un fichier —, donc ce cas vit à côté, et la
    mutation `cited[target] = {citing.name}` le rend rouge.
    """
    for nom in ("CLAUDE.md", "CONTRIBUTING.md"):
        (tmp_path / nom).write_text("voir .claude/skills/cycle-pr/scripts/x.py", encoding="utf-8")

    cited = cited_scripts(tmp_path, ["CLAUDE.md", "CONTRIBUTING.md"])

    assert cited == {".claude/skills/cycle-pr/scripts/x.py": {"CLAUDE.md", "CONTRIBUTING.md"}}


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Lance `git` dans `repo`, **sans shell**, et rend le processus terminé.

    Sans shell à dessein : sur le poste Windows, MSYS réécrit certains arguments avant que git ne
    les voie — un `<rev>:<chemin>` devient un chemin, `git show` rend zéro octet, et le résultat se
    lit comme « fichier différent » au lieu de « rien lu ».

    Args:
        repo: le dépôt dans lequel lancer la commande.
        *args: les arguments de `git`, sans le nom du programme.

    Returns:
        Le processus terminé, code de sortie compris — jamais `check=True` : ici le **code de
        sortie est la mesure**, pas un incident.
    """
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture(scope="module")
def gate_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Un dépôt jetable portant les trois états qu'une porte de fraîcheur doit distinguer.

    Trois références, toutes sur la même ligne du même fichier pour que la fusion morde :
    le tag `base` (l'état que la PR a vérifié), la branche `trunk` (le trunk qui a avancé depuis)
    et la branche `lateral` (une autre PR de la vague, en conflit avec `trunk`).
    """
    repo = tmp_path_factory.mktemp("portes")
    git(repo, "init", "-q", "-b", "trunk")
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-qm", "base")
    git(repo, "tag", "base")
    git(repo, "branch", "lateral")
    (repo / "f.txt").write_text("avance\n", encoding="utf-8")
    git(repo, "commit", "-qam", "avance")
    git(repo, "checkout", "-q", "lateral")
    (repo / "f.txt").write_text("autre\n", encoding="utf-8")
    git(repo, "commit", "-qam", "autre")
    return repo


# Le motif de recensement du docstring ci-dessous est volontairement **sans `--quiet`** : cette
# alternative n'appariait aucune des 17 lignes de la population, et une alternative morte fait
# chercher une famille de portes qui n'existe pas.
#
# Les codes de sortie sur lesquels repose la **forme** que `cycle-pr` et `pr-paralleles`
# prescrivent pour une porte de fraîcheur : une commande dont le code de sortie porte la
# condition, `&&` la rendant bloquante. Une commande qui **imprime** n'est pas une porte, et le
# dernier cas ci-dessous est ce qui le mesure — `rev-parse` rend deux SHA différents en sortant
# en 0, donc l'action enchaînée part quand même (obs 69, l'incident d'origine).
#
# Le cas « ancêtre strict » est la **borne** de la forme, pas un détail : `--is-ancestor` dit
# « ancêtre ou égal », donc un seul appel ne distingue l'égalité du retard que dans un sens. C'est
# pourquoi les skills chaînent **deux** prédicats, un par direction, partout où l'égalité est la
# condition (création de branche, création de worktree) — et un seul là où le trunk n'avance que
# vers l'avant (le merge, obs 60).
#
# Le cas « référence inconnue » est la borne du prédicat `merge-tree` : il sort en 1 comme sur un
# conflit, là où sa documentation promet un autre code à toute erreur. Un 1 ne prouve donc un
# conflit que sur des références validées d'abord — ce que fait le script de croisement de
# `pr-paralleles` §7 (mesuré le 2026-10-21, git 2.47.1, lot 4b de #134).
FRESHNESS_GATE_FORMS = {
    "is-ancestor-rend-0-sur-deux-refs-egales": (
        ("merge-base", "--is-ancestor", "trunk", "trunk"),
        0,
    ),
    "is-ancestor-rend-1-quand-le-trunk-a-avance": (
        ("merge-base", "--is-ancestor", "trunk", "base"),
        1,
    ),
    "is-ancestor-rend-0-sur-un-ancetre-strict": (
        ("merge-base", "--is-ancestor", "base", "trunk"),
        0,
    ),
    "merge-tree-rend-0-sans-conflit": (("merge-tree", "--write-tree", "base", "trunk"), 0),
    "merge-tree-rend-1-avec-conflit": (("merge-tree", "--write-tree", "trunk", "lateral"), 1),
    "merge-tree-rend-1-sur-une-reference-inconnue": (
        ("merge-tree", "--write-tree", "trunk", "nope"),
        1,
    ),
    "rev-parse-rend-0-sur-deux-SHA-differents": (("rev-parse", "base", "trunk"), 0),
}


def references_resolues(repo: Path, *refs: str) -> dict[str, str]:
    """Les SHA de ces références, par un `rev-parse --verify` dont le **code de sortie** décide.

    Lire `stdout` seul ne suffit pas, et c'est mesuré : sans `--verify`, `git rev-parse <absente>`
    écrit le **nom de la référence** sur stdout en sortant en 128 — trois références inexistantes
    rendraient donc trois valeurs non vides et distinctes. C'est la classe du principe transverse
    n° 1 : une seule méthode qui conclut n'est pas une mesure.

    Args:
        repo: le dépôt où résoudre.
        *refs: les références attendues résolubles.

    Returns:
        Chaque référence et son SHA.

    Raises:
        AssertionError: une référence ne résout pas — l'état même que le témoin doit exclure.
    """
    resolues: dict[str, str] = {}
    for ref in refs:
        done = git(repo, "rev-parse", "--verify", ref)
        assert done.returncode == 0, (
            f"`{ref}` ne résout pas dans {repo} ({done.returncode}) : {done.stderr.strip()}"
        )
        resolues[ref] = done.stdout.strip()
    return resolues


def test_le_depot_temoin_porte_bien_trois_etats_distincts(gate_repo: Path) -> None:
    """Le témoin positif du dépôt jetable : sans lui, les codes de sortie ne prouvent rien.

    Trois références égales rendraient 0 partout, et la table ci-dessous se lirait comme une
    mesure. Dénombrement de la classe sur ce delta : **2** lectures de la sortie d'une commande
    git, **1** fuyait — l'autre est la table ci-dessous, où le code de sortie *est* la mesure.
    """
    heads = references_resolues(gate_repo, "base", "trunk", "lateral")

    assert len(set(heads.values())) == 3, f"les trois références ne sont pas distinctes : {heads}"


def test_une_reference_absente_est_refusee_par_la_resolution(tmp_path: Path) -> None:
    """Le correctif du témoin, épinglé — sans ce cas-ci, rien ne le gardait.

    Le témoin ci-dessus ne peut pas prouver son propre correctif : sa fixture construit toujours
    les trois références, donc l'état où la lecture de `stdout` seul mentait n'y existe pas, et
    retirer `--verify` l'y laissait **VERT** (mesuré). Ce cas crée cet état — un dépôt neuf, sans
    aucune référence — et c'est lui qui rougit si la résolution cesse de lire le code de sortie.
    """
    git(tmp_path, "init", "-q", "-b", "trunk")

    with pytest.raises(AssertionError, match="ne résout pas"):
        references_resolues(tmp_path, "base")


@pytest.mark.parametrize(
    ("args", "expected"),
    FRESHNESS_GATE_FORMS.values(),
    ids=FRESHNESS_GATE_FORMS.keys(),
)
def test_la_porte_de_fraicheur_porte_sa_condition_dans_son_code_de_sortie(
    gate_repo: Path, args: tuple[str, ...], expected: int
) -> None:
    """**Dénombrement de la classe « une porte qui ne garde pas », écrit avant le premier
    correctif** (`cycle-pr` 4.2, cliquet).

    Recensement du 2026-10-13 sur **`c459f04`**, la base du lot — l'état *avant* le premier
    correctif, qui est le seul où la classe se dénombre. **15 sites**, en 17 lignes appariées
    plus **un site que le motif ne voit pas** :

        git grep -c -E "rev-parse|merge-base|merge-tree|doit rendre|rend deux fois|is-ancestor" \
            c459f04 -- .claude/skills/cycle-pr/SKILL.md .claude/skills/pr-paralleles/SKILL.md \
            .claude/agents/ .claude/rules/

    Elle rend `relecteur.md:2`, `cycle-pr/SKILL.md:8`, `pr-paralleles/SKILL.md:7` — 17 lignes pour
    14 contrôles distincts (deux lignes de `cycle-pr` sont des **renvois** aux deux
    auto-vérifications du `relecteur`, et deux lignes de `pr-paralleles` décrivent la même porte,
    en prose puis en bloc de commandes). **La révision est dans la commande à dessein** : sans
    elle, le même grep grossit à chaque commit de ce lot, qui nomme ces commandes pour les
    prescrire — 20 lignes dès `5cd7bf7`, où `verificateur.md` en ajoute 3.

    Répartition : **4 relevés** (une datation de preuve, qui ne garde aucune action), **1 sonde**
    d'outillage, et **10 portes**, dont **6 fuyaient** en étant écrites comme un affichage —
    création de branche, création de worktree, le merge lui-même, et les trois `merge-tree`, qui
    étaient déjà des prédicats sans être employés comme tels.

    Le motif **sous-compte, et sur le site qui compte le plus** : la porte de merge de `cycle-pr`
    Étape 7 ne nommait **aucune** commande (« refaire le contrôle de base »), donc aucun grep ne
    pouvait l'apparier. Un recensement par motif d'une classe « porte absente » est par
    construction une borne inférieure, et c'est l'inverse de ce dont on a besoin.

    **4 portes restent des lectures, avec leur raison** — ce n'est pas un reste à faire :
    trois (les deux auto-vérifications du `relecteur`, la vérification de placement d'une session
    pair) sont suivies d'une **phase entière** de travail et non d'une commande unique, donc il
    n'y a rien à quoi se chaîner ; la quatrième (`gh pr view --json state,headRefOid` avant
    `git branch -D`) compare les valeurs de **deux outils**, ce qui exige une substitution de
    commande — refusée par le garde d'une session isolée (obs 60). Ce qu'elle garde est une
    suppression locale, récupérable par le reflog. Le lot 3 de #107 retire la vérification de
    placement avec son geste : le lead ne place plus de session, l'application le fait.

    Ce test n'éprouve pas du code du projet : il **établit** les affirmations que les deux skills
    font sur ces commandes. Il passe donc dès sa première exécution, et c'est attendu
    (`cycle-pr` 3.1, premier cas) — le rouge se constate en mutant un code attendu de la table,
    pas en retirant du code de production.
    """
    done = git(gate_repo, *args)

    assert done.returncode == expected, (
        f"`git {' '.join(args)}` rend {done.returncode} au lieu de {expected} — "
        f"sortie : {done.stdout.strip()!r} / {done.stderr.strip()!r}"
    )


# Chaque site qui lit le code de `git merge-tree` comme un prédicat sur une référence qui peut
# manquer, et la phrase qui y borne le 1 — le cas `merge-tree-rend-1-sur-une-reference-inconnue`.
MERGE_TREE_SUR_UNE_REFERENCE_INCONNUE = {
    "pr-paralleles-croisement": (
        ".claude/skills/pr-paralleles/SKILL.md",
        "`merge-tree` sort en 1 aussi sur une référence inconnue",
    ),
    "script-de-croisement": (
        ".claude/skills/pr-paralleles/scripts/croisement-fichiers.py",
        "`git merge-tree`, qui sort en 1 sur une référence inconnue comme sur un conflit",
    ),
    "coordinatrice-derive": (
        ".claude/skills/cycle-pr/references/coordinatrice.md",
        "mais 1 aussi sur une référence inconnue, sortie standard vide",
    ),
    "verificateur-conflit": (
        ".claude/agents/verificateur.md",
        "Il sort en **1** aussi sur une référence inconnue",
    ),
}


@pytest.mark.parametrize(
    ("fichier", "phrase"),
    MERGE_TREE_SUR_UNE_REFERENCE_INCONNUE.values(),
    ids=MERGE_TREE_SUR_UNE_REFERENCE_INCONNUE.keys(),
)
def test_un_1_de_merge_tree_n_est_un_conflit_que_sur_des_references_qui_existent(
    fichier: str, phrase: str
) -> None:
    """**Dénombrement de la classe « `merge-tree` lu comme 0 sans conflit, 1 avec », pris avant
    le premier correctif** (cleanup holistique du lot 4b de #134, sur `37e0846`) :

        git grep -n "merge-tree" 37e0846 -- .claude/ CLAUDE.md CONTRIBUTING.md .github/

    rend 19 lignes, toutes sous `.claude/`. **5 sites**, en 8 lignes, y lisent le code comme un
    prédicat ; **4** sont bornés ci-dessus — `pr-paralleles` §7 et la docstring du script de
    croisement au bloc D, la dérive de la coordinatrice et le §4 du `verificateur` à ce cleanup —
    et **1** est laissé : `cycle-pr` Étape 7 compare `origin/<trunk>` et `HEAD`, deux références
    que tout clone porte après le `git fetch origin` qui précède, et son `&&` bloque sur tout 1.
    Les 11 autres lignes ne lisent pas le 1 : le code rendu tel quel du `releveur`, le gabarit du
    verdict du `verificateur`, le `merge-tree` à 0 que `cycle-pr` Étape 7 prête à la
    coordinatrice, ses deux contrôles « lus », et le code et la sortie du script.
    """
    assert phrase in texte_normalise(fichier), f"`{fichier}` ne borne plus le 1 de `merge-tree`"


# Les portes que les skills **prescrivent** : le fichier, l'action que la porte garde, et le
# prédicat qui doit la précéder — sur **une seule ligne**, reliés par `&&`.
#
# `FRESHNESS_GATE_FORMS` épingle les **codes de sortie de git**, un fait tiers qui ne régresse
# jamais. Cette table-ci épingle la **forme écrite dans les skills**, qui a régressé **trois** fois
# (obs 59, 60, 69). Les deux sont nécessaires, et c'est mesuré : rendre l'Étape 1 à
# `git rev-parse main origin/main`, ou scinder la porte de merge en deux commandes, laissait la
# première table entièrement VERTE.
#
# **Ce que cette porte ne couvre pas**, borné à dessein : elle exige qu'une forme gardée
# **existe**, pas qu'aucune forme non gardée ne subsiste ailleurs dans le fichier. Un second
# passage qui prescrirait la même action sans porte ne rougirait pas — aucun motif ne distingue une
# prescription d'une mention en prose, et la prose de ces skills cite les formes fautives à dessein
# pour les condamner. C'est le cas où `cleanup-verbatim.md` demande de **borner** plutôt que
# d'élargir un motif qui imite un analyseur.
# Le quatrième champ est le **nombre** de prédicats attendus : 2 là où la condition est l'égalité
# (création de branche — un par direction, parce que `--is-ancestor` dit « ancêtre ou égal »), 1
# au merge, où le trunk n'avance que vers l'avant. Sans ce champ, ramener la porte à un
# seul prédicat — le bloquant de la passe 1, « `main` en avance passe » — restait VERT (mesuré,
# passe 2) : la table exigeait qu'un prédicat existe, pas qu'il y en ait deux. Le prédicat de
# conversation (#197) a sa ligne à lui : une porte qui en chaîne deux d'outils différents se lit
# une fois par prédicat, chacun compté seul.
PORTES_PRESCRITES: list[tuple[str, str, str, int]] = [
    (".claude/skills/cycle-pr/SKILL.md", "git checkout -b", "git merge-base --is-ancestor", 2),
    (".claude/skills/cycle-pr/SKILL.md", "gh pr merge", "git merge-base --is-ancestor", 1),
    (".claude/skills/cycle-pr/SKILL.md", "gh pr merge", "porte-merge.py conversation", 1),
    (".claude/skills/triage/hors-scope.md", "gh pr merge", "porte-merge.py conversation", 1),
    (
        ".claude/skills/cycle-pr/references/sessions-liees.md",
        "git branch -D",
        "git merge-base --is-ancestor",
        1,
    ),
    (
        ".claude/skills/cycle-pr/references/session-relecture.md",
        "git branch -D",
        "git merge-base --is-ancestor",
        1,
    ),
]


def predicats_a_gauche(ligne: str, action: str, predicat: str) -> list[list[str]]:
    """Les arguments de chaque prédicat placé à gauche de l'action sur cette ligne, dans l'ordre.

    Args:
        ligne: une ligne de prose de skill.
        action: la commande que la porte garde.
        predicat: la commande dont le code de sortie porte la condition.

    Returns:
        Une liste par occurrence du prédicat à gauche de l'action — ses arguments, jusqu'au `&&`
        qui le chaîne —, vide si rien ne chaîne. Chaque prédicat doit porter **son** `&&`, et le
        texte qui touche l'action doit finir par `&&` : un `;` entre le dernier prédicat et
        l'action n'est pas une chaîne, même si un `&&` apparaît plus à gauche — mesuré à la relance,
        `git fetch origin && git merge-base … ; gh pr merge …` passait pour une porte.
    """
    gauche = ligne.split(action)[0]
    if not gauche.rstrip().endswith("&&"):
        return []
    return [
        segment.split("&&")[0].split() for segment in gauche.split(predicat)[1:] if "&&" in segment
    ]


@pytest.mark.parametrize(
    ("skill", "action", "predicat", "attendus"),
    PORTES_PRESCRITES,
    ids=[
        f"{Path(skill).parent.name if Path(skill).stem == 'SKILL' else Path(skill).stem}"
        f"-{action.replace(' ', '-')}-{predicat.split()[-1].lstrip('-')}"
        for skill, action, predicat, _ in PORTES_PRESCRITES
    ],
)
def test_chaque_porte_prescrite_est_un_predicat_chaine_a_son_action(
    skill: str, action: str, predicat: str, attendus: int
) -> None:
    """Une porte réécrite en affichage, scindée de son action, ou ramenée à un seul prédicat ne
    rougissait nulle part.

    C'est le cliquet de la classe : `cleanup-verbatim.md` exige qu'un correctif qui ferme un chemin
    soit « épinglé dans l'artefact par un test paramétré, pas par une phrase de docstring ». Le
    dénombrement de la classe vit dans
    `test_la_porte_de_fraicheur_porte_sa_condition_dans_son_code_de_sortie`. Des 6 portes qui
    fuyaient, cette table en épinglait **3** : celles que la prose prescrit en **bloc de
    commandes**, où une action unique suit le prédicat. Les 3 `merge-tree` sont des prédicats
    nommés en prose sans action unique en bloc — pas épinglables par cette forme, et c'est dit, pas
    tu. Elle en épinglait une **quatrième**, née après ce dénombrement et hors de sa population :
    la porte d'ancêtre qui précède la suppression d'un échafaudage `claude/…` (`sessions-liees.md`,
    lot 1 de #107, relecture de la PR #109). **Elle en épingle 3 depuis le lot 3 de #107**, qui
    retire la création de worktree de `pr-paralleles` avec son geste : le lead ne crée plus de
    worktree, l'application en donne un à chaque session, dont le premier geste part d'`origin/`
    (`DEPARTS_EXPLICITES`) — la porte n'avait plus d'action à garder, et son absence est gardée
    par `GESTES_RETIRES_DE_PR_PARALLELES`. **4 depuis le lot 3 de #134** : le retrait de la
    branche du sous-agent `relecteur`, en repli, passe de `git branch -d` — qui compare à `HEAD`
    et refuse dès que le trunk a avancé (obs 86) — à la porte d'ancêtre contre `origin/<trunk>`
    (`session-relecture.md`, « Repli »). **5 portes en 6 lignes depuis #197**, qui chaîne le
    prédicat de conversation (`porte-merge.py conversation`) devant `gh pr merge` : dans la porte
    de `cycle-pr` Étape 7, à côté de celle d'ancêtre, et dans le déroulé de
    `triage/hors-scope.md`, étape 6, qui n'en avait aucune.

    Le prédicat doit se trouver **à gauche de l'action sur la même ligne**, avec un `&&` entre les
    deux — ce qui distingue une porte d'une lecture suivie d'une seconde commande (obs 59) —, en
    **autant d'exemplaires** que la table l'exige, et pour deux exemplaires, avec les **deux ordres
    d'arguments** : deux prédicats dans le même sens couvrent la même direction deux fois. Les
    lignes de prose qui *citent* les formes fautives pour les condamner ne peuvent pas apparier,
    puisqu'elles ne nomment pas `git merge-base --is-ancestor`.
    """
    lignes = (REPOSITORY_ROOT / skill).read_text(encoding="utf-8-sig").splitlines()
    nommant = [ligne for ligne in lignes if action in ligne]
    trouves = [predicats_a_gauche(ligne, action, predicat) for ligne in nommant]
    conformes = [
        args
        for args in trouves
        if len(args) == attendus and (attendus == 1 or args[0] == args[1][::-1])
    ]

    assert nommant, f"`{skill}` ne nomme plus `{action}` — le motif a-t-il cessé de mordre ?"
    assert conformes, (
        f"`{skill}` ne prescrit `{action}` derrière {attendus} `{predicat}` chaîné(s) par `&&` "
        f"— les deux ordres d'arguments pour deux — sur aucune de ses {len(nommant)} ligne(s) qui "
        f"le nomment ; trouvé : {trouves}"
    )


# Les créations de branche **hors porte** — celles qu'une session fait depuis le worktree d'une
# issue en lots, donc depuis la branche **mergée** du lot précédent — doivent nommer leur point de
# départ : `git checkout -b <nouvelle> origin/<trunk>`. Sans lui, `checkout -b` part de HEAD et
# emporte les commits réécrits du lot mort (mesuré : 1 commit emporté, 0 depuis `origin/main`).
# Le bloquant B-1 de la passe 2 s'était fermé dans la prose sans cliquet, et la relance l'a
# mesuré : retirer `origin/<trunk>` du gabarit restait VERT — la seconde fois dans ce lot qu'un
# bloquant se ferme sans test (I-1 avant lui).
#
# Population : les commandes entre backticks qui commencent par `git checkout -b <`, dans les
# fichiers où une session peut être **ailleurs que sur `main`** — 4 depuis le lot 1 de #107, qui
# ajoute le premier geste d'un enfant placé sur l'échafaudage `claude/…` d'un worktree de
# l'application (`sessions-liees.md`), 5 depuis le lot 2b, qui ajoute la branche d'intégration et
# celle d'un lot (`coordinatrice.md`). Deux formes nues existent à
# dessein et n'entrent pas ici : `taille-pr.md`, qui nomme la convention de branche, et le bloc de
# commandes de `cycle-pr` Étape 1, qui crée la branche **sur `main`**, derrière la porte à deux
# prédicats — un bloc n'est pas entre backticks, donc le motif ne le voit pas. La prose qui
# *condamne* la forme nue n'a pas de `<` derrière `-b`, et n'apparie pas non plus.
DEPARTS_EXPLICITES = [
    ".claude/skills/cycle-pr/references/prompt-lot-suivant.md",
    ".claude/skills/pr-paralleles/SKILL.md",
    ".claude/skills/cycle-pr/SKILL.md",
    ".claude/skills/cycle-pr/references/sessions-liees.md",
    ".claude/skills/cycle-pr/references/coordinatrice.md",
]
# Le préfixe optionnel `git fetch origin && ` admet le premier geste de `sessions-liees.md`, écrit
# en une seule commande ; il reste ancré au backtick ouvrant, si bien qu'un bloc de commandes —
# dont les lignes ne commencent pas par un backtick — n'apparie toujours pas.
CHECKOUT_CITE = re.compile(r"`(?:git fetch origin && )?git checkout -b \\?<[^`]*`")


@pytest.mark.parametrize(
    "fichier",
    DEPARTS_EXPLICITES,
    ids=[f"{Path(f).parent.name}-{Path(f).name}" for f in DEPARTS_EXPLICITES],
)
def test_chaque_creation_de_branche_hors_porte_nomme_son_point_de_depart(fichier: str) -> None:
    """Une création de branche sans `origin/` dans un fichier où l'on n'est pas sur `main` est la
    branche du lot précédent qui continue — ce que `pr-paralleles` Étape 8 interdit en toutes
    lettres, et que rien ne tenait."""
    texte = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8-sig")
    commandes = CHECKOUT_CITE.findall(texte)
    sans_depart = [commande for commande in commandes if "origin/" not in commande]

    assert commandes, (
        f"`{fichier}` ne cite plus `git checkout -b <…>` entre backticks — le motif a-t-il cessé "
        "de mordre ?"
    )
    assert not sans_depart, (
        f"création de branche sans point de départ dans `{fichier}` : {sans_depart}"
    )


# Le protocole des sessions liées (#107, lot 1) vit dans une référence unique, que les skills qui
# le suivent citent sans le recopier (obs 52) : un skill qui perd son renvoi applique de mémoire ce
# que la référence fixe — héritage du mode, identité, premier geste, signal de fin.
SESSIONS_LIEES = "references/sessions-liees.md"
SKILLS_DES_SESSIONS_LIEES = [
    ".claude/skills/cycle-pr/SKILL.md",
    ".claude/skills/pr-paralleles/SKILL.md",
    ".claude/skills/interroge-moi/SKILL.md",
    ".claude/skills/triage/SKILL.md",
    ".claude/skills/vers-prd/SKILL.md",
    ".claude/skills/vers-issues/SKILL.md",
    ".claude/skills/repercussions/SKILL.md",
    ".claude/skills/contradiction/SKILL.md",
    ".claude/skills/bug-vers-issue/SKILL.md",
    ".claude/skills/plan-qa/SKILL.md",
    ".claude/skills/execution-qa/SKILL.md",
]


@pytest.mark.parametrize(
    "skill", SKILLS_DES_SESSIONS_LIEES, ids=[Path(s).parent.name for s in SKILLS_DES_SESSIONS_LIEES]
)
def test_chaque_skill_des_sessions_liees_cite_leur_reference(skill: str) -> None:
    """Le renvoi existe dans le skill, et la référence qu'il vise existe sur le disque."""
    texte = (REPOSITORY_ROOT / skill).read_text(encoding="utf-8-sig")

    assert (REPOSITORY_ROOT / ".claude/skills/cycle-pr" / SESSIONS_LIEES).is_file()
    assert SESSIONS_LIEES in texte, f"`{skill}` ne cite plus `{SESSIONS_LIEES}`"


COORDINATRICE_REF = ".claude/skills/cycle-pr/references/coordinatrice.md"
PR_PARALLELES_SKILL = ".claude/skills/pr-paralleles/SKILL.md"
INTERROGE_MOI_SKILL = ".claude/skills/interroge-moi/SKILL.md"
CYCLE_PR_SKILL = ".claude/skills/cycle-pr/SKILL.md"
PORTES_REF = ".claude/skills/cycle-pr/references/portes.md"
TRIAGE_SKILL = ".claude/skills/triage/SKILL.md"
HORS_SCOPE_REF = ".claude/skills/triage/hors-scope.md"
VERS_ISSUES_SKILL = ".claude/skills/vers-issues/SKILL.md"
REPERCUSSIONS_SKILL = ".claude/skills/repercussions/SKILL.md"
CONTRADICTION_SKILL = ".claude/skills/contradiction/SKILL.md"
CONTRAINTES_RULE = ".claude/rules/contraintes.md"
BUG_VERS_ISSUE_SKILL = ".claude/skills/bug-vers-issue/SKILL.md"
BRIEF_AGENT_REF = ".claude/skills/triage/brief-agent.md"
EXECUTION_QA_SKILL = ".claude/skills/execution-qa/SKILL.md"
PLAN_QA_SKILL = ".claude/skills/plan-qa/SKILL.md"
INIT_PROJET_SKILL = ".claude/skills/init-projet/SKILL.md"
GABARIT_PLAN_QA_REF = ".claude/skills/plan-qa/references/gabarit-plan-qa.md"
EXEMPLE_BLOC_ISSUE_REF = ".claude/skills/plan-qa/references/exemple-bloc-issue.md"


# `gh … list --help` cite la doc de l'outil, il ne liste rien : hors population.
LISTE_GH = re.compile(r"gh (?:issue|pr) list(?! --help)[^`\n]*")


def test_chaque_liste_gh_de_pr_paralleles_porte_sa_limite() -> None:
    """Sans `--limit`, `gh issue list` et `gh pr list` s'arrêtent à 30 (`gh issue list --help`) :
    un crible tronqué en silence ne propose pas l'issue qu'il n'a pas lue.

    **Dénombrement, écrit avant le correctif** (relecture de la PR #133, passe 1, m-2) : 4 sites
    dans `pr-paralleles` — crible de l'étape 0, étape 1, tableau de l'étape 4, bilan de vague —,
    dont 1 borné par `fd6678f`. **Bornes** : ce fichier seul ; les autres skills en ont d'autres,
    hors du lot (Notes de la PR #133). Un site s'écrit sur une ligne : une commande coupée par `\\`
    avant son `--limit` rougit à tort (relecture, passe 2, R-1).
    """
    sites = LISTE_GH.findall((REPOSITORY_ROOT / PR_PARALLELES_SKILL).read_text(encoding="utf-8"))

    assert len(sites) == 4, f"population changée, re-dénombrer : {sites}"
    assert all("--limit" in site for site in sites), [s for s in sites if "--limit" not in s]


def texte_normalise(fichier: str) -> str:
    """Le texte du fichier, espaces normalisés et marges `# ` de tête de ligne retirées."""
    brut = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8-sig")
    return " ".join(re.sub(r"(?m)^[ \t]*#[ \t]?", "", brut).split())


def prose_du_harnais() -> Iterator[tuple[str, str]]:
    """Chaque fichier suivi de la prose du harnais (`HARNESS_PROSE_GLOBS`), avec son texte
    normalisé : une forme coupée en fin de ligne s'y lit d'un tenant (obs 124)."""
    suivis = set(tracked_files())
    for glob in HARNESS_PROSE_GLOBS:
        for path in sorted(REPOSITORY_ROOT.glob(glob)):
            if (fichier := path.relative_to(REPOSITORY_ROOT).as_posix()) in suivis:
                yield fichier, texte_normalise(fichier)


# Une fermeture d'issue prescrite retire aussi son état : une issue **fermée** n'en porte aucun, et
# une fermeture manuelle laisse ce geste à faire (`triage`, « Rôles »). Dénombrement (relecture de
# la PR #153, passe 1, I2 ; classe : une fermeture d'issue sans retrait de son état),
# `grep -rn "issue close" .claude/skills --include=*.md` : **4** sites — `triage/SKILL.md` ×2
# (`wontfix` bug et enhancement : `label --add wontfix --remove <état>`), `triage/hors-scope.md`
# étape 8 (idem), `repercussions/SKILL.md` (doublon) ; **1** fuyait (`repercussions`). La forme du
# geste, `issue close <n>` (obs 139), en rend 3 au 2026-10-23 : le `wontfix` d'enhancement de
# `triage` renvoie au déroulé de `hors-scope.md`, étape 8, qui porte la commande.
FERMETURES_D_ISSUE = {
    "triage-wontfix-bug": TRIAGE_SKILL,
    "triage-wontfix-enhancement-par-son-deroule": HORS_SCOPE_REF,
    "repercussions-doublon": REPERCUSSIONS_SKILL,
}
COMMANDE_ISSUE_CLOSE = re.compile(r"issue close <\w+>")
# La coupure entre deux blocs de prose : une ligne vide, ou le début d'un élément de liste (`- `,
# `* ` ou `<n>. `).
COUPURE_DE_BLOC = re.compile(r"\n[ \t]*\n|\n(?=[ \t]*(?:[-*]|\d+\.) )")


def blocs_du_geste(path: Path, geste: re.Pattern[str]) -> list[str]:
    """Les paragraphes et éléments de liste du fichier qui portent le geste, espaces normalisés."""
    texte = path.read_text(encoding="utf-8-sig")
    blocs = (" ".join(bloc.split()) for bloc in COUPURE_DE_BLOC.split(texte))
    return [bloc for bloc in blocs if geste.search(bloc)]


def sites_du_geste(geste: re.Pattern[str], motif: str = SKILL_PROSE) -> list[str]:
    """Le fichier de chaque bloc de prose qui porte le geste, trié ; la prose des skills par
    défaut, `motif` pour une autre population."""
    return sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in REPOSITORY_ROOT.glob(motif)
        for _ in blocs_du_geste(path, geste)
    )


def test_les_fermetures_d_issue_sont_celles_de_la_table() -> None:
    """Un site neuf, ou retiré, rougit ici : la table se re-dénombre avant de changer."""
    assert sites_du_geste(COMMANDE_ISSUE_CLOSE) == sorted(FERMETURES_D_ISSUE.values())


@pytest.mark.parametrize("fichier", FERMETURES_D_ISSUE.values(), ids=FERMETURES_D_ISSUE.keys())
def test_chaque_fermeture_d_issue_retire_son_etat(fichier: str) -> None:
    """Le bloc qui ferme l'issue porte `--remove <état>`."""
    fermetures = blocs_du_geste(REPOSITORY_ROOT / fichier, COMMANDE_ISSUE_CLOSE)
    sans_retrait = [bloc for bloc in fermetures if "--remove <état>" not in bloc]

    assert not sans_retrait, f"`{fichier}` ferme une issue sans retirer son état : {sans_retrait}"


# Une réécriture de corps distant — corps d'issue par `issue edit --body-file`, brief par
# `brief write` — part d'un texte que **la session lit elle-même**, au moment d'écrire, jamais du
# rapport d'un équipier : un rapport peut en convertir les fins de ligne ou les espaces, et
# `ecriture-relue.py`, qui relit contre le fichier écrit, ne le voit pas (obs 87, 106). Classe
# (relecture de la PR #155, passe 1, I2) : une lecture préalable confiée au `releveur`, ou que la
# « Délégation » du skill laisse lire comme confiée à lui. **Population**, par la forme du geste
# (obs 139), `grep -rn -E "issue edit|brief write" .claude/skills --include=*.md` lu par bloc sur
# `a485d0a` : **23** blocs, dont **11** réécrivent un corps ou un brief déjà publié —
# `bug-vers-issue` étape 7, fermé par `4873d92` ; `repercussions` ×4 (corps et brief de l'étape 5,
# doublon, complétion), qui **fuyaient** : leur lecture ne nommait pas son lecteur, et la
# « Délégation » rendait au `releveur` « le corps des issues examinées » et « le brief en entier »
# sans borne ; `interroge-moi` ×3 (« Décisions », l'autre issue, le PRD), indemnes : sa
# « Délégation » ne donne au `releveur` aucun corps d'issue ; la seconde passe de `vers-issues`,
# hors classe : le texte vient du fichier local de la session ; `issue edit --append` de
# `cycle-pr`, dont le script lit lui-même le corps (`issue_append`), et `patch-checkbox-gh.md`
# (lot 7b), hors périmètre. Les **12** autres renvoient à un site ou le nomment — dont
# l'amendement en place de `brief-agent.md`, sans lecture propre : il s'exécute à l'étape 5 de
# `repercussions` —, ou publient un brief neuf (`triage`, `brief-agent.md`).
#
# Le lot 7b2 (2026-10-26) retire les deux blocs de `patch-checkbox-gh.md` — son push par
# `gh issue edit --body-file`, l'une des 11, et sa mention ETag, l'un des 12 — : `execution-qa`
# patche par `checkbox patch --paires`, dont le script lit lui-même le corps courant, hors classe
# comme `issue_append`, et que le geste ne compte pas. Même commande après sa prose : **21** blocs,
# 10 réécritures et 11 autres.
REECRITURES_DE_CORPS = {
    "bug-vers-issue-delegation-renvoi": BUG_VERS_ISSUE_SKILL,
    "bug-vers-issue-etape-7-lu-par-la-session": BUG_VERS_ISSUE_SKILL,
    "bug-vers-issue-erreurs-courantes-renvoi": BUG_VERS_ISSUE_SKILL,
    "cycle-pr-append-lu-par-le-script-hors-perimetre": CYCLE_PR_SKILL,
    "interroge-moi-delegation-renvoi": INTERROGE_MOI_SKILL,
    "interroge-moi-decisions-indemne": INTERROGE_MOI_SKILL,
    "interroge-moi-autre-issue-indemne": INTERROGE_MOI_SKILL,
    "interroge-moi-prd-indemne": INTERROGE_MOI_SKILL,
    "repercussions-delegation-renvoi": REPERCUSSIONS_SKILL,
    "repercussions-corps-lu-par-la-session": REPERCUSSIONS_SKILL,
    "repercussions-brief-lu-par-la-session": REPERCUSSIONS_SKILL,
    "repercussions-doublon-lu-par-la-session": REPERCUSSIONS_SKILL,
    "repercussions-completion-lue-par-la-session": REPERCUSSIONS_SKILL,
    "brief-agent-publication-texte-neuf": BRIEF_AGENT_REF,
    "brief-agent-amendement-en-place-renvoi": BRIEF_AGENT_REF,
    "triage-disclaimer-mention": TRIAGE_SKILL,
    "triage-decisions-renvoi-interroge-moi": TRIAGE_SKILL,
    "triage-brief-texte-neuf": TRIAGE_SKILL,
    "triage-brief-non-interroge-texte-neuf": TRIAGE_SKILL,
    "vers-issues-delegation-renvoi": VERS_ISSUES_SKILL,
    "vers-issues-seconde-passe-fichier-local": VERS_ISSUES_SKILL,
}
GESTE_DE_REECRITURE = re.compile(r"issue edit|brief write")


def test_les_reecritures_de_corps_sont_celles_de_la_table() -> None:
    """Un bloc neuf, ou retiré, rougit ici : la table se re-dénombre avant de changer. Le classement
    que portent les clés est celui du dénombrement, lu bloc par bloc ; ce test ne le vérifie pas."""
    assert sites_du_geste(GESTE_DE_REECRITURE) == sorted(REECRITURES_DE_CORPS.values())


# --- Les marques qui règlent une case de plan de QA (#134, lot 7b2) -----------------------------

# Chaque marque de `SETTLED_MARKS` (`ecriture-relue.py`) — une case laissée `[ ]` qui la porte,
# `checkbox next` ne la rend plus — avec l'annotation qu'`execution-qa/SKILL.md` prescrit pour
# elle, en littéraux, lue dans tout le fichier : une marque réglée qu'aucune étape n'écrit laisse la
# case en attente pour toujours. Contrainte V1 du lot 7b1 : rouge
# sur `ffbe52e` pour ` — accepté`, que `SKILL.md` n'y écrivait qu'au §6 et dans la « Passe
# finale », sans tiret ni date.
ANNOTATIONS_QUI_REGLENT_UNE_CASE = {
    "needs-issue": ("🔴", "` 🔴 needs-issue — <résumé sur une ligne>`"),
    "bloque": (" — BLOQUÉ", "` — BLOQUÉ : <raison>`"),
    "accepte": (" — accepté", "` — accepté : <décision>, <date>`"),
}


def test_les_marques_qui_reglent_une_case_sont_celles_du_script() -> None:
    """Une marque ajoutée au script, ou retirée, rougit ici : sa prescription se relit avec elle."""
    ecriture_relue = load_script("cycle-pr", "ecriture-relue")

    assert set(ecriture_relue.SETTLED_MARKS) == {
        marque for marque, _ in ANNOTATIONS_QUI_REGLENT_UNE_CASE.values()
    }


@pytest.mark.parametrize(
    ("marque", "annotation"),
    ANNOTATIONS_QUI_REGLENT_UNE_CASE.values(),
    ids=ANNOTATIONS_QUI_REGLENT_UNE_CASE.keys(),
)
def test_chaque_marque_qui_regle_une_case_est_prescrite_par_execution_qa(
    marque: str, annotation: str
) -> None:
    """L'annotation porte sa marque, et `execution-qa` la prescrit telle quelle."""
    assert marque in annotation, f"« {annotation} » ne porte pas la marque « {marque} »"
    assert annotation in texte_normalise(EXECUTION_QA_SKILL), (
        f"`{EXECUTION_QA_SKILL}` ne prescrit plus « {annotation} »"
    )


# --- Le type de chaque case d'un plan de QA (#134, lot 7a) ---------------------------------------

# Une ligne de case de plan de QA : un ou plusieurs éléments de liste ouverts sur la ligne, chacun
# derrière ses blancs ou ses citations `>`, le dernier suivi d'une case à cocher et de blancs.
PLAN_QA_CASE = re.compile(r"^(?:[ \t>]*(?:[-*+]|\d+[.)])[ \t]+)+\[[ \txX]\][ \t]+")
# La même ligne, la marque de type juste après la case (`gabarit-plan-qa.md`, « Types de case ») :
# une commande en un seul segment entre accents graves ou une observation, chacune suivie de ` → `
# et de son attendu.
PLAN_QA_CASE_TYPEE = re.compile(
    PLAN_QA_CASE.pattern + r"(?:\*\*Commande\*\* — `[^`]+`|\*\*Observation\*\* — .+) → \S"
)
# Les fichiers de `plan-qa` qui portent des cases de plan ; celles de `SKILL.md` sont la relecture
# de jugement de la session, pas un plan.
PLAN_QA_PLANS = (GABARIT_PLAN_QA_REF, EXEMPLE_BLOC_ISSUE_REF)


def cases(texte: str) -> list[str]:
    """Les lignes de case de `texte` ; une puce de critère (`- **C1** — …`) n'en est pas une."""
    return [ligne for ligne in texte.splitlines() if PLAN_QA_CASE.match(ligne)]


def cases_sans_type(texte: str) -> list[str]:
    """Les lignes de case de `texte` sans marque de type valide juste après la case.

    La marque se lit en tête de case : les annotations qu'`execution-qa` ajoute en fin de ligne et
    la bascule `[ ]` → `[x]` ne la touchent pas.
    """
    return [ligne for ligne in cases(texte) if not PLAN_QA_CASE_TYPEE.match(ligne)]


# Le recueil de `cases`, de `cases_sans_type` et de la commande « Cases sans type » de la passe
# comptable, des deux côtés (obs 138), en littéraux (obs 80) : chaque ligne, puis est-ce une case,
# est-elle sans type.
PLAN_QA_CASE_FORMS = {
    "commande complete": (
        "- [ ] **Commande** — `curl -s -o /dev/null -w '%{http_code}' $API/health` → `200`",
        True,
        False,
    ),
    "observation": (
        "- [ ] **Observation** — l'état vide de la liste → le CTA visible (C1)",
        True,
        False,
    ),
    "cochee et annotee": (
        "- [x] **Commande** — `docker compose ps api` → `running` (C2) — running, 2026-10-26",
        True,
        False,
    ),
    "cochee en majuscule": ("- [X] **Observation** — la console → aucune erreur", True, False),
    "indentee": ("  - [ ] **Observation** — le bouton pendant l'envoi → désactivé", True, False),
    "sans type": ("- [ ] L'application démarre.", True, True),
    "commande sans fleche": (
        "- [ ] **Commande** — `docker compose ps api` montre `running`",
        True,
        True,
    ),
    "commande sans segment": ("- [ ] **Commande** — docker compose ps api → `running`", True, True),
    "commande sans gras": ("- [ ] Commande — `docker compose ps api` → `running`", True, True),
    "type inconnu": ("- [ ] **Manuel** — ouvrir la page → rendu correct", True, True),
    "puce de critere": ("- **C1** — un PDF valide de 1 Mo est accepté", False, False),
    "puce etoile": ("* [ ] L'application démarre.", True, True),
    "puce plus": ("+ [ ] L'application démarre.", True, True),
    "liste ordonnee point": ("1. [ ] L'application démarre.", True, True),
    "liste ordonnee parenthese": ("12) [x] L'application démarre.", True, True),
    "deux espaces": ("-  [ ] L'application démarre.", True, True),
    "tabulation": ("-\t[ ] L'application démarre.", True, True),
    "tabulation entre crochets": ("- [\t] L'application démarre.", True, True),
    "deux blancs apres la case": ("- [ ]  **Observation** — la console → propre", True, False),
    "tabulation apres la case": ("- [ ]\t**Observation** — la console → propre", True, False),
    "citation": ("> - [ ] L'application démarre.", True, True),
    "puce dans une puce": ("- * [ ] L'application démarre.", True, True),
    "citation dans une puce": ("- > 1. [ ] L'application démarre.", True, True),
    "commande segment vide": ("- [ ] **Commande** — `` → `running`", True, True),
    "commande attendu vide": ("- [ ] **Commande** — `ls` → ", True, True),
    "observation sans gras": ("- [ ] Observation — la console → aucune erreur", True, True),
    "observation vide": ("- [ ] **Observation** — ", True, True),
    "observation sans action": ("- [ ] **Observation** —  → aucune erreur", True, True),
    "observation sans attendu": ("- [ ] **Observation** — regarder la page", True, True),
    "observation attendu vide": ("- [ ] **Observation** — la console → ", True, True),
    "puce ordinaire": ("- Issues dans le périmètre : #127", False, False),
    "crochets hors liste": ("[ ] L'application démarre.", False, False),
    "prose qui cite une case": ("`- [ ] **Commande** — …` est la forme d'une case.", False, False),
    "marqueur colle": ("-[ ] L'application démarre.", False, False),
    "case collee": ("- [ ]L'application démarre.", False, False),
    "citation sans puce": ("> [ ] L'application démarre.", False, False),
    "puce puis citation sans puce": ("- > [ ] L'application démarre.", False, False),
}


@pytest.mark.parametrize(
    ("ligne", "est_une_case", "sans_type"),
    PLAN_QA_CASE_FORMS.values(),
    ids=PLAN_QA_CASE_FORMS.keys(),
)
def test_le_type_d_une_case_de_plan_de_qa_se_reconnait(
    ligne: str, est_une_case: bool, sans_type: bool
) -> None:
    """Une case est un élément de liste GFM qui s'ouvre sur une case à cocher puis un blanc (spec
    GFM §5.2 « List items », §5.3 « Task list items ») ; son type, la marque qui suit.

    **Dénombrement** (passe 1 de la relecture de la PR #157, constats I1 et (2)), écrit avant le
    correctif, par axe — *N formes, k vues sur `e4e05db`* ; une forme par entrée au recueil :
    - marqueur de liste : `-`, `*`, `+`, `<n>.`, `<n>)` — 5, 1 vue ;
    - blanc entre marqueur et case : un espace, plusieurs, une tabulation — 3, 1 vue ;
    - état : espace, tabulation (« un blanc », §5.3), `x`, `X` — 4, 3 vues ;
    - blanc entre case et type : un espace, plusieurs, une tabulation — 3, 1 vue ;
    - conteneur sur la ligne : indentation, citation `>`, puce dans une puce, citation dans une
      puce — 4, 1 vue ;
    - Commande : gras, segment entre accents graves, segment non vide, ` → ` juste après, attendu
      non vide — 5, 3 vues ; Observation : gras, texte non vide, ` → `, attendu non vide, et
      l'Observation vide — 5, 0 vue ; aucun type, type inconnu — 2, 2 vues ;
    - vrais négatifs : puce de critère, puce ordinaire, crochets hors liste, prose qui cite une
      case, marqueur collé, case collée, citation sans puce, puce puis citation sans puce — 8,
      1 vu.

    **Ce que le motif lit de plus que GFM** : une ligne de code — bloc clôturé, ou cinq blancs
    après le marqueur — compte comme case. Un refus de trop, jamais une fuite ; et le gabarit garde
    ses cases dans un bloc clôturé, que le motif doit lire.
    """
    assert (bool(cases(ligne)), bool(cases_sans_type(ligne))) == (est_une_case, sans_type)


@pytest.mark.parametrize("fichier", PLAN_QA_PLANS)
def test_chaque_case_d_un_plan_de_qa_porte_son_type(fichier: str) -> None:
    """Critère « 7a » du brief de #134 : le type de chaque case est écrit dans le plan, pour que
    l'exécutant se lise sans décision.

    **Population** : les cases des deux fichiers de `PLAN_QA_PLANS` ; sur `4b51a71`, **34** et
    **26**, **0** typée — vu rouge là. Au lot 7a, les critères d'acceptation d'un bloc sortent des
    cases (`- **C<k>** — …`) : **32** et **22**, toutes typées ; **23** dans l'exemple quand sa
    première case garde le corps de l'upload pour les suivantes. **Ce que la garde ne voit
    pas** : une commande fausse mais bien formée, un attendu vague — la marque dit qui joue la
    case, pas que la case est juste.
    """
    texte = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8")

    assert cases(texte), f"`{fichier}` n'a aucune case : `PLAN_QA_CASE` ne la voit plus"
    assert cases_sans_type(texte) == []


@pytest.mark.parametrize("fichier", PLAN_QA_PLANS)
def test_aucune_case_d_un_plan_de_qa_ne_porte_de_marque_reglee(fichier: str) -> None:
    """Le texte d'une case du gabarit ou de l'exemple ne porte aucune marque réglée — celles de
    `SETTLED_MARKS`, lues dans le script — ni « BUG # » : `checkbox next` sauterait la case, la
    campagne finirait avec elle `[ ]`, et le `grep "BUG #"` de la reprise (`execution-qa` §2) la
    ramasserait (I2 de la passe 1 de relecture de la PR #159).

    **Dénombrement**, écrit avant le correctif, sur `d99e9a8` : **32** lignes de case dans
    `gabarit-plan-qa.md`, **23** dans `exemple-bloc-issue.md` ; **1** portait une marque, la case
    « chaque constat majeur → un lien `🔴 BUG #N` » de la Définition du Terminé du gabarit (`🔴` et
    « BUG # »), rouge là. Deux autres cases du même bloc nomment « BLOQUÉ » et « accepté » sans
    « — » devant : indemnes, ce ne sont pas des marques.
    """
    marques = (*load_script("cycle-pr", "ecriture-relue").SETTLED_MARKS, "BUG #")
    texte = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8")

    assert [ligne for ligne in cases(texte) if any(m in ligne for m in marques)] == []


# Les commandes de la passe comptable (`plan-qa`, « Passe finale avant publication »), chacune sous
# sa puce `- **<nom>** — ` : un bloc clôturé `bash`, ou un segment `cat …` ou `grep …` entre accents
# graves.
PASSE_COMPTABLE = re.compile(r"^### 1\. Passe comptable.*?(?=^### )", re.MULTILINE | re.DOTALL)
PUCE_DE_LA_PASSE = re.compile(r"^- \*\*", re.MULTILINE)
COMMANDE_EN_BLOC = re.compile(r"```bash\n(.+?)\n")
COMMANDE_EN_LIGNE = re.compile(r"`((?:cat|grep) [^`]+)`")
# Leurs noms, en littéraux (obs 80) ; leur égalité avec le texte est un second test.
COMMANDES_DE_LA_PASSE_COMPTABLE = ("Cases sans type", "Critères → cases", "Marqueurs", "Structure")


def commandes_de_la_passe_comptable() -> dict[str, str]:
    """Chaque commande de la passe comptable de `plan-qa`, par le nom de sa puce."""
    section = PASSE_COMPTABLE.search((REPOSITORY_ROOT / PLAN_QA_SKILL).read_text(encoding="utf-8"))
    assert section, f"`{PLAN_QA_SKILL}` n'a plus de « 1. Passe comptable »"
    commandes: dict[str, str] = {}
    for puce in PUCE_DE_LA_PASSE.split(section.group())[1:]:
        nom, corps = puce.split("** — ", 1)
        commande = COMMANDE_EN_BLOC.search(corps) or COMMANDE_EN_LIGNE.search(corps)
        assert commande, f"la puce « {nom} » de la passe comptable n'a pas de commande"
        commandes[nom] = commande.group(1).strip()
    return commandes


def test_la_passe_comptable_n_a_que_les_commandes_recensees() -> None:
    """Une commande ajoutée à la passe comptable entre au recueil, donc sous l'épingle suivante."""
    assert tuple(commandes_de_la_passe_comptable()) == COMMANDES_DE_LA_PASSE_COMPTABLE


@pytest.mark.parametrize("nom", COMMANDES_DE_LA_PASSE_COMPTABLE)
def test_une_commande_de_la_passe_comptable_lit_le_brouillon_par_un_tube(nom: str) -> None:
    """Le brouillon entre par `cat <brouillon> |` : le hook RTK du poste réécrit un `grep` de tête
    en `rtk grep`, dont la sortie reformatée et tronquée a caché la case sans type d'un brouillon
    témoin, et laisse natif le `grep` placé après le `|`. Rejouées sous le hook, telles qu'écrites,
    le 2026-11-03 vers 17:30 UTC sur deux brouillons témoins, l'un conforme, l'autre fautif
    (`plan-qa`, « Passe comptable »). **Ce que ce test ne voit pas** : le hook lui-même, absent de
    la CI."""
    assert commandes_de_la_passe_comptable()[nom].startswith("cat <brouillon> | grep ")


@pytest.mark.parametrize("nom", COMMANDES_DE_LA_PASSE_COMPTABLE)
def test_une_commande_de_la_passe_comptable_n_a_aucune_barre_oblique_inverse(nom: str) -> None:
    r"""Aucun motif de la passe comptable ne contient de `\` : sous le hook RTK du poste, un `grep`
    en tête de commande devient `rtk grep`, et un argument **sans espace** y perd ses `\` — mesuré
    le 2026-10-26, rtk 0.43.0 : `rtk grep -nE '^a+\[b\]'` sort `aab`, `rtk grep -nE 'x \[y'` sort
    `x [y` (B1 de la passe 2 de relecture de la PR #157). Un `\` s'écrit en expression entre
    crochets : `[[]`, `[]]`, `[*]`, `[(]`, `[)]`.

    **Dénombrement** (classe par la forme du geste, obs 139 : un motif que la passe fait taper à
    l'`executant` contient `\`), écrit avant le correctif, sur `1b5b758` : **5** motifs `grep` —
    « Cases sans type » ×2 (la sélection, puis le filtre `grep -v`), « Critères → cases »,
    « Marqueurs », « Structure » ; **4** contiennent `\`, tous sauf « Marqueurs » ; **1** est sans
    espace, la sélection de « Cases sans type » ; **4** sont réécrits par le hook, le filtre après
    `|` restant le `grep` natif (`rtk hook claude` rejoué sur la commande). **1** fuyait, cette
    sélection : rien sur un plan qui a une case sans type, codes `1 1`. Les trois autres réécrits
    sortaient juste — même sortie avec et sans le hook sur les deux témoins de la relecture. Le
    correctif retire le `\` des quatre, même de ceux qui marchaient.

    **Ce que ce test ne voit pas** : le hook lui-même, qui n'existe que sur le poste, pas en CI —
    une autre réécriture que la perte des `\` ne se voit qu'au rejeu de la session sur ses deux
    témoins.
    """
    assert "\\" not in commandes_de_la_passe_comptable()[nom]


@pytest.mark.parametrize(
    ("ligne", "sans_type"),
    [(ligne, sans_type) for ligne, _, sans_type in PLAN_QA_CASE_FORMS.values()],
    ids=PLAN_QA_CASE_FORMS.keys(),
)
def test_la_commande_des_cases_sans_type_s_accorde_au_recueil(
    ligne: str, sans_type: bool, bash_de_ce_systeme: str, tmp_path: Path
) -> None:
    """La commande « Cases sans type » de la passe comptable sort une ligne du recueil si et
    seulement si `cases_sans_type` la refuse (I2 de la passe 2 de relecture de la PR #157 : l'une
    changeait sans que l'autre rougisse). Une sortie d'erreur rougit : une commande cassée ne sort
    rien, comme sur une case typée.

    **Ce que ce test ne voit pas** : le hook RTK n'existe que sur le poste, pas en CI — la commande
    tourne ici sous `subprocess`, sans lui, et reste verte avec une barre oblique inverse remise.
    C'est l'épingle « aucune barre oblique inverse » qui ferme B1, et le rejeu de la session sur ses
    deux témoins qui le mesure. L'accord de « Critères → cases » avec `PLAN_QA_CASE` n'est pas
    gardé.
    """
    brouillon = tmp_path / "brouillon.md"
    brouillon.write_text(f"{ligne}\n", encoding="utf-8", newline="\n")
    commande = commandes_de_la_passe_comptable()["Cases sans type"].replace(
        "<brouillon>", shlex.quote(brouillon.as_posix())
    )

    resultat = subprocess.run(
        [bash_de_ce_systeme, "-c", commande],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert (bool(resultat.stdout), resultat.stderr) == (sans_type, "")


# « Jamais d'auto-merge » devient « jamais d'auto-merge **dans le trunk** » (#107, lot 2a) : une
# PR de lot se merge sans go dans la branche d'intégration de son issue, par
# `.claude/skills/cycle-pr/scripts/merge-lot.py`. Une mention restée nue dirait le contraire de la
# règle — interdire ce que `cycle-pr` Étape 7 prescrit —, ou, réécrite ailleurs, la ferait lire
# comme levée pour le trunk aussi.
#
# **Population**, recensée avant le premier correctif sur `7e94d11` : `grep -rn -i "auto-merge"
# .claude/ CONTRIBUTING.md` rend **8 lignes**, toutes nues (le brief en annonçait 6 — journal de
# spec de #107, 2026-10-17) : `contraintes.md`, `cycle-pr/SKILL.md` (en-tête, Étape 7),
# `pr-paralleles/SKILL.md` (« Règles »), `verificateur.md`, `pipeline.config.md` (porte `ask`),
# `prompt-lot-suivant.md` (renvoi au titre de la règle), `CONTRIBUTING.md`. La garde lit cette
# prose entière, `CLAUDE.md` compris : une mention neuve y entre d'office.
#
# **Bornes.** `.github/` n'en est pas : sa seule mention, en commentaire de `dependabot.yml`, parle
# des PR du bot, qui visent toujours le trunk — la forme nue y est vraie (relevé à la première
# exécution de cette garde, 2026-10-17). Et la garde exige que chaque « auto-merge » soit suivi de
# « dans le trunk », pas que la phrase qui suit dise vrai — « jamais d'auto-merge dans le trunk,
# sauf vers `main` » passerait.
AUTO_MERGE_NU = re.compile(r"auto-merge(?!\s+dans\s+le\s+trunk)", re.IGNORECASE)
AUTO_MERGE_PROSE_GLOBS = [".claude/**/*.md", "CLAUDE.md", "CONTRIBUTING.md"]
AUTO_MERGE_FORMES = {
    "regle-nue": ("- **Jamais d'auto-merge.** Même avec CI verte", True),
    "renvoi-nu-au-titre": ("`contraintes.md`, « Jamais d'auto-merge ».", True),
    "borne-au-trunk": ("**Jamais d'auto-merge dans le trunk.** Même CI verte", False),
    "borne-coupee-par-un-retour-a-la-ligne": ("jamais d'auto-merge dans le\n  trunk", False),
}


@pytest.mark.parametrize(("prose", "nue"), AUTO_MERGE_FORMES.values(), ids=AUTO_MERGE_FORMES.keys())
def test_le_motif_de_l_auto_merge_ne_vise_que_la_forme_nue(prose: str, nue: bool) -> None:
    """Le témoin des deux côtés : une forme nue appariée, une forme bornée laissée."""
    assert bool(AUTO_MERGE_NU.search(prose)) is nue


def test_chaque_mention_de_l_auto_merge_le_borne_au_trunk() -> None:
    """La population entière, pas les trois sites que le critère du brief nomme."""
    nues = [
        f"{path.relative_to(REPOSITORY_ROOT).as_posix()} : {match.group(0)}"
        for path, match in prose_citations(
            REPOSITORY_ROOT, tracked_files(), AUTO_MERGE_PROSE_GLOBS, AUTO_MERGE_NU
        )
    ]

    assert not nues, f"« auto-merge » sans « dans le trunk » : {nues}"


# --- Ce que `cycle-pr` renvoie au go du briefing est annoncé à l'Étape 1 (#77, lot 4c) ----------

CYCLE_PR = REPOSITORY_ROOT / CYCLE_PR_SKILL

# Chaque question qu'une étape **ultérieure** dit « demandée au go du briefing », et le mot que
# l'Étape 1 doit porter pour qu'un agent qui suit le skill dans l'ordre la pose à ce moment-là —
# une exception placée après l'étape qui agit n'est jamais appliquée (obs 30). Dénombré le
# 2026-10-14 avant le correctif, relecture de la PR #89, passe 2 : `go du briefing` apparaît
# 2 fois dans `cycle-pr`, l'une à l'Étape 1 (la règle des `[V]` groupées), l'autre à l'Étape 7
# (l'accord pour le vérificateur hors vague) — 1 renvoi hors de l'Étape 1, 1 fuyait.
QUESTIONS_DU_GO = {
    "accord pour le vérificateur hors vague": "l'accord pour lancer soi-même",
    "accord pour la session de relecture": "l'accord pour démarrer sa session de relecture",
    # D-1 de #197 : les relances de CI de la PR, couvertes d'avance, que l'Étape 7 renvoie au go.
    "relances de CI couvertes par le go": "Le go couvre aussi les relances de CI de la PR",
}


def etape_1() -> str:
    """Le texte de l'Étape 1 de `cycle-pr`, de son titre à celui de l'Étape 2."""
    texte = CYCLE_PR.read_text(encoding="utf-8")
    return texte[texte.index("## Étape 1 ") : texte.index("## Étape 2 ")]


@pytest.mark.parametrize("mot", QUESTIONS_DU_GO.values(), ids=QUESTIONS_DU_GO.keys())
def test_une_question_renvoyee_au_go_du_briefing_est_nommee_a_l_etape_1(mot: str) -> None:
    """Sans elle, la question part à l'étape qui la cite : 6 h 37 d'absence au lot 4b de #77,
    posée à l'Étape 7, à un moment où il ne restait rien d'indépendant à faire."""
    assert mot in etape_1()


def test_chaque_renvoi_au_go_du_briefing_a_sa_question_dans_le_recueil() -> None:
    """L'autre sens : un renvoi au go ajouté hors de l'Étape 1 fait rougir ici tant qu'il n'est
    pas inscrit au recueil — donc nommé à l'Étape 1."""
    texte = CYCLE_PR.read_text(encoding="utf-8")
    hors_etape_1 = texte.count("go du briefing") - etape_1().count("go du briefing")

    assert hors_etape_1 == len(QUESTIONS_DU_GO), (
        f"{hors_etape_1} renvoi(s) au go du briefing hors Étape 1 pour {len(QUESTIONS_DU_GO)} "
        "question(s) au recueil : une question renvoyée au go s'inscrit à QUESTIONS_DU_GO et se "
        "nomme à l'Étape 1 ; une mention qui n'est pas une question se reformule"
    )


# --- La session de relecture, une par PR (#134, lot 3) -------------------------------------------

SESSION_RELECTURE_REF = ".claude/skills/cycle-pr/references/session-relecture.md"
RELECTEUR_ROLE = ".claude/agents/relecteur.md"


# Les trois textes qui font démarrer, réveiller ou nettoyer la session de relecture la citent au
# lieu de la recopier (critère 2 du bloc « Lot 3 » de #134).
RENVOIS_A_LA_SESSION_DE_RELECTURE = [CYCLE_PR_SKILL, PR_PARALLELES_SKILL, COORDINATRICE_REF]


@pytest.mark.parametrize("fichier", RENVOIS_A_LA_SESSION_DE_RELECTURE)
def test_chaque_texte_qui_demarre_la_relecture_cite_son_protocole(fichier: str) -> None:
    """Un texte qui la démarre sans la citer en recopie le protocole, ou en invente un."""
    assert "session-relecture.md" in texte_normalise(fichier), (
        f"`{fichier}` ne cite plus `session-relecture.md`"
    )


def test_la_forme_du_reveil_n_est_normative_qu_une_fois() -> None:
    """« relis <SHA> » ne s'écrit qu'au protocole ; ailleurs, on y renvoie (critère 2 du bloc).

    **Population** : la prose du harnais (`HARNESS_PROSE_GLOBS`) — `.claude/`, `CLAUDE.md`,
    `CONTRIBUTING.md`, `.github/`. Vu rouge sur une copie de la forme dans `cycle-pr/SKILL.md`.
    """
    sites = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path, _ in prose_citations(
            REPOSITORY_ROOT, tracked_files(), HARNESS_PROSE_GLOBS, re.compile(r"relis <SHA>")
        )
    ]

    assert sites == [SESSION_RELECTURE_REF], sites


def test_un_controle_de_proprete_par_git_status_voit_les_fichiers_non_suivis() -> None:
    """Un contrôle de propreté attend un `git status --porcelain` vide : sans
    `--untracked-files=normal`, une configuration `status.showUntrackedFiles=no` y cache un
    fichier non suivi (mesuré le 2026-10-21, git 2.47.1, bloc B du lot 4a de #134).

    **Population** : la prose du harnais (`HARNESS_PROSE_GLOBS`). Recensé le 2026-10-21 :
    2 mentions sans l'option, dont 1 contrôle — `relecteur.md`, corrigé ; l'autre, à l'Étape 1
    de `cycle-pr`, déplacée par #177 dans `cycle-pr/references/portes.md` (« Au blocage »),
    écarte la commande pour lire l'avance d'une branche. Vu rouge sur `relecteur.md` avant
    correction.
    """
    sans_l_option = re.compile(r"git status --porcelain(?! --untracked-files=normal)")
    sites = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path, _ in prose_citations(
            REPOSITORY_ROOT, tracked_files(), HARNESS_PROSE_GLOBS, sans_l_option
        )
    ]

    assert sites == [PORTES_REF], sites


VOIT_LES_NON_SUIVIS = "--untracked-files=normal"


def arguments_de_git(node: ast.AST) -> list[ast.expr] | None:
    """Les arguments qui suivent `git` dans un appel de l'une des deux formes lues : une séquence —
    tuple, liste ou arguments d'un appel — dont la tête est la constante `"git"`, ou l'appel d'une
    fonction nommée `git`, dont les arguments suivent un `git` implicite ; `None` hors de ces formes.
    Ne sont pas lues : une tête nommée (`(GIT, "status")`) et une chaîne shell (`"git status …"`)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "git":
        return node.args
    if isinstance(node, ast.Tuple | ast.List):
        elements = node.elts
    elif isinstance(node, ast.Call):
        elements = node.args
    else:
        return None
    tete = elements[0] if elements else None
    return elements[1:] if isinstance(tete, ast.Constant) and tete.value == "git" else None


def sous_commande_git(arguments: list[ast.expr]) -> object:
    """Le premier argument qui n'est pas une option globale — `-C <dossier>` et `-c <clé=valeur>`
    sautés avec leur valeur —, ou `None` : `git submodule status` a pour sous-commande `submodule`."""
    rang = 0
    while rang < len(arguments):
        argument = arguments[rang]
        valeur = argument.value if isinstance(argument, ast.Constant) else None
        if valeur in ("-C", "-c"):
            rang += 2
        elif isinstance(valeur, str) and valeur.startswith("-"):
            rang += 1
        else:
            return valeur
    return None


def lectures_de_git_status(source: str) -> list[list[object]]:
    """Les constantes de chaque lecture de `git status` du source Python (`arguments_de_git`), lue
    par l'arbre syntaxique quelle que soit sa mise en page."""
    sites: list[list[object]] = []
    for node in ast.walk(ast.parse(source)):
        arguments = arguments_de_git(node)
        if arguments is not None and sous_commande_git(arguments) == "status":
            sites.append([e.value for e in arguments if isinstance(e, ast.Constant)])
    return sites


# Le témoin des deux côtés, en littéraux : chaque forme, et pour chacune de ses lectures, si elle
# porte l'option.
LECTURES_DE_GIT_STATUS_FORMES: dict[str, tuple[str, list[bool]]] = {
    "tuple-avec-l-option": (
        'S = ("git", "status", "--porcelain", "--untracked-files=normal")',
        [True],
    ),
    "tuple-sans-l-option": ('S = ("git", "status", "--porcelain")', [False]),
    "liste-sur-plusieurs-lignes": ('run([\n    "git",\n    "status",\n])', [False]),
    "option-c-avant-la-sous-commande": (
        'run(["git", "-C", d, "status", "--untracked-files=normal"])',
        [True],
    ),
    "option-c-minuscule-avant-la-sous-commande": (
        'run(["git", "-c", "core.quotepath=off", "status"])',
        [False],
    ),
    "option-longue-avant-la-sous-commande": ('run(["git", "--no-pager", "status"])', [False]),
    "arguments-d-un-appel": ('run("git", "status", "--porcelain")', [False]),
    "fonction-git-sans-l-option": ('git("status", "--porcelain")', [False]),
    "fonction-git-avec-l-option": ('git("status", "--untracked-files=normal")', [True]),
    "tete-nommee-non-lue": ('run((GIT, "status", "--porcelain"))', []),
    "chaine-shell-non-lue": ('run("git status --porcelain", shell=True)', []),
    "submodule-status-hors-classe": ('S = ("git", "submodule", "status")', []),
    "gh-auth-status-hors-classe": ('A = ("gh", "auth", "status")', []),
    "git-log-hors-classe": ('L = ("git", "log", "-1")', []),
}


@pytest.mark.parametrize(
    ("source", "attendu"),
    LECTURES_DE_GIT_STATUS_FORMES.values(),
    ids=LECTURES_DE_GIT_STATUS_FORMES.keys(),
)
def test_une_lecture_de_git_status_se_lit_avec_ou_sans_l_option(
    source: str, attendu: list[bool]
) -> None:
    """Le témoin, une forme par entrée : la lecture sans l'option se voit, celle qui la porte passe ;
    une tête nommée et une chaîne shell ne sont pas lues ; `git submodule status`, `gh auth status`
    ou un autre `git` restent hors de la population."""
    sites = lectures_de_git_status(source)

    assert [VOIT_LES_NON_SUIVIS in site for site in sites] == attendu


def test_chaque_script_qui_lit_git_status_voit_les_fichiers_non_suivis() -> None:
    """Même règle que la prose (`cleanup-verbatim.md`, « Comment l'appliquer ») : `amorcage.py
    commit` l'a enfreinte dans du code livré, défaut passé sous 32 mutations rouges sur 32
    (obs 145).

    **Population recomptée à chaque exécution** : les scripts Python suivis sous `.claude/`, lus par
    `lectures_de_git_status` — jamais une liste de sites. Deux formes lues, la séquence à tête
    `"git"` et l'appel d'une fonction `git` ; une tête nommée et une chaîne shell ne le sont pas
    (`arguments_de_git`, témoins au recueil). Relevé le 2026-11-03 sur `05014a6` :
    `git grep -n '"status"' -- '.claude/*.py'` rend 2 séquences à tête `"git"`, les 2 avec l'option
    (`sonde-outillage.py`, `amorcage.py`), 0 tête nommée, 0 autre sous-commande `git` ;
    `git grep -n -e "git status" -e "def git" -e "git(" -- '.claude/*.py'`, 0 appel de fonction
    `git` et 0 chaîne shell hors docstring.
    """
    lectures = [
        (fichier, site)
        for fichier in tracked_files()
        if fichier.startswith(".claude/") and fichier.endswith(".py")
        for site in lectures_de_git_status((REPOSITORY_ROOT / fichier).read_text(encoding="utf-8"))
    ]

    assert lectures, "aucune lecture de `git status` lue : le motif a-t-il cessé de mordre ?"
    assert [f for f, site in lectures if VOIT_LES_NON_SUIVIS not in site] == []


# --- Les renvois aux barreaux de « Création d'issues en cours de cycle » (#134, lot 7c) ----------

SECTION_DES_BARREAUX = "## Création d'issues en cours de cycle"
RENVOI_DE_BARREAU = re.compile(r"\bbarreaux? \d+(?:(?:, | ou | et | à )\d+)*", re.IGNORECASE)
# Le recueil du motif, des deux côtés (obs 138), en littéraux (obs 80) : le texte, puis les numéros
# qu'il cite.
RENVOI_DE_BARREAU_FORMES: dict[str, tuple[str, list[int]]] = {
    "un-numero": ("par le barreau 4 porte", [4]),
    "deux-numeros": ("barreau 2 ou 4, le brouillon", [2, 4]),
    "enumeration": ("les barreaux 1, 2 et 4", [1, 2, 4]),
    "plage": ("les barreaux 2 à 4", [2, 4]),
    "majuscule": ("Barreau 3 :", [3]),
    "premier-barreau-hors-classe": ("au **premier barreau qui tient**", []),
    "barreau-par-barreau-hors-classe": ("appliquer la règle barreau par barreau", []),
}
# Chaque fichier de la prose du harnais qui cite un barreau par son numéro, et les numéros cités,
# dans l'ordre du texte.
# Le vide relevé (#195, obs 143) part au barreau 2 : `cycle-pr` Étape 4, « Sévérité », et
# `relecteur.md`.
RENVOIS_AUX_BARREAUX = {
    CONTRAINTES_RULE: [4],
    BUG_VERS_ISSUE_SKILL: [1, 3],
    CONTRADICTION_SKILL: [2, 4],
    CYCLE_PR_SKILL: [3, 2, 3, 2, 2],
    RELECTEUR_ROLE: [2],
    "CONTRIBUTING.md": [3],
    REPERCUSSIONS_SKILL: [4],
    VERS_ISSUES_SKILL: [4],
}
# Les barreaux, par leur tête en gras, dans l'ordre : un barreau inséré, retiré ou déplacé
# renumérote ceux qui le suivent sous leurs renvois, qui se relisent avant que la liste change.
TETES_DES_BARREAUX = [
    "il tient dans la PR courante en moins d'un commit",
    "une issue ouverte possède le sujet",
    "un correctif évident",
    "sinon",
]


def barreaux_cites(texte: str) -> list[int]:
    """Les numéros de barreau que `texte` cite, dans l'ordre."""
    return [
        int(numero)
        for renvoi in RENVOI_DE_BARREAU.findall(texte)
        for numero in re.findall(r"\d+", renvoi)
    ]


def barreaux_existants() -> list[tuple[int, str]]:
    """Le numéro et la tête en gras de chaque barreau de « Création d'issues en cours de cycle »."""
    texte = (REPOSITORY_ROOT / CONTRAINTES_RULE).read_text(encoding="utf-8")
    section = texte.split(SECTION_DES_BARREAUX, 1)[1].split("\n## ", 1)[0]
    barreaux = re.findall(r"(?m)^[ \t]*(\d+)\. \*\*(.+?)\*\*", section)
    return [(int(numero), tete) for numero, tete in barreaux]


@pytest.mark.parametrize(
    ("texte", "numeros"),
    RENVOI_DE_BARREAU_FORMES.values(),
    ids=RENVOI_DE_BARREAU_FORMES.keys(),
)
def test_un_renvoi_de_barreau_se_lit_par_ses_numeros(texte: str, numeros: list[int]) -> None:
    """Chaque numéro d'un renvoi est lu ; « premier barreau », sans numéro, n'en est pas un."""
    assert barreaux_cites(texte) == numeros


def test_les_renvois_aux_barreaux_sont_ceux_de_la_table() -> None:
    """Un renvoi « barreau <n> » ajouté à la prose du harnais rougit ici tant que la table ne le
    porte pas : il se relit alors contre la liste, au test suivant.

    **Population** : la prose suivie du harnais (`HARNESS_PROSE_GLOBS`), texte aux espaces
    normalisés (`texte_normalise`, obs 124), `contraintes.md` compris — son renvoi interne est de
    la même forme (obs 139).

    **Dénombrement, écrit avant le correctif** (lot 7c de #134, qui insère le barreau « correctif
    évident » en 3) : sur `beb6190`, **4** sites — `contraintes.md` (« Une issue ouverte par le
    barreau 3 »), `contradiction` (« barreau 2 ou 3 »), `repercussions` et `vers-issues`
    (« barreau 3 ») —, **5** numéros cités, **4** fuyaient : chaque « 3 », le brouillon, devenu le
    barreau 4 ; le « 2 » de `contradiction` reste juste. Commande : ce test, sur une copie de
    travail de `beb6190` ; `git grep -nE "barreaux? [0-9]" beb6190 -- .claude CLAUDE.md
    CONTRIBUTING.md .github` rend les mêmes 4 sites, aucun coupé en fin de ligne.

    Hors de cette forme (obs 139), les renvois sans numéro : « Création d'issues en cours de
    cycle » cherché sur le même texte normalisé rend, hors de la règle, **13** renvois, dont ces 3
    numérotés et **10** sans numéro ; **1** fuyait, la vérif de fumée de `cycle-pr` Étape 7, qui
    énumère les barreaux — épinglée à part. Les 9 autres renvoient à la règle sans l'énumérer,
    pour une décision, ou vers un brouillon `bug-vers-issue`, qui qualifie (`repercussions` ×2).
    """
    renvois = {
        fichier: numeros
        for fichier, texte in prose_du_harnais()
        if (numeros := barreaux_cites(texte))
    }

    assert renvois == RENVOIS_AUX_BARREAUX


def test_la_liste_des_barreaux_est_celle_que_citent_les_renvois() -> None:
    """Un barreau inséré, retiré ou déplacé rougit ici, avant de renuméroter ses renvois en
    silence : sans ce test, un barreau inséré restait vert (mutation, 2026-10-27)."""
    assert barreaux_existants() == list(enumerate(TETES_DES_BARREAUX, start=1))


@pytest.mark.parametrize(
    ("fichier", "numeros"), RENVOIS_AUX_BARREAUX.items(), ids=RENVOIS_AUX_BARREAUX.keys()
)
def test_chaque_barreau_cite_existe(fichier: str, numeros: list[int]) -> None:
    """Un renvoi au-delà du dernier barreau rougit."""
    existants = [numero for numero, _ in barreaux_existants()]

    assert set(numeros) <= set(existants), f"`{fichier}` cite {numeros}, la liste a {existants}"


# Le renvoi qui remplace un passage de `cycle-pr/SKILL.md` déplacé vers ses références (#177) :
# `→ [references/<f>](references/<f>), « <titre> ».`, en fin de ligne, après une tête en gras ou non.
RENVOI_DE_REFERENCE = re.compile(r"(?m)→ \[references/([^\]]+)\]\(references/\1\), « (.+) »\.$")
# Le recueil du motif, des deux côtés : le texte, puis le fichier et le titre qu'il lit.
RENVOI_DE_REFERENCE_FORMES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "sans-tete": ("→ [references/a.md](references/a.md), « Un titre ».", [("a.md", "Un titre")]),
    "avec-tete": ("**Tête.** → [references/b.md](references/b.md), « Tête ».", [("b.md", "Tête")]),
    "lien-vers-un-autre-fichier-hors-classe": ("→ [references/a.md](references/b.md), « T ».", []),
    "lien-sans-fleche-hors-classe": ("[references/a.md](references/a.md), « T »", []),
}
TEXTE_DE_CYCLE_PR = (REPOSITORY_ROOT / CYCLE_PR_SKILL).read_text(encoding="utf-8")
RENVOIS_DE_CYCLE_PR = RENVOI_DE_REFERENCE.findall(TEXTE_DE_CYCLE_PR)


@pytest.mark.parametrize(
    ("texte", "renvois"),
    RENVOI_DE_REFERENCE_FORMES.values(),
    ids=RENVOI_DE_REFERENCE_FORMES.keys(),
)
def test_un_renvoi_de_reference_se_lit_par_son_fichier_et_son_titre(
    texte: str, renvois: list[tuple[str, str]]
) -> None:
    """Le motif lit le renvoi, tête en gras ou non, et rien d'autre qu'un renvoi."""
    assert RENVOI_DE_REFERENCE.findall(texte) == renvois


def test_chaque_fleche_de_cycle_pr_vers_une_reference_est_lue_par_le_motif() -> None:
    """Le test suivant ne passe ni à vide ni à côté : 34 renvois au commit qui l'introduit, et
    chaque `→ [references/` du skill en est un. Un renvoi mal formé — point final retiré, ligne
    coupée — sortait sinon de la population en silence, et le test suivant restait vert."""
    assert RENVOIS_DE_CYCLE_PR
    assert len(RENVOIS_DE_CYCLE_PR) == TEXTE_DE_CYCLE_PR.count("→ [references/")


@pytest.mark.parametrize(
    ("fichier", "titre"), RENVOIS_DE_CYCLE_PR, ids=[titre for _, titre in RENVOIS_DE_CYCLE_PR]
)
def test_chaque_renvoi_de_cycle_pr_mene_a_un_titre_de_sa_reference(
    fichier: str, titre: str
) -> None:
    """Un renvoi dont la référence ne porte pas le titre `## <titre>` rougit : sans ce test, un
    renvoi vers un titre absent restait vert (mutation M6, passe 1 de la PR #182)."""
    reference = REPOSITORY_ROOT / ".claude/skills/cycle-pr/references" / fichier
    titres = re.findall(r"(?m)^## (.+)$", reference.read_text(encoding="utf-8"))

    assert titre in titres, f"`{fichier}` ne porte pas « {titre} »"


# --- La règle du sujet : aucun seuil de taille ne fait plus découper (#195) ---------------------

# `taille-pr.md` faisait découper une PR au-delà de « ~10 fichiers » ou de « ~500 lignes de diff », et
# rouvrir le découpage au « double de l'estimation ». La règle du sujet (#195 ; étude du 2026-10-29,
# §8.5) n'a plus de seuil de lignes, de fichiers ni d'estimation : seul le périmètre rouvre le
# découpage. Un de ces seuils réécrit dans un texte qui découpe le rétablirait, la session suivant
# le texte et non l'intention. Le motif lit chaque seuil sous ses variantes — tilde ou non, verbe
# conjugué, « deux fois » ou « 2× » (relecture de la PR #199, passe 1, m1), apostrophe
# typographique, coupe de ligne — et laisse les nombres de la règle neuve.
SEUIL_DE_TAILLE_RETIRE = re.compile(
    r"(?<!\d)(?<!\d\s)~?\s?(?:10\s+fichiers|500\s+lignes)"
    r"|(?:doubl\w*\s+(?:de\s+)?|deux\s+fois\s+|2\s?[×x]\s+)"
    r"(?:l['’]\s?|son\s+|leur\s+)estimation",
    re.IGNORECASE,
)
SEUIL_DE_TAILLE_FORMES = {
    "regle-d-origine": ("Au-delà de **~10 fichiers** ou **~500 lignes de diff**, découper.", True),
    "gabarit-du-body": ("Au-delà de **~10 fichiers** ou **~500 lignes** de diff", True),
    "sans-tilde": ("au-delà de 500 lignes de diff, découper la PR", True),
    "tilde-et-espace": ("PR ≤ ~ 10 fichiers", True),
    "double-de-l-estimation": ("le **double de l'estimation du briefing** rouvre", True),
    "double-coupe-en-fin-de-ligne": ("l'absolu, et le double de\nl'estimation du briefing", True),
    "doubler-son-estimation": ("n'autorise pas un lot à doubler son estimation", True),
    "apostrophe-typographique": ("au double de l’estimation", True),
    "deux-fois-l-estimation": ("au-delà de deux fois l'estimation, rouvrir", True),
    "fois-deux-en-symbole": ("un lot à 2× son estimation se re-découpe", True),
    "plancher": ("Un sujet estimé sous ~300 lignes", False),
    "bloc": ("≈ 650 lignes ou ≈ 350 K de contexte de `developpeur`", False),
    "revue-de-fin-de-vague": ("moins de 3 PR de plus de 1 500 lignes", False),
    "revue-espace-insecable": ("plus de 1\u202f500 lignes", False),
    "nombre-colle": ("une PR de 1500 lignes", False),
    "voie-courte": ("≤ 50 lignes et ≤ 3 fichiers", False),
}
# Les textes qui décident d'un découpage — en issues, en lots, ou d'un regroupement sous le
# plancher. **Dénombrement**, écrit avant le correctif (relecture de la PR #199, passe 1, I2 :
# `triage`, que le point 2 de la règle nomme, manquait) : `git grep -c -i "découp" -- .claude`
# sur `0a8b14a`, lu fichier par fichier — **9** groupes décident, 4 étaient lus. Ajoutés :
# `triage` (le plancher ; `brief-agent.md`, un découpage en lots se valide par ses tests),
# `bug-vers-issue` (issue unique ou découpage), `interroge-moi` (le découpage, coût présenté au
# mainteneur), `repercussions` (re-découpage d'une issue ouverte), `contraintes.md` (la réponse
# type de la voie T, « découpe en lots » ; passe 2, m7). Hors classe, parce qu'ils le citent sans
# le décider : `pr-paralleles` (une vague choisit des issues, elle n'en découpe aucune),
# `CLAUDE.md`, `CONTRIBUTING.md`, `developpeur.md`, `pipeline.config.md` et `init-projet` (le rang
# des issues dans la table des sources), `vers-prd` (le PRD que `vers-issues` découpe),
# `cleanup-verbatim.md` (« découplées »).
TEXTES_QUI_DECOUPENT = {
    "regle-de-taille": ".claude/rules/taille-pr.md",
    "cycle-pr": CYCLE_PR_SKILL,
    "references-de-cycle-pr": ".claude/skills/cycle-pr/references/*.md",
    "vers-issues": VERS_ISSUES_SKILL,
    "triage": ".claude/skills/triage/*.md",
    "bug-vers-issue": ".claude/skills/bug-vers-issue/**/*.md",
    "interroge-moi": INTERROGE_MOI_SKILL,
    "repercussions": ".claude/skills/repercussions/**/*.md",
    "contraintes": CONTRAINTES_RULE,
}


@pytest.mark.parametrize(
    ("texte", "seuil"), SEUIL_DE_TAILLE_FORMES.values(), ids=SEUIL_DE_TAILLE_FORMES.keys()
)
def test_le_motif_des_seuils_de_taille_retires_ne_vise_qu_eux(texte: str, seuil: bool) -> None:
    """Le témoin des deux côtés : chaque forme d'un seuil retiré appariée, chaque nombre de la règle
    du sujet laissé."""
    assert bool(SEUIL_DE_TAILLE_RETIRE.search(texte)) is seuil


@pytest.mark.parametrize("motif", TEXTES_QUI_DECOUPENT.values(), ids=TEXTES_QUI_DECOUPENT.keys())
def test_aucun_texte_qui_decoupe_ne_rend_un_seuil_de_taille_retire(motif: str) -> None:
    """**Population**, texte aux espaces normalisés : sur `69f1dfe`, **7** seuils dans 2 fichiers —
    `taille-pr.md` ×4 (« Découpage »), `cycle-pr/SKILL.md` ×3 (3.5 et gabarit du body de
    l'Étape 5) ; **0** sur la tête. Commande : ce test sur une copie de travail de `69f1dfe`."""
    fichiers = [
        p.relative_to(REPOSITORY_ROOT).as_posix() for p in sorted(REPOSITORY_ROOT.glob(motif))
    ]
    sites = [
        f"{fichier} : {seuil.group(0).strip()}"
        for fichier in fichiers
        for seuil in SEUIL_DE_TAILLE_RETIRE.finditer(texte_normalise(fichier))
    ]

    assert fichiers, f"`{motif}` ne désigne plus aucun fichier"
    assert not sites, f"un seuil de taille retiré fait de nouveau découper : {sites}"


def test_le_bloc_gh_pr_create_porte_label_et_milestone() -> None:
    """Label et milestone dans le bloc que l'agent copie (obs 114 : la PR #123 est née sans l'un ni
    l'autre). Texte brut, ligne qui suit l'appel : le texte normalisé retire les marges `# `, et une
    option commentée y passerait (relecture de la PR #199, passe 2, m4)."""
    bloc = (
        "gh pr create --draft --assignee @me \\\n"
        '  --label "<label de catégorie>" --milestone "<thème des fichiers>" \\\n'
    )
    assert bloc in (REPOSITORY_ROOT / CYCLE_PR_SKILL).read_text(encoding="utf-8")


# --- La porte de merge lit la trace du run, la conversation et le brief (#197) -----------------

VERIFICATEUR_ROLE = ".claude/agents/verificateur.md"


# Une lecture des commentaires d'une PR qui prouve un verdict ou garde un merge lit aussi ses
# commentaires en ligne, **après** le relevé : `gh pr view <n> --comments` ne rend pas ceux d'une
# revue, que `--releve` compte (PR #200, le 2026-10-29 vers 21 h UTC, population vivante : 9 revues
# sans texte comptées, 0 ligne de `--comments`, 9 commentaires en ligne par `gh api` ; 5 éléments
# pour 0 ligne à la passe 2 de relecture), et un élément arrivé entre une lecture et le relevé qui
# la suit passerait la porte compté sans avoir été lu. **Dénombrement, écrit avant le correctif**
# (relecture de la PR #200, passe 2, I1), sur `f165555` :
#
#     git grep -n -e "comments" f165555 -- ".claude/*.md" CLAUDE.md CONTRIBUTING.md
#
# rend 11 lignes en 8 fichiers. **2** lisent les commentaires d'une PR comme preuve, et **fuyaient**
# toutes deux — aveugles aux commentaires en ligne, lues avant le relevé : le point 1 du
# `verificateur` et la PR sans `verificateur` de `cycle-pr` Étape 7, qui gardent l'une et l'autre le
# go. **6** lisent ceux d'une issue, qui n'a pas de revue (`gh issue view`, `issues/<n>/comments`),
# et **3** parlent de commentaires de code : hors classe. Les sites qui prennent un relevé sans
# commande de lecture : `git grep -n -e "--releve"` rend 4 lignes, les 2 ci-dessus plus la voie
# courte, qui renvoie à « Vérification d'avant-go », indemne une fois sa lecture corrigée, et
# l'étape 6 de `triage/hors-scope.md`, qui lisait avant de relever et **fuyait** ; le relevé neuf
# de « Le go, puis le merge », lu sans la commande, renvoie de même. 3 sites corrigés en tout,
# ceux de la table.
LECTURES_DES_COMMENTAIRES_D_UNE_PR = {
    "verificateur-point-1": VERIFICATEUR_ROLE,
    "cycle-pr-pr-sans-verificateur": CYCLE_PR_SKILL,
    "hors-scope-releve-neuf": HORS_SCOPE_REF,
}
LECTURE_DES_COMMENTAIRES_D_UNE_PR = re.compile(r"gh pr view <n> --comments")
COMMENTAIRES_EN_LIGNE = "gh api --paginate repos/{owner}/{repo}/pulls/<n>/comments"


def test_les_lectures_des_commentaires_d_une_pr_sont_celles_de_la_table() -> None:
    """Un site neuf rougit ici tant qu'il n'est pas inscrit, donc lu par le test suivant ; les
    rôles en font partie, d'où la population de `.claude/` entière."""
    sites = sites_du_geste(LECTURE_DES_COMMENTAIRES_D_UNE_PR, ".claude/**/*.md")

    assert sites == sorted(LECTURES_DES_COMMENTAIRES_D_UNE_PR.values())


@pytest.mark.parametrize(
    "fichier",
    LECTURES_DES_COMMENTAIRES_D_UNE_PR.values(),
    ids=LECTURES_DES_COMMENTAIRES_D_UNE_PR.keys(),
)
def test_chaque_lecture_des_commentaires_d_une_pr_suit_le_releve_et_lit_les_commentaires_en_ligne(
    fichier: str,
) -> None:
    """Dans le bloc qui lit, le relevé précède la lecture, et la lecture nomme les commentaires en
    ligne."""
    blocs = blocs_du_geste(REPOSITORY_ROOT / fichier, LECTURE_DES_COMMENTAIRES_D_UNE_PR)

    assert blocs, f"`{fichier}` ne lit plus les commentaires de la PR"
    for bloc in blocs:
        assert COMMENTAIRES_EN_LIGNE in bloc, f"`{fichier}` ne lit pas les commentaires en ligne"
        assert "--releve" in bloc, f"`{fichier}` lit la conversation sans la relever"
        assert bloc.index("--releve") < bloc.index("--comments"), (
            f"`{fichier}` lit la conversation avant de la relever"
        )


# La tête que `porte-merge.py trunk` lie au run est celle que la porte passe à
# `--match-head-commit` : un seul nom aux deux commandes, sans quoi deux valeurs peuvent les
# remplir (correctif du script après la passe 2 de relecture de la PR #200). Dénombré sur
# `f165555` :
#
#     git grep -n "porte-merge.py trunk <run>" f165555 -- "*.md"
#
# rend 5 appels de `trunk` dans la prose — voie courte, Étapes 5 et 7 de `cycle-pr`,
# `verificateur.md`, `pr-paralleles` —, tous sous `<SHA de tête>`, la porte sous
# `<SHA de tête vérifié>`.
APPEL_DE_TRUNK = re.compile(r"porte-merge\.py trunk <run> (?:<[^<>]+>|\S+) <([^<>]+)>")
NOM_DE_LA_TETE = "SHA de tête vérifié"


def test_chaque_appel_de_trunk_nomme_la_tete_comme_la_porte() -> None:
    """Le dernier argument de chaque appel de `trunk` porte le nom de la tête de `gh pr merge`."""
    appels = [
        (fichier, tete)
        for fichier, texte in prose_du_harnais()
        for tete in APPEL_DE_TRUNK.findall(texte)
    ]

    assert appels, "aucun appel de `porte-merge.py trunk` lu : le motif a-t-il cessé de mordre ?"
    assert all(tete == NOM_DE_LA_TETE for _, tete in appels), appels
    assert f"--match-head-commit <{NOM_DE_LA_TETE}>" in texte_normalise(CYCLE_PR_SKILL)
