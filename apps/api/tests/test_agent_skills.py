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
import shlex
import shutil
import subprocess
import sys
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
# passe 2) : la table exigeait qu'un prédicat existe, pas qu'il y en ait deux.
PORTES_PRESCRITES: list[tuple[str, str, str, int]] = [
    (".claude/skills/cycle-pr/SKILL.md", "git checkout -b", "git merge-base --is-ancestor", 2),
    (".claude/skills/cycle-pr/SKILL.md", "gh pr merge", "git merge-base --is-ancestor", 1),
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
        f"-{action.replace(' ', '-')}"
        for skill, action, _, _ in PORTES_PRESCRITES
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
    (`session-relecture.md`, « Repli »).

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


# Les invariants que le lot 1 de #107 inscrit dans la prose, chacun avec la phrase qui le porte.
#
# **Population** : une entrée par point du bloc « Lot 1/4 » de #107 et par décision de son brief
# que le lot fait écrire (3, 7, 9, 10, 11, 16), par observation que le bloc fait fermer (94, 98,
# 102), plus les deux que la relecture a ajoutées (le lead désigné par le prompt, l'UUID de
# scratchpad qui n'adresse pas une session liée) et les deux de l'amendement qui a suivi la mesure
# sur l'enfant jetable (l'enfant lit son parent dans son prompt, la porte du nettoyage compare
# l'échafaudage à sa source — journal de spec de #107, 2026-10-16). La commande du
# premier geste porte trois invariants à elle seule (`origin/`, `--no-track`, `&&`). Gardés
# ailleurs : les renvois (`SKILLS_DES_SESSIONS_LIEES`, onze au 2026-10-26), le point de départ
# `origin/` (`DEPARTS_EXPLICITES`), la porte du nettoyage (`PORTES_PRESCRITES`). Restent en
# lecture, à dessein : les formes du message de fin autres que celle d'un lot — sauf celle de fin
# d'interrogatoire, que l'étape 0 de `pr-paralleles` consomme depuis le lot 4 (gardée plus bas).
#
# **Recensée à la passe 2 de la relecture de la PR #109**, après qu'un premier dénombrement à
# 9 invariants s'est révélé n'être que les échantillons de la passe 1 : 4 invariants verrouillés
# restaient sans garde (héritage du mode, `fresh`, note automatique, commandes intégrées) et 2
# renvois après corrections pouvaient retrouver leur confirmation (mesuré : mutations VERTES).
#
# **Borne** : le test exige que la phrase **existe**, pas qu'aucune phrase contraire ne s'ajoute
# ailleurs — une confirmation rétablie à côté d'une phrase intacte reste verte (mesuré, passe 2).
# Une phrase réécrite fait rougir, et c'est voulu : la réécriture d'un invariant verrouillé se
# relit.
#
# **Lot 2b** (la coordinatrice) : une entrée par point du bloc « Lot 2/4 » que 2a n'a pas livré, par
# décision du brief que 2b fait écrire (4, 5, 8, 12, 14, 16, 17), par entrée du journal de spec
# qu'il applique (pré-démarrage, amorce de la PR d'intégration) et pour l'obs 85 qu'il ferme, plus
# l'**ordre** et la **condition** du protocole — que la relecture de la PR #122 a trouvés sans garde
# (I1 : cinq mutations VERTES) — et un cas par constat important qu'elle a fait corriger. Gardés
# ailleurs : les deux créations de branche (`DEPARTS_EXPLICITES`), le merge d'un lot
# (`test_merge_lot.py`, lot 2a), le comportement de git sous `merge-tree` (`FRESHNESS_GATE_FORMS`
# garde git, pas la prose qui l'emploie : celle-ci l'est ici).
#
# **Lot 3** (`pr-paralleles`) : une entrée par point du bloc « Lot 3/4 » qui écrit une règle, par
# décision du brief qu'il fait écrire (8, 9, 16) et pour l'obs 103 ; la mesure de `bind_pr`
# (journal de spec, 2026-10-18) en ajoute une. Gardés ailleurs : les gestes que le lot retire
# (`GESTES_RETIRES_DE_PR_PARALLELES`) et le premier geste d'un enfant (`DEPARTS_EXPLICITES`).
#
# **Lot 4** (l'étape 0 de `pr-paralleles`) : une entrée par point du bloc « Lot 4/4 » qui écrit
# une règle, par décision du brief qu'il fait écrire (8, 15) et pour la forme de fin d'interrogatoire,
# que l'étape 0 est la première à consommer — 12 ; plus 5 par correctif du `/code-review` de la
# PR #133 et 12 par constat de sa relecture, passe 1 (I-1 à I-4, m-3 à m-5), plus 1 de sa
# vérification d'avant-go (chaque message de fin attendu) — 30. Gardés ailleurs :
# `use_worktree` écrit à chaque démarrage (`USE_WORKTREE_EXPLICITE`), l'ordre de l'étape
# (`ORDRE_DE_PR_PARALLELES`), la limite de chaque `gh … list`
# (`test_chaque_liste_gh_de_pr_paralleles_porte_sa_limite`).
SESSIONS_LIEES_REF = ".claude/skills/cycle-pr/references/sessions-liees.md"
COORDINATRICE_REF = ".claude/skills/cycle-pr/references/coordinatrice.md"
PROMPT_LOT_SUIVANT = ".claude/skills/cycle-pr/references/prompt-lot-suivant.md"
PR_PARALLELES_SKILL = ".claude/skills/pr-paralleles/SKILL.md"
INTERROGE_MOI_SKILL = ".claude/skills/interroge-moi/SKILL.md"
CYCLE_PR_SKILL = ".claude/skills/cycle-pr/SKILL.md"
BRIEFING_REF = ".claude/skills/cycle-pr/references/briefing.md"
PORTES_REF = ".claude/skills/cycle-pr/references/portes.md"
CLOTURE_REF = ".claude/skills/cycle-pr/references/cloture.md"
TRIAGE_SKILL = ".claude/skills/triage/SKILL.md"
HORS_SCOPE_REF = ".claude/skills/triage/hors-scope.md"
RELEVEUR_ROLE = ".claude/agents/releveur.md"
VERS_PRD_SKILL = ".claude/skills/vers-prd/SKILL.md"
VERS_ISSUES_SKILL = ".claude/skills/vers-issues/SKILL.md"
REPERCUSSIONS_SKILL = ".claude/skills/repercussions/SKILL.md"
CONTRADICTION_SKILL = ".claude/skills/contradiction/SKILL.md"
CONTRAINTES_RULE = ".claude/rules/contraintes.md"
BUG_VERS_ISSUE_SKILL = ".claude/skills/bug-vers-issue/SKILL.md"
COLLECTE_CONTEXTE_REF = ".claude/skills/bug-vers-issue/references/collecte-contexte.md"
GABARIT_BUG_REF = ".claude/skills/bug-vers-issue/references/gabarit-issue-bug.md"
GABARIT_DECOUPAGE_REF = ".claude/skills/bug-vers-issue/references/gabarit-issue-decoupage.md"
THEMES_MILESTONES_REF = ".claude/skills/triage/themes-milestones.md"
BRIEF_AGENT_REF = ".claude/skills/triage/brief-agent.md"
PATCH_CHECKBOX_REF = ".claude/skills/execution-qa/references/patch-checkbox-gh.md"
EXECUTION_QA_SKILL = ".claude/skills/execution-qa/SKILL.md"
INTAKE_ECHEC_REF = ".claude/skills/execution-qa/references/gabarit-intake-echec.md"
COMMENTAIRE_PHASE_REF = ".claude/skills/execution-qa/references/gabarit-commentaire-phase.md"
CORRECTION_BUG_REF = ".claude/skills/execution-qa/references/standard-correction-bug.md"
PLAN_QA_SKILL = ".claude/skills/plan-qa/SKILL.md"
AUDIT_SPEC_UI_SKILL = ".claude/skills/audit-spec-ui/SKILL.md"
INIT_PROJET_SKILL = ".claude/skills/init-projet/SKILL.md"
GABARIT_PLAN_QA_REF = ".claude/skills/plan-qa/references/gabarit-plan-qa.md"
EXEMPLE_BLOC_ISSUE_REF = ".claude/skills/plan-qa/references/exemple-bloc-issue.md"
TAXONOMIE_COUVERTURE_REF = ".claude/skills/plan-qa/references/taxonomie-couverture.md"
INVARIANTS_DES_SESSIONS_LIEES = {
    # Héritage (décision 7).
    "heritage-sans-permission-mode": (
        SESSIONS_LIEES_REF,
        "**Jamais de `permission_mode`** au démarrage d'un enfant : il hérite de celui du parent",
    ),
    "contexte-neuf-jamais-fork": (SESSIONS_LIEES_REF, "`context: fresh`, jamais `fork`"),
    # Identité.
    "enfant-lit-son-parent-dans-son-prompt": (
        SESSIONS_LIEES_REF,
        "L'enfant lit l'adresse de son parent dans **son prompt système**",
    ),
    "parent-designe-l-enfant-par-son-session-id": (
        SESSIONS_LIEES_REF,
        "Le parent désigne l'enfant par le `session_id` (`local_…`)",
    ),
    "porte-du-nettoyage-sur-la-source": (
        SESSIONS_LIEES_REF,
        "git merge-base --is-ancestor claude/<slug>-<hex> <source> && git branch -D",
    ),
    # Porté par `pr-paralleles` Étape 5 jusqu'au lot 3, qui retire l'identification par le
    # scratchpad : la phrase de la référence garde le même invariant.
    "scratchpad-n-adresse-pas-une-session-liee": (
        SESSIONS_LIEES_REF,
        "pas l'identifiant `local_…` de l'application",
    ),
    # Premier geste (décision 10).
    "premier-geste-chaine-sans-suivi": (
        SESSIONS_LIEES_REF,
        "`git fetch origin && git checkout -b <type>/<slug> --no-track origin/<base>`",
    ),
    "echafaudage-sans-commit": (
        SESSIONS_LIEES_REF,
        "La branche `claude/…` reste un **échafaudage** : rien ne s'y commit",
    ),
    # Messages sans confirmation, jamais une approbation (décision 3).
    "messages-sans-confirmation": (SESSIONS_LIEES_REF, "**part sans confirmation du mainteneur**"),
    "message-du-lead-jamais-approbation": (
        BRIEFING_REF,
        "un message du lead n'est jamais une approbation",
    ),
    "lead-designe-par-le-prompt": (
        BRIEFING_REF,
        "est la session que ce prompt désigne comme tel, à défaut l'émettrice",
    ),
    "en-tete-sans-confirmation": (
        BRIEFING_REF,
        "l'envoyer par `SendMessage`, **sans confirmation**",
    ),
    # #134 lot 2a, décision 2 : la vérification d'avant-go passe du lead à la session PR ; les
    # quatre phrases de l'état envoyé au lead, épinglées ici depuis #107, sont retirées avec lui.
    "verificateur-lance-par-la-session-pr": (
        CYCLE_PR_SKILL,
        "**La session PR lance son `verificateur`**",
    ),
    "pr-paralleles-le-lead-ne-verifie-plus": (
        PR_PARALLELES_SKILL,
        "le lead ne reçoit plus d'état à vérifier et ne lance aucun `verificateur`",
    ),
    # Fin de travail (décision 11, obs 85, 94, 98).
    "fin-de-tour-jamais-un-signal": (
        SESSIONS_LIEES_REF,
        "La note automatique n'est **jamais** un signal.",
    ),
    "forme-de-fin-d-un-lot": (
        SESSIONS_LIEES_REF,
        r"« lot \<k>/\<n> terminé — PR #\<M> mergée dans \<base> — passation : \<chemin> »",
    ),
    "message-de-fin-aussi-au-lead": (
        SESSIONS_LIEES_REF,
        "En vague, le même message part aussi au lead s'il n'est pas le parent.",
    ),
    "interroge-moi-previent-le-parent": (
        INTERROGE_MOI_SKILL,
        "prévenir le parent par le message de fin de la même référence",
    ),
    # Passation (décision 9).
    "passation-du-lot-termine": (
        SESSIONS_LIEES_REF,
        "`passations/<date>-issue-<N>-lot-<k>-prompt.md` — lot `k` **terminé**",
    ),
    "passation-de-relais": (SESSIONS_LIEES_REF, "`passations/<date>-issue-<N>-lot-<k>-relais.md`"),
    "passation-par-pointeur": (
        SESSIONS_LIEES_REF,
        "La passation se remet par son chemin, dans le message de fin, jamais par son texte",
    ),
    # Nettoyage (décision 16).
    "archiver-ne-nettoie-pas": (
        SESSIONS_LIEES_REF,
        "Archiver un enfant (`archive_session`, réversible) détache son HEAD et ne retire ni",
    ),
    # Commandes intégrées (obs 94, 98, 115) : elles closent le tour de la session de relecture,
    # sans coût ; la session PR ne les joue qu'en repli, et y enchaîne dans le même tour.
    "commandes-integrees-closent-le-tour-de-la-relecture": (
        CYCLE_PR_SKILL,
        "**Ces deux commandes closent un tour — celui de la session de relecture.**",
    ),
    "commandes-integrees-en-repli-seulement": (
        CYCLE_PR_SKILL,
        (
            "En repli seulement, la session PR les joue : la consigne vaut alors pour la forme du"
            " rapport, pas pour l'arrêt du cycle, et elle enchaîne dans le même tour."
        ),
    ),
    "config-relecture-fin-de-tour-sans-cout": (
        ".claude/pipeline.config.md",
        (
            "Son outil de rapport peut clore le tour de la session de relecture, sans coût"
            " (`cycle-pr` 4.2, obs 94) — il ne l'a clos à aucune des deux passes du 2026-10-20"
            " (PR #141)"
        ),
    ),
    "config-securite-fin-de-tour-sans-cout": (
        ".claude/pipeline.config.md",
        "clôt le tour de la session de relecture, sans coût (`cycle-pr` 4.2, obs 98, 115).",
    ),
    # Question à la fois et groupement des `[V]` (obs 102).
    "interroge-moi-moment-et-forme": (
        INTERROGE_MOI_SKILL,
        (
            "le groupement porte sur le **moment** — un point d'arrêt, jamais le fil de l'eau —, "
            "cette règle sur la **forme**"
        ),
    ),
    # Coordinatrice (#107, lot 2b) : le découpage et ce qu'il fait de la session.
    "decoupage-fait-la-coordinatrice": (
        BRIEFING_REF,
        "la session devient la **coordinatrice** de ses lots",
    ),
    "issue-a-un-lot-inchangee": (
        BRIEFING_REF,
        "Une issue à un seul lot ne change rien : la session porte le cycle elle-même et délègue le code (3.1)",
    ),
    "coordinatrice-sans-code": (COORDINATRICE_REF, "La coordinatrice **n'écrit pas de code**"),
    # Au go du découpage (journal de spec, 2026-10-17 ; décisions 8, 12).
    "sessions-demarrees-au-go-du-decoupage": (
        COORDINATRICE_REF,
        "démarre d'un coup les sessions des lots non mergés",
    ),
    "start-session-d-un-lot": (
        COORDINATRICE_REF,
        "`context: fresh`, worktree de l'application, `wake_when_done: true`",
    ),
    "effort-par-lot": (
        COORDINATRICE_REF,
        (
            "`high` par défaut, `max` si le bloc du lot porte un ADR, une surface de sécurité ou "
            "un contrat entre piles, `medium` pour un lot de doc ou de config seule"
        ),
    ),
    "brief-nomme-le-lead-ou-aucun": (
        COORDINATRICE_REF,
        "nomme toujours son lead — celui de la vague, ou « aucun »",
    ),
    # Branche et PR d'intégration (décision 4 ; journal de spec, 2026-10-17).
    "branche-d-integration-depuis-le-trunk": (
        COORDINATRICE_REF,
        "`git fetch origin && git checkout -b <type>/<slug> --no-track origin/<trunk>`",
    ),
    "amorce-de-la-pr-d-integration": (COORDINATRICE_REF, "GitHub refuse une PR sans commit"),
    "pr-d-integration-marquee": (
        COORDINATRICE_REF,
        "« En vol pour #<N> (intégration, <n> lots) », puis `Closes #<N>`",
    ),
    "branche-de-lot-depuis-l-integration": (
        COORDINATRICE_REF,
        "`git fetch origin && git checkout -b <type>/<slug>-lot-<k> --no-track origin/<type>/<slug>`",
    ),
    "pr-de-lot-sans-closes": (
        COORDINATRICE_REF,
        "« En vol pour #<N> (lot <k>/<n>) », sans `Closes`",
    ),
    # Deux preuves, puis la dérive (décisions 12, 14 ; obs 85).
    "message-sans-passation-n-ouvre-rien": (
        COORDINATRICE_REF,
        "Un message de fin sans fichier de passation n'ouvre pas le lot suivant",
    ),
    # Cité : un chemin de passation Windows perd ses antislashs dans le shell (`/code-review` de la
    # PR #122), et le fichier présent se lirait absent.
    "passation-testee-chemin-cite": (COORDINATRICE_REF, "`test -f '<chemin>'` sort en 0"),
    # La condition du protocole (relecture de la PR #122, I1 : mutés, restaient verts) ; son
    # **ordre** l'est par `ORDRE_DE_LA_COORDINATRICE`, plus bas — une phrase présente ne dit rien de
    # sa place (relance, N1 : deux mutations VERTES).
    "attente-des-lots-suivants": (
        COORDINATRICE_REF,
        "chaque autre lot reçoit « attends le message « ouvre le lot <k>/<n> — passation : <chemin> »",
    ),
    "premier-geste-pas-avant-ouvre": (
        COORDINATRICE_REF,
        "au message « ouvre » — à la lecture de son brief pour le premier lot non mergé — et pas avant",
    ),
    "arret-sur-tout-code-non-nul": (
        COORDINATRICE_REF,
        "sur tout autre code non nul, elle s'arrête et lui remonte la sortie",
    ),
    "liste-des-pr-de-lot-a-chaque-lot": (
        COORDINATRICE_REF,
        "elle ajoute la PR #<M> à la liste du body de la PR d'intégration — première ligne intacte",
    ),
    "archivage-sur-accord": (
        SESSIONS_LIEES_REF,
        "Archiver un enfant attend l'accord du mainteneur",
    ),
    "passation-a-la-coordinatrice-a-l-etape-8": (
        CLOTURE_REF,
        "dans le message de fin, **à la coordinatrice**, qui ouvre la session du lot suivant",
    ),
    "derive-apres-chaque-lot": (
        COORDINATRICE_REF,
        "`git merge-tree --write-tree origin/<trunk> origin/<type>/<slug>`",
    ),
    "arret-au-premier-conflit": (
        COORDINATRICE_REF,
        "elle s'arrête au premier conflit et le remonte au mainteneur",
    ),
    "jamais-de-force-push-sur-l-integration": (
        COORDINATRICE_REF,
        "jamais de force-push sur la branche d'intégration",
    ),
    "merge-final-en-rebase": (COORDINATRICE_REF, "squash seulement sur demande explicite"),
    "repercussions-une-fois": (
        COORDINATRICE_REF,
        "`repercussions` tourne une fois, au merge de la PR d'intégration",
    ),
    "relais-par-carte": (COORDINATRICE_REF, "par une **carte de proposition**"),
    # Relecture de la PR #122 : I2 à I6, M4.
    "gabarit-worktree-sans-coordinatrice": (
        PROMPT_LOT_SUIVANT,
        "Si worktree, sans coordinatrice : tu es sur la branche **mergée**",
    ),
    "relais-remis-a-la-coordinatrice": (
        CLOTURE_REF,
        "à la coordinatrice pour une session de lot",
    ),
    "coordinatrice-au-plafond": (
        COORDINATRICE_REF,
        "La coordinatrice y tourne en Opus 5.5, effort `high`",
    ),
    "nettoyage-des-sessions-de-lot": (
        COORDINATRICE_REF,
        "se fait une fois, après ce merge, sur un seul accord du mainteneur",
    ),
    "lien-d-une-pr-de-lot-non-repose": (
        COORDINATRICE_REF,
        "Le lien d'une PR de lot ne se repose pas",
    ),
    "pas-de-mot-cle-sur-une-pr-de-lot": (
        CYCLE_PR_SKILL,
        "une PR de lot vers une branche d'intégration n'en reçoit pas",
    ),
    "arret-de-lot-previent-la-coordinatrice": (
        COORDINATRICE_REF,
        "« bloquant : go humain requis dans cette fenêtre — session de relecture à démarrer »",
    ),
    "repli-manuel": (COORDINATRICE_REF, "l'échec devient une observation du journal"),
    # La session de lot (décisions 5, 17).
    "en-tete-session-de-lot": (
        CYCLE_PR_SKILL,
        "lire d'abord [references/coordinatrice.md](references/coordinatrice.md), « La session de lot »",
    ),
    "lead-d-une-session-de-lot": (
        BRIEFING_REF,
        "pour une session de lot, celle que son brief nomme, ou aucune",
    ),
    # Lot 8b de #134 (2026-10-26) : le démarrage des lots par la coordinatrice, le go délégué et sa
    # relecture (journal de spec de #134, 2026-10-21, relais de la coordinatrice ; obs 131) ; les
    # paramètres du démarrage sont gardés par `USE_WORKTREE_EXPLICITE`. Par la forme, sur les lignes
    # ajoutées : 10 moitiés restrictives — 4 « seul(ement) », 2 « sauf », 2 « ne … pas », « aucun »,
    # « hors de ce cas » —, et 1 reprise d'une ligne repliée (« jamais un point de départ »), toutes
    # épinglées et vues rouges par `mutation.py`.
    "branche-mergee-jamais-un-depart": (COORDINATRICE_REF, "n'est jamais un point de départ"),
    "go-du-briefing-humain-ou-delegue": (
        COORDINATRICE_REF,
        "humain, dans la fenêtre de la session de lot, ou délégué à la coordinatrice**",
    ),
    "go-delegue-seulement-sans-v-ecart-ni-c": (
        COORDINATRICE_REF,
        (
            "valable seulement pour un briefing sans `[V]`, sans écart au bloc du lot et sans"
            " `[C]`. Hors de ce cas, la session s'arrête à son Étape 1."
        ),
    ),
    "go-delegue-question-au-mainteneur": (
        COORDINATRICE_REF,
        (
            "Sur un go délégué hors de ce cas, elle pose la question au mainteneur dans la fenêtre"
            " du lot et prévient la coordinatrice"
        ),
    ),
    "bloquant-sur-go-delegue": (COORDINATRICE_REF, "bloquant : [V] en attente dans cette fenêtre"),
    "fin-de-tour-pas-un-signal": (COORDINATRICE_REF, "note de fin de tour n'est pas un signal"),
    "ouverture-par-la-coordinatrice": (COORDINATRICE_REF, "La coordinatrice prépare alors"),
    "demarree-a-son-ouverture": (
        COORDINATRICE_REF,
        "**démarrée à son ouverture**, sur décision du mainteneur, elle naît après le merge",
    ),
    "demarree-dans-un-tour-du-mainteneur": (
        COORDINATRICE_REF,
        "dans le premier tour ouvert par un message du mainteneur, seul geste humain qui reste",
    ),
    "outils-d-une-session-pre-demarree": (
        COORDINATRICE_REF,
        (
            "pré-démarrée, elle lit `git diff <SHA de son démarrage>..HEAD -- .claude/ CLAUDE.md`"
            " et les sections touchées par `Read`, et passe un rôle modifié dans le brief de son"
            " sous-agent"
        ),
    ),
    "relecture-en-repli-sur-go-delegue": (
        COORDINATRICE_REF,
        (
            "la relecture passe par le repli sous-agent `relecteur` (`session-relecture.md`,"
            " « Repli »), sauf si un tour humain s'ouvre dans la fenêtre du lot avant la passe"
        ),
    ),
    "repli-par-un-message-d-abord": (
        COORDINATRICE_REF,
        (
            "`start_session` refusé ou aucun tour du mainteneur qui vienne, la coordinatrice"
            " demande au mainteneur d'ouvrir un tour par un message, le seul geste humain, et"
            " seulement s'il ne le peut pas"
        ),
    ),
    # Passe 1 de la PR #162, CR-1 et m5 — classe : une phrase de la session de lot écrite pour une
    # seule de ses formes, ou pour le seul go humain. **Dénombrement, écrit avant le correctif** :
    # les 8 puces de « La session de lot », **1** fuyait — le premier geste ; le go délégué, relayé
    # par le fichier de démarrage, est propre à la forme démarrée à son ouverture par construction
    # — ; ses 7 renvois entrants (`grep -rn` du titre dans `.claude/` : 9 lignes, moins le titre et
    # une phrase du relais), **2** fuyaient — le go annoncé au go du découpage, et `cycle-pr` (m5,
    # `cycle-pr-sauf-go-delegue`).
    "premier-geste-de-la-forme-demarree-a-son-ouverture": (
        COORDINATRICE_REF,
        "et pas avant ; démarrée à son ouverture, à la lecture de son fichier de démarrage :",
    ),
    "go-du-decoupage-sauf-go-delegue": (
        COORDINATRICE_REF,
        "— sauf go délégué, où la relecture passe au repli `relecteur` (« La session de lot »)",
    ),
    "go-du-decoupage-annonce-un-go-par-lot": (
        COORDINATRICE_REF,
        "annonce un go par lot, dans sa fenêtre",
    ),
    "base-de-la-pr-de-lot": (COORDINATRICE_REF, "se lit `origin/<type>/<slug>`"),
    "verification-jamais-a-la-coordinatrice": (
        COORDINATRICE_REF,
        "lance elle-même son `verificateur` (`cycle-pr` Étape 7), jamais la coordinatrice",
    ),
    "etape-8-du-lot-bornee": (
        COORDINATRICE_REF,
        (
            "Son Étape 8 se borne à cocher ses critères, nettoyer sa session de relecture et écrire"
            " sa passation"
        ),
    ),
    "relecteur-plage-depuis-la-base-de-la-pr": (
        ".claude/agents/relecteur.md",
        "La plage que tu reçois part de la base de la PR",
    ),
    "verificateur-base-d-une-pr-de-lot": (
        ".claude/agents/verificateur.md",
        "`<trunk>` se lit cette branche partout ci-dessous",
    ),
    # Passation (obs 85) et frontière de lot.
    "passation-en-dernier": (
        CYCLE_PR_SKILL,
        "**La passation s'écrit en dernier, depuis les artefacts**",
    ),
    # Relecture de la PR #139, passe 2, I-6 : `pr-paralleles` 6 fait lire la base du verdict dans
    # les Notes ; sans sa ligne d'en-tête, la colonne « Base du verdict » n'a plus de source.
    "verdict-en-tete-dans-les-notes": (
        CYCLE_PR_SKILL,
        "au moins sa ligne d'en-tête (base, tête) et ses lignes « Fichiers croisés »",
    ),
    "passation-sans-point-ouvert": (PROMPT_LOT_SUIVANT, "jamais un point encore ouvert (obs 85)"),
    "passation-remise-a-la-coordinatrice": (
        PROMPT_LOT_SUIVANT,
        "remis par ce chemin à la coordinatrice",
    ),
    "pr-paralleles-un-worktree-neuf-par-lot": (
        PR_PARALLELES_SKILL,
        "chaque lot a sa session et son worktree neufs",
    ),
    # Lot 3 : `pr-paralleles` démarre, suit et nettoie ses sessions (bloc « Lot 3/4 », décisions
    # 8, 9, 16 du brief, obs 92, 93, 103, et la mesure de `bind_pr` du journal de spec du
    # 2026-10-18). Étape 3 : qui démarre, dans quel tour, avec quoi.
    "lead-demarre-une-session-par-issue": (
        PR_PARALLELES_SKILL,
        (
            "le lead se nomme d'abord `vague-<k>`, comme à l'étape 0, puis démarre d'un coup une"
            " session par issue retenue, une par `start_session`"
        ),
    ),
    "demarrage-au-seul-tour-du-mainteneur": (
        PR_PARALLELES_SKILL,
        "Dans le tour où le mainteneur valide le lot (étape 2), et dans celui-là seulement",
    ),
    "start-session-d-une-issue": (
        PR_PARALLELES_SKILL,
        (
            "`context: fresh`, worktree de l'application, `wake_when_done: true`,"
            " `title: <préfixe> › #<N>`"
        ),
    ),
    "brief-de-l-etape-5": (PR_PARALLELES_SKILL, "`prompt` : le brief de l'étape 5"),
    # Décision 8 : barème d'effort et plafond de l'arbre.
    "effort-par-bareme": (
        PR_PARALLELES_SKILL,
        "L'effort de chaque session suit le barème de la coordinatrice",
    ),
    "plafond-demande-a-l-etape-2": (
        PR_PARALLELES_SKILL,
        "si la session lead est en dessous d'Opus 5.5, effort `max`, de l'y passer d'abord",
    ),
    # Relecture de la PR #130, passe 1 : m-2 (mutation VERTE sans cette entrée), I-6.
    "brief-premier-geste-sans-suivi": (
        PR_PARALLELES_SKILL,
        "`git fetch origin && git checkout -b <type>/<slug> --no-track origin/main`",
    ),
    "brief-transmet-les-services": (
        PR_PARALLELES_SKILL,
        "Services à état recensés pour cette issue (étape 2) : <liste, ou « aucun »>.",
    ),
    # Obs 42 re-mesurée (2026-10-18) : l'archivage libère le dossier, dans le tour du message.
    "archivage-libere-le-dossier": (
        PR_PARALLELES_SKILL,
        "C'est l'archivage qui libère le dossier.",
    ),
    "archivage-dans-le-tour-du-message": (
        PR_PARALLELES_SKILL,
        "deux archivages acceptés dans un tour ouvert par un message de session",
    ),
    # `/code-review` de la PR #130 : omis, `use_worktree` donne le dossier du lead.
    "worktree-demande-en-clair": (
        PR_PARALLELES_SKILL,
        "Le worktree se demande en clair, `use_worktree: true`",
    ),
    "orphelines-lues-en-entier": (
        PR_PARALLELES_SKILL,
        "plus la branche du lead lui-même par `get_session` sur `self`",
    ),
    # Passe 2, R-4 : la clause de pagination, mutée seule, restait verte.
    "orphelines-sans-pagination": (PR_PARALLELES_SKILL, "rend 20 lignes par défaut"),
    "lead-ne-cree-ni-worktree-ni-branche": (
        PR_PARALLELES_SKILL,
        "Le lead ne crée ni worktree ni branche",
    ),
    "provisionnement-par-la-session": (
        PR_PARALLELES_SKILL,
        "**Provisionner son worktree — la session le fait, juste après son premier geste.**",
    ),
    # Étape 4 : le tableau hors dépôt (décision 9), et qui le lit.
    "tableau-hors-depot": (
        PR_PARALLELES_SKILL,
        "Maintenir un fichier `PR-PARALLELES.md` **hors du dépôt**",
    ),
    "repercussions-lit-le-tableau-hors-depot": (
        REPERCUSSIONS_SKILL,
        "hors dépôt, dans le dossier du projet qui porte `skill-observations/`",
    ),
    "colonne-session-par-identifiant": (
        PR_PARALLELES_SKILL,
        "le titre passé à `start_session` et le `local_…` qu'il a rendu",
    ),
    # Étape 5 : relais ; Étape 6 : le résumé au mainteneur (obs 103).
    "relais-de-vague-par-carte": (
        PR_PARALLELES_SKILL,
        "le lead ne peut pas démarrer la remplaçante : il la propose par une carte de proposition",
    ),
    "resume-information-pas-question": (
        PR_PARALLELES_SKILL,
        "Ce résumé est une **information**, jamais une question",
    ),
    "boite-de-fin-de-tour-sans-question": (
        PR_PARALLELES_SKILL,
        "le lead rend le récapitulatif seul, sans question ni bouton",
    ),
    # Étape 7 : l'état et le récit d'une session silencieuse.
    "session-disparue-par-get-session": (
        PR_PARALLELES_SKILL,
        "Son état se lit par `get_session` sur le `local_…` du tableau",
    ),
    "transcript-d-un-dossier-reutilise": (
        PR_PARALLELES_SKILL,
        "le bon transcript est celui dont la dernière écriture rejoint son `lastActivityAt`",
    ),
    # Étape 8 : archiver, puis worktree, branche de PR, échafaudage, orphelines (décision 16).
    "archiver-avant-de-retirer": (PR_PARALLELES_SKILL, "**archiver la session d'abord**"),
    "echafaudage-source-lue-par-get-session": (
        SESSIONS_LIEES_REF,
        "`get_session` le rend (`sourceBranch`",
    ),
    "orphelines-hors-sessions-vivantes": (
        PR_PARALLELES_SKILL,
        "qu'aucune session non archivée ne nomme (`list_sessions`, champ `branch`)",
    ),
    "bind-pr-en-repli": (
        SESSIONS_LIEES_REF,
        "`bind_pr` ne sert que si `get_status` ne la rapporte pas",
    ),
    # Docs mises à jour dans le même lot (bloc « Lot 3/4 », dernier point).
    "contributing-une-session-par-issue": (
        "CONTRIBUTING.md",
        "la session lead démarre une session par issue, chacune dans un worktree de l'application",
    ),
    "claude-md-sessions-liees": ("CLAUDE.md", "**Sessions liées.**"),
    "taille-pr-premier-geste": (
        ".claude/rules/taille-pr.md",
        "la porte vaut pour une branche créée sur `main`",
    ),
    # Lot 4 : l'étape 0 de `pr-paralleles` — entrée, crible, proposition, sessions, fin.
    "etape-0-entree": (
        PR_PARALLELES_SKILL,
        "aucune, moins que le `n` donné, ou une seule sans argument",
    ),
    # `/code-review` de la PR #133 : argument mêlé, troncature de `gh`, issues en vol au crible,
    # dossier partagé, session muette.
    "etape-0-argument-mele": (
        PR_PARALLELES_SKILL,
        "ou si une issue nommée en argument n'est pas prête",
    ),
    "etape-0-crible-sans-troncature": (
        PR_PARALLELES_SKILL,
        "`gh issue list --state open --limit 200 --json number,title,labels,author,body`",
    ),
    "etape-0-crible-sans-issue-en-vol": (
        PR_PARALLELES_SKILL,
        "et retirées celles en vol, comme à l'entrée",
    ),
    "etape-0-dossier-du-lead-fige": (
        PR_PARALLELES_SKILL,
        "tant que ses sessions lisent, n'y écrit rien et n'y change pas de branche",
    ),
    "etape-0-session-muette": (
        PR_PARALLELES_SKILL,
        "une session muette suit l'étape 7, « Session disparue »",
    ),
    # Relecture de la PR #133, passe 1 : I-1 (tête en avance), I-2 (message après la
    # transition), I-3 (session d'un bug), I-4 (écriture exigée), m-3 à m-5.
    "etape-0-premier-geste-du-lead": (
        PR_PARALLELES_SKILL,
        (
            "`git fetch origin && git merge-base --is-ancestor HEAD origin/main && git merge"
            " --ff-only origin/main`"
        ),
    ),
    "etape-0-tete-en-avance-refusee": (
        PR_PARALLELES_SKILL,
        "Le prédicat refuse une tête en avance ou divergente",
    ),
    "etape-0-message-apres-la-transition": (
        PR_PARALLELES_SKILL,
        (
            "Le message ne part qu'une fois la transition appliquée, y compris celui que demande"
            " `interroge-moi` à sa fin"
        ),
    ),
    "etape-0-forme-de-fin-consommee": (
        PR_PARALLELES_SKILL,
        "« interrogatoire #N terminé — ready-for-agent proposé »",
    ),
    "etape-0-bug-sans-branche": (
        PR_PARALLELES_SKILL,
        "`git fetch origin && git switch --detach origin/main` — aucune branche à créer",
    ),
    "etape-0-bug-provisionne": (
        PR_PARALLELES_SKILL,
        "puis les gestes 1 à 5 de `pr-paralleles` étape 3, « Provisionner son worktree »",
    ),
    "etape-0-bug-seul-archive": (
        PR_PARALLELES_SKILL,
        "C'est la seule session de l'étape qui s'archive, sur l'accord de la proposition",
    ),
    "etape-0-accord-d-archiver-le-bug": (
        PR_PARALLELES_SKILL,
        "demande l'accord d'archiver, une fois vérifiée, la session d'une issue `bug`",
    ),
    "etape-0-ecriture-exigee-bloquante": (
        PR_PARALLELES_SKILL,
        "ne se fait pas ici : « bloquant : <…> » à ton parent",
    ),
    "etape-0-etats-sans-session": (PR_PARALLELES_SKILL, "hors `needs-info` et `ready-for-human`"),
    "etape-0-issues-pretes-sans-session": (
        PR_PARALLELES_SKILL,
        "Les issues déjà prêtes y entrent sans session",
    ),
    "etape-0-bloqueur-ouvert-non-propose": (
        PR_PARALLELES_SKILL,
        "une issue dont un bloqueur est ouvert n'est pas proposée",
    ),
    "etape-0-brief-d-agent-verifie": (
        PR_PARALLELES_SKILL,
        "`gh issue view <N> --comments` un `## Brief d'agent`",
    ),
    "etape-0-bloqueurs-lus-dans-github": (
        PR_PARALLELES_SKILL,
        "chaque numéro de « Bloquée par » lu dans GitHub",
    ),
    "etape-0-recouvrement-par-le-crible-de-l-etape-2": (
        PR_PARALLELES_SKILL,
        "le crible de l'étape 2, lu par domaines",
    ),
    "etape-0-proposition-motivee": (
        PR_PARALLELES_SKILL,
        "issue, état de triage, domaine, chemin critique, HITL attendu",
    ),
    "etape-0-rien-avant-l-accord": (PR_PARALLELES_SKILL, "Rien ne s'ouvre avant l'accord"),
    "etape-0-modele-et-effort-herites": (PR_PARALLELES_SKILL, "`model` et `effort` omis"),
    "etape-0-brief-par-l-outil-skill": (
        PR_PARALLELES_SKILL,
        "Invoque le skill `triage` (outil Skill) avec #N",
    ),
    "etape-0-sessions-non-archivees": (
        PR_PARALLELES_SKILL,
        "Ne pas archiver une session sans worktree",
    ),
    "etape-0-message-puis-github": (PR_PARALLELES_SKILL, "il ne prouve rien seul"),
    # Vérification d'avant-go de la PR #133, go 1 : l'attente de **chaque** message de fin.
    "etape-0-chaque-message-attendu": (
        PR_PARALLELES_SKILL,
        "Chaque message reçu et vérifié, la préparation **se termine**",
    ),
    # D-10 (#134, lot 3) : la vague se conduit dans une session neuve, plus dans celle-ci.
    "etape-0-vague-dans-une-session-neuve": (
        PR_PARALLELES_SKILL,
        "Le lead de la vague naît donc neuf, sans le contexte de la préparation",
    ),
    # La forme que l'étape 0 consomme : elle n'est plus « en lecture, à dessein ».
    "fin-d-interrogatoire": (
        SESSIONS_LIEES_REF,
        "« interrogatoire #\\<N> terminé — ready-for-agent proposé »",
    ),
    # #186, volet 1 (D-1, D-2, D-7, D-8) : le titre par ascendance. Une entrée par règle de
    # « Titre », sur la moitié qui restreint (obs 126), puis chaque geste qui nomme une session
    # à l'étape qui agit. Les 15 appels sont gardés à part (`TITRES_DES_SESSIONS_DEMARREES`).
    "titre-repere-modifiable": (
        SESSIONS_LIEES_REF,
        "Ni le titre d'une session, un repère que l'application ou le mainteneur peuvent changer",
    ),
    "titre-separateur": (
        SESSIONS_LIEES_REF,
        "`<préfixe> › <suffixe>`, le séparateur ` › ` étant espace, U+203A, espace",
    ),
    "appel-ne-donne-que-son-suffixe": (
        SESSIONS_LIEES_REF,
        "Chaque appel ne donne que son suffixe et renvoie ici.",
    ),
    "title-sous-60-caracteres-sans-name": (
        SESSIONS_LIEES_REF,
        (
            "tout `start_session` passe `title: <préfixe> › <suffixe>`, sous 60 caractères, et"
            " **pas de `name`**"
        ),
    ),
    "name-sans-separateur-ni-diese": (SESSIONS_LIEES_REF, "ne peut donc porter ni ` › ` ni `#`"),
    "titre-mesure-en-place": (
        SESSIONS_LIEES_REF,
        (
            'est celui que `get_session {"session_id":"self"}` rend dans l\'enfant, toujours en place'
            " plusieurs minutes après"
        ),
    ),
    "prefixe-lu-sur-self-jamais-dans-list-sessions": (
        SESSIONS_LIEES_REF,
        'lu par `get_session {"session_id":"self"}` — jamais dans `list_sessions`, qui l\'exclut',
    ),
    "prefixe-sans-le-role": (
        SESSIONS_LIEES_REF,
        "**sans le rôle qui suit le sujet de son dernier segment**",
    ),
    "prefixe-garde-le-relais": (SESSIONS_LIEES_REF, "Le rang de relais, lui, reste."),
    "suffixe-numerote-si-autre-sujet": (
        SESSIONS_LIEES_REF,
        "précédé de `#<N>` quand l'enfant porte une autre issue ou PR que son parent",
    ),
    "racines": (
        SESSIONS_LIEES_REF,
        (
            "lead de vague `vague-<k>` (`<k>` : `pr-paralleles` Étape 4) ; session PR seule ou"
            " session de tri `#<N>` ; campagne de QA `qa-<plan>` ; relevé `/triage` `triage` ;"
            " toute autre, `#<N>` si elle porte une issue, sinon le nom de son skill"
        ),
    ),
    "racine-se-nomme-avant-son-premier-start-session": (
        SESSIONS_LIEES_REF,
        'Elle se nomme par `set_session_title` sur `"self"` avant son premier `start_session`.',
    ),
    "coordinatrice-se-renomme": (
        SESSIONS_LIEES_REF,
        "la session qui devient coordinatrice se renomme `<son titre> coordinatrice`",
    ),
    "relais-soeur-pas-fille": (
        SESSIONS_LIEES_REF,
        (
            "prend le titre de la précédente suivi de ` (relais <r>)` : sa sœur, pas sa fille, et"
            " ses enfants prennent ce titre pour préfixe"
        ),
    ),
    "homonymes-numerotes": (SESSIONS_LIEES_REF, "le second prend ` 2`, le suivant ` 3`"),
    "renommer-demande-l-accord-du-mainteneur": (
        SESSIONS_LIEES_REF,
        "l'application demande l'accord du mainteneur si c'est lui qui a posé le titre",
    ),
    "renommer-refuse-sans-surveillance": (
        SESSIONS_LIEES_REF,
        "et refuse en session sans surveillance",
    ),
    "un-exemple-par-forme": (
        SESSIONS_LIEES_REF,
        (
            "| lead | `vague-3` | | issue | `vague-3 › #145` | | coordinatrice |"
            " `vague-3 › #145 coordinatrice` | | lot | `vague-3 › #145 › lot 2` | | sous-lot |"
            " `vague-3 › #145 › lot 2 › 2a` | | relecture | `vague-3 › #145 › relecture` | |"
            " session relayée | `vague-3 › #145 (relais 2)` | | racines hors vague | `#<N>`,"
            " `qa-<plan>`, `triage` |"
        ),
    ),
    "lead-se-nomme-a-l-etape-0": (
        PR_PARALLELES_SKILL,
        (
            'le lead se nomme d\'abord `vague-<k>` (`set_session_title` sur `"self"`, `<k>` lu'
            " comme le dit l'étape 4), puis démarre une session par issue à préparer"
        ),
    ),
    "en-tete-du-tableau": (PR_PARALLELES_SKILL, "Vague <k> — <date>"),
    "rang-de-la-vague": (
        PR_PARALLELES_SKILL,
        (
            "`<k>` est le rang de la vague : celui de l'en-tête que la vague précédente a laissé dans"
            " `PR-PARALLELES.md` (étape 8), plus 1 — 1 sans fichier"
        ),
    ),
    "titre-repere-local-adresse": (
        PR_PARALLELES_SKILL,
        "Le titre est un repère ; le `local_…` est l'adresse de `SendMessage`",
    ),
    "nettoyage-garde-l-en-tete": (
        PR_PARALLELES_SKILL,
        "et garder son en-tête : la vague suivante y lit son rang (étape 4)",
    ),
    "coordinatrice-se-renomme-avant-ses-sessions": (
        COORDINATRICE_REF,
        (
            "la coordinatrice se renomme d'abord `<son titre> coordinatrice` (`set_session_title`"
            ' sur `"self"` ; `sessions-liees.md`, « Identité »), puis démarre d\'un coup les'
            " sessions des lots non mergés"
        ),
    ),
    "suffixe-d-un-sous-lot": (COORDINATRICE_REF, "suffixe `lot <k> › <k><x>` pour un sous-lot"),
    "ouverture-garde-le-renommage": (
        COORDINATRICE_REF,
        "La forme démarrée à son ouverture remplace ce démarrage, pas le renommage",
    ),
    # #186, volet 2 (D-3, D-4, D-6, D-9) : le lead et la coordinatrice nourrissent le tableau de
    # bord des sessions. Une entrée par règle de `pr-paralleles` Étape 4 et de `coordinatrice.md`,
    # moitié qui restreint comprise (obs 126), et par appel placé à l'étape qui agit. Le barème est
    # gardé à part (`BAREME_D_AVANCEMENT`).
    "maj-a-chaque-mise-a-jour-du-tableau": (
        PR_PARALLELES_SKILL,
        (
            "À chaque mise à jour de `PR-PARALLELES.md`, le lead appelle `tableau_de_bord_maj`"
            " (`mcp__tableau-de-bord-sessions__tableau_de_bord_maj`) pour la carte de chaque issue"
            " dont la ligne a changé."
        ),
    ),
    "outil-absent-saute-sans-bruit": (
        PR_PARALLELES_SKILL,
        "`ToolSearch` sur son nom complet —, l'appel est sauté, sans aucun message ni erreur",
    ),
    "un-seul-auteur-par-carte": (
        PR_PARALLELES_SKILL,
        "Une carte a **un seul auteur** : la coordinatrice si l'issue en a une",
    ),
    "le-lead-saute-les-cartes-a-coordinatrice": (
        PR_PARALLELES_SKILL,
        (
            "Le lead ne nourrit pas la carte d'une issue à coordinatrice, qu'il reconnaît à sa PR"
            " d'intégration, ouverte par « En vol pour #<N> (intégration », ou au titre de sa"
            " session, terminé par `coordinatrice`"
        ),
    ),
    "champ-sujet": (PR_PARALLELES_SKILL, "`sujet` : `#<N>` — une carte par issue ;"),
    "champ-titre": (PR_PARALLELES_SKILL, "`titre` : `#<N> <titre court de l'issue>` ;"),
    "champ-avancement": (PR_PARALLELES_SKILL, "`avancement` : de 0 à 100, par le barème"),
    "champ-resume": (
        PR_PARALLELES_SKILL,
        "réécrite à chaque appel, qui dit l'état courant et quand le mainteneur doit agir",
    ),
    "champ-sessions": (
        PR_PARALLELES_SKILL,
        (
            "`sessions` : les sessions de la colonne Session de ses lignes — relais et lots compris,"
            " des sœurs que la chaîne de `startedBy` ne relie pas (étape 5) — et leurs descendantes,"
            ' lues dans `list_sessions {"linked": true}` par cette chaîne, chacune en'
            " `{ titre, local_id, role }`"
        ),
    ),
    "champ-etat": (
        PR_PARALLELES_SKILL,
        (
            "`etat` : la colonne État traduite — `🟡 en cours` → `en-cours`, `🔵 en review` →"
            " `en-review`, `🟢 mergée` → `mergee`, `⚪ worktree nettoyé` → `nettoyee`."
        ),
    ),
    "bareme-ecrit-une-fois": (
        PR_PARALLELES_SKILL,
        "barème écrit une fois, ici ; la coordinatrice y renvoie",
    ),
    "etape-lue-sans-nouveau-message": (
        PR_PARALLELES_SKILL,
        "L'étape se lit sur des signaux que le lead observe déjà, sans nouveau message entre sessions",
    ),
    "signaux-de-l-etape": (
        PR_PARALLELES_SKILL,
        (
            "- aucune PR pour la branche → Étape 1 ; - PR draft sans autre commit que l'amorce →"
            " Étape 2 ; - PR draft avec des commits → Étape 3 ; - PR draft portant des commentaires"
            " de relecture (`/code-review --comment` de la session de relecture) → Étape 4 ; - PR"
            " draft dont le body porte `## Summary`, le body définitif de l'Étape 5 → Étape 5 ; -"
            " PR sortie du draft → Étape 6 ; - Notes portant le verdict d'avant-go → Étape 7 ; - PR"
            " mergée → 100 %."
        ),
    ),
    "message-recu-nuance-le-resume": (
        PR_PARALLELES_SKILL,
        "— fin de travail, blocage — peut faire avancer l'étape ou nuancer le `resume`",
    ),
    "carte-a-jour-a-la-convergence": (
        PR_PARALLELES_SKILL,
        "mettre à jour `PR-PARALLELES.md` et la carte de son issue (étape 4)",
    ),
    "carte-nettoyee": (PR_PARALLELES_SKILL, "et sa carte `etat: nettoyee` (étape 4)"),
    "le-lead-retire-ses-seules-cartes": (
        PR_PARALLELES_SKILL,
        (
            "`tableau_de_bord_retirer` (`mcp__tableau-de-bord-sessions__tableau_de_bord_retirer`)"
            " sur le `sujet` de chaque carte que le lead a nourrie, avec le même saut silencieux"
        ),
    ),
    "coordinatrice-seul-auteur-de-sa-carte": (
        COORDINATRICE_REF,
        (
            "elle est le seul auteur de la carte de son issue au tableau de bord des sessions"
            " (`pr-paralleles` Étape 4, « Le tableau de bord des sessions »)"
        ),
    ),
    "coordinatrice-nourrit-sa-carte-a-chaque-changement": (
        COORDINATRICE_REF,
        (
            "Elle appelle `tableau_de_bord_maj` à chaque changement d'état d'un lot ou de la PR"
            " d'intégration — PR d'intégration en draft et sessions de lot démarrées (« Au go du"
            " découpage »), lot mergé et lot ouvert (« Ouvrir le lot suivant »), PR d'intégration"
            " sortie du draft puis mergée (« Après le dernier lot ») — et `tableau_de_bord_retirer`"
            " à son nettoyage final (même section)."
        ),
    ),
    "coordinatrice-renvoie-le-saut-et-la-formule": (
        COORDINATRICE_REF,
        "même saut silencieux si l'outil manque, et l'avancement par la formule des lots",
    ),
    "lots-jamais-des-cartes": (
        COORDINATRICE_REF,
        "les lots en sont des `sessions`, `role` `lot <k>` ou `<k><x>`, jamais des cartes",
    ),
    "coordinatrice-dans-ses-sessions": (
        COORDINATRICE_REF,
        'sa propre session aussi, lue par `get_session {"session_id":"self"}`',
    ),
    "etat-de-la-pr-d-integration": (
        COORDINATRICE_REF,
        "`en-cours` en draft, `en-review` hors du draft, `mergee` au merge",
    ),
}


# #186, D-4 : le barème d'avancement s'écrit une fois, à l'Étape 4 de `pr-paralleles` ; la
# coordinatrice y renvoie. Une ligne par étape, puis la formule d'une issue en lots.
BAREME_D_AVANCEMENT = [
    "| Étape 1 — briefing | 10 % |",
    "| Étape 2 — draft | 15 % |",
    "| Étape 3 — commits | 40 % |",
    "| Étape 4 — relecture | 60 % |",
    "| Étape 5 — ready | 70 % |",
    "| Étape 6 — review + CI | 80 % |",
    "| Étape 7 — avant-go | 90 % |",
    "| mergée | 100 % |",
    "`((k−1) + avancement du lot k) / n`",
]


@pytest.mark.parametrize("ligne", BAREME_D_AVANCEMENT)
def test_le_bareme_d_avancement_s_ecrit_une_fois(ligne: str) -> None:
    """Présente dans `pr-paralleles`, absente de toute autre prose du harnais : recopiée, elle
    vieillit seule. Vu rouge en recopiant une ligne, puis la formule, dans `coordinatrice.md`."""
    sites = [fichier for fichier, texte in prose_du_harnais() if ligne in texte]

    assert sites == [PR_PARALLELES_SKILL], f"« {ligne} » : {sites}"


def test_la_carte_de_la_coordinatrice_s_annonce_avant_son_premier_appel() -> None:
    """La règle précède « Au go du découpage », premier geste qui nourrit la carte : lue après,
    elle arrive une fois les sessions démarrées (`cleanup-verbatim.md`, ordre d'exécution)."""
    assert_dans_l_ordre(
        COORDINATRICE_REF,
        "Elle appelle `tableau_de_bord_maj` à chaque changement d'état",
        "Au go du découpage — démarrer des sessions dans un tour du mainteneur",
    )


# `use_worktree` omis, `start_session` donne à l'enfant le dossier de son parent quand celui-ci
# travaille dans un dossier simple (description de l'outil, lue le 2026-10-18) : deux sessions y
# basculeraient tour à tour la même branche. **Dénombrement, écrit avant le correctif** (relecture
# de la PR #130, passe 2, R-1) : `grep -rn start_session .claude CLAUDE.md CONTRIBUTING.md` rend
# 5 sites qui démarrent une session devant avoir son worktree — `pr-paralleles` Étape 3 (fermé par
# `ef0b3a8`), son repli d'Étape 8 (renvoi à l'Étape 3, fermé avec elle), sa carte de relais, et
# dans `coordinatrice.md` les sessions de lot et la carte de relais : **3 fuyaient**. La relance
# en a trouvé un **6ᵉ**, qui fuyait aussi : la carte de proposition du même repli, seconde voie
# du renvoi — 6 sites, 4 fuyaient. Le lot 4 en ajoute **2** à l'étape 0 de `pr-paralleles`, écrits
# en clair dès leur création : les sessions de préparation, **sans** worktree (`false` : omis, un
# lead placé dans un worktree leur en donnerait un — description de l'outil, lue le 2026-10-19), et
# la reproduction d'un bug, avec le sien — 8 sites. Le lot 6a2 en ajoute **6** (relecture de la
# PR #151, passe 1), recensés avant le correctif par `grep -n start_session` dans les sept fichiers
# de `triage`, `interroge-moi`, `vers-prd` et `vers-issues`, plus la session `init-projet` que
# `themes-milestones.md` propose sans le mot : la session de tri du relevé et celle d'une issue
# `bug`, l'interrogatoire, la session de tri du brief, `vers-issues`, `init-projet` — **3**
# fuyaient (les deux du relevé, par renvoi à `pr-paralleles` ; `init-projet`, sans paramètre) —,
# 14 sites. Le lot 6b en ajoute **4** dans `repercussions` (2026-10-23, bloc 1), écrits en clair
# dès leur création : la session `contradiction` de l'étape 1 et sa carte de proposition, la
# session `plan-qa` de l'étape 7, les sessions de brouillon — `bug-vers-issue` ou `vers-issues`, une
# phrase pour les deux — de « Ce que ce skill ne fait pas » ; `grep -n start_session` dans ses deux
# fichiers en retrouve trois, la carte de proposition n'ayant pas le mot — 18 sites. Le lot 6b2 en
# ajoute **2** dans `contradiction` (2026-10-25), écrits en clair dès leur création : la session
# `repercussions` de l'étape 5 et sa carte de proposition ; `grep -n start_session` dans les
# fichiers de `contradiction` et de `bug-vers-issue` en retrouve un, le démarrage — la carte n'a pas
# le mot, et `bug-vers-issue` ne démarre aucune session — 20 sites. Le lot 7b2 en ajoute **2** dans
# `execution-qa` (2026-10-26), écrits en clair dès leur création : la session `bug-vers-issue` de
# l'option (a) de son §4 et sa carte de proposition, toutes deux **sans** worktree — elle lit le
# code de la campagne et n'écrit que dans GitHub ; `grep -rn start_session` dans ses cinq fichiers
# en retrouve un, le démarrage — 22 sites. Le lot 8b en ajoute **3** (2026-10-26) : dans
# `coordinatrice.md`, écrite en clair dès sa création, **sans** worktree, la session de lot
# démarrée à son ouverture dans le worktree frère que prépare la coordinatrice ; dans `init-projet`,
# sans le mot, les sessions `vers-prd` ou `vers-issues` de l'étape 13 — une phrase pour les deux —
# et la session `init-projet` que fait proposer la « Note », où renvoient cinq skills — **2**
# fuyaient, recensés au cleanup holistique par la forme du geste sur les lignes ajoutées
# (`propos…`, `démarr…`, `start_session`, `ouvre`, `naît`, dans la phrase de « session ») : 21
# phrases — 3 sites, 13 renvois à l'un d'eux ou à `session-relecture.md`, 5 hors classe (une PR
# qu'on ouvre, un titre, les outils d'une session) —, 25 sites. Le lot 7c en ajoute **1** dans
# `bug-vers-issue` (2026-10-27), écrit en clair dès sa création, **avec** worktree : la session
# `cycle-pr` de la petite PR d'un correctif évident, étape 1, démarrage et carte en une phrase —
# 26 sites. Un site nouveau n'entre pas ici de lui-même : la garde lit des phrases, le grep
# re-dérive la population.
USE_WORKTREE_EXPLICITE = {
    "pr-paralleles-etape-0-sans-worktree": (
        PR_PARALLELES_SKILL,
        "`context: fresh`, `use_worktree: false` écrit en clair",
    ),
    "pr-paralleles-etape-0-reproduction": (
        PR_PARALLELES_SKILL,
        "reçoit au contraire son propre worktree, `use_worktree: true`",
    ),
    "pr-paralleles-etape-3": (
        PR_PARALLELES_SKILL,
        "Le worktree se demande en clair, `use_worktree: true`",
    ),
    "pr-paralleles-carte-de-relais": (
        PR_PARALLELES_SKILL,
        "(`start_session`, `initiation: own_initiative`, `use_worktree: true`, brief : la passation)",
    ),
    "pr-paralleles-repli-par-carte": (
        PR_PARALLELES_SKILL,
        "sinon par une carte de proposition (`initiation: own_initiative`, `use_worktree: true`)",
    ),
    "coordinatrice-sessions-de-lot": (
        COORDINATRICE_REF,
        "worktree de l'application, `wake_when_done: true`, `use_worktree: true`",
    ),
    "coordinatrice-lot-demarre-a-son-ouverture": (
        COORDINATRICE_REF,
        "`cwd` : ce dossier, `use_worktree: false`",
    ),
    "coordinatrice-carte-de-relais": (
        COORDINATRICE_REF,
        "(`start_session`, `initiation: own_initiative`, `use_worktree: true`, brief : la passation",
    ),
    "triage-releve-vers-le-tri": (
        TRIAGE_SKILL,
        "`context: fresh`, `use_worktree: false` écrit en clair",
    ),
    "triage-releve-vers-le-tri-d-un-bug": (
        TRIAGE_SKILL,
        "Une issue `bug` reçoit au contraire son propre worktree, `use_worktree: true`",
    ),
    "triage-tri-vers-l-interrogatoire": (
        TRIAGE_SKILL,
        (
            "`use_worktree: false` — elle lit le code et n'écrit que dans GitHub —,"
            " `title: <préfixe> › interrogatoire`"
        ),
    ),
    "interroge-moi-vers-le-tri-du-brief": (
        INTERROGE_MOI_SKILL,
        "`use_worktree: false`, `title: <préfixe> › tri`",
    ),
    "vers-prd-vers-vers-issues": (
        VERS_PRD_SKILL,
        "`use_worktree: false`, `title: <préfixe> › vers-issues #<n>`",
    ),
    "themes-milestones-vers-init-projet": (
        THEMES_MILESTONES_REF,
        "démarrée avec `use_worktree: true` : elle écrit sur une branche",
    ),
    "repercussions-vers-contradiction": (
        REPERCUSSIONS_SKILL,
        "`use_worktree: true`, `title: <préfixe> › contradiction`",
    ),
    "repercussions-vers-contradiction-par-carte": (
        REPERCUSSIONS_SKILL,
        (
            "hors d'un tour du mainteneur, une carte de proposition (`initiation: own_initiative`,"
            " `context: fresh`, `use_worktree: true`, même titre et même prompt)"
        ),
    ),
    "repercussions-vers-plan-qa": (
        REPERCUSSIONS_SKILL,
        "`use_worktree: true`, `title: <préfixe> › plan-qa <thème>`",
    ),
    "repercussions-vers-les-brouillons": (
        REPERCUSSIONS_SKILL,
        "`context: fresh`, `use_worktree: true` : pour un défaut, `bug-vers-issue`",
    ),
    "contradiction-vers-repercussions": (
        CONTRADICTION_SKILL,
        (
            "démarrer la session `repercussions` : `start_session`, `initiation: user_asked`,"
            " `context: fresh`, `use_worktree: true`"
        ),
    ),
    "contradiction-vers-repercussions-par-carte": (
        CONTRADICTION_SKILL,
        (
            "Hors d'un tour du mainteneur, une carte de proposition (`initiation: own_initiative`,"
            " `context: fresh`, `use_worktree: true`, même titre et même prompt)"
        ),
    ),
    "execution-qa-vers-bug-vers-issue": (
        EXECUTION_QA_SKILL,
        (
            "`start_session`, `initiation: user_asked`, `context: fresh`, `use_worktree: false` —"
            " elle lit le code de la campagne et n'écrit que dans GitHub —, `title: <préfixe> › bug`"
        ),
    ),
    "execution-qa-vers-bug-vers-issue-par-carte": (
        EXECUTION_QA_SKILL,
        (
            "Hors d'un tour du mainteneur, une carte de proposition (`initiation: own_initiative`,"
            " `context: fresh`, `use_worktree: false`, même titre et même prompt)"
        ),
    ),
    "init-projet-vers-la-planification": (
        INIT_PROJET_SKILL,
        (
            "Elles démarrent avec `use_worktree: false` : leur seule écriture de dépôt, l'archive"
            " de `vers-prd`, passe par son `executant` en isolation `worktree`."
        ),
    ),
    "init-projet-note-amorcage-sans-worktree": (
        INIT_PROJET_SKILL,
        (
            "Absent, c'est un amorçage, `use_worktree: false` : il écrit à la racine du projet, qui"
            " n'est peut-être pas encore un dépôt git"
        ),
    ),
    "init-projet-note-reconfiguration-avec-worktree": (
        INIT_PROJET_SKILL,
        (
            "incomplet, une reconfiguration, `use_worktree: true` : elle écrit sur une branche,"
            " par une PR."
        ),
    ),
    "bug-vers-issue-vers-la-petite-pr": (
        BUG_VERS_ISSUE_SKILL,
        (
            "`start_session`, `initiation: user_asked` dans un tour où le mainteneur la demande,"
            " sinon une carte de proposition, `initiation: own_initiative` ; `context: fresh`,"
            " `use_worktree: true`"
        ),
    ),
}


@pytest.mark.parametrize(
    ("fichier", "phrase"), USE_WORKTREE_EXPLICITE.values(), ids=USE_WORKTREE_EXPLICITE.keys()
)
def test_chaque_session_demarree_dans_un_worktree_le_demande_en_clair(
    fichier: str, phrase: str
) -> None:
    """Le paramètre est écrit au site qui démarre la session, pas seulement dans un renvoi."""
    assert phrase in texte_normalise(fichier), f"`{fichier}` ne porte plus « {phrase} »"


# Les gestes que le lot 3 de #107 retire de `pr-paralleles` : le lead ne crée plus de worktree,
# ne place plus de session, ne l'identifie plus par son scratchpad ni par `ListAgents`, et ne
# tient plus son tableau dans le dépôt. **Population** : un cas par geste retiré du bloc
# « Lot 3/4 » (Étapes 3, 5, 7, et le `.gitignore`), relevée sur `ded3567`, base du lot, où chaque
# forme est présente — chaque cas y est rouge, ce qui prouve que le motif mord ; plus la sortie
# par `ExitWorktree` du message de clôture de `cycle-pr`, que l'archivage remplace (relecture de
# la PR #130, m-7). **Borne** : la garde lit des formes, pas un sens ; une paraphrase d'un geste
# retiré passerait.
GESTES_RETIRES_DE_PR_PARALLELES = {
    "worktree-cree-par-le-lead": (PR_PARALLELES_SKILL, "git worktree add"),
    "worktree-frere-du-depot": (PR_PARALLELES_SKILL, "../<repo>--"),
    "placement-par-enter-worktree": (PR_PARALLELES_SKILL, "EnterWorktree"),
    "etat-par-list-agents": (PR_PARALLELES_SKILL, "ListAgents"),
    "identite-par-le-scratchpad": (PR_PARALLELES_SKILL, "répertoire scratchpad"),
    "noms-qui-tournent": (PR_PARALLELES_SKILL, "Les noms tournent"),
    "tableau-ignore-a-la-racine": (".gitignore", "/PR-PARALLELES.md"),
    "sortie-par-exit-worktree": (CYCLE_PR_SKILL, "ExitWorktree"),
}


@pytest.mark.parametrize(
    ("fichier", "forme"),
    GESTES_RETIRES_DE_PR_PARALLELES.values(),
    ids=GESTES_RETIRES_DE_PR_PARALLELES.keys(),
)
def test_aucun_geste_retire_de_pr_paralleles_ne_reste_dans_sa_prose(
    fichier: str, forme: str
) -> None:
    """Un geste retiré qui reste écrit se rejoue : la session suit le texte, pas l'intention."""
    assert not porte_la_forme(fichier, forme), f"`{fichier}` porte encore « {forme} »"


@pytest.mark.parametrize(
    ("fichier", "phrase"),
    INVARIANTS_DES_SESSIONS_LIEES.values(),
    ids=INVARIANTS_DES_SESSIONS_LIEES.keys(),
)
def test_chaque_invariant_des_sessions_liees_garde_sa_phrase(fichier: str, phrase: str) -> None:
    """La phrase est lue sur le texte aux espaces normalisés, marges `# ` de tête de ligne retirées :
    un retour à la ligne de la prose, ou du commentaire en colonne de `pipeline.config.md`, ne la
    casse pas, une réécriture si."""
    texte = texte_normalise(fichier)

    assert phrase in texte, f"`{fichier}` ne porte plus « {phrase} »"


# #186, D-1 : chaque `start_session` qui nommait son enfant à plat lui donne son titre — le
# suffixe seul, la règle dans « Identité ». **Population**, sur `d2e9b09` : la commande de D-1,
# `grep -rnoE "\`?name: [^,\`]+" .claude/skills CLAUDE.md CONTRIBUTING.md`, frontmatter et
# exemples de code retirés, rend 15 appels dans 9 fichiers — un cas chacun, en littéraux.
TITRES_DES_SESSIONS_DEMARREES = [
    (PR_PARALLELES_SKILL, "#<N> tri"),
    (PR_PARALLELES_SKILL, "#<N>"),
    (COORDINATRICE_REF, "lot <k>"),
    (".claude/skills/cycle-pr/references/session-relecture.md", "relecture"),
    (TRIAGE_SKILL, "#<N>"),
    (TRIAGE_SKILL, "interrogatoire"),
    (INTERROGE_MOI_SKILL, "tri"),
    (EXECUTION_QA_SKILL, "bug"),
    (REPERCUSSIONS_SKILL, "contradiction"),
    (REPERCUSSIONS_SKILL, "plan-qa <thème>"),
    (REPERCUSSIONS_SKILL, "bug"),
    (REPERCUSSIONS_SKILL, "vers-issues"),
    (VERS_PRD_SKILL, "vers-issues #<n>"),
    (CONTRADICTION_SKILL, "repercussions"),
    (CONTRADICTION_SKILL, "repercussions #<m>"),
]
# Relecture de la PR #188, passe 1 : une racine qui suit son skill démarrait son enfant sans
# s'être nommée, et son titre généré devenait le préfixe. Sur `1a44985`, 3 des 15 appels
# portaient le geste à l'étape qui agit (lead ×2, coordinatrice), 12 non. Sans `.`, `;` ni `:`
# hors du code : `morceaux_du_texte` n'y coupe pas.
RENVOI_A_L_IDENTITE = "(`sessions-liees.md`, « Identité », une racine se nomme d'abord)"


@pytest.mark.parametrize(("fichier", "suffixe"), TITRES_DES_SESSIONS_DEMARREES)
def test_chaque_session_demarree_recoit_son_suffixe_et_le_renvoi_a_l_identite(
    fichier: str, suffixe: str
) -> None:
    """L'appel donne son suffixe et renvoie à la règle, sans la recopier (obs 52) ; le renvoi
    rappelle à une racine de se nommer avant, à l'étape qui agit."""
    forme = f"`title: <préfixe> › {suffixe}` {RENVOI_A_L_IDENTITE}"

    assert forme in texte_normalise(fichier), f"`{fichier}` ne porte plus « {forme} »"


def test_aucune_session_demarree_n_est_nommee_a_plat() -> None:
    """`name` ne porte ni ` › ` ni `#` : rétabli, il rend la barre latérale à plat. Vu rouge sur
    `d2e9b09`, où la forme rend les 15 appels de `TITRES_DES_SESSIONS_DEMARREES`. Trois formes
    d'un `name` muni d'une valeur : `` `name: x` ``, `` `name` : `x` `` et `` name `x` `` (relecture
    de la PR #188, passe 1, constat 2 : la seule première laissait la troisième VERTE)."""
    a_plat = [
        (fichier, nom)
        for fichier, texte in prose_du_harnais()
        for nom in re.findall(r"`name: [^,`]+|`name`\s*:?\s*`[^`]+`|\bname `[^`]+`", texte)
    ]

    assert not a_plat, f"`name` à plat : {a_plat}"


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


def porte_la_forme(fichier: str, forme: str) -> bool:
    """Vrai si le texte normalisé du fichier porte la forme, lue sans la casse : en tête de phrase,
    une forme retirée revient avec une majuscule (mutation VERTE, passe d'écriture du lot 3)."""
    return forme.lower() in texte_normalise(fichier).lower()


# « Une tâche par session » (#134, lot 2b) : ce que `CLAUDE.md` « Orchestration » et
# « Observation continue » disent de la délégation — un énoncé par point du critère 2b qui les
# nomme, et la phrase de `cycle-pr` 4.2 qui en dépend.
#
# **Une épingle garde aussi la moitié restrictive de son énoncé** — « jamais », « seule »,
# « seulement », « ne … pas », « reste à » : épingler la moitié qui fait laisse retirer en vert la
# moitié qui interdit (relecture de la PR #140, passe 1, I-2 : 5 sondes sur 5 VERTES). Dénombrement
# écrit avant le correctif, sur `b82a8fe` : **24** moitiés restrictives dans les énoncés de ce delta,
# **7** épinglées, **17** non — 15 gardées par une ancre allongée ou neuve ci-dessous, 2 (« contexte
# complet », « cleanup pass, review avant merge ») par le test d'absence qui suit la table.
INVARIANTS_DU_CONTEXTE_COURT = {
    "une-tache-par-session": ("CLAUDE.md", "**Une tâche par session.**"),
    "le-reste-part-dans-un-contexte-neuf": (
        "CLAUDE.md",
        "Le reste part dans un contexte neuf qui meurt avec sa tâche",
    ),
    "effort-d-une-session-pr-fixe-au-demarrage": (
        "CLAUDE.md",
        (
            "L'effort d'une session PR se fixe à son démarrage — le brief de `start_session`, ou"
            " `/effort` avant le briefing — et ne change plus en cours de session"
        ),
    ),
    "effort-max-au-go-seulement": (
        "CLAUDE.md",
        "la coordinatrice et le lead ne reçoivent `/effort max` qu'au go, avant tout enfant",
    ),
    "la-session-de-dialogue-garde-merge-et-cloture": (
        "CLAUDE.md",
        "arbitrages `decisions-vs-doc`, dialogue avec l'utilisateur, merge et clôture",
    ),
    "liste-tools-troisieme-axe": ("CLAUDE.md", "La **liste `tools:`** fixe le plancher"),
    "le-brief-porte-le-niveau-ponytail": (
        "CLAUDE.md",
        "son brief porte le bloc, le niveau `ponytail` (« Minimalisme »)",
    ),
    "task-observer-reste-aux-sessions": ("CLAUDE.md", "`task-observer` reste aux sessions"),
    "reprise-par-message": ("CLAUDE.md", "**Un sous-agent arrêté se reprend par message**"),
    "reprise-jamais-un-equipier-neuf": (
        "CLAUDE.md",
        "jamais un équipier neuf pour une retouche de la même tranche",
    ),
    "lire-borne": ("CLAUDE.md", "puis lire la plage (`Read` avec `offset` et `limit`)"),
    "lire-borne-jamais-un-fichier-entier": (
        "CLAUDE.md",
        "jamais un fichier entier pour une fonction, une section ou une ligne",
    ),
    "role-visible-a-une-session-neuve": ("CLAUDE.md", "n'est visible qu'à une session **neuve**"),
    "role-visible-la-reprise-garde-la-liste": (
        "CLAUDE.md",
        "la reprise d'une conversation garde la liste de son démarrage",
    ),
    "repli-general-purpose-borne": ("CLAUDE.md", "pour un rôle **sans** liste `tools:` seulement"),
    "cycle-pr-repli-borne": (
        CYCLE_PR_SKILL,
        "un rôle à outils réduits se lance depuis une session neuve (`CLAUDE.md`, « Orchestration »)",
    ),
    "cycle-pr-repli-hors-tour-humain": (
        CYCLE_PR_SKILL,
        "que la session PR ne démarre pas hors d'un tour humain",
    ),
    "sessions-liees-une-par-sous-lot": (
        "CLAUDE.md",
        "une par lot et une par sous-lot — **un sous-lot est un lot**",
    ),
    "sessions-liees-une-session-de-relecture-par-pr": (
        "CLAUDE.md",
        "la session PR, une session de relecture par PR, au go de son briefing",
    ),
    "observation-une-session-seulement": ("CLAUDE.md", "**Seule une session** l'invoque"),
    "observation-un-sous-agent-ne-lit-pas-le-journal": (
        "CLAUDE.md",
        "Un sous-agent ne lit pas le journal",
    ),
    # Les règles de fond sans porteur nommé : **15** sur 40 (étude du 2026-10-19, §19.6, lu le
    # 2026-10-20), chacune nommant le sien là où elle vit — 7 dans `contraintes.md`, 3 dans
    # `cleanup-verbatim.md`, 1 dans `taille-pr.md`, 1 dans `decisions-vs-doc.md`, 3 dans
    # `CLAUDE.md`. Puis leurs renvois entrants : « amendé dans la session », 3 sites sur `81ae8c3`
    # (`grep` sur le texte aux blancs normalisés), la règle comprise ; le rapport du `developpeur`.
    "porteur-voie-v": (
        CONTRAINTES_RULE,
        "Un `developpeur` ne la pose pas : il note son hypothèse et rend la `[V]` dans son rapport",
    ),
    "porteur-voie-v-executant-et-releveur": (
        CONTRAINTES_RULE,
        "`executant` et `releveur` ne classent aucune question, ils remontent tout choix",
    ),
    "porteur-voie-c": (
        CONTRAINTES_RULE,
        "Un `developpeur` s'arrête et remonte les deux citations",
    ),
    "porteur-explorer-plutot-que-demander": (
        CONTRAINTES_RULE,
        (
            "par un `releveur` pour un relevé, l'`executant` pour une cartographie (`cycle-pr`"
            " Étape 1), la conclusion restant à la session"
        ),
    ),
    "porteur-creation-d-issues": (
        CONTRAINTES_RULE,
        "un sous-agent n'ouvre ni issue ni brouillon, le `developpeur` remonte le vide dans son rapport",
    ),
    "porteur-ecritures-distantes": (CONTRAINTES_RULE, "La relecture est à qui écrit"),
    "porteur-maintenance-continue": (
        CONTRAINTES_RULE,
        "l'auteur du commit — le `developpeur` pour la doc descriptive de son bloc",
    ),
    "porteur-maintenance-amendement-reste-a-la-session": (
        CONTRAINTES_RULE,
        "l'amendement d'une source de vérité reste à la session de dialogue",
    ),
    "porteur-points-d-arret-humains": (
        CONTRAINTES_RULE,
        (
            "C'est la session PR qui prend l'arrêt : elle coupe le bloc du `developpeur` au commit"
            " qui assemble l'écran"
        ),
    ),
    "porteur-cleanup-holistique": (
        ".claude/rules/cleanup-verbatim.md",
        (
            "le cleanup holistique, un `developpeur` neuf sur le diff complet de la branche, qui ne"
            " rend que des commits"
        ),
    ),
    "porteur-rapporter-a-voix-haute": (
        ".claude/rules/cleanup-verbatim.md",
        (
            "Un `developpeur` le rend dans son rapport final — son contexte meurt avec lui —, et la"
            " session PR le relaie aux Notes de la PR"
        ),
    ),
    "porteur-denombrement-avant-correctif": (
        ".claude/rules/cleanup-verbatim.md",
        "la session PR pour un constat de relecture",
    ),
    "porteur-gabarit-a-chaque-commit": (
        ".claude/rules/taille-pr.md",
        "Le `developpeur` rend le chiffre avec chaque commit et s'arrête au seuil que porte son brief",
    ),
    "porteur-deux-sorties": (
        ".claude/rules/decisions-vs-doc.md",
        (
            "par la session de dialogue qui a décidé (session PR ; `triage`, `interroge-moi` ou"
            " `vers-issues` hors cycle ; lead d'une vague, coordinatrice d'une issue en lots"
        ),
    ),
    "porteur-deux-sorties-seule-a-lancer": (
        ".claude/rules/decisions-vs-doc.md",
        (
            "seule à lancer `/contradiction` (qui propage aux rangs inférieurs et aux issues) ; les"
            " sous-agents remontent les deux citations"
        ),
    ),
    "porteur-niveau-ponytail": ("CLAUDE.md", "le niveau voyage dans le brief"),
    "porteur-glossaire": ("CLAUDE.md", "Les noms de tests sont à qui les écrit"),
    "porteur-context7": ("CLAUDE.md", "parmi les rôles, ceux dont la liste `tools:` le porte"),
    "porteur-context7-un-role-sans-remonte": (
        "CLAUDE.md",
        "un rôle qui ne l'a pas remonte la question à son appelant",
    ),
    "renvoi-deux-sorties-claude-md": (
        "CLAUDE.md",
        "amendé par la session de dialogue qui a décidé",
    ),
    "renvoi-deux-sorties-contributing": (
        "CONTRIBUTING.md",
        "amendé par la session de dialogue qui a décidé",
    ),
    "renvoi-rapporter-a-voix-haute": (
        ".claude/agents/developpeur.md",
        "le compte rendu de chaque cleanup pass",
    ),
    "renvoi-gabarit-et-vides-au-rapport": (
        ".claude/agents/developpeur.md",
        "le chiffre de `git diff --stat <base>...HEAD` après chaque commit",
    ),
    # **Une épingle par élément dénombré** : un commentaire qui compte N éléments sans une ancre
    # chacun dénombre ce qu'il ne garde pas (relecture de la PR #140, passe 2, I-1 : 10 sondes sur
    # 10 VERTES). Dénombrement écrit avant le correctif, sur `e9d7231` : **27** éléments dans les
    # deux blocs ci-dessous — 11 rôles et conditions dans 5 lignes de `pipeline.config.md`, 16
    # exécutants dans les 7 maillons de `CONTRIBUTING.md` —, **9** épinglés, **18** non (le 18ᵉ,
    # « lancé par » du 3bis, trouvé à la relance).
    #
    # `pipeline.config.md` : 5 lignes, 4 commandes (« test brut » back et front, « validation »,
    # « relecture », « sécurité ») qui disaient « lancée par `cycle-pr` », chacune avec son rôle,
    # son intérim et, pour « sécurité », sa condition.
    "config-test-brut": (
        ".claude/pipeline.config.md",
        (
            "le verdict se lit ici, par le `developpeur` avant commit (cycle-pr 3.2) et le"
            " `releveur` des portes (4.2)"
        ),
    ),
    "config-test-brut-front": (
        ".claude/pipeline.config.md",
        "lue comme celle du back (`developpeur` avant commit, `releveur` des portes)",
    ),
    "config-validation": (
        ".claude/pipeline.config.md",
        "Jouée par un `releveur` que la session PR lance avant tout push",
    ),
    "config-relecture": (
        ".claude/pipeline.config.md",
        (
            "Lancée par la session de relecture à chaque réveil, avant le protocole du `relecteur`"
            " (`session-relecture.md` de `cycle-pr`) — par la session PR seulement en repli —"
        ),
    ),
    "config-securite": (
        ".claude/pipeline.config.md",
        (
            "Lancée par la session de relecture (par la session PR seulement en repli),"
            " **seulement** si le diff touche une zone sensible ou une surface exposée"
        ),
    ),
    # `CONTRIBUTING.md`, « Le flux en une page » : 7 maillons (0, 1, 2, 3, 3bis, 4, 5), chacun
    # nomme qui l'exécute — le 3bis deux fois : qui lance, et qui amende
    # (`renvoi-deux-sorties-contributing`, ci-dessus).
    "contributing-configurer": ("CONTRIBUTING.md", "`init-projet`, dans une session de dialogue"),
    "contributing-planifier": (
        "CONTRIBUTING.md",
        "chacun dans une session de dialogue avec le mainteneur",
    ),
    "contributing-interroger": ("CONTRIBUTING.md", "**obligatoire**, dans une session de dialogue"),
    "contributing-amender-lance-par-la-session": (
        "CONTRIBUTING.md",
        "`contradiction`, lancé par la session de dialogue dès qu'une de ses décisions",
    ),
    "contributing-implementer": (
        "CONTRIBUTING.md",
        (
            "`cycle-pr`, porté par la session PR, qui orchestre et délègue : briefing pré-PR"
            " (relevés au `releveur`, cartographie à l'`executant`)"
        ),
    ),
    "contributing-developpeur-relecteur-cleanup": (
        "CONTRIBUTING.md",
        (
            "un `developpeur` neuf par bloc de plus de ~50 lignes : TDD red-green-refactor, cycle"
            " `modif → test → cleanup → test → commit` (relecture à contexte vierge au socle, par la"
            " session de relecture que la session PR démarre à son go) → cleanup holistique par un"
            " `developpeur` neuf au-delà de 3 commits ou 150 lignes → relecture à contexte vierge"
            " finale, par la même session"
        ),
    ),
    "contributing-verificateur": (
        "CONTRIBUTING.md",
        "vérification d'avant-go par le `verificateur`, que la session PR lance",
    ),
    "contributing-lead-tient-le-tableau": (
        "CONTRIBUTING.md",
        "chacune dans un worktree de l'application, et tient le tableau de bord",
    ),
    "contributing-repercuter": (
        "CONTRIBUTING.md",
        (
            "Porté par la session PR en fin de `cycle-pr` — collecte au `releveur`, go d'édition au"
            " mainteneur dans sa fenêtre ; pour une issue en lots, par la coordinatrice au merge de"
            " la PR d'intégration"
        ),
    ),
    "contributing-valider": (
        "CONTRIBUTING.md",
        "`bug-vers-issue`, chacun dans une session de dialogue",
    ),
    # Lot 6a2 de #134 : les skills de cadrage et de tri nomment leur exécutant (`triage` d'abord).
    "6a-releveur-cite-sans-conclure": (
        RELEVEUR_ROLE,
        "le passage qui répond, cité mot pour mot ; ce qu'il faut en conclure n'est pas à toi",
    ),
    "6a-triage-une-session-par-issue": (
        TRIAGE_SKILL,
        "une session de tri par issue, qui ne reçoit que le numéro",
    ),
    "6a-triage-jamais-l-interrogatoire-dans-le-tri": (
        TRIAGE_SKILL,
        "jamais l'interrogatoire dans la session de tri",
    ),
    "6a-triage-out-of-scope-par-une-pr": (
        TRIAGE_SKILL,
        "`.out-of-scope/` s'écrit par une PR",
    ),
    "6a-hors-scope-jamais-sur-le-trunk": (
        HORS_SCOPE_REF,
        "par une PR, jamais par un commit direct sur le trunk",
    ),
    "6a-themes-domaines-par-une-pr": (
        THEMES_MILESTONES_REF,
        "les domaines de `.claude/pipeline.config.md` s'amendent par une PR",
    ),
    "6a-brief-reprend-les-decisions": (
        BRIEF_AGENT_REF,
        "reprennent la section « Décisions » du corps de l'issue",
    ),
    "6a-interroge-moi-decisions-dans-le-corps": (
        INTERROGE_MOI_SKILL,
        "dans la section « Décisions » du corps de l'issue, chaque ligne datée",
    ),
    "6a-interroge-moi-jamais-dans-la-session-pr": (
        INTERROGE_MOI_SKILL,
        "jamais dans la session PR",
    ),
    "6a-interroge-moi-jamais-dans-le-dossier-partage": (
        INTERROGE_MOI_SKILL,
        "jamais dans le dossier partagé",
    ),
    "6a-vers-prd-archive-par-une-pr": (
        VERS_PRD_SKILL,
        "le fichier d'archive s'écrit par une PR",
    ),
    "6a-vers-prd-archive-jamais-sur-le-trunk": (
        VERS_PRD_SKILL,
        (
            "rien n'attend ce merge, pas même la publication du PRD ; jamais un commit direct sur"
            " le trunk"
        ),
    ),
    "6a-vers-prd-vers-issues-dans-sa-session": (
        VERS_PRD_SKILL,
        "`vers-issues` part du PRD publié, dans sa propre session",
    ),
    "6a-vers-issues-source-en-argument": (
        VERS_ISSUES_SKILL,
        "la source se passe en argument",
    ),
    "6a-vers-issues-sans-argument-s-arrete": (
        VERS_ISSUES_SKILL,
        "Sans argument, la session s'arrête et demande la référence",
    ),
    "6a-vers-issues-lots-des-la-creation": (
        VERS_ISSUES_SKILL,
        "porte ses lots dès sa création",
    ),
    "6a-vers-issues-re-decoupage-jamais-pour-un-depassement-prevu": (
        VERS_ISSUES_SKILL,
        "reste la voie d'un dépassement découvert, jamais d'un dépassement prévisible",
    ),
    # Relecture de la PR #151, passe 1, I1 : une issue interrogée avant D-13 n'a pas de section
    # « Décisions ». Passe 2, B1 : la forme d'avant D-13 acceptait des notes de triage, que l'étape
    # 5 poste à toute issue mise en `needs-interrogation`. **Dénombrement, écrit avant le
    # correctif, sur toute la population de l'état** — population vivante, relevée le 2026-10-23 à
    # 16 h 27 UTC : `gh issue list --label needs-interrogation` rend 2 issues, `gh issue view <n>
    # --json body,comments` lu pour chacune, aucun corps avec la section. #6 porte en commentaire
    # un brief d'agent, « Décisions verrouillées (interrogatoire du 2026-09-23) » : interrogée ;
    # #11 n'a qu'un commentaire, « Notes de triage » : non interrogée. Règle de la passe 1 : 2
    # reconnues sur 2, dont 1 faux positif (#11) ; règle corrigée : 1 sur 2, ni faux positif ni
    # faux négatif. Sites qui reconnaissent l'issue interrogée, par la forme du geste : 7 ; 5
    # fuyaient — la définition (`triage` étape 4) et la paraphrase de `brief-agent.md`, corrigées,
    # et trois renvois qui en héritent (`triage` étape 5, « Changement d'état rapide », modèle de
    # `brief-agent.md`) ; indemnes, la porte de `cycle-pr` Étape 1 (« décisions consignées dans le
    # brief d'agent ») et sa reprise dans `interroge-moi`.
    "6a-triage-interrogee-avant-d-13": (
        TRIAGE_SKILL,
        (
            "interrogée avant D-13 de #134, ses « Décisions verrouillées » consignées en commentaire"
            " — d'un brief d'agent ou d'un interrogatoire —"
        ),
    ),
    "6a-triage-notes-de-triage-jamais-interrogatoire": (
        TRIAGE_SKILL,
        "Des notes de triage seules ne valent jamais interrogatoire",
    ),
    "6a-triage-prete-si-deja-interrogee": (
        TRIAGE_SKILL,
        "ne se posent que sur une issue déjà interrogée (étape 4)",
    ),
    "6a-triage-rapide-deja-interrogee": (TRIAGE_SKILL, "L'issue est déjà interrogée (étape 4)"),
    "6a-brief-decisions-d-avant-d-13": (
        BRIEF_AGENT_REF,
        (
            "pour une issue interrogée avant D-13, ses « Décisions verrouillées » consignées en"
            " commentaire, jamais des notes de triage"
        ),
    ),
    # I3 : l'issue `wontfix` se fermait dès l'ouverture de sa PR `.out-of-scope/`, que personne ne
    # merge. **Dénombrement, écrit avant le correctif** — une issue fermée citant un artefact de
    # dépôt pas encore mergé, dans les sept fichiers des quatre skills (`grep` de « ferm »,
    # « close », « par une PR ») : 11 sites, **3** fuyaient — `triage` étape 5, `wontfix`
    # d'enhancement ; `hors-scope.md`, « Confirmer » et « Quand écrire ». Indemnes : le `wontfix`
    # d'un bug (aucun artefact), « Changement d'état rapide » (renvoi à l'étape 5), « Reconsidérer »
    # et la suppression, le domaine d'`init-projet`, l'archive de `vers-prd`, l'amendement
    # d'`interroge-moi` (aucune issue fermée), l'exemple de brief d'enhancement (pas un geste).
    "6a-triage-jamais-fermee-avant-le-merge": (
        TRIAGE_SKILL,
        "l'issue ne se ferme jamais sur un fichier absent du trunk",
    ),
    "6a-hors-scope-sans-go-reste-ouverte": (
        HORS_SCOPE_REF,
        "Puis seulement, la PR mergée — sans go, l'issue reste ouverte dans son état —",
    ),
    "6a-hors-scope-ferme-apres-merge": (HORS_SCOPE_REF, "puis fermée une fois cette PR mergée"),
    # I4 : `triage` confiait au `releveur` des lectures que « Ce que tu fais » ne couvrait pas, et
    # une lecture web qu'il ne peut pas faire. **Dénombrement, écrit avant le correctif** — chaque
    # délégation au `releveur` et à l'`executant` des sept fichiers, confrontée à « Ce que tu
    # fais » et aux `tools:` du rôle : **24** recensées, **16** hors mandat. Au `releveur`, 18 dont
    # 13 : lecture de l'issue, de `.out-of-scope/` et des domaines, des thèmes, du code sur ancres
    # (`triage`, `interroge-moi`, `vers-prd`, `vers-issues`), des sources de vérité (aucune puce de
    # lecture) ; relevé des cinq catégories (issues fermées) et dénombrements (« Collectes » ne
    # rend ni l'un ni l'autre) ; reproduction (« Cases » : QA et fumée) ; capacités d'un
    # fournisseur (ni WebFetch ni WebSearch) ; « résumé des commentaires » de `vers-issues` (résumer,
    # c'est dire ce qui compte). À l'`executant`, 6 dont 3 : scratch et contre-épreuve (aucune
    # puce hors commit), création d'un `.out-of-scope/` (nom et raison laissés à son choix).
    "6a-releveur-lectures-bornees": (
        RELEVEUR_ROLE,
        "le texte ou les lignes rendus tels quels, sans dire ce qui compte",
    ),
    "6a-releveur-collectes-compte": (RELEVEUR_ROLE, "tout compte d'une commande donnée"),
    "6a-releveur-cases-reproduction": (RELEVEUR_ROLE, "ou d'une reproduction de bug"),
    # Décision du mainteneur, 2026-10-23, sur l'arrêt `decisions-vs-doc` de la passe 1 : le
    # `releveur` vérifie une capacité de fournisseur par `context7` quand la doc y est indexée, la
    # session sinon ; il rend les commentaires tels quels, filtrés par les critères de l'appelant.
    "6a-releveur-fournisseur-par-context7": (RELEVEUR_ROLE, "une doc absente de l'index remonte"),
    "6a-releveur-commentaires-filtres": (
        RELEVEUR_ROLE,
        "ses commentaires tels quels, tous ou filtrés par les critères que donne ton appelant",
    ),
    "6a-triage-fournisseur-par-context7": (
        TRIAGE_SKILL,
        "ou plusieurs candidates, remonte à la session, qui la lit à la source",
    ),
    "6a-vers-issues-fournisseur-par-context7": (
        VERS_ISSUES_SKILL,
        "ou plusieurs candidates, remonte à la session, qui la lit à la source",
    ),
    "6a-executant-artefacts-jetables": (
        ".claude/agents/executant.md",
        "**sans commit** ; ce qu'il faut en conclure n'est pas à toi",
    ),
    "6a-hors-scope-nom-et-texte-donnes": (HORS_SCOPE_REF, "nom et texte rédigés par la session"),
    "6a-vers-issues-commentaires-tels-quels": (
        VERS_ISSUES_SKILL,
        "rend le corps et les commentaires tels quels, filtrés par les critères que la session donne",
    ),
    # Passe 2, I5 et I6 : une PR de dépôt qu'ouvre une session de `triage`, `interroge-moi` ou
    # `vers-prd` (D-12) n'avait de déroulé — qui ouvre, relit, merge au go — que dans
    # `hors-scope.md`. **Dénombrement, écrit avant le correctif**, par la forme du geste — la
    # session fait ouvrir une PR (`grep` de « par une PR », « ouvre la PR », « PR de » dans les
    # sept fichiers, puis lecture) : 11 sites, le déroulé source compris (`hors-scope.md`, « Quand
    # écrire », étapes 5 et 6). **5** sans déroulé : « Reconsidérer » (`hors-scope.md`), l'archive
    # de `vers-prd` (ouverte, ni relue ni mergée par personne), la « Délégation » d'`interroge-moi`
    # et ses deux renvois (rang supérieur, arrêt) ; **1** renvoi au déroulé entier, dont les étapes
    # 7 et 8 (`wontfix`, fermeture) ne valent pas pour une suppression ; **4** indemnes : l'étape 5
    # de `triage`, « Confirmer », et les délégations à l'`executant` de `triage` et de `vers-prd`,
    # dont l'étape qui agit renvoie. Hors classe : `themes-milestones.md`, deux fois, renvoie à une
    # session `init-projet`.
    "6a-hors-scope-reconsiderer-au-deroule": (
        HORS_SCOPE_REF,
        "supprimé ou mis à jour par une PR, au déroulé de « Quand écrire » (étapes 5 et 6)",
    ),
    "6a-hors-scope-supprimer-aux-etapes-5-et-6": (
        HORS_SCOPE_REF,
        "par une PR, aux étapes 5 et 6 du déroulé ci-dessus",
    ),
    "6a-vers-prd-archive-au-deroule-hors-scope": (
        VERS_PRD_SKILL,
        (
            "la session ouvre la PR, la relit et la merge au go du mainteneur, au déroulé de"
            " `triage/hors-scope.md` (« Quand écrire », étapes 5 et 6)"
        ),
    ),
    "6a-interroge-moi-pr-au-deroule-hors-scope": (
        INTERROGE_MOI_SKILL,
        (
            "qui part par une PR que la session ouvre, relit et merge au go du mainteneur, au"
            " déroulé de `triage/hors-scope.md` (« Quand écrire », étapes 5 et 6)"
        ),
    ),
    "6a-interroge-moi-decision-apres-le-merge": (
        INTERROGE_MOI_SKILL,
        (
            "la ligne de « Décisions » qui l'exige ne s'écrit qu'une fois la PR mergée — sans go, le"
            " point reste une question ouverte"
        ),
    ),
    "6a-interroge-moi-arret-attend-le-merge": (
        INTERROGE_MOI_SKILL,
        "L'amendement qu'un arrêt décide part par une PR, et la décision attend son merge",
    ),
    # Lot 6b de #134, bloc 1 (2026-10-23) : `repercussions` nomme ses exécutants. Une entrée par
    # point du brief du bloc qui écrit une règle, et la moitié restrictive de chaque énoncé qui en
    # porte une (obs 126), plus les dettes que le lot 6a2 laissait à 6b dans `cycle-pr` et
    # `pr-paralleles`. Dénombrement, au cleanup du bloc : **21** moitiés restrictives dans les
    # énoncés neufs de `repercussions`, **18** épinglées au premier jet, **3** non — la carte de
    # proposition de la « Délégation », la première page seule sans `--paginate`, le brouillon
    # démarré dans le tour du mainteneur —, épinglées depuis ; « n'amende jamais », gardé tel quel,
    # l'est aussi. Gardés ailleurs : la délégation (D5),
    # l'absence d'écriture `gh` directe et le renvoi au script (`SKILLS_SANS_ECRITURE_GH_DIRECTE`),
    # le renvoi aux sessions liées (`SKILLS_DES_SESSIONS_LIEES`), `use_worktree` à chaque démarrage
    # (`USE_WORKTREE_EXPLICITE`).
    "6b-repercussions-releveur-sans-conclure": (
        REPERCUSSIONS_SKILL,
        "Ce qui compte reste à la session",
    ),
    "6b-repercussions-script-par-la-session": (
        REPERCUSSIONS_SKILL,
        "appelée par la session elle-même : un geste isolé coûte plus délégué",
    ),
    "6b-repercussions-sessions-au-tour-du-mainteneur": (
        REPERCUSSIONS_SKILL,
        (
            "chacune démarrée dans le tour du mainteneur qui l'accepte, hors de ce tour par une"
            " carte de proposition"
        ),
    ),
    "6b-repercussions-worktree-de-ses-sessions": (
        REPERCUSSIONS_SKILL,
        (
            "Une session que celle-ci démarre reçoit son propre worktree, `use_worktree: true` :"
            " `repercussions` tourne dans la session PR, dont le worktree est retiré après le"
            " merge, et une session démarrée dans ce dossier y vivrait et serait archivée avec"
            " elle (description de `start_session`, lue le 2026-10-23)"
        ),
    ),
    # Relecture de la PR #153, passe 1, I3 : personne n'était chargé de nettoyer les sessions que
    # `repercussions` démarre. Dénombrement (classe : une session démarrée dont le nettoyage n'a
    # pas de porteur nommé), sites de démarrage de `repercussions/SKILL.md` : **4**
    # (`contradiction` et sa carte, `plan-qa`, brouillons) ; **4** fuyaient ; une phrase les couvre.
    # Passe 2, I4 : cette phrase écrivait le protocole des sessions liées hors de sa source unique ;
    # il passe à `sessions-liees.md`, où `repercussions` renvoie désormais. Dénombrement (classe : une
    # règle de ce protocole écrite dans un skill au lieu de `sessions-liees.md`), énoncés des lignes
    # ajoutées à `repercussions/SKILL.md` par la PR qui prescrivent un geste de session : **13** —
    # démarrages 8 (« Délégation » : tour du mainteneur ou carte, `<N>` du nom, `use_worktree` ;
    # étape 1 : `contradiction`, sa carte, `repercussions` redémarré ; étape 7 : `plan-qa` ;
    # brouillons), messages 3 (étape 1 renvoie à l'étape 6 ; étape 6, même renvoi
    # qu'`interroge-moi` ; message de clôture qui nomme les enfants), nettoyages 2 (« à leur message
    # « terminé » » ; la session qui archive) ; **3** fuyaient, les trois derniers. Les démarrages
    # n'écrivent que leurs paramètres au site.
    "6b-repercussions-nettoyage-de-ses-sessions": (
        REPERCUSSIONS_SKILL,
        (
            "Ces sessions sont les enfants de la session qui les démarre, nettoyées au protocole de"
            " `sessions-liees.md` (« Nettoyage », « Fin de travail »)."
        ),
    ),
    "6b-sessions-liees-suffixe-des-enfants-au-travail": (
        SESSIONS_LIEES_REF,
        (
            "Toute forme admet un suffixe, « — enfants au travail : `local_…`, … », que porte le"
            " message d'une session qui a démarré des enfants encore au travail"
        ),
    ),
    # Relecture de la PR #153, relance, m8 : sans borne, une forme qui finit par `<chemin>` faisait
    # lire le suffixe comme une partie du chemin.
    "6b-sessions-liees-le-suffixe-suit-le-dernier-champ": (
        SESSIONS_LIEES_REF,
        (
            "Le suffixe suit le dernier champ : un `<chemin>` s'arrête avant « — enfants au"
            " travail »."
        ),
    ),
    # Relecture de la PR #153, relance, I5 : le suffixe ne nomme que des enfants encore au travail,
    # et l'archiveur les nettoyait sans attendre leur fin. Dénombrement écrit avant le correctif
    # (classe : un geste de nettoyage qui ne nomme pas sa condition de fin), « Nettoyage » de
    # `sessions-liees.md` et ses renvois, `grep -rn "Nettoyage" .claude/skills` le 2026-10-23 :
    # 13 lignes, **7** gestes ; **1** fuyait, l'archiveur ; **6** indemnes — `coordinatrice.md`
    # (après le merge de la PR d'intégration), `session-relecture.md` et `cycle-pr` Étape 8 (boucle
    # fermée), `pr-paralleles` Étape 8 (message de fin reçu), `repercussions` (par « Fin de
    # travail ») et le parent de « Nettoyage », dont ces cinq renvois portent le quand. Hors classe :
    # `pr-paralleles` 0 (n'archive pas), `get_session` de « Premier geste » (lecture), le suffixe
    # (renvoi à l'archiveur).
    "6b-sessions-liees-l-archiveur-nettoie-les-enfants-nommes": (
        SESSIONS_LIEES_REF,
        (
            "La session qui archive un parent nettoie, à la place du parent, les enfants que son"
            " message de fin nomme, chacun une fois son travail fini — son dernier message, lu par"
            " `list_events` (non mesuré), est une forme de « Fin de travail »"
        ),
    ),
    "6b-sessions-liees-l-archiveur-jamais-avant": (
        SESSIONS_LIEES_REF,
        (
            "—, jamais avant : le message de fin d'un enfant à un parent archivé est supposé perdu,"
            " non mesuré."
        ),
    ),
    # Relecture de la PR #153, relance, m9 : une session sans parent n'avait personne à qui nommer
    # ses enfants au travail.
    "6b-sessions-liees-sans-parent-le-mainteneur-archive": (
        SESSIONS_LIEES_REF,
        (
            "Une session sans parent nomme ses enfants au travail au mainteneur, dans son dernier"
            " tour, sous la même forme ; c'est lui qui l'archive."
        ),
    ),
    # Relecture de la PR #153, passe 1, I1 : après un arrêt `contradiction`, la passe de l'issue
    # fermée n'était jamais reprise — tenu par cette entrée, `6b-repercussions-session-contradiction`
    # et `6b-repercussions-reprise-sur-l-issue-fermee`. Dénombrement (classe : une passe qui s'arrête
    # pour une autre session sans que rien ne la reprenne), recensé dans `repercussions/SKILL.md` :
    # **1** site d'arrêt qui passe la main (étape 1, `contradiction`) ; **1** fuyait. Hors classe :
    # l'étape 5 « le poser au mainteneur et laisser l'issue intacte » (la passe continue sur les
    # autres issues).
    "6b-repercussions-pr-d-amendement": (
        REPERCUSSIONS_SKILL,
        (
            "Avec une PR d'amendement — une PR mergée par une `contradiction` née d'une décision,"
            " sans issue fermée à l'origine, qui amende une source de vérité ou déplace l'effet"
            " d'une décision hors de ce qu'elle affirme, sans fermer d'issue —, le delta réel est"
            " cette PR"
        ),
    ),
    "6b-repercussions-amendement-sans-qa": (REPERCUSSIONS_SKILL, "l'étape 7 est sans objet"),
    "6b-repercussions-journal-de-l-amendement": (
        REPERCUSSIONS_SKILL,
        (
            "la ligne de journal cite cette PR, pas une issue fermée (« Réconciliée avec la PR #<m>"
            " (amendement du cadrage §9.3 | déplacement de …), du 26 août 2026 »)"
        ),
    ),
    "6b-repercussions-l-issue-fermee-en-mode-amendement": (
        REPERCUSSIONS_SKILL,
        (
            "En mode amendement, `#<fermée>`, `<issue fermée>` et le `#47` des exemples se lisent"
            " « l'amendement, PR #<m> » — `pr-<m>` dans un chemin : la clé d'idempotence de l'étape 2"
            " est alors la ligne qui cite cette PR"
        ),
    ),
    "6b-repercussions-grep-des-sources-au-releveur": (
        REPERCUSSIONS_SKILL,
        "un `releveur` le passe et rend les passages autour des ancres ; le verdict reste à la session",
    ),
    "6b-repercussions-contradiction-au-tour-du-mainteneur": (
        REPERCUSSIONS_SKILL,
        "Dans le tour où le mainteneur l'accepte, démarrer la session `contradiction`",
    ),
    "6b-repercussions-session-contradiction": (
        REPERCUSSIONS_SKILL,
        (
            "`start_session`, `initiation: user_asked`, `context: fresh`, `use_worktree: true`,"
            f" `title: <préfixe> › contradiction` {RENVOI_A_L_IDENTITE}, prompt"
            " `/contradiction` suivi du bloc d'arrêt — ses deux citations — et de `origine : #<N>`"
        ),
    ),
    "6b-repercussions-reprise-sur-l-issue-fermee": (
        REPERCUSSIONS_SKILL,
        (
            "Quelle que soit sa sortie — amendement, document gagnant ou arrêt écarté —, elle"
            " redémarre `repercussions` sur `#<N>` avec la ligne `contradiction soldée` qui la nomme"
            " (`contradiction`, étape 5) : la passe reprend, les étapes 2 à 7 suivent, QA comprise"
        ),
    ),
    # Relecture de la PR #155, passe 2, I1 : la session redémarrée par `contradiction` ne relève
    # pas l'arrêt soldé, et trace l'effet mergé que le document gagnant laisse en place. Les
    # consignes par sortie : `SORTIES_DE_CONTRADICTION`.
    "6b2-repercussions-arret-solde-ne-se-releve-pas": (
        REPERCUSSIONS_SKILL,
        (
            "**Démarrée avec une ligne `contradiction soldée : <sortie>`** — celle que"
            " `contradiction` ajoute au bloc d'arrêt à son étape 5 —, la session tient cet arrêt"
            " pour soldé : il ne se lève pas une seconde fois"
        ),
    ),
    "6b2-repercussions-document-gagne-par-creation-d-issues": (
        REPERCUSSIONS_SKILL,
        (
            "(`.claude/rules/contraintes.md`, « Création d'issues en cours de cycle ») — la"
            " complétion `[complétion]` d'une issue ouverte qui possède le sujet, sinon un"
            " brouillon, par le chemin de « Ce que ce skill ne fait pas » —"
        ),
    ),
    "6b2-repercussions-document-gagne-deja-porte": (
        REPERCUSSIONS_SKILL,
        (
            "sauf si une issue ouverte le porte déjà (« Une contradiction déjà portée par une issue"
            " ouverte », ci-dessus) ; puis les étapes 2 à 7 suivent"
        ),
    ),
    "6b-repercussions-arret-previent-le-parent": (
        REPERCUSSIONS_SKILL,
        "Démarrée par une autre, cette session-ci prévient alors son parent (étape 6)",
    ),
    "6b-repercussions-n-amende-jamais": (
        REPERCUSSIONS_SKILL,
        "Ce skill **n'amende jamais un document lui-même**",
    ),
    # Cleanup holistique de la PR #153 : sans issue impactée, l'étape 4 s'arrêtait et sautait
    # l'étape 6 — récapitulatif et message de fin d'une session démarrée par une autre — et
    # l'étape 7, la QA d'un thème vidé, qui ne dépend pas des issues impactées. Dénombrement écrit
    # avant le correctif (classe : une sortie anticipée qui saute une étape due ensuite ; par la
    # forme du geste, obs 139 — « s'arrêter », « se taire », « on se tait »), dans
    # `repercussions/SKILL.md` le 2026-10-23 : **4** sites ; **2** fuyaient — l'étape 4, fermée
    # ici, et l'étape 1, « s'arrêter avant l'étape 2 », dont la passe redémarrée reprend les
    # étapes 2 à 7 mais dont la session sautait le message de fin de l'étape 6, fermée par
    # `6b-repercussions-arret-previent-le-parent` ; **2** indemnes — « On se tait », sur une issue
    # sans édition formulable, la passe continuant sur les autres, et le « se taire » de l'étape 7,
    # la dernière, sur une QA déjà proposée.
    "6b-repercussions-sans-impact-passe-a-l-etape-6": (
        REPERCUSSIONS_SKILL,
        "— et passer à l'étape 6, l'étape 7 restant due",
    ),
    # Relecture de la PR #155, passe 1, I2, hors de `bug-vers-issue` : le corps et le brief que
    # `repercussions` réécrit sont lus par la session, jamais repris d'un rapport. Dénombrement de
    # la classe : `REECRITURES_DE_CORPS` ; anciennes formes : `RETIRES_DU_CONTEXTE_VIVANT`.
    "6b2-repercussions-releveur-pas-ce-que-l-etape-5-reecrit": (
        REPERCUSSIONS_SKILL,
        (
            "le corps des issues examinées et leurs commentaires filtrés par les ancres données, le"
            " brief en entier — contexte des étapes 2 et 3, pas le corps ni le brief que l'étape 5"
            " réécrit —"
        ),
    ),
    "6b2-repercussions-corps-lu-par-la-session": (
        REPERCUSSIONS_SKILL,
        (
            "le corps courant, lu par la session elle-même juste avant d'écrire, dans ce même"
            " `<fichier>` (`gh api repos/{owner}/{repo}/issues/<n> --jq .body`, sans le LF final"
            " que `--jq` ajoute)"
        ),
    ),
    "6b2-repercussions-corps-par-aucun-rapport": (
        REPERCUSSIONS_SKILL,
        (
            "il ne passe par le rapport d'aucun équipier, qui pourrait en convertir les fins de"
            " ligne ou les espaces"
        ),
    ),
    "6b2-repercussions-brief-lu-par-la-session": (
        REPERCUSSIONS_SKILL,
        "même lecture, par la session elle-même, du commentaire qui s'ouvre par `## Brief d'agent`",
    ),
    "6b2-repercussions-relire-c-est-la-lecture-de-la-session": (
        REPERCUSSIONS_SKILL,
        "c'est la lecture de la session ci-dessus, faite au moment d'écrire",
    ),
    "6b2-repercussions-doublon-lu-par-la-session": (
        REPERCUSSIONS_SKILL,
        (
            "« Fermée en doublon de #<M> après #<fermée> », dans le corps (`issue edit --body-file`,"
            " lu par la session elle-même comme à « Éditer le corps »)"
        ),
    ),
    "6b2-repercussions-completion-lue-par-la-session": (
        REPERCUSSIONS_SKILL,
        "corps et brief lus par la session elle-même comme à l'étape 5 (« Éditer le corps »)",
    ),
    "6b-repercussions-remplacements-ancres": (
        REPERCUSSIONS_SKILL,
        "appliqué **par remplacements ancrés en mémoire** sur ce texte",
    ),
    "6b-repercussions-fins-de-ligne-gardees": (
        REPERCUSSIONS_SKILL,
        "ses fins de ligne gardées : le script relit contre ce fichier et ne voit pas une conversion",
    ),
    "6b-repercussions-appel-apres-les-controles": (
        REPERCUSSIONS_SKILL,
        "l'appel attend les deux contrôles ci-dessous",
    ),
    "6b-repercussions-brief-write": (
        REPERCUSSIONS_SKILL,
        (
            "`brief write <n> --body-file <fichier>`, qui édite en place le seul brief, jamais un"
            " second brief concurrent"
        ),
    ),
    "6b-repercussions-brief-sur-toutes-les-pages": (
        REPERCUSSIONS_SKILL,
        (
            "`gh api --paginate repos/{owner}/{repo}/issues/<n>/comments --jq '.[] | select(.body |"
            " startswith(\"## Brief d'\"'\"'agent\")) | .body'`, sans le LF final que `--jq` ajoute"
            " (mesuré sous Git Bash le 2026-10-23 sur #134, une page : octet pour octet le `.body`"
            " de son brief lu seul) — sans `--paginate`, la première page seule"
        ),
    ),
    "6b-repercussions-verification-dans-le-fichier": (
        REPERCUSSIONS_SKILL,
        (
            "chercher dans le fichier chaque « citation issue » marquée `brief` — **zéro occurrence"
            " attendue** — et l'ancre du contenu voulu — **présente**"
        ),
    ),
    "6b-repercussions-comment-pr": (
        REPERCUSSIONS_SKILL,
        "`comment <PR> --body-file <fichier>`, que le script relit en entier",
    ),
    "6b-repercussions-retour-par-label": (
        REPERCUSSIONS_SKILL,
        "`label <n> --add needs-interrogation --remove <ready-for-agent | ready-for-human>`",
    ),
    # Relecture de la PR #153, passe 1, I2 : la fermeture en doublon laissait le label d'état sur
    # une issue fermée. Tenu aussi par `test_chaque_fermeture_d_issue_retire_son_etat`, dont la
    # table, `FERMETURES_D_ISSUE`, porte le dénombrement.
    "6b-repercussions-fermee-en-doublon": (
        REPERCUSSIONS_SKILL,
        (
            "— le skill ne commente jamais une issue —, puis `issue close <n> --reason not_planned`,"
            " puis `label <n> --remove <état>` — l'état que l'issue porte, lu sur elle, sous son"
            " label réel (mapping de `.claude/pipeline.config.md`) : une issue fermée n'en porte"
            " aucun (`triage`, « Rôles »)"
        ),
    ),
    "6b-repercussions-seules-transitions-d-etat": (
        REPERCUSSIONS_SKILL,
        (
            "**Il ne re-trie pas.** Les seules transitions d'état qu'il applique sont le retour en"
            " `needs-interrogation` décrit ci-dessus et le retrait de l'état d'une issue qu'il ferme"
            " en doublon, par `label` (« Délégation ») ; tout autre changement d'état passe par"
            " `triage`"
        ),
    ),
    # Cleanup holistique de la PR #153 : le message de fin partait « le récapitulatif fait », avant
    # l'étape 7 que doit la passe redémarrée par `contradiction` (« QA comprise »), et jamais à
    # l'arrêt de l'étape 1. Sites qui font partir ce message dans `repercussions/SKILL.md`, le
    # 2026-10-23 : **1**, l'étape 6, la « Délégation » n'en disant que le contenu ; il fuyait.
    "6b-repercussions-fin-de-travail": (
        REPERCUSSIONS_SKILL,
        (
            "la passe finie — après l'étape 7, ou à l'arrêt de l'étape 1 —, prévenir le parent par"
            " le message de fin de la même référence (« Fin de travail ») — la fin du tour ne le"
            " prévient pas"
        ),
    ),
    "6b-repercussions-proposer-puis-demarrer": (
        REPERCUSSIONS_SKILL,
        (
            "**Proposer, puis démarrer sur accord.** La proposition reste une question au"
            " mainteneur ; sur son accord, dans ce tour, démarrer la session"
        ),
    ),
    # Relecture de la PR #153, passe 1, CR2 : le `name` d'un texte libre sortait de `[a-z0-9-]`.
    # Depuis #186 (D-1), le titre porte le thème tel quel, sous 60 caractères (« Identité »).
    "6b-repercussions-session-plan-qa": (
        REPERCUSSIONS_SKILL,
        (
            "`start_session`, `initiation: user_asked`, `context: fresh`, `use_worktree: true`,"
            f" `title: <préfixe> › plan-qa <thème>` {RENVOI_A_L_IDENTITE}, prompt"
            ' `/plan-qa "<thème>"`.'
        ),
    ),
    "6b-repercussions-brouillon-au-tour-du-mainteneur": (
        REPERCUSSIONS_SKILL,
        "un brouillon dans sa propre session, démarrée dans le tour où le mainteneur l'accepte",
    ),
    "6b-repercussions-plan-hors-depot": (
        REPERCUSSIONS_SKILL,
        "un fichier de plan que la session écrit hors du dépôt",
    ),
    "6b-repercussions-pourquoi-hors-depot": (
        REPERCUSSIONS_SKILL,
        "un fichier non suivi dans le worktree de la session PR salirait son arbre",
    ),
    "6b-repercussions-brouillon-montre-au-mainteneur": (
        REPERCUSSIONS_SKILL,
        "La session de brouillon le montre au mainteneur, qui décide",
    ),
    "6b-cycle-pr-repercussions-prescrit-le-commentaire": (
        CYCLE_PR_SKILL,
        "`repercussions` le prescrit à son étape 5, « Issues en vol »",
    ),
    "6b-pr-paralleles-repercussions-prescrit-le-commentaire": (
        PR_PARALLELES_SKILL,
        "`repercussions` le prescrit à son étape 5, « Issues en vol »",
    ),
    # Lot 6b2 de #134 (2026-10-25) : `contradiction` et `bug-vers-issue` nomment leurs exécutants.
    # Une entrée par point du brief du lot qui écrit une règle dans le corps — le frontmatter et le
    # tableau d'ouverture de `contradiction` la résument, sans entrée —, et la moitié restrictive de
    # chaque énoncé qui en porte une (obs 126), plus la dette de `cycle-pr` Étape 8 et le déroulé de
    # `hors-scope.md`, qui nomme `contradiction`. Dénombrement, au cleanup holistique, par la forme,
    # sur les morceaux (`morceaux_du_texte`) des six fichiers de prose absents de `ecae185` :
    # **18** moitiés restrictives — 8 « reste à », 6 « ne … pas », 2 « jamais », 2 « seule » —, plus
    # **9** sous une forme voisine — 2 « Sans argument », 3 « aucun », « sans le LF final », « rien
    # à démarrer », « remonte à la session », « elle-même » — : **27**, toutes épinglées, 23 au
    # premier jet, 4 au cleanup du bloc, vues rouges. Gardés ailleurs : la délégation (D5),
    # l'absence d'écriture `gh` directe, le renvoi au script et son
    # exemption (`SKILLS_SANS_ECRITURE_GH_DIRECTE`, `ECRITURE_RELUE_SANS_OBJET`), le renvoi aux
    # sessions liées (`SKILLS_DES_SESSIONS_LIEES`), `use_worktree` à chaque démarrage
    # (`USE_WORKTREE_EXPLICITE`), le contexte vivant retiré (`RETIRES_DU_CONTEXTE_VIVANT`).
    "6b2-contradiction-ecriture-de-depot-par-une-pr": (
        CONTRADICTION_SKILL,
        "toute écriture de dépôt de ce skill part par une PR (D-12 de #134",
    ),
    "6b2-contradiction-raisonnement-dans-le-body": (
        CONTRADICTION_SKILL,
        "le raisonnement va dans le body de la PR qui porte l'amendement",
    ),
    "6b2-contradiction-affirmation-reste-a-la-session": (
        CONTRADICTION_SKILL,
        "la recherche « par affirmation » — reste à la session, sur les passages rendus",
    ),
    "6b2-contradiction-entree-arret-ecrit": (CONTRADICTION_SKILL, "L'entrée est l'arrêt écrit"),
    "6b2-contradiction-entree-par-ses-deux-voies": (
        CONTRADICTION_SKILL,
        (
            "par la session qui l'a levé, qui le recopie en invoquant le skill, ou par le prompt de"
            " la session que `repercussions` démarre, qui y ajoute `origine : #<N>`"
        ),
    ),
    "6b2-contradiction-sans-argument": (
        CONTRADICTION_SKILL,
        "Sans argument, la session s'arrête et demande les deux citations",
    ),
    "6b2-contradiction-sans-arret-decisions-vs-doc-d-abord": (
        CONTRADICTION_SKILL,
        "un § passé sans arrêt qui l'ait établi : dérouler d'abord `decisions-vs-doc`",
    ),
    "6b2-contradiction-premier-geste": (
        CONTRADICTION_SKILL,
        (
            "son premier geste lit les documents sur le trunk à jour,"
            " `git fetch origin && git switch --detach origin/<trunk>`"
        ),
    ),
    "6b2-contradiction-aucune-branche": (
        CONTRADICTION_SKILL,
        "Aucune branche à créer : l'amendement part du worktree isolé de l'`executant` (étape 4)",
    ),
    "6b2-contradiction-relecture-des-citations-a-la-session": (
        CONTRADICTION_SKILL,
        "Cette relecture reste à la session",
    ),
    "6b2-contradiction-cascade-au-releveur": (
        CONTRADICTION_SKILL,
        (
            "la première et la troisième partent au `releveur`, avec les termes que donne la"
            " session ; la deuxième reste à la session, sur les passages qu'il rend"
        ),
    ),
    "6b2-contradiction-context7-au-releveur": (
        CONTRADICTION_SKILL,
        (
            "un `releveur` pose la question à la documentation à jour de la bibliothèque"
            " (`context7`) et rend le passage cité mot pour mot ; la conclusion reste à la session"
        ),
    ),
    "6b2-contradiction-doc-hors-index-a-la-session": (
        CONTRADICTION_SKILL,
        "ou plusieurs candidates, remonte à la session, qui la lit à la source",
    ),
    "6b2-contradiction-par-une-pr": (
        CONTRADICTION_SKILL,
        "l'amendement part par une PR, jamais par un commit direct sur le trunk",
    ),
    "6b2-contradiction-dans-la-pr-de-la-session": (
        CONTRADICTION_SKILL,
        "**dans une session PR**, il entre dans sa PR, par un commit de son `developpeur`",
    ),
    # Relecture de la PR #155, passe 1, M4 : les sessions de dialogue hors PR, nommées comme
    # `.claude/rules/decisions-vs-doc.md`, « Deux sorties » — le lead et la coordinatrice compris.
    "6b2-contradiction-hors-pr-sessions-de-dialogue": (
        CONTRADICTION_SKILL,
        (
            "**hors PR** — une session de tri, d'interrogatoire ou de `vers-issues`, le lead d'une"
            " vague, la coordinatrice d'une issue en lots, ou celle que `repercussions` démarre —"
        ),
    ),
    "6b2-contradiction-pr-d-amendement-au-deroule-hors-scope": (
        CONTRADICTION_SKILL,
        (
            "une PR d'amendement, au déroulé de `.claude/skills/triage/hors-scope.md` (« Quand"
            " écrire », étapes 5 et 6)"
        ),
    ),
    "6b2-contradiction-executant-isole": (
        CONTRADICTION_SKILL,
        "un `executant` en isolation `worktree`, jamais dans le dossier partagé",
    ),
    "6b2-contradiction-merge-au-go": (
        CONTRADICTION_SKILL,
        "la session pousse la branche, ouvre la PR, la relit et la merge au go du mainteneur",
    ),
    # Relecture de la PR #155, passe 2 : la PR de l'effet déplacé dans le dépôt (sortie 1b) n'avait
    # pas de table des édits décrite.
    "6b2-contradiction-table-des-edits-du-deplacement": (
        CONTRADICTION_SKILL,
        (
            "Quand le mainteneur retient à l'étape 3 l'effet déplacé dans le dépôt (sortie 1b de"
            " `decisions-vs-doc`), la table des édits porte ce déplacement, et non un amendement,"
            " par le même déroulé de PR"
        ),
    ),
    "6b2-contradiction-quatre-gestes-un-commit": (
        CONTRADICTION_SKILL,
        "La table des édits porte, dans le même commit, ces quatre gestes",
    ),
    "6b2-hors-scope-nomme-contradiction": (
        HORS_SCOPE_REF,
        (
            "ses étapes 5 et 6 valent pour toute PR qu'ouvre une session de `triage`,"
            " `interroge-moi`, `vers-prd`, `contradiction`, `audit-spec-ui` ou `init-projet`, qui y"
            " renvoient"
        ),
    ),
    "6b2-contradiction-mode-sans-copie": (
        CONTRADICTION_SKILL,
        (
            "Le mode qui confronte aux issues une PR mergée par ce skill vit dans `repercussions`,"
            " étape 1 (« PR d'amendement ») : ce skill ne le recopie pas"
        ),
    ),
    "6b2-contradiction-rien-a-demarrer-en-session-pr": (
        CONTRADICTION_SKILL,
        (
            "la passe `repercussions` de `cycle-pr` Étape 8 le confronte aux issues — rien à"
            " démarrer ici"
        ),
    ),
    # Relecture de la PR #155, passe 2, I1 : la relance part à la sortie, plus au seul merge d'un
    # amendement. Les deux relances et leur table : `SORTIES_DE_CONTRADICTION`.
    "6b2-contradiction-repercussions-au-tour-de-la-sortie": (
        CONTRADICTION_SKILL,
        (
            "**Hors PR**, dans le tour du mainteneur où la sortie est connue, démarrer la session"
            " `repercussions`"
        ),
    ),
    "6b2-contradiction-rend-la-passe-quelle-que-soit-la-sortie": (
        CONTRADICTION_SKILL,
        (
            "il **délègue à `repercussions`** une fois sa PR mergée, et, démarré par une passe"
            " `repercussions`, la fait reprendre quelle que soit la sortie"
        ),
    ),
    "6b2-contradiction-se-taire-ne-dispense-pas-de-la-relance": (
        CONTRADICTION_SKILL,
        "On se tait ; avec `origine : #<N>`, se taire ne dispense pas de la relance de l'étape 5",
    ),
    "6b2-contradiction-citation-introuvable-vers-l-etape-5": (
        CONTRADICTION_SKILL,
        (
            "Une citation qui ne s'y retrouve pas : pas de contradiction (« Le livrable »), et, avec"
            " `origine : #<N>`, la session passe aux étapes 5 et 6"
        ),
    ),
    "6b2-contradiction-fin-de-travail": (
        CONTRADICTION_SKILL,
        (
            "prévenir le parent par le message de fin de `sessions-liees.md` (« Fin de travail »),"
            " sous la forme que la table de l'étape 5 donne à sa sortie, suivie du suffixe"
            " « — enfants au travail : `local_…` » qui nomme la session `repercussions` démarrée,"
            " absent quand la relance est restée une carte de proposition — la fin du tour ne le"
            " prévient pas"
        ),
    ),
    "6b2-contradiction-l-archiveur-nettoie": (
        CONTRADICTION_SKILL,
        "La session qui l'archive nettoie cette enfant (« Nettoyage »)",
    ),
    "6b2-contradiction-n-edite-aucune-issue": (
        CONTRADICTION_SKILL,
        "**Il n'édite aucune issue lui-même.** C'est `repercussions`, à l'étape 5",
    ),
    "6b2-contradiction-code-perime-par-creation-d-issues": (
        CONTRADICTION_SKILL,
        (
            "Une décision qui périme du code déjà écrit suit « Création d'issues en cours de"
            " cycle » (`.claude/rules/contraintes.md`), pas une édition sauvage"
        ),
    ),
    "6b2-bug-vers-issue-releveur-sans-conclure": (
        BUG_VERS_ISSUE_SKILL,
        "Ce qui compte reste à la session",
    ),
    "6b2-bug-vers-issue-script-par-la-session": (
        BUG_VERS_ISSUE_SKILL,
        "appelée par la session elle-même : un geste isolé coûte plus délégué",
    ),
    "6b2-bug-vers-issue-demarree-par-une-autre": (
        BUG_VERS_ISSUE_SKILL,
        (
            "cette session peut être démarrée par une autre : la session de QA (`execution-qa`),"
            " qui reprend la QA dans sa propre session"
        ),
    ),
    "6b2-bug-vers-issue-mode-dans-l-argument": (
        BUG_VERS_ISSUE_SKILL,
        "Le mode se lit dans l'argument",
    ),
    "6b2-bug-vers-issue-mode-pilote": (
        BUG_VERS_ISSUE_SKILL,
        (
            "un numéro d'issue `qa-plan`, suivi de l'ancre de la case qui échoue et de l'intake"
            " d'échec écrit : un chemin de fichier, ou l'URL d'un commentaire de l'issue du plan"
        ),
    ),
    "6b2-bug-vers-issue-sans-argument": (
        BUG_VERS_ISSUE_SKILL,
        "Sans argument, la session s'arrête et demande la description ou la case.",
    ),
    "6b2-bug-vers-issue-intake-sans-question": (
        BUG_VERS_ISSUE_SKILL,
        "l'intake écrit est la source : aucune question, sauf pour un champ manquant",
    ),
    "6b2-bug-vers-issue-questions-dans-cette-session": (
        BUG_VERS_ISSUE_SKILL,
        "au plus 2 ou 3 courtes questions au mainteneur, dans cette session",
    ),
    "6b2-bug-vers-issue-coupables-a-la-session": (
        BUG_VERS_ISSUE_SKILL,
        "le choix du ou des coupables reste à la session",
    ),
    "6b2-bug-vers-issue-argument-et-intake": (
        BUG_VERS_ISSUE_SKILL,
        (
            "**L'argument et l'intake écrit** — la description passée en argument, ou l'intake que"
            " le `releveur` rend tel quel"
        ),
    ),
    "6b2-bug-vers-issue-proprietaire-a-la-session": (
        BUG_VERS_ISSUE_SKILL,
        "la conclusion — qui possède le sujet — reste à la session",
    ),
    "6b2-bug-vers-issue-ouverte-commentee": (
        BUG_VERS_ISSUE_SKILL,
        "**ouverte** : la commenter (`comment <N> --body-file <fichier>`), sur son accord",
    ),
    "6b2-bug-vers-issue-fermee-issue-soeur": (
        BUG_VERS_ISSUE_SKILL,
        "elle est **fermée** : créer une issue sœur qui la cite (`issue create`, étape 6)",
    ),
    "6b2-bug-vers-issue-jamais-rouverte": (
        BUG_VERS_ISSUE_SKILL,
        (
            "une issue fermée ne porte aucun rôle d'état (`triage`, « Rôles ») ; rouverte, elle"
            " serait hors de toute file de tri, et `ecriture-relue.py` n'a pas de réouverture"
        ),
    ),
    "6b2-bug-vers-issue-pas-en-silence": (BUG_VERS_ISSUE_SKILL, "ne consigne pas en silence"),
    "6b2-bug-vers-issue-creation-relue": (
        BUG_VERS_ISSUE_SKILL,
        (
            'ecriture-relue.py issue create --title "<titre>" --body-file <brouillon>'
            " --label <qa-finding> --label <needs-triage>"
        ),
    ),
    "6b2-bug-vers-issue-labels-du-mapping": (
        BUG_VERS_ISSUE_SKILL,
        "`<qa-finding>` et `<needs-triage>` sont les labels réels du mapping",
    ),
    "6b2-bug-vers-issue-decoupage-une-creation-a-la-fois": (
        BUG_VERS_ISSUE_SKILL,
        "puis les enfants un par un, dans l'ordre des dépendances, chacun par son `issue create`",
    ),
    "6b2-bug-vers-issue-patch-du-plan": (
        BUG_VERS_ISSUE_SKILL,
        "par `issue edit <plan> --body-file <fichier>`",
    ),
    # Relecture de la PR #155, passe 1, I2 : le corps qui se patche ne transite par aucun rapport
    # (obs 87, 106). Classe : une lecture de corps distant, destinée à une réécriture, confiée hors
    # de la session. Dénombrement par la forme du geste (obs 139), `grep -rn "issue edit"
    # .claude/skills/contradiction .claude/skills/bug-vers-issue` : 3 lignes, **1** réécriture —
    # l'étape 7 ; la « Délégation » et « Erreurs courantes » y renvoient. Les autres lectures du
    # plan sont du contexte (étapes 2 et 3), bornées dans la « Délégation ». L'ancienne phrase est
    # tenue absente par `RETIRES_DU_CONTEXTE_VIVANT`.
    "6b2-bug-vers-issue-corps-lu-par-la-session": (
        BUG_VERS_ISSUE_SKILL,
        (
            "la session lit elle-même le corps courant, juste avant le patch, dans ce même"
            " `<fichier>` (`gh api repos/{owner}/{repo}/issues/<plan> --jq .body`, sans le LF final"
            " que `--jq` ajoute)"
        ),
    ),
    "6b2-bug-vers-issue-corps-par-aucun-rapport": (
        BUG_VERS_ISSUE_SKILL,
        (
            "il ne passe par le rapport d'aucun équipier, qui pourrait en convertir les fins de"
            " ligne ou les espaces"
        ),
    ),
    "6b2-bug-vers-issue-releveur-pas-le-corps-patche": (
        BUG_VERS_ISSUE_SKILL,
        (
            "le corps du plan QA autour de la case — contexte des étapes 2 et 3, pas le corps que"
            " l'étape 7 patche —"
        ),
    ),
    "6b2-bug-vers-issue-remplacements-en-memoire": (
        BUG_VERS_ISSUE_SKILL,
        "les remplacements se font en mémoire, par correspondance exacte de ligne complète",
    ),
    "6b2-bug-vers-issue-ligne-introuvable-arrete": (
        BUG_VERS_ISSUE_SKILL,
        "chaque ancienne ligne trouvée une seule fois, sinon s'arrêter et le dire au mainteneur",
    ),
    # Relecture de la PR #155, passe 1, M2 : l'entrée d'Index est un ajout, ancré comme un
    # remplacement.
    "6b2-bug-vers-issue-index-ancre-sur-son-titre": (
        BUG_VERS_ISSUE_SKILL,
        (
            "l'entrée s'insère après la dernière ligne de l'Index des constats, ancrée sur sa ligne"
            " de titre, trouvée de même une seule fois"
        ),
    ),
    "6b2-bug-vers-issue-patch-regles-de-correspondance-seules": (
        BUG_VERS_ISSUE_SKILL,
        (
            "« Correspondance par ligne complète » et « Détecter les éditions concurrentes » —"
            " leurs règles de correspondance seules : sa lecture et son push sont ceux de cette"
            " étape"
        ),
    ),
    "6b2-bug-vers-issue-fins-de-ligne-gardees": (
        BUG_VERS_ISSUE_SKILL,
        (
            "le résultat est écrit tel quel dans le fichier, ses fins de ligne gardées : le script"
            " relit contre ce fichier et ne voit pas une conversion"
        ),
    ),
    "6b2-bug-vers-issue-fin-de-travail": (
        BUG_VERS_ISSUE_SKILL,
        (
            "prévenir le parent par le message de fin de la même référence (« Fin de travail »),"
            " « terminé — <livrable> », le livrable nommant la classe : « BUG #<N> consigné »,"
            " « attendu faux, case réécrite », « environnement, case à rejouer », « correctif"
            " évident, petite PR proposée » ou « correctif évident, rendu à ta PR : <correctif> »"
            " — la fin du tour ne le prévient pas"
        ),
    ),
    "6b2-bug-vers-issue-la-qa-reprend": (BUG_VERS_ISSUE_SKILL, "la QA reprend dans sa session"),
    "6b2-bug-vers-issue-labels-reels": (
        BUG_VERS_ISSUE_SKILL,
        "Les labels réels se lisent dans le mapping de `.claude/pipeline.config.md`",
    ),
    "6b2-bug-vers-issue-label-absent-arrete": (
        BUG_VERS_ISSUE_SKILL,
        "`issue create` refuse en le nommant : s'arrêter et le dire au mainteneur",
    ),
    "6b2-bug-vers-issue-erreur-intake-ecrit": (
        BUG_VERS_ISSUE_SKILL,
        "Rédiger sans relire l'intake d'échec écrit",
    ),
    "6b2-collecte-contexte-lectures-au-releveur": (
        COLLECTE_CONTEXTE_REF,
        (
            "Les commandes de ce fichier sont des lectures, lancées par un `releveur` (SKILL.md,"
            " « Délégation ») ; ce qui compte reste à la session"
        ),
    ),
    "6b2-collecte-contexte-argument-et-intake": (
        COLLECTE_CONTEXTE_REF,
        "1. L'argument et l'intake écrit",
    ),
    "6b2-gabarit-decoupage-une-creation-a-la-fois": (
        GABARIT_DECOUPAGE_REF,
        "une `issue create` à la fois (SKILL.md, étape 6)",
    ),
    # Lot 7a de #134 (2026-10-26) : `plan-qa` nomme ses exécutants et publie par l'écriture relue.
    # Une entrée par point du brief du bloc 2 qui écrit une règle — « Délégation », « Entrées »,
    # étapes 1, 2, 5, 6 et 7, « Passe finale avant publication » scindée, « Erreurs fréquentes » ;
    # dans le gabarit, sa règle 3, « Saisie d'échec » et l'Index des constats — et par moitié
    # restrictive (obs 126), plus la dette de `cycle-pr` Étape 8. Dénombrement, au cleanup du
    # bloc, par la forme, sur les lignes ajoutées des fichiers de prose
    # (`git diff -U0 -- .claude/skills/`) : **24** moitiés restrictives — 6 « refuse », 4 « ne …
    # pas » ou « ne … rien », 4 « la session » sans « reste à », 3 « jamais », 2 « reste à » ou
    # « garde », 2 « elle-même », « uniquement », « n'… que », « sauf » — : toutes épinglées, 21 au
    # premier jet, 3 au cleanup, vues rouges par `mutation.py` ; le correctif de la passe 1 de
    # relecture en ajoute une, l'attendu de l'Observation ; celui de la passe 2, trois : l'attendu
    # sur la ligne de la case — Commande, Observation, erreur « Case sans type ». Gardés ailleurs :
    # la délégation (D5), l'absence d'écriture `gh` directe et
    # le renvoi au script (`SKILLS_SANS_ECRITURE_GH_DIRECTE`), le renvoi aux sessions liées
    # (`SKILLS_DES_SESSIONS_LIEES`), le contexte vivant et la création de label retirés
    # (`RETIRES_DU_CONTEXTE_VIVANT`), le type de chaque case du gabarit et de l'exemple
    # (`test_chaque_case_d_un_plan_de_qa_porte_son_type`), l'accord de la commande « cases sans
    # type » avec `cases_sans_type` (`test_la_commande_des_cases_sans_type_s_accorde_au_recueil`),
    # l'absence de `\` dans les commandes de la passe comptable
    # (`test_une_commande_de_la_passe_comptable_n_a_aucune_barre_oblique_inverse`). **Ce qui n'est
    # pas gardé** : l'accord de la commande « critères → cases » avec `PLAN_QA_CASE`.
    "7a-plan-qa-jugement-a-la-session": (
        PLAN_QA_SKILL,
        (
            "La session garde le jugement : le périmètre — le mode, et la question au mainteneur"
            " du mode 4 —, les surfaces lues dans la config, le choix des phases et des cases et"
            " leur type, les « Décision QA », la rédaction, le go de publication."
        ),
    ),
    "7a-plan-qa-releveur-noms-verifies": (
        PLAN_QA_SKILL,
        (
            "chaque nom vérifié contre les migrations ou les modèles, chaque endpoint ou chemin"
            " incertain vérifié localement (étapes 1 et 5)"
        ),
    ),
    "7a-plan-qa-releveur-sans-conclure": (
        PLAN_QA_SKILL,
        "Il rend les relevés dans un fichier ; ce qui compte reste à la session",
    ),
    "7a-plan-qa-executant-ne-corrige-rien": (
        PLAN_QA_SKILL,
        (
            "il rend « conforme » ou les lignes en échec, et ne corrige rien ; une case sans type"
            " refuse la publication"
        ),
    ),
    "7a-plan-qa-script-par-la-session": (
        PLAN_QA_SKILL,
        "appelée par la session elle-même : un geste isolé coûte plus délégué",
    ),
    "7a-plan-qa-demarree-par-repercussions": (
        PLAN_QA_SKILL,
        (
            "cette session peut être démarrée par `repercussions`, à son étape 7, qui lui passe"
            " le thème"
        ),
    ),
    "7a-plan-qa-qa-hors-de-ce-contexte": (
        PLAN_QA_SKILL,
        (
            "la QA se déroule dans une session `execution-qa` distincte, qui reçoit le numéro du"
            " plan publié, jamais dans le contexte de celle-ci"
        ),
    ),
    "7a-plan-qa-ne-demarre-pas-execution-qa": (
        PLAN_QA_SKILL,
        "`plan-qa` ne la démarre pas : il rend le numéro",
    ),
    "7a-plan-qa-mode-1-au-releveur": (
        PLAN_QA_SKILL,
        "Le `releveur` (« Délégation ») relève le corps du PRD, puis les issues d'implémentation",
    ),
    "7a-plan-qa-mode-2-au-releveur": (
        PLAN_QA_SKILL,
        "Le `releveur` relève le corps et les critères d'acceptation de chaque issue.",
    ),
    "7a-plan-qa-mode-3-au-releveur": (
        PLAN_QA_SKILL,
        "Le `releveur` relève les issues du milestone",
    ),
    "7a-plan-qa-mode-4-question-a-la-session": (
        PLAN_QA_SKILL,
        (
            "le `releveur` relève les thèmes dont toutes les issues sont fermées et qui n'ont pas"
            " encore d'issue `qa-plan`, et la session demande au mainteneur lequel recetter. S'il"
            " n'y en a aucun, elle lui demande quelles issues sont dans le périmètre — **ne jamais"
            " deviner un périmètre de QA**"
        ),
    ),
    "7a-plan-qa-tous-les-modes-au-releveur": (
        PLAN_QA_SKILL,
        (
            "Dans tous les modes, le `releveur` (« Délégation ») rend aussi : - le PRD s'il est"
            " connu, dont la session tire la section « Vue d'ensemble »"
        ),
    ),
    "7a-plan-qa-config-et-glossaire-par-la-session": (
        PLAN_QA_SKILL,
        (
            "La session lit elle-même `.claude/pipeline.config.md` (stack, commandes, domaines,"
            " surfaces), `CLAUDE.md` et le glossaire du domaine"
        ),
    ),
    "7a-plan-qa-inspection-au-releveur": (
        PLAN_QA_SKILL,
        (
            "L'inspection part au `releveur` (« Délégation »), à qui la session donne la liste des"
            " surfaces de la config et des fichiers touchés par les commits du périmètre"
        ),
    ),
    "7a-plan-qa-instruction-verifiee-seule": (
        PLAN_QA_SKILL,
        "la session n'inclut comme instruction que ce que la carte a vérifié",
    ),
    "7a-plan-qa-label-du-mapping": (
        PLAN_QA_SKILL,
        (
            "portant le label `qa-plan` — le label réel est celui du mapping de"
            " `.claude/pipeline.config.md`"
        ),
    ),
    "7a-plan-qa-label-absent-arrete": (
        PLAN_QA_SKILL,
        (
            "S'il manque au dépôt, `issue create` refuse en le nommant : s'arrêter et le dire"
            " au mainteneur"
        ),
    ),
    "7a-plan-qa-persistance-par-le-releve": (
        PLAN_QA_SKILL,
        (
            "uniquement sur les noms réels que le relevé du `releveur` a vérifiés contre les"
            " migrations"
        ),
    ),
    "7a-plan-qa-decision-apres-le-type": (
        PLAN_QA_SKILL,
        (
            "marque la case avec `Décision QA :`, **après** sa marque de type — le plus souvent"
            " `**Observation** — Décision QA : … → <attendu>` : une case de décision reste une case"
            " typée, sinon la passe comptable la refuse comme case sans type"
        ),
    ),
    "7a-plan-qa-passe-finale-avant-le-go": (
        PLAN_QA_SKILL,
        (
            "La « Passe finale avant publication » d'abord, rejouée après chaque révision : le go"
            " du mainteneur porte sur le texte qui part"
        ),
    ),
    "7a-plan-qa-publication-relue": (
        PLAN_QA_SKILL,
        (
            "python .claude/skills/cycle-pr/scripts/ecriture-relue.py issue create --title"
            ' "Plan QA: <périmètre>" --body-file <brouillon> --label <qa-plan>'
        ),
    ),
    "7a-plan-qa-label-reel-et-numero": (
        PLAN_QA_SKILL,
        (
            "`<qa-plan>` étant le label réel du mapping (étape 2) ; le script relit corps, titre et"
            " labels, et sa ligne de sortie porte le numéro"
        ),
    ),
    "7a-plan-qa-rend-le-numero": (
        PLAN_QA_SKILL,
        (
            "Rends le numéro de l'issue, ou le chemin du fichier : c'est ce que reçoit la"
            " session `execution-qa`"
        ),
    ),
    "7a-plan-qa-passe-comptable-ses-entrees": (
        PLAN_QA_SKILL,
        (
            "1. Passe comptable — `executant` La session lui passe le chemin du brouillon et"
            " celui du relevé des issues du périmètre (numéros et critères)"
        ),
    ),
    "7a-plan-qa-passe-comptable-refuse": (
        PLAN_QA_SKILL,
        (
            "rend « conforme » ou chaque ligne en échec ; il ne corrige rien. Tout échec refuse la"
            " publication : la session corrige le brouillon et relance la passe."
        ),
    ),
    "7a-plan-qa-cases-sans-type-commande": (
        PLAN_QA_SKILL,
        (
            "grep -nE '^([[:blank:]>]*([-*+]|[[:digit:]]+[.)])[[:blank:]]+)+[[][[:blank:]xX][]]"
            "[[:blank:]]+' <brouillon> | grep -vE '^[[:digit:]]+:([[:blank:]>]*([-*+]|"
            "[[:digit:]]+[.)])[[:blank:]]+)+[[][[:blank:]xX][]][[:blank:]]+([*][*]Commande[*][*] —"
            " `[^`]+`|[*][*]Observation[*][*] — .+) → [^[:space:]]'"
        ),
    ),
    "7a-plan-qa-criteres-vers-cases": (
        PLAN_QA_SKILL,
        (
            "`grep -nE '^## |^- [*][*]C[[:digit:]]+[*][*] — |^([[:blank:]>]*([-*+]|[[:digit:]]+"
            "[.)])[[:blank:]]+)+[[][[:blank:]xX][]][[:blank:]]+.*[(]C[[:digit:]]+(, C[[:digit:]]+)*"
            "[)]' <brouillon>` : chaque issue du relevé a son titre"
            " `## Bloc de fonctionnalité : Issue #<N>` ; sous chacun, avant le titre suivant,"
            " autant de lignes `- **C<k>** —` que l'issue a de critères, et chaque `C<k>` cité par"
            " au moins une case"
        ),
    ),
    "7a-plan-qa-marqueurs": (
        PLAN_QA_SKILL,
        (
            "`grep -nE 'TODO|FIXME|à compléter|<[^<>[:space:]][^<>]*>' <brouillon>` : toute ligne"
            " sortie porte un marqueur ou un espace réservé du gabarit"
        ),
    ),
    "7a-plan-qa-structure": (
        PLAN_QA_SKILL,
        (
            "« Paliers de sévérité » une fois, avant la première phase ; chaque `## Phase` — sauf"
            " la Phase Finale, qui clôt le plan — et chaque `## Bloc de fonctionnalité` suivi de sa"
            " ligne `**Règle d'arrêt**` avant le titre suivant"
        ),
    ),
    "7a-plan-qa-relecture-de-jugement": (PLAN_QA_SKILL, "2. Relecture de jugement — la session"),
    "7a-plan-qa-noms-du-releve": (
        PLAN_QA_SKILL,
        (
            "Chaque route, table, fichier, variable d'environnement ou fixture d'une case vient du"
            " relevé du `releveur`, vérifié contre le dépôt."
        ),
    ),
    "7a-plan-qa-erreur-case-sans-type": (
        PLAN_QA_SKILL,
        (
            "`**Commande** —` ou `**Observation** —` en tête, puis ` → ` et l'attendu sur la ligne"
            " de la case (gabarit, « Types de case ») ; la passe comptable la refuse"
        ),
    ),
    "7a-gabarit-plan-qa-passe-comptable-refuse": (
        GABARIT_PLAN_QA_REF,
        "Une case sans type n'est pas publiable : la passe comptable la refuse",
    ),
    "7a-gabarit-plan-qa-commande-attendu-sur-sa-ligne": (
        GABARIT_PLAN_QA_REF,
        (
            "dans un seul segment entre accents graves, puis ` → ` et son attendu sur la ligne même"
            " de la case"
        ),
    ),
    "7a-gabarit-plan-qa-observation-porte-son-attendu": (
        GABARIT_PLAN_QA_REF,
        (
            "Une case **Observation** — rendu, état d'écran, console, ergonomie — porte de même"
            " ` → ` et son attendu sur sa première ligne"
        ),
    ),
    "7a-gabarit-plan-qa-intake-ecrit": (
        GABARIT_PLAN_QA_REF,
        (
            "l'intake de `execution-qa/references/gabarit-intake-echec.md` s'écrit — dans un"
            " fichier, ou en commentaire de l'issue du plan —, ses champs sans contenu supprimés,"
            " jamais laissés vides"
        ),
    ),
    "7a-gabarit-plan-qa-intake-en-argument": (
        GABARIT_PLAN_QA_REF,
        (
            "La session de consignation `bug-vers-issue` le reçoit en argument, dans son mode"
            " piloté par un plan : le numéro du plan, l'ancre de la case, le chemin ou l'URL de"
            " l'intake."
        ),
    ),
    "7a-gabarit-plan-qa-index-modele-non-recopie": (
        GABARIT_PLAN_QA_REF,
        "ne se recopie pas dans le plan publié",
    ),
    "7a-cycle-pr-plan-qa-nomme-la-famille": (
        CLOTURE_REF,
        (
            "`triage`, `interroge-moi`, `vers-prd`, `vers-issues`, `repercussions`,"
            " `bug-vers-issue`, `plan-qa`, `execution-qa` et `init-projet` (`depot create`,"
            " `label create`) les nomment. Toute écriture qu'il ne fait pas reste sous la règle"
            " « Écritures sur un artefact distant »"
        ),
    ),
    # Lot 7b2 de #134 (2026-10-26) : `execution-qa` délègue, son état est la forge, son échec
    # s'écrit et se consigne dans une session distincte. Une entrée par point du brief du bloc qui
    # écrit une règle — « Délégation », §1 à §4, §6, « Décisions de politique », « Passe finale »,
    # « Erreurs courantes » ; les quatre références ; la dette de `bug-vers-issue` et la ligne
    # d'Index du gabarit de `plan-qa` —, et par moitié restrictive (obs 126). Dénombrement par la
    # forme, sur les lignes ajoutées des fichiers de prose
    # (`git diff -U0 ffbe52e d99e9a8 -- .claude/skills/`) : **60** moitiés restrictives
    # — 10 « jamais », 12 « ne … pas », « ne … rien », « ne … plus » ou « ne … ni », 6 « pas »
    # elliptique, 7 « elle-même », 5 « la session » ou « cette session » sans « elle-même » ni
    # « reste à », 5 « seul », 4 « aucun », 3 « s'arrêter », 3 « sans », 2 « hors », « ni … ni »,
    # « n'… que », « reste à » — et 2 de plus sur la ligne réécrite de l'étape 7 de
    # `bug-vers-issue` (« une seule fois », « s'arrêter »), déjà gardées par
    # `6b2-bug-vers-issue-ligne-introuvable-arrete` ; toutes épinglées, vues rouges sur `ffbe52e`
    # sauf deux phrases inchangées sur une ligne réécrite (`7b2-execution-qa-travail-preserve`,
    # `7b2-execution-qa-pas-de-preuve-inutile`), vues rouges par `mutation.py`. Gardés ailleurs :
    # la délégation (D5), l'absence d'écriture `gh` directe et
    # le renvoi au script (`SKILLS_SANS_ECRITURE_GH_DIRECTE`), le renvoi aux sessions liées
    # (`SKILLS_DES_SESSIONS_LIEES`), `use_worktree` et « n'écrit que dans GitHub » au démarrage de
    # la consignation (`USE_WORKTREE_EXPLICITE`), le contexte vivant retiré
    # (`RETIRES_DU_CONTEXTE_VIVANT`), l'annotation de chaque marque réglée
    # (`ANNOTATIONS_QUI_REGLENT_UNE_CASE`).
    "7b2-bug-vers-issue-intake-ecrit-par-la-qa": (
        BUG_VERS_ISSUE_SKILL,
        "La session de QA démarre ce mode, avec l'intake qu'elle a écrit (`execution-qa`, §4).",
    ),
    "7b2-gabarit-plan-qa-index-par-bug-vers-issue": (
        GABARIT_PLAN_QA_REF,
        (
            "La session `bug-vers-issue` ajoute les liens ici à mesure qu'elle consigne les bugs de"
            " la campagne — son étape 7."
        ),
    ),
    "7b2-execution-qa-principe": (
        EXECUTION_QA_SKILL,
        (
            "Chaque échec offre à l'utilisateur trois options explicites (consigner, reporter, faire"
            " corriger). Ne jamais auto-invoquer `bug-vers-issue`. **Ne jamais fusionner deux"
            " surfaces en un seul verdict** quand une seule a été réellement testée — « le service"
            " répond » ne dit rien de ce que l'utilisateur voit."
        ),
    ),
    "7b2-execution-qa-jugement-a-la-session": (
        EXECUTION_QA_SKILL,
        (
            "La session garde le jugement : le dialogue avec le mainteneur — les cases"
            " **Observation** —, le verdict de chaque case, les décisions de politique, le choix"
            " entre les options d'un échec, la rédaction de l'intake et du commentaire de phase, le"
            " démarrage des sessions."
        ),
    ),
    "7b2-execution-qa-releveur-commande-telle-qu-ecrite": (
        EXECUTION_QA_SKILL,
        (
            "les cases **Commande** : la commande exacte et l'attendu du plan, tapés tels qu'écrits,"
            " la sortie lue brute, sans résumeur — la forme « test brut » de"
            " `.claude/pipeline.config.md` quand le poste en a une (obs 144)"
        ),
    ),
    "7b2-execution-qa-releveur-premier-ko": (
        EXECUTION_QA_SKILL,
        (
            "Il rend OK ou KO par case, le code de sortie, la sortie brute si KO, et s'arrête au"
            " premier KO, qui remonte ; plusieurs cases d'un bloc partent dans un seul brief"
        ),
    ),
    "7b2-execution-qa-releveur-releves": (
        EXECUTION_QA_SKILL,
        (
            "Lui reviennent aussi l'état de l'arbre et les fichiers que les cases du bloc nomment"
            " (§2), l'état des issues des cases `🔴 BUG #N` et des PR des cases `🔴 PR #<M>` à la"
            " reprise (§2), le recoupement BD / logs (« Patrons par surface »), les commandes"
            " finales (§6) et la preuve lourde, rassemblée dans un fichier (§3, étape 6). Le verdict"
            " de la case reste à la session"
        ),
    ),
    "7b2-execution-qa-script-par-la-session": (
        EXECUTION_QA_SKILL,
        (
            "**script** — la prochaine case (`checkbox next`, §2), le patch des cases (`checkbox"
            " patch --paires`, §3, étape 5), le commentaire de phase et l'intake (`comment`, §3,"
            " étape 6, et §4), par `python .claude/skills/cycle-pr/scripts/ecriture-relue.py`,"
            " appelé par la session elle-même : un geste isolé coûte plus délégué"
        ),
    ),
    "7b2-execution-qa-sessions-distinctes": (
        EXECUTION_QA_SKILL,
        (
            "**sessions distinctes** — la consignation d'un échec (`bug-vers-issue`, §4, option"
            " (a)), sa correction (`cycle-pr`, option (c)), et la reprise de la case corrigée : une"
            " session de QA neuve, démarrée sur le numéro du plan une fois la correction mergée,"
            " dont le §2 trouve la case — jamais la suite du contexte qui a corrigé"
        ),
    ),
    "7b2-execution-qa-etat-a-la-forge": (
        EXECUTION_QA_SKILL,
        (
            "L'état du plan est la forge : aucune copie locale du corps. La prochaine case se lit"
            " par le script, le bloc courant dans le corps (§2), et chaque mise à jour est un"
            " fichier de paires que le script applique au corps courant, puis relit"
        ),
    ),
    "7b2-execution-qa-repli-markdown": (
        EXECUTION_QA_SKILL,
        "En mode de repli markdown, le fichier du plan est l'état, lu et édité en place",
    ),
    "7b2-execution-qa-prochaine-case": (
        EXECUTION_QA_SKILL,
        (
            "`python .claude/skills/cycle-pr/scripts/ecriture-relue.py checkbox next <plan>` rend le"
            " titre de son bloc, puis sa ligne : la première case `- [ ]` qui ne porte ni `🔴`, ni"
            " ` — BLOQUÉ`, ni ` — accepté` (§3, étape 4, et §4). En mode de repli markdown, la"
            " première case `- [ ]` du fichier qui ne porte aucune de ces marques, lue par `Read`."
            " Sans case en attente, passer au §6."
        ),
    ),
    "7b2-execution-qa-bloc-lu-par-la-session": (
        EXECUTION_QA_SKILL,
        (
            "la session le lit elle-même dans le corps, une fois par bloc, borné : ses titres par"
            ' `gh issue view <plan> --json body -q .body | grep -n "^## "`, puis sa plage par'
            ' `gh issue view <plan> --json body -q .body | sed -n "<début>,<fin>p"`. Elle y lit'
            " chaque case, son type — **Commande** ou **Observation**, écrit dans le plan"
            " (`plan-qa/references/gabarit-plan-qa.md`, « Types de case ») — et son état."
        ),
    ),
    "7b2-execution-qa-arbre-au-releveur": (
        EXECUTION_QA_SKILL,
        (
            "au `releveur` (« Délégation »), une fois par bloc, pas une fois par case :"
            " `git status --short`, `git log -10 --oneline`, et les fichiers que les cases du bloc"
            " nomment"
        ),
    ),
    "7b2-execution-qa-travail-preserve": (
        EXECUTION_QA_SKILL,
        "Préserver les changements de l'utilisateur ; ne jamais annuler du travail sans rapport.",
    ),
    "7b2-execution-qa-reprise": (
        EXECUTION_QA_SKILL,
        (
            "les cases `🔴 BUG #N` dont l'issue est fermée par une PR"
            " (`closedByPullRequestsReferences` non vide) se rejouent (§4, option (c)) ; une issue"
            " fermée sans PR — wontfix, doublon — ne se rejoue pas. Les cases `🔴 PR #<M>` — la"
            " petite PR d'un correctif évident (§4) — se rejouent une fois leur PR mergée. La"
            " session les trouve dans le corps (`gh issue view <plan> --json body -q .body | grep"
            " -nE \"🔴 (BUG|PR) #\"`) ; l'état de chaque issue, et la PR qui l'a fermée, sont un relevé"
            " du `releveur` (`gh issue view <N> --json state,closedByPullRequestsReferences`), comme"
            " l'état de chaque petite PR (`gh pr view <M> --json state,mergedAt`). Passée, la ligne"
            " entière devient `- [x] <texte de la case> — corrigé par #<PR>, <date>`, **sans**"
            " `🔴 BUG #N` ni `🔴 PR #<M>`."
        ),
    ),
    "7b2-execution-qa-commande-au-releveur": (
        EXECUTION_QA_SKILL,
        (
            "**Commande** — au `releveur` (« Délégation ») : les cases Commande qui se suivent dans"
            " le bloc partent dans un seul brief."
        ),
    ),
    "7b2-execution-qa-observation-en-dialogue": (
        EXECUTION_QA_SKILL,
        (
            "**Observation** — le dialogue avec le mainteneur : les clics UI ou l'action exacts,"
            " l'attendu énoncé avant qu'il ne les exécute"
        ),
    ),
    "7b2-execution-qa-resultats-selon-le-type": (
        EXECUTION_QA_SKILL,
        (
            "**Examiner les résultats observés** — le relevé du `releveur`, ou ce que rapporte le"
            " mainteneur."
        ),
    ),
    "7b2-execution-qa-pas-de-preuve-inutile": (
        EXECUTION_QA_SKILL,
        "Ne pas demander de preuve qui ne change pas la décision.",
    ),
    "7b2-execution-qa-verdict-en-paire": (
        EXECUTION_QA_SKILL,
        (
            "**Décider de la case** — chaque verdict s'écrit en paire dans un fichier que le script"
            " n'a pas encore appliqué (étape 5), sauf l'échec, dont la paire part seule (§4,"
            " étape 1)"
        ),
    ),
    "7b2-execution-qa-accepte": (
        EXECUTION_QA_SKILL,
        (
            "**Accepté** → un écart observé que le mainteneur accepte : laisser `- [ ]`, ajouter"
            " ` — accepté : <décision>, <date>`. La case ne passe pas, elle est réglée :"
            " `checkbox next` ne la rend plus."
        ),
    ),
    "7b2-execution-qa-patch-par-paires": (
        EXECUTION_QA_SKILL,
        (
            "une paire par case décidée, dans un fichier, appliquée par"
            " `python .claude/skills/cycle-pr/scripts/ecriture-relue.py checkbox patch <plan>"
            " --paires <fichier>`"
        ),
    ),
    "7b2-execution-qa-refus-arrete": (
        EXECUTION_QA_SKILL,
        (
            "Un refus sur une ancienne ligne introuvable ou en double est une édition concurrente :"
            " rien n'est écrit — s'arrêter et le dire au mainteneur, avec la ligne la plus proche"
            " que le script nomme."
        ),
    ),
    "7b2-execution-qa-commentaire-par-la-session": (
        EXECUTION_QA_SKILL,
        (
            "rassemblée dans un fichier par le `releveur` : la session le rédige"
            " (`references/gabarit-commentaire-phase.md`) et le publie elle-même par"
            " `python .claude/skills/cycle-pr/scripts/ecriture-relue.py comment <plan> --body-file"
            " <fichier>`"
        ),
    ),
    "7b2-execution-qa-echec-annote-et-intake-ecrit": (
        EXECUTION_QA_SKILL,
        (
            "Annoter la ligne ` 🔴 needs-issue — <résumé sur une ligne>`, par une paire appliquée"
            " tout de suite, seule dans son propre fichier — celui des autres verdicts attend la"
            " fin du bloc (§3, étape 5) —, pour que l'échec soit visible sur l'issue."
            " 2. **Écrire** l'intake de l'échec avec `references/gabarit-intake-echec.md` — les"
            " champs sans contenu supprimés, pas laissés vides —, dans un fichier du scratchpad de"
            " la session, jamais dans l'arbre de la campagne (§3, étape 6), et le publier en"
            " commentaire de l'issue du plan : `python"
            " .claude/skills/cycle-pr/scripts/ecriture-relue.py comment <plan> --body-file"
            " <intake>`. Son URL se compose de l'`id` que rend la sortie :"
            " `https://github.com/<owner>/<repo>/issues/<plan>#issuecomment-<id>`. En mode de"
            " repli markdown, l'intake est un fichier hors de l'arbre de la campagne et de tout"
            " worktree éphémère, et son chemin tient lieu d'URL."
        ),
    ),
    "7b2-execution-qa-consigner-dans-une-session-distincte": (
        EXECUTION_QA_SKILL,
        (
            "**(a) Consigner maintenant** — dans une session `bug-vers-issue` distincte, que cette"
            " session démarre dans le tour où le mainteneur choisit (a)"
        ),
    ),
    "7b2-execution-qa-prompt-de-consignation": (
        EXECUTION_QA_SKILL,
        (
            "prompt `/bug-vers-issue #<plan> <ancre de la case> <URL de l'intake>`, la forme de son"
            " `argument-hint`"
        ),
    ),
    "7b2-execution-qa-un-seul-auteur": (
        EXECUTION_QA_SKILL,
        (
            "Le marqueur `🔴 BUG #N` et l'Index des constats, ou la case que réécrit une autre"
            " classe, la session `bug-vers-issue` les patche elle-même (ses étapes 1 et 7) : cette"
            " session ne les écrit pas, un seul auteur. La QA reprend dans cette session sur son"
            " message « terminé — <livrable> » (`sessions-liees.md`, « Fin de travail »), jamais sur"
            " sa fin de tour."
        ),
    ),
    "7b2-execution-qa-reporter": (
        EXECUTION_QA_SKILL,
        "**(b) Reporter** — laisser `🔴 needs-issue`, continuer la QA, consigner plus tard en lot.",
    ),
    "7b2-execution-qa-correction-hors-de-la-qa": (
        EXECUTION_QA_SKILL,
        (
            "**(c) Faire corriger** — la correction n'a jamais lieu dans cette session : (a)"
            " d'abord, qui qualifie ; elle passe ensuite par `cycle-pr`, dans sa propre session —"
            " une petite PR sans issue pour un correctif évident — la case marquée ` 🔴 correctif"
            " évident — …` par `bug-vers-issue`, puis ` 🔴 PR #<M>` par la session de la petite PR"
            " à sa draft (`cycle-pr` Étape 2) —, l'issue consignée pour un défaut à étudier"
            " (`references/standard-correction-bug.md`) ; la case se rejoue à la reprise"
            " (§2), jamais dans la suite du contexte qui a corrigé."
        ),
    ),
    "7b2-execution-qa-termine-accepte": (
        EXECUTION_QA_SKILL,
        (
            "est `[x]` (ou explicitement ` — N/A : <raison>`), ou laissée `[ ]` avec ` — accepté :"
            " <décision>, <date>`. - Vérifier que chaque constat bloquant a un lien `🔴 BUG #N`"
            " (consigné) ou `🔴 PR #<M>` (petite PR), un ` — corrigé par #<PR>, <date>` (repris,"
            " §2) ou une annotation"
            " ` — accepté : <décision>, <date>`. - Faire relancer par le `releveur` les commandes"
            " finales listées dans le plan, après toute correction"
            " mergée. - Appliquer les dernières paires, dans un fichier neuf (§3, étape 5) : aucune"
            " décision ne reste hors de l'issue."
        ),
    ),
    "7b2-execution-qa-decision-ou-accepte": (
        EXECUTION_QA_SKILL,
        (
            "` — Décision : <politique choisie>, <date>` si la case passe, ` — accepté : <décision>,"
            " <date>` si l'écart est accepté sans qu'elle passe (§3, étape 4)."
        ),
    ),
    "7b2-execution-qa-code-jamais-dans-cette-session": (
        EXECUTION_QA_SKILL,
        (
            "Un changement de code qu'exige la politique choisie ne se fait jamais dans cette"
            " session : c'est une tâche séparée — consignée (§4, option (a)), corrigée par"
            " `cycle-pr` —, pas une partie du cochage de la case."
        ),
    ),
    "7b2-execution-qa-passe-finale": (
        EXECUTION_QA_SKILL,
        (
            "porte une annotation explicite de non-passage (` — N/A`, ` — BLOQUÉ`, `🔴`,"
            " ` — accepté`)."
        ),
    ),
    "7b2-execution-qa-passe-finale-preuve-patch-index": (
        EXECUTION_QA_SKILL,
        (
            "rassemblée par le `releveur`, est dans un commentaire de synthèse de phase publié par"
            " `comment`, pas entassée en ligne. - [ ] Chaque échec a un lien `🔴 BUG #N` ou"
            " `🔴 PR #<M>`, un ` — corrigé par #<PR>`, OU une annotation reporté / accepté. - [ ] Le"
            " patch du bloc"
            " est appliqué et relu par le"
            " script ; aucune paire ne reste à appliquer. - [ ] L'Index des constats, qu'écrivent"
            " les sessions `bug-vers-issue`, porte chaque bug consigné dans cette phase."
        ),
    ),
    "7b2-execution-qa-erreur-consigner-par-defaut": (
        EXECUTION_QA_SKILL,
        (
            "| Auto-invoquer bug-vers-issue sur un échec | Toujours proposer les trois options"
            " d'abord. Mise en avant par défaut = (a) consigner. |"
        ),
    ),
    "7b2-execution-qa-erreur-patch-a-la-main": (
        EXECUTION_QA_SKILL,
        (
            "| Patcher le corps à la main, ou depuis une copie locale | Une paire par case,"
            " appliquée au corps courant par `checkbox patch --paires` — voir"
            " `references/patch-checkbox-gh.md`. | | Écrire `🔴 BUG #N` ou l'Index des constats"
            " depuis cette session | La session `bug-vers-issue` les écrit, seule (§4, option (a)). |"
        ),
    ),
    "7b2-execution-qa-erreur-jamais-corriger": (
        EXECUTION_QA_SKILL,
        (
            "| Corriger un bug dans la session de QA | Jamais : (a) qualifie ; la correction passe"
            " par `cycle-pr`, dans sa propre session, en petite PR ou sur l'issue consignée (c). |"
        ),
    ),
    "7b2-commentaire-phase-publie-par-la-session": (
        COMMENTAIRE_PHASE_REF,
        (
            "La session le rédige et le publie elle-même : `python"
            " .claude/skills/cycle-pr/scripts/ecriture-relue.py comment <plan> --body-file"
            " <commentaire.md>`, relu sous l'`id` publié. La preuve lourde — commandes, lignes BD,"
            " logs — vient du fichier où le `releveur` l'a rassemblée"
        ),
    ),
    "7b2-intake-ecrit-et-consomme-en-argument": (
        INTAKE_ECHEC_REF,
        (
            "L'intake s'**écrit** : en commentaire de l'issue du plan, publié par `comment <plan>"
            " --body-file` depuis un fichier du scratchpad de la session, jamais de l'arbre de la"
            " campagne (`SKILL.md` §4, étape 2), ou, en mode de repli markdown, dans un fichier hors"
            " de l'arbre de la campagne et de tout worktree éphémère. La session `bug-vers-issue`"
            " distincte qui le consomme le reçoit en argument — son URL ou son chemin — quand"
            " l'utilisateur choisit l'option (a) « consigner maintenant » : elle ne lit rien"
            " d'autre de la session de QA."
        ),
    ),
    "7b2-patch-checkbox-etat-a-la-forge": (
        PATCH_CHECKBOX_REF,
        (
            "L'état du plan est la forge : ni copie locale du corps, ni paire gardée hors d'un"
            " fichier — chaque mise à jour est un fichier de paires que `ecriture-relue.py` applique"
            " au corps courant, puis relit."
        ),
    ),
    "7b2-patch-checkbox-regle-fondamentale": (
        PATCH_CHECKBOX_REF,
        (
            "**Faire correspondre par texte de ligne exact, pas par index. Faire remonter un"
            " avertissement si la ligne que tu comptais mettre à jour a changé.** Le script lit le"
            " corps courant au moment d'écrire : aucune lecture à refaire avant le patch."
        ),
    ),
    "7b2-patch-checkbox-fichier-de-paires": (
        PATCH_CHECKBOX_REF,
        (
            "une paire `(ancienne_ligne, nouvelle_ligne)` : une ligne `< <ancienne>`, puis une ligne"
            " `> <nouvelle>`, dans un fichier UTF-8 du scratchpad de la session, jamais dans"
            " l'arbre de la campagne, dont `SKILL.md` §2 préserve le `git status`."
        ),
    ),
    "7b2-patch-checkbox-ancienne-lue-par-la-session": (
        PATCH_CHECKBOX_REF,
        (
            "L'ancienne ligne se copie de la lecture du bloc que la session a faite elle-même"
            " (`SKILL.md` §2). Le format exact, ses refus et son rejeu sont le contrat du script —"
            " `python .claude/skills/cycle-pr/scripts/ecriture-relue.py --help` —, qu'on ne recopie"
            " pas ici."
        ),
    ),
    "7b2-patch-checkbox-titres-cites-par-bug-vers-issue": (
        PATCH_CHECKBOX_REF,
        (
            "2. Correspondance par ligne complète Appliquer la substitution par **correspondance"
            " exacte de ligne complète**."
        ),
    ),
    "7b2-patch-checkbox-editions-concurrentes": (
        PATCH_CHECKBOX_REF,
        "3. Détecter les éditions concurrentes Pour chaque paire, dans le corps courant :",
    ),
    "7b2-patch-checkbox-le-script-tient-les-regles": (
        PATCH_CHECKBOX_REF,
        (
            "Le script tient ces règles : il valide toutes les paires avant la première écriture, et"
            " refuse sans rien écrire en nommant la ligne la plus proche, ou le double."
        ),
    ),
    "7b2-patch-checkbox-applique-par-la-session": (
        PATCH_CHECKBOX_REF,
        (
            "Appelé par la session elle-même. Un refus (§3) ou une relecture non conforme :"
            " s'arrêter et le dire au mainteneur."
        ),
    ),
    "7b2-patch-checkbox-cadence": (
        PATCH_CHECKBOX_REF,
        (
            "Patcher à la fin d'une phase ou d'un bloc par issue (ou à la fin d'un sous-groupe"
            " significatif au sein d'un bloc long). Ne pas patcher après chaque bascule de case —"
            " cela gonfle l'historique de l'issue et augmente la surface de risque d'édition"
            " concurrente. Exception : la paire d'un échec, appliquée tout de suite, seule dans son"
            " propre fichier (`SKILL.md` §4, étape 1). Pour un bloc de longue durée, patcher"
            " périodiquement de toute façon"
        ),
    ),
    "7b2-patch-checkbox-repli-sans-script": (
        PATCH_CHECKBOX_REF,
        (
            "Utiliser l'outil `Edit` avec la même règle de correspondance exacte de ligne (§2 et"
            " §3). - Pas de script : le fichier est local."
        ),
    ),
    "7b2-patch-checkbox-ce-qu-il-ne-prouve-pas": (
        PATCH_CHECKBOX_REF,
        (
            "il ne verrouille rien : une édition faite par un tiers entre sa lecture et son écriture"
            " est écrasée — est écrit dans sa docstring, « Ce qu'il ne prouve pas » (`--help`),"
            " seule source."
        ),
    ),
    "7b2-correction-jamais-dans-la-qa": (
        CORRECTION_BUG_REF,
        (
            "La session de QA ne corrige jamais : un échec se qualifie (`SKILL.md` §4, option (a)),"
            " et sa correction passe par `cycle-pr`, dans sa propre session, sur l'issue consignée"
            " ou, correctif évident, sur une petite PR sans issue (option (c)). Ce standard vaut"
            " pour cette session `cycle-pr` quand elle corrige un bug trouvé en QA."
        ),
    ),
    "7b2-correction-reprise-dans-une-session-de-qa": (
        CORRECTION_BUG_REF,
        (
            "La case ne se rejoue pas dans la session qui a corrigé : elle se rejoue dans une"
            " session de QA neuve, démarrée sur le numéro du plan une fois la correction mergée,"
            " dont le §2 trouve la case (`SKILL.md` §2, « La reprise »). Passée, la ligne entière"
            " devient `- [x] <texte de la case> — corrigé par #<PR>, <date>`, **sans**"
            " `🔴 BUG #N` ni `🔴 PR #<M>`."
        ),
    ),
    # Passe 1 de relecture de la PR #159 (2026-10-26) : **15** moitiés restrictives ajoutées à la
    # prose, par la forme (`git diff -U0 --word-diff=plain d99e9a8 60df616 --
    # .claude/skills/execution-qa .claude/skills/plan-qa`), toutes épinglées — ci-dessous, ou dans l'entrée du lot qu'elle met
    # à jour. I1 : un fichier de paires rejoué après que la session `bug-vers-issue` a réécrit
    # `🔴 needs-issue` en `🔴 BUG #N` est refusé en entier, ses paires valides comprises, sur une
    # « ligne la plus proche » qui nomme une autre case quand celle-ci ressemble plus — mesuré le
    # 2026-10-26 par `replace_lines` sur un bloc de trois cases. Classe : un site d'`execution-qa`
    # qui applique un fichier de paires. Dénombrement par la forme du geste (obs 139), écrit avant
    # le correctif, sur `d99e9a8` — `checkbox patch`, « paire », « patch » dans ses cinq fichiers,
    # plus la reprise que le brief de la passe nomme : **16** sites. **6** exposés au rejeu, une
    # épingle chacun, qui prescrit le fichier neuf — `SKILL.md` §3, étape 4 (« le fichier du
    # bloc », où le cleanup holistique a trouvé la paire d'échec encore admise,
    # `7b2-execution-qa-verdict-en-paire`), étape 5 (muette sur le réemploi,
    # `7b2-execution-qa-un-fichier-par-application`), §4, étape 1 (la paire d'échec, appliquée par
    # l'étape 5, donc dans le fichier du bloc, `7b2-execution-qa-echec-annote-et-intake-ecrit`), §6
    # (« le dernier patch », `7b2-execution-qa-termine-accepte`) ; `patch-checkbox-gh.md` §1 (muet,
    # `7b2-patch-checkbox-un-fichier-par-application`), §5 (la cadence par bloc, sans l'exception
    # du §4, `7b2-patch-checkbox-cadence`). **2** exposés par renvoi seulement, sans épingle
    # propre — la reprise, `SKILL.md` §2 et `standard-correction-bug.md`, quand elle revenait à la
    # session de la campagne réveillée, son fichier de bloc en main : fermée par l'étape 5 et par
    # la session neuve (m3). **8** indemnes : `SKILL.md` « Délégation » (nomme l'outil), §1 et
    # l'en-tête de `patch-checkbox-gh.md` (« chaque mise à jour est un fichier »), « Passe finale »
    # (vérifie, n'applique rien), « Erreurs courantes » (l'outil contre le patch à la main) ;
    # `patch-checkbox-gh.md` §3 (le refus, qui est le symptôme), §4 (applique le fichier que §1
    # écrit), « Mode de repli markdown » (`Edit` relit le fichier à chaque geste).
    "7b2-execution-qa-un-fichier-par-application": (
        EXECUTION_QA_SKILL,
        (
            "(`references/patch-checkbox-gh.md`). Un fichier par application : une paire appliquée"
            " ne se rejoue pas, et les verdicts suivants vont dans un fichier neuf."
        ),
    ),
    "7b2-patch-checkbox-un-fichier-par-application": (
        PATCH_CHECKBOX_REF,
        (
            "Un fichier par application : une paire appliquée ne se rejoue pas, et les verdicts"
            " suivants vont dans un fichier neuf. Entre deux applications, une ligne écrite peut"
            " changer — la session `bug-vers-issue` réécrit `🔴 needs-issue` en `🔴 BUG #N` — et le"
            " rejeu d'une paire qui la porte fait refuser le fichier entier, sur une « ligne la plus"
            " proche » qui peut nommer une autre case."
        ),
    ),
    # Même passe, m4 : un fichier qu'écrit la campagne dans son arbre salit le `git status` que
    # `SKILL.md` §2 fait préserver. Population, quatre fichiers : les paires, la preuve lourde du
    # `releveur`, le commentaire de phase, l'intake. La précision est là où chacun s'écrit —
    # `patch-checkbox-gh.md` §1 (`7b2-patch-checkbox-fichier-de-paires`), `SKILL.md` §3, étape 6,
    # pour la preuve et le commentaire (ci-dessous), §4, étape 2, et `gabarit-intake-echec.md` pour
    # l'intake (`7b2-execution-qa-echec-annote-et-intake-ecrit`,
    # `7b2-intake-ecrit-et-consomme-en-argument`) ; l'intake du mode de repli, que consomme une
    # session ultérieure, reste hors de tout worktree éphémère, et sort de l'arbre de la campagne.
    "7b2-execution-qa-fichiers-hors-de-l-arbre": (
        EXECUTION_QA_SKILL,
        (
            "Ces deux fichiers, la preuve et le commentaire, s'écrivent dans le scratchpad de la"
            " session, jamais dans l'arbre de la campagne : le §2 en préserve le `git status`."
        ),
    ),
    # Même passe, constat 4 de la passe mécanique : le script n'a pas de forçage.
    "7b2-patch-checkbox-introuvable-en-paire-neuve": (
        PATCH_CHECKBOX_REF,
        (
            "Demander s'il faut sauter cette mise à jour, l'écrire en une paire neuve sur la ligne"
            " actuelle, ou abandonner."
        ),
    ),
    # Lot 8b de #134 (2026-10-26) : `audit-spec-ui` prend son chemin en argument et nomme ses
    # exécutants. Une entrée par règle écrite — argument, `description`, « Délégation » (jugement,
    # chaque délégation, D-12), arrêt sans chemin, renvoi de l'étape qui agit, arrêt avant les
    # corrections et sa case — et par moitié restrictive (obs 126) : par la forme, sur les lignes
    # ajoutées du skill, 9 — 3 « aucune », 2 « jamais », « ne … ni », « n'… que », « garde »,
    # « requis » — et 7 « la session » qui agit, toutes épinglées et vues rouges par `mutation.py` ;
    # l'annonce de l'arrêt en tête de « Avant de livrer », doublon de sa case, retirée au cleanup
    # holistique. La liste de `hors-scope.md` reçoit `audit-spec-ui`
    # (`6b2-hors-scope-nomme-contradiction`). Gardés ailleurs : la délégation (D5),
    # `SKILLS_SANS_ECRITURE_GH_DIRECTE`, `ECRITURE_RELUE_SANS_OBJET`, `RETIRES_DU_CONTEXTE_VIVANT`.
    "8b-audit-spec-ui-argument": (AUDIT_SPEC_UI_SKILL, "[chemin du document à auditer — requis]"),
    "8b-audit-spec-ui-description": (
        AUDIT_SPEC_UI_SKILL,
        "puis, après le go du mainteneur sur le rapport, appliquer les corrections",
    ),
    "8b-audit-spec-ui-jugement": (
        AUDIT_SPEC_UI_SKILL,
        (
            "La session garde le jugement : la déclaration d'autorité et le périmètre (étapes 0.2"
            " et 0.3), les constats de goût et de conception, le choix de chaque correction, le"
            " rapport, l'arrêt avant les corrections."
        ),
    ),
    "8b-audit-spec-ui-inventaire": (AUDIT_SPEC_UI_SKILL, "(étape 0.1), rendu dans un fichier"),
    "8b-audit-spec-ui-propagation-et-residus": (
        AUDIT_SPEC_UI_SKILL,
        "la propagation — chaque valeur d'origine cherchée dans tout le corpus — et les résidus",
    ),
    "8b-audit-spec-ui-executant-passes": (
        AUDIT_SPEC_UI_SKILL,
        "**`executant`** — les six passes mécaniques, sur le chemin reçu et l'inventaire",
    ),
    "8b-audit-spec-ui-executant-edition": (
        AUDIT_SPEC_UI_SKILL,
        "et ne juge ni ne corrige ; puis l'édition des corrections que la session a choisies",
    ),
    "8b-audit-spec-ui-correction-par-une-pr": (
        AUDIT_SPEC_UI_SKILL,
        (
            "une spec versionnée dans un dépôt se corrige par une PR, portée par la session qui a"
            " décidé, jamais par un commit direct sur le trunk (D-12 de #134) : dans une session"
            " PR, la correction entre dans sa PR ; hors PR, la session l'ouvre, la relit et la"
            " merge au go du mainteneur, au déroulé de `triage/hors-scope.md` (« Quand écrire »,"
            " étapes 5 et 6). Une spec hors dépôt se corrige sur place, sans commit."
        ),
    ),
    "8b-audit-spec-ui-arret-sans-chemin": (
        AUDIT_SPEC_UI_SKILL,
        "**Sans chemin, la session s'arrête et demande le chemin au mainteneur** — jamais une spec",
    ),
    "8b-audit-spec-ui-etape-0-1": (AUDIT_SPEC_UI_SKILL, "**Inventorier** — le `releveur`"),
    "8b-audit-spec-ui-passes": (AUDIT_SPEC_UI_SKILL, "L'`executant` (« Délégation ») les déroule"),
    "8b-audit-spec-ui-aucune-correction-avant-le-go": (
        AUDIT_SPEC_UI_SKILL,
        "**aucune correction ne part avant son go sur le rapport**",
    ),
    "8b-audit-spec-ui-go-partiel": (AUDIT_SPEC_UI_SKILL, "le go peut n'en retenir qu'une partie"),
    "8b-audit-spec-ui-edition": (AUDIT_SPEC_UI_SKILL, "**Édition** — l'`executant` applique"),
    "8b-audit-spec-ui-propagation": (AUDIT_SPEC_UI_SKILL, "le `releveur` cherche la valeur"),
    "8b-audit-spec-ui-propagation-retenue": (
        AUDIT_SPEC_UI_SKILL,
        "celles que la session retient repartent à l'`executant`",
    ),
    "8b-audit-spec-ui-residus": (AUDIT_SPEC_UI_SKILL, "**Résidus** — le `releveur` re-cherche"),
    "8b-audit-spec-ui-reste": (AUDIT_SPEC_UI_SKILL, "la session vérifie qu'il n'en reste aucune"),
    "8b-audit-spec-ui-case-de-l-arret": (
        AUDIT_SPEC_UI_SKILL,
        "aucune correction partie avant son go sur le rapport",
    ),
    # Lot 8b de #134 (2026-10-26) : `init-projet` nomme ses exécutants et fait ses gestes de dépôt
    # par script. Une entrée par règle écrite — « Délégation », un paragraphe par main, D-12 en
    # reconfiguration, copie non rejouée, ordre copie → fusion, barre finale, clé au mainteneur,
    # sessions distinctes des étapes 11 et 13 et de la « Note » —, par geste qui nomme sa
    # sous-commande (8) et par délégation à l'étape qui agit ; et par moitié restrictive (obs 126) :
    # par la forme, sur les lignes ajoutées du skill, 32 — 10 « ne … pas | rien | plus »,
    # 4 « jamais », 4 « refus… », 3 « sinon », 3 « sans », 2 « hors », « garde », « reste à »,
    # « restent au », « aucune », « pas de », « tant que » —, dont 2 sans portée restrictive
    # (`hors-scope.md`, « projet sans code »), et 1 reprise d'une ligne réécrite (« Ne rien
    # inventer en silence »), épinglée au cleanup holistique : toutes dans une phrase épinglée et
    # vues rouges par `mutation.py` (65 mutations au premier jet, 2 au cleanup holistique, toutes
    # rouges). La liste de `hors-scope.md` reçoit `init-projet`
    # (`6b2-hors-scope-nomme-contradiction`). Gardés ailleurs : la délégation (D5),
    # `SKILLS_SANS_ECRITURE_GH_DIRECTE` — les deux `gh pr ready` devenus la sortie du draft —, le
    # renvoi au script (`cites_ecriture_relue`, forme du skill voisin de `SCRIPT_REFERENCE`),
    # `use_worktree` à chaque session proposée (`USE_WORKTREE_EXPLICITE`).
    "8b-init-projet-reconfiguration-par-une-pr": (
        INIT_PROJET_SKILL,
        (
            "Ses écritures de dépôt partent **par une PR**, portée par la session qui a décidé,"
            " jamais par un commit direct sur le trunk (D-12 de #134) : la session l'ouvre, la"
            " relit et la merge au go du mainteneur, au déroulé de `triage/hors-scope.md`"
            " (« Quand écrire », étapes 5 et 6)."
        ),
    ),
    "8b-init-projet-copie-non-rejouee": (
        INIT_PROJET_SKILL,
        (
            "La copie de l'étape 7 ne se rejoue pas : `copie` refuse dès qu'une cible"
            " diffère de sa source — `settings.json` fusionné, `CLAUDE.md` finalisé."
        ),
    ),
    "8b-init-projet-dialogue-a-la-session": (
        INIT_PROJET_SKILL,
        (
            "La session garde le dialogue avec le mainteneur — chemin du boilerplate, public ou"
            " privé, profil validé valeur par valeur, mapping de labels, skills publics à cocher"
            " —, le choix des valeurs et le récapitulatif. Le reste change de main :"
        ),
    ),
    "8b-init-projet-delegation-releveur": (
        INIT_PROJET_SKILL,
        (
            "**`releveur`** — l'inspection de l'étape 3, rendue en tableau pré-rempli dans un"
            " fichier ; à l'étape 7, l'empreinte et l'étiquette la plus précise de chaque action"
            " (`git ls-remote`), les valeurs de `package-ecosystem` lues dans la référence"
            " Dependabot, passage cité (`context7`), la vérification du runtime épinglé ; à"
            " l'étape 11, le verdict de chaque commande — code de sortie et sortie brute, dans un"
            " fichier. Il ne décide rien : ce qui compte reste à la session ;"
        ),
    ),
    "8b-init-projet-delegation-executant": (
        INIT_PROJET_SKILL,
        (
            "**`executant`** — la génération de chaque fichier, en tranche entièrement spécifiée"
            " par la session (valeurs validées, gabarit, empreintes relevées) :"
            " `.claude/pipeline.config.md` (étape 5), `ci.yml`, `dependabot.yml` et `.gitignore`"
            " (étape 7), `CLAUDE.md` finalisé (étape 9) ;"
        ),
    ),
    "8b-init-projet-delegation-scripts": (
        INIT_PROJET_SKILL,
        (
            "**scripts** — les gestes de dépôt, appelés par la session elle-même : un geste isolé"
            " coûte plus délégué (`CLAUDE.md`, « Orchestration »). En amorçage, les skills ne"
            " sont pas encore dans le projet : `amorcage.py` se lance par"
            " `python <répertoire de ce skill>/scripts/amorcage.py` — `depot init` (étape 2),"
            " `copie` (7), `valide` (7), `ignore` (7), `mcp` (10), `commit` (12) —,"
            " `ecriture-relue.py` par"
            " `python <répertoire de ce skill>/../cycle-pr/scripts/ecriture-relue.py` —"
            " `depot create` (2), `label create --mapping` (6). Le contrat de chacun est son"
            " `--help` ;"
        ),
    ),
    "8b-init-projet-delegation-sessions": (
        INIT_PROJET_SKILL,
        (
            "**sessions distinctes** — la première PR de code d'un projet sans code, une session"
            " `cycle-pr` (étape 11) ; `vers-prd` ou `vers-issues`, des sessions que l'étape 13"
            " propose, jamais enchaînées dans celle-ci ; protocole commun :"
            " `.claude/skills/cycle-pr/references/sessions-liees.md`."
        ),
    ),
    "8b-init-projet-depot-init": (
        INIT_PROJET_SKILL,
        (
            "Si le projet n'est pas un dépôt git : `amorcage.py depot init` (« Délégation ») ; le"
            " premier commit est celui d'amorçage (étape 12)."
        ),
    ),
    "8b-init-projet-depot-create": (
        INIT_PROJET_SKILL,
        (
            "Sinon, demander public ou privé, puis créer le dépôt et son remote `origin` :"
            " `ecriture-relue.py depot create <owner>/<repo> --private|--public`"
        ),
    ),
    "8b-init-projet-inspection-par-le-releveur": (
        INIT_PROJET_SKILL,
        (
            "**Ne rien inventer en silence.** Le `releveur` inspecte le repo (« Délégation ») et"
            " rend des valeurs pré-remplies, que la session fait corriger par l'utilisateur. Ce"
            " qui reste ambigu après inspection se **demande**."
        ),
    ),
    "8b-init-projet-mapping-en-fichier": (
        INIT_PROJET_SKILL,
        "Le mapping validé s'écrit dans un fichier JSON pour l'étape 6",
    ),
    # Passe 1 de la PR #162, m3 : des 4 fichiers de travail de l'amorçage, seul le mapping n'avait
    # pas de lieu — inspection et verdicts du `releveur` à `mktemp`, copie de `valide` en tempfile.
    "8b-init-projet-mapping-hors-de-l-arbre": (
        INIT_PROJET_SKILL,
        "Ce fichier vit **hors de l'arbre du projet**, dans un dossier temporaire",
    ),
    "8b-init-projet-config-par-l-executant": (
        INIT_PROJET_SKILL,
        (
            "L'`executant` (« Délégation ») le génère depuis ce gabarit et les valeurs validées ;"
            " la session le confirme"
        ),
    ),
    "8b-init-projet-gabarit-sortie-du-draft": (
        INIT_PROJET_SKILL,
        "corrigées avant la sortie du draft si elles dévient. Toute PR qui n'est pas l'œuvre",
    ),
    "8b-init-projet-label-create": (
        INIT_PROJET_SKILL,
        (
            "`ecriture-relue.py label create --mapping <fichier>` (« Délégation »), sur le fichier"
            " de l'étape 4, crée les labels absents du dépôt ; sa sortie dit ce qui a été créé, et"
            " nomme un label présent sous une autre couleur sans le modifier."
        ),
    ),
    "8b-init-projet-copie": (
        INIT_PROJET_SKILL,
        "`amorcage.py copie <boilerplate>` (« Délégation ») copie `template/`, hors `.github/`",
    ),
    "8b-init-projet-copie-puis-fusion": (
        INIT_PROJET_SKILL,
        (
            "**L'ordre est copie, puis fusion** : un `settings.json` déjà présent sous un autre"
            " contenu fait refuser la copie entière — le mettre de côté, copier, puis le fusionner"
            " à la main. Après la fusion, `copie` ne repasse plus : il refuserait sur ce fichier."
        ),
    ),
    "8b-init-projet-ci-par-l-executant": (
        INIT_PROJET_SKILL,
        "l'`executant` génère `.github/workflows/ci.yml`",
    ),
    "8b-init-projet-empreintes-par-le-releveur": (
        INIT_PROJET_SKILL,
        "Empreintes et étiquettes sont relevées par le `releveur`",
    ),
    "8b-init-projet-garde-sortie-du-draft": (
        INIT_PROJET_SKILL,
        (
            "une draft n'a aucun run, le premier part au passage en ready (`cycle-pr` Étape 5),"
            " puis chaque push en lance un"
        ),
    ),
    "8b-init-projet-dependabot-par-l-executant": (
        INIT_PROJET_SKILL,
        "Puis l'`executant` génère `.github/dependabot.yml`",
    ),
    "8b-init-projet-ecosysteme-cite-par-le-releveur": (
        INIT_PROJET_SKILL,
        "pas de mémoire — le `releveur` en cite le passage",
    ),
    "8b-init-projet-runtime-par-le-releveur": (
        INIT_PROJET_SKILL,
        "le `releveur` vérifie qu'aucune recette n'invoque le binaire nu d'un runtime épinglé",
    ),
    "8b-init-projet-valide": (
        INIT_PROJET_SKILL,
        "`amorcage.py valide <fichier> --schema vendor.github-workflows`",
    ),
    "8b-init-projet-gitignore-par-l-executant": (
        INIT_PROJET_SKILL,
        "L'`executant` le génère depuis les **chemins déclarés**",
    ),
    "8b-init-projet-ignore-et-barre-finale": (
        INIT_PROJET_SKILL,
        (
            "`amorcage.py ignore --exclus <chemin> … --suivis <chemin> …` sur une liste de chemins"
            " fabriqués depuis le profil : ceux qui doivent être exclus, et les lockfiles/sources"
            " qui doivent rester suivis ; **un dossier absent se nomme avec sa barre finale**"
            " (`node_modules/`) ou par un chemin qu'il contient. Un fichier de motifs ne se relit"
            " pas, il se teste."
        ),
    ),
    "8b-init-projet-skills-par-copie": (
        INIT_PROJET_SKILL,
        "`copie` (étape 7) a copié les skills de la pipeline",
    ),
    "8b-init-projet-claude-md-par-l-executant": (
        INIT_PROJET_SKILL,
        "l'`executant` (« Délégation »), sur les sections et le chemin que la session lui donne",
    ),
    "8b-init-projet-mcp": (
        INIT_PROJET_SKILL,
        (
            "`amorcage.py mcp context7 https://mcp.context7.com/mcp` (« Délégation ») : rien à"
            " faire si `claude mcp list` le liste déjà ; sinon il l'ajoute — transport HTTP"
            " distant, portée utilisateur, sans clé : suffisant, débit limité —, puis relit la"
            " liste. 2. Pour référence, la commande qu'il lance, puis celles qui restent au"
            " mainteneur :"
        ),
    ),
    "8b-init-projet-cle-au-mainteneur": (
        INIT_PROJET_SKILL,
        (
            "**ce geste reste au mainteneur, qui tape lui-même la commande** (`contraintes.md`,"
            " « Jamais d'information dérivée d'un secret »)."
        ),
    ),
    "8b-init-projet-verdict-par-le-releveur": (
        INIT_PROJET_SKILL,
        (
            "le `releveur` (« Délégation ») lance réellement `test` et chaque commande des"
            " « gates bloquants en CI » de la config, et rend le verdict de chacune — code de"
            " sortie et sortie brute — dans un fichier."
        ),
    ),
    "8b-init-projet-premiere-pr-de-code-distincte": (
        INIT_PROJET_SKILL,
        (
            "Cette première PR de code est une **session `cycle-pr` distincte** (« Délégation »)"
            " : celle-ci ne la mène pas."
        ),
    ),
    "8b-init-projet-commit": (
        INIT_PROJET_SKILL,
        (
            "`amorcage.py commit` (« Délégation ») refuse tant qu'un fichier suivi viole les"
            " règles d'ignore — `.gitignore` n'agit pas rétroactivement sur des fichiers déjà"
            " stagés — et les nomme tous : les sortir de l'index (`git rm --cached`), puis le"
            " relancer. Sinon il commite `chore: amorçage pipeline de dev`, puis relit."
        ),
    ),
    "8b-init-projet-prochaines-etapes-proposees": (
        INIT_PROJET_SKILL,
        (
            "que la session **propose** en sessions distinctes (« Délégation »), jamais"
            " enchaînées dans celle-ci."
        ),
    ),
    "8b-init-projet-note-s-arrete": (
        INIT_PROJET_SKILL,
        (
            "S'il est absent ou incomplet, le skill **s'arrête** et propose une session"
            " `init-projet` distincte (protocole :"
            " `.claude/skills/cycle-pr/references/sessions-liees.md`) — il ne l'enchaîne pas dans"
            " sa propre session."
        ),
    ),
    # Passe 1 de la PR #162, I1 — classe : une tranche confiée à l'`executant` par le lot, dont la
    # cible ne doit pas être commitée par lui. **Dénombrement, écrit avant le correctif**, par la
    # forme du geste (obs 139 ; `grep -n executant` des deux skills sur `41910a2` : 11 lignes, dont
    # la liste de fichiers de l'étape 7, hors classe) : **8** tranches, **7** fuyaient — les 5
    # générations d'`init-projet` en amorçage (le premier commit est l'étape 12 ; en
    # reconfiguration, la branche de la PR, D-12), l'édition et la propagation d'`audit-spec-ui`
    # hors dépôt (`git add` y sort en 128, « is outside repository », git 2.47.1, 2026-10-26 ; dans
    # un dépôt, la branche de la PR) ; indemnes, les six passes, qui ne rendent que des constats.
    "8b-init-projet-executant-sans-commit-en-amorcage": (
        INIT_PROJET_SKILL,
        "en amorçage **sans commit**, le premier commit étant `commit` (étape 12) ;",
    ),
    "8b-executant-init-projet-sans-commit-en-amorcage": (
        ".claude/agents/executant.md",
        "en amorçage **sans commit**, le premier commit étant celui d'amorçage, que la session fait",
    ),
    "8b-executant-hors-depot-sans-commit": (
        ".claude/agents/executant.md",
        "Une cible hors dépôt ne se commite pas, ni ce que ta mission dit **sans commit**.",
    ),
    # Le même lot y renvoie aussi les cinq autres skills qui lançaient `init-projet` sans
    # configuration (`LANCER_INIT_PROJET`) : une entrée par phrase neuve, « s'arrêter »
    # compris, et pour `cycle-pr` sa moitié « ne jamais deviner », sur une ligne réécrite.
    "8b-cycle-pr-sans-config-propose-init-projet": (
        CYCLE_PR_SKILL,
        (
            "Si le fichier est absent, s'arrêter et proposer une session `init-projet` distincte"
            " (`init-projet`, « Note pour les autres skills ») ; ne jamais deviner une commande."
        ),
    ),
    "8b-pr-paralleles-sans-config-propose-init-projet": (
        PR_PARALLELES_SKILL,
        "sinon s'arrêter et proposer une session `init-projet` distincte",
    ),
    "8b-triage-sans-config-propose-init-projet": (
        TRIAGE_SKILL,
        "sinon s'arrêter et proposer une session `init-projet` distincte",
    ),
    "8b-vers-issues-sans-config-propose-init-projet": (
        VERS_ISSUES_SKILL,
        "sinon s'arrêter et proposer une session `init-projet` distincte",
    ),
    "8b-vers-prd-sans-config-propose-init-projet": (
        VERS_PRD_SKILL,
        "sinon s'arrêter et proposer une session `init-projet` distincte",
    ),
    # Lot 7c de #134 (2026-10-27) : un échec se qualifie avant de se consigner, et un correctif
    # évident part en petite PR, sans issue — le barreau 3 de « Création d'issues en cours de
    # cycle ». Une entrée par phrase neuve, qui garde ses moitiés restrictives (obs 126) : par la
    # forme, sur les mots ajoutés de `bug-vers-issue` (`git diff -U0 --word-diff=plain`), 17 —
    # « aucune » ×3, « jamais », « ne … pas », « n'… que », « seul » ×2, « sans décision »,
    # « dans le doute » ×2, « avant toute », « s'arrête », « elle-même » ×2, « telle qu'écrite »
    # ×2 —, toutes épinglées, chaque épingle vue rouge par `mutation.py`. Gardés ailleurs : les
    # renvois numérotés aux barreaux (`RENVOIS_AUX_BARREAUX`), le worktree de la petite PR
    # (`USE_WORKTREE_EXPLICITE`).
    "7c-contraintes-barreau-du-correctif-evident": (
        CONTRAINTES_RULE,
        (
            "3. **un correctif évident** — visible à la lecture des lignes, sans décision de"
            " comportement — hors du périmètre de la PR courante → une **petite PR** par la"
            " **voie courte** de `cycle-pr`, sans issue ;"
        ),
    ),
    # Coupe prudente (audit du 2026-10-27, §5) : la voie courte remplace cinq étapes du cycle pour
    # un correctif évident borné ; l'épingle garde la liste des étapes remplacées, pas la prose.
    "voie-courte-remplace-cinq-etapes": (
        CYCLE_PR_SKILL,
        (
            "Elle **remplace** les Étapes 1, 2, 5, 7 et 8 ; les Étapes 3 et 6 s'appliquent telles"
            " quelles — 3.2 et 3.4 réduits au `lint` et au test ciblé —, la session codant"
            " elle-même (3.1), l'Étape 4 sous la forme du point 3."
        ),
    ),
    "voie-courte-conditions-d-entree": (
        CYCLE_PR_SKILL,
        (
            "dont le diff attendu tient en **≤ 50 lignes et ≤ 3 fichiers**, sans zone sensible ni"
            " surface visible (`.claude/pipeline.config.md`, « Périmètre ») et sans toucher"
            " `.claude/`, emprunte cette voie."
        ),
    ),
    "voie-courte-go-humain": (CYCLE_PR_SKILL, "puis go humain, puis"),
    "7c-cycle-pr-fumee-petite-pr-avant-le-brouillon": (
        CYCLE_PR_SKILL,
        (
            "puis propriétaire ouvert (une automatisation qu'on a fait taire se répare, elle ne se"
            " doublonne pas), puis petite PR pour un correctif évident, puis brouillon soumis au"
            " mainteneur"
        ),
    ),
    "7c-bug-vers-issue-description": (
        BUG_VERS_ISSUE_SKILL,
        (
            "Qualifie d'abord l'échec : attendu faux, environnement et correctif évident ne"
            " deviennent pas une issue."
        ),
    ),
    "7c-bug-vers-issue-consigne-le-seul-defaut-a-etudier": (
        BUG_VERS_ISSUE_SKILL,
        "le qualifier et, défaut à étudier, le consigner comme une issue GitHub",
    ),
    "7c-bug-vers-issue-principe": (
        BUG_VERS_ISSUE_SKILL,
        (
            "et elle n'existe que pour un défaut à étudier : l'échec se qualifie d'abord (étape 1)."
            " Toujours pré-publier, ne jamais publier en silence."
        ),
    ),
    "7c-bug-vers-issue-classe-a-la-session": (
        BUG_VERS_ISSUE_SKILL,
        "La session garde le jugement : la classe de l'échec,",
    ),
    "7c-bug-vers-issue-retest-au-releveur": (
        BUG_VERS_ISSUE_SKILL,
        (
            "le retest d'un échec d'environnement (étape 1), l'action rejouée telle qu'écrite,"
            " rendue OK ou KO avec sa sortie brute. Ce qui compte reste à la session"
        ),
    ),
    "7c-bug-vers-issue-case-par-le-script": (
        BUG_VERS_ISSUE_SKILL,
        "la réécriture d'une case ou de son marqueur (`checkbox patch --paires`, étape 1)",
    ),
    "7c-bug-vers-issue-demarre-la-petite-pr": (
        BUG_VERS_ISSUE_SKILL,
        "elle démarre la session `cycle-pr` de la petite PR d'un correctif évident (étape 1)",
    ),
    "7c-bug-vers-issue-qualifier-avant-toute-ecriture": (
        BUG_VERS_ISSUE_SKILL,
        (
            "**Qualifier.** La session elle-même, jamais un équipier, range l'échec dans **une**"
            " classe, preuve à l'appui, et la montre au mainteneur avec ce qu'elle écrira, avant"
            " toute écriture — même go qu'un brouillon."
        ),
    ),
    "7c-bug-vers-issue-dans-le-doute": (
        BUG_VERS_ISSUE_SKILL,
        "**Dans le doute : défaut à étudier.**",
    ),
    "7c-bug-vers-issue-une-paire-lue-par-la-session": (
        BUG_VERS_ISSUE_SKILL,
        (
            "Piloté par un plan, une sortie qui touche la case s'écrit en une seule paire —"
            " l'ancienne ligne lue par la session elle-même dans le corps courant, comme à"
            " l'étape 7 —, appliquée par `python .claude/skills/cycle-pr/scripts/ecriture-relue.py"
            " checkbox patch <plan> --paires <fichier>`."
        ),
    ),
    "7c-bug-vers-issue-attendu-faux": (
        BUG_VERS_ISSUE_SKILL,
        (
            "**Attendu faux** — preuve : la source que la case cite (critère `C<k>`, spec, texte"
            " même de la case) donne l'observé. Piloté par un plan : la ligne de la case réécrite"
            " par une paire, attendu corrigé et ` 🔴 needs-issue — …` retiré ; la session de QA la"
            " rejoue à sa reprise, où `checkbox next` la retrouve. Libre : dire au mainteneur"
            " pourquoi l'observé est juste. Aucune issue."
        ),
    ),
    "7c-bug-vers-issue-environnement": (
        BUG_VERS_ISSUE_SKILL,
        (
            "**Environnement** — preuve : l'intake ou un relevé nomme une cause hors du produit —"
            " outil introuvable, service arrêté, fichier verrouillé, réseau"
            " (`cycle-pr/references/tests.md`,"
            " « Échec d'outillage ≠ échec de code »). La cause levée, par le mainteneur s'il le"
            " faut, un `releveur` rejoue l'action de l'intake telle qu'écrite — le mainteneur, pour"
            " une case **Observation**. Reproduit : défaut à étudier. Non reproduit : aucune"
            " issue ; piloté par un plan, ` 🔴 needs-issue — …` retiré par une paire, et la case se"
            " rejoue à la reprise."
        ),
    ),
    # Passe 1 de la PR #163, I1 et I2 : la branche suit le prédicat du barreau, pas l'identité du
    # parent, et le propriétaire (barreau 2) précède la petite PR. Classe d'I1, par la forme du
    # geste (« démarrée par », « parent », « née d' » sur les lignes ajoutées du delta, obs 139),
    # écrite avant le correctif : **5** branches, **1** fuyait, celle-ci ; indemnes, les 3 du message
    # de fin, dont le prédicat est l'identité (`sessions-liees.md`, « Fin de travail »), et la draft
    # de `cycle-pr` Étape 2, conditionnée sur sa case. I3, puis I4 : écritures sur le corps d'une
    # issue tierce hors de `repercussions`, **2**, **2** fuyaient ; le propriétaire ouvert suit
    # désormais les étapes 2 à 7 — **0** écriture de ce genre dans le delta.
    "7c-bug-vers-issue-correctif-evident": (
        BUG_VERS_ISSUE_SKILL,
        (
            "**Correctif évident** — visible à la lecture des lignes, sans décision de"
            " comportement : l'attendu est déjà écrit (critère, spec, case) et le code le contredit"
            " lisiblement. La PR du parent encore ouverte, et le correctif y tient en moins d'un"
            " commit (« Création d'issues en cours de cycle », barreau 1) : il lui retourne, par le"
            " message de fin. Sinon, avant toute petite PR, la recherche du propriétaire de"
            " l'étape 3, collecte du `releveur` : si une issue ouverte possède le sujet, l'échec"
            " devient un défaut à étudier et suit les étapes 2 à 7, où l'étape 3 montre la"
            " correspondance au mainteneur. Une issue fermée n'est pas un propriétaire ; une automatisation qui possède le sujet"
            " se répare par la petite PR. Sans issue ouverte qui le possède, une petite PR par la"
            " voie courte de `cycle-pr` (barreau 3), dans sa propre session :"
        ),
    ),
    "7c-bug-vers-issue-correctif-evident-sans-issue": (
        BUG_VERS_ISSUE_SKILL,
        (
            "le prompt décrivant le correctif et, piloté par un plan, le plan et l'ancre de la"
            " case. Aucune issue ; piloté par un plan, ` 🔴 needs-issue — …` devient ` 🔴 correctif"
            " évident — <résumé>` par une paire."
        ),
    ),
    "7c-bug-vers-issue-defaut-a-etudier": (
        BUG_VERS_ISSUE_SKILL,
        "**Défaut à étudier** — tout le reste : les étapes 2 à 7, jusqu'à l'issue.",
    ),
    "7c-bug-vers-issue-sortie-sans-les-etapes-2-a-7": (
        BUG_VERS_ISSUE_SKILL,
        (
            "Hors défaut à étudier, la procédure s'arrête après cette sortie et, pour une session"
            " démarrée par une autre, son message de fin (après l'étape 7)."
        ),
    ),
    "7c-bug-vers-issue-erreur-consigner-sans-qualifier": (
        BUG_VERS_ISSUE_SKILL,
        (
            "| Consigner sans qualifier l'échec | Une classe prouvée d'abord (étape 1) : seul le"
            " défaut à étudier devient une issue ; dans le doute, défaut à étudier. |"
        ),
    ),
    # La petite PR en QA : `🔴 correctif évident — …`, puis `🔴 PR #<M>`, rejouée à la reprise.
    # Classe : un site qui énumère les états d'une case en échec. Dénombrement par la forme
    # (obs 139), écrit avant le correctif, `grep -n "BUG #"` des fichiers d'`execution-qa` et de
    # `plan-qa` : **8** sites, **6** fuyaient — `SKILL.md` « Délégation », §2, §4 (a), §6, « Passe
    # finale », `standard-correction-bug.md` —, mis à jour dans leurs entrées 7b2 ; indemnes,
    # « Erreurs courantes » (l'auteur de `🔴 BUG #N`) et `patch-checkbox-gh.md` (un exemple de
    # réécriture) ; plus la Phase Finale du gabarit, sans la forme, ci-dessous.
    "7c-execution-qa-qualifie-d-abord": (
        EXECUTION_QA_SKILL,
        (
            "Elle qualifie d'abord l'échec (son étape 1) : une issue ne part que pour un défaut à"
            " étudier."
        ),
    ),
    "7c-plan-qa-echecs-qualifies": (
        PLAN_QA_SKILL,
        (
            "les échecs trouvés pendant l'exécution sont qualifiés par `bug-vers-issue`, qui ne"
            " consigne en issue que le défaut à étudier."
        ),
    ),
    "7c-gabarit-plan-qa-petite-pr": (
        GABARIT_PLAN_QA_REF,
        (
            "chaque constat majeur → un lien vers son issue de bug consignée ou vers sa petite PR,"
            " ou une décision `reporté` explicite."
        ),
    ),
    "7c-cycle-pr-correctif-evident-sans-interrogatoire": (
        CYCLE_PR_SKILL,
        (
            "Un correctif évident — visible à la lecture, sans décision de comportement"
            " (`contraintes.md`, barreau 3) — n'a rien à interroger : sa qualification, écrite"
            " dans le body de la PR — draft, ou PR de la voie courte — avec sa preuve, en tient lieu."
        ),
    ),
    "7c-cycle-pr-marqueur-de-la-petite-pr": (
        CYCLE_PR_SKILL,
        (
            "Pour une draft née d'un échec de QA (case ` 🔴 correctif évident — …`), la session,"
            " une fois la draft ouverte, remplace ce marqueur par ` 🔴 PR #<M>` sur la case, par"
            " une paire"
            " (`python .claude/skills/cycle-pr/scripts/ecriture-relue.py checkbox patch <plan>"
            " --paires <fichier>`, `execution-qa/references/patch-checkbox-gh.md`) : c'est ce que"
            " lit la reprise de la QA."
        ),
    ),
}


@pytest.mark.parametrize(
    ("fichier", "phrase"),
    INVARIANTS_DU_CONTEXTE_COURT.values(),
    ids=INVARIANTS_DU_CONTEXTE_COURT.keys(),
)
def test_chaque_invariant_du_contexte_court_garde_sa_phrase(fichier: str, phrase: str) -> None:
    """Même lecture que les invariants des sessions liées : texte aux espaces normalisés."""
    assert phrase in texte_normalise(fichier), f"`{fichier}` ne porte plus « {phrase} »"


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


def sites_du_geste(geste: re.Pattern[str]) -> list[str]:
    """Le fichier de chaque bloc de prose des skills qui porte le geste, trié."""
    return sorted(
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in REPOSITORY_ROOT.glob(SKILL_PROSE)
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
# `repercussions` —, ou publient un brief neuf (`triage`, `brief-agent.md`). Le renvoi « Relire le
# corps — et le brief — juste avant d'écrire » de `repercussions`, sans le geste, nommait la
# lecture fautive : épinglé avec elle (`INVARIANTS_DU_CONTEXTE_COURT`).
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


# Ce que la session de dialogue ne garde plus, et ce qu'un équipier ne reçoit plus (critère 2b :
# « = 0 » sur `CLAUDE.md`, 2 au 2026-10-20 sur `81ae8c3`).
RETIRES_DE_L_ORCHESTRATION = ["cleanup pass, review avant merge", "contexte complet"]


@pytest.mark.parametrize("phrase", RETIRES_DE_L_ORCHESTRATION)
def test_l_orchestration_ne_rend_pas_ce_qu_elle_a_retire(phrase: str) -> None:
    """Vu rouge sur `81ae8c3`, où chacune est présente une fois."""
    assert not porte_la_forme("CLAUDE.md", phrase), f"`CLAUDE.md` porte encore « {phrase} »"


# Le contexte vivant que le lot 6b2 de #134 retire de `contradiction` et de `bug-vers-issue`
# (2026-10-25) : une source lue dans la conversation — la conversation, ses derniers tours,
# l'intake d'échec qui y est « capturé » —, la réouverture d'une issue, que `ecriture-relue.py`
# n'a pas, et la lecture sans lecteur nommé, ou par le `releveur`, d'un corps que l'étape 7 de
# `bug-vers-issue` ou l'étape 5 de `repercussions` réécrit (relecture de la PR #155, passe 1, I2 ;
# dénombrement : `REECRITURES_DE_CORPS`). `gh label create` est tenu par
# `SKILLS_SANS_ECRITURE_GH_DIRECTE`.
#
# **Population** de « conversation » et « derniers tours », par la forme, sur `ecae185`, base du
# lot — `git show ecae185:<fichier> | grep -n -i -E "conversation|derniers tours"` sur les cinq
# fichiers des deux skills : **8** formes, `contradiction` 4, `bug-vers-issue` 2,
# `collecte-contexte.md` 2 (titre §1, « ~10 derniers tours »), les deux gabarits 0. Au commit
# `57c049b`, la table en gardait 3, par leur phrase, et 5 fuyaient (relecture de la PR #155,
# passe 1, I1 ; classe : un échantillon déclaré inventaire, obs 127). « conversation » est donc
# gardé dans chacun des cinq fichiers, liste littérale (obs 80) tenue égale aux dossiers des deux
# skills. Le critère « 6a, 6b » du brief de #134 tolère une mention de dialogue avec le
# mainteneur ; il n'y en a aucune aujourd'hui, d'où le zéro : une mention ajoutée se reformule, ou
# entre dans une exemption nommée ici. Les autres formes, sur `ecae185` : « capturé » à 4 lignes
# (`bug-vers-issue` 3, `collecte-contexte.md` 1), « rouvrir » à 1. Chaque cas est rouge sur
# `ecae185`, sauf les gabarits, à 0, et l'ancienne phrase d'I2, entrée au commit `57c049b` :
# ceux-là sont vus rouges par mutation inverse. Les trois formes de `repercussions` sont rouges sur
# `a485d0a`.
#
# Le lot 7a (2026-10-26) y ajoute `plan-qa`, par le critère « 7a, 7b » du brief de #134 — « chaque
# occurrence restante est un dialogue ». **Population** sur `4b51a71`, base du lot, par la même
# commande sur ses quatre fichiers : **1** forme, `gabarit-plan-qa.md` (« Saisie d'échec », l'intake
# « capturé dans la conversation ») — une source, pas un dialogue ; les trois autres fichiers à 0.
# Même garde, un fichier par entrée : le gabarit rouge sur `e4e05db`, qui n'en touche pas la
# phrase, les trois autres vus rouges par mutation inverse. S'y ajoute la création du label qui
# manque, que `ecriture-relue.py` n'a pas, écrite en prose à l'étape 2 et dans « Sortie » — seule
# la commande de « Sortie » tombe sous `gh_writes` —, rouge sur `e4e05db`.
#
# Le lot 7b2 (2026-10-26) y ajoute `execution-qa`, par les critères « 7b » et « 7a, 7b » du même
# brief : l'intake « capturé dans la conversation », la copie de travail locale et la paire gardée
# « en mémoire » remplacés par un support écrit, la correction « en session » retirée.
# **Population** par la forme (obs 139) sur `ffbe52e`, base du lot —
# `git show ffbe52e:<fichier> | grep -n -i -F -e <forme> …` sur ses cinq fichiers, en lignes :
# « conversation » 2, `SKILL.md` §4 et `gabarit-intake-echec.md`, deux sources, aucun dialogue —
# les trois autres fichiers à 0 ; « capturer » 2, les mêmes ; « capturé » 1, `SKILL.md` (l'intake
# « capturée » de l'option (a)) — « captures d'écran », 2 lignes, est une preuve, pas la forme ;
# « /tmp/qa-plan » 4 (`SKILL.md` 1, `patch-checkbox-gh.md` 3) ; « copie de travail » 10 (8, 2) ;
# « re-récupér » 5 (2, 3) ; « pousser » 10 (5, 5) ; « repouss » 6, `SKILL.md` ; « push » 2 (1, 1) ;
# « en mémoire » 2, `patch-checkbox-gh.md` ; « en session » 7 (`SKILL.md` 3,
# `standard-correction-bug.md` 4). Une entrée par forme et par fichier qui la porte, plus
# « conversation » dans chacun des cinq fichiers : 22 entrées, toutes rouges sur `ffbe52e` sauf
# les trois « conversation » des fichiers à 0, vues rouges par mutation inverse.
#
# Le lot 8b (2026-10-26) y ajoute `audit-spec-ui`, dont l'objet audité sans argument était « la
# spécification en discussion dans la conversation » : il prend désormais un chemin, sans lequel
# la session s'arrête. **Population** sur `0c408db`, base du lot, par la forme —
# `git show 0c408db:<AUDIT_SPEC_UI_SKILL> | grep -n -i -E "conversation|en discussion"`, seul
# fichier du dossier : **2** lignes, l'`argument-hint` (« en discussion ») et l'étape 0 (« en
# discussion dans la conversation ») ; une entrée par forme, toutes deux rouges sur `0c408db`.
RETIRES_DU_CONTEXTE_VIVANT = {
    "contradiction-conversation": (CONTRADICTION_SKILL, "conversation"),
    "bug-vers-issue-conversation": (BUG_VERS_ISSUE_SKILL, "conversation"),
    "collecte-contexte-conversation": (COLLECTE_CONTEXTE_REF, "conversation"),
    "gabarit-issue-bug-conversation": (GABARIT_BUG_REF, "conversation"),
    "gabarit-issue-decoupage-conversation": (GABARIT_DECOUPAGE_REF, "conversation"),
    "plan-qa-conversation": (PLAN_QA_SKILL, "conversation"),
    "gabarit-plan-qa-conversation": (GABARIT_PLAN_QA_REF, "conversation"),
    "exemple-bloc-issue-conversation": (EXEMPLE_BLOC_ISSUE_REF, "conversation"),
    "taxonomie-couverture-conversation": (TAXONOMIE_COUVERTURE_REF, "conversation"),
    "plan-qa-label-cree-s-il-manque": (PLAN_QA_SKILL, "le label s'il manque"),
    "collecte-contexte-derniers-tours": (COLLECTE_CONTEXTE_REF, "derniers tours"),
    "bug-vers-issue-intake-capture": (BUG_VERS_ISSUE_SKILL, "capturé"),
    "collecte-contexte-intake-capture": (COLLECTE_CONTEXTE_REF, "capturé"),
    "bug-vers-issue-rouvrir": (BUG_VERS_ISSUE_SKILL, "rouvrir"),
    "bug-vers-issue-corps-patche-lu-par-le-releveur": (
        BUG_VERS_ISSUE_SKILL,
        "relu en octets par le `releveur`",
    ),
    "repercussions-corps-relu-sans-lecteur": (
        REPERCUSSIONS_SKILL,
        "le corps courant relu en octets",
    ),
    "repercussions-brief-relu-sans-lecteur": (REPERCUSSIONS_SKILL, "même lecture en octets"),
    "repercussions-relire-sans-lecteur": (REPERCUSSIONS_SKILL, "la lecture en octets ci-dessus"),
    "execution-qa-conversation": (EXECUTION_QA_SKILL, "conversation"),
    "gabarit-intake-echec-conversation": (INTAKE_ECHEC_REF, "conversation"),
    "gabarit-commentaire-phase-conversation": (COMMENTAIRE_PHASE_REF, "conversation"),
    "patch-checkbox-conversation": (PATCH_CHECKBOX_REF, "conversation"),
    "standard-correction-bug-conversation": (CORRECTION_BUG_REF, "conversation"),
    "execution-qa-intake-a-capturer": (EXECUTION_QA_SKILL, "capturer"),
    "gabarit-intake-echec-a-capturer": (INTAKE_ECHEC_REF, "capturer"),
    "execution-qa-intake-capture": (EXECUTION_QA_SKILL, "capturé"),
    "execution-qa-copie-dans-tmp": (EXECUTION_QA_SKILL, "/tmp/qa-plan"),
    "patch-checkbox-copie-dans-tmp": (PATCH_CHECKBOX_REF, "/tmp/qa-plan"),
    "execution-qa-copie-de-travail": (EXECUTION_QA_SKILL, "copie de travail"),
    "patch-checkbox-copie-de-travail": (PATCH_CHECKBOX_REF, "copie de travail"),
    "execution-qa-re-recuperer": (EXECUTION_QA_SKILL, "re-récupér"),
    "patch-checkbox-re-recuperer": (PATCH_CHECKBOX_REF, "re-récupér"),
    "execution-qa-pousser": (EXECUTION_QA_SKILL, "pousser"),
    "patch-checkbox-pousser": (PATCH_CHECKBOX_REF, "pousser"),
    "execution-qa-repousser": (EXECUTION_QA_SKILL, "repouss"),
    "execution-qa-push": (EXECUTION_QA_SKILL, "push"),
    "patch-checkbox-push": (PATCH_CHECKBOX_REF, "push"),
    "patch-checkbox-paire-en-memoire": (PATCH_CHECKBOX_REF, "en mémoire"),
    "execution-qa-correction-en-session": (EXECUTION_QA_SKILL, "en session"),
    "standard-correction-bug-en-session": (CORRECTION_BUG_REF, "en session"),
    "audit-spec-ui-conversation": (AUDIT_SPEC_UI_SKILL, "conversation"),
    "audit-spec-ui-en-discussion": (AUDIT_SPEC_UI_SKILL, "en discussion"),
}


@pytest.mark.parametrize(
    ("fichier", "forme"),
    RETIRES_DU_CONTEXTE_VIVANT.values(),
    ids=RETIRES_DU_CONTEXTE_VIVANT.keys(),
)
def test_le_contexte_vivant_retire_ne_revient_pas(fichier: str, forme: str) -> None:
    """Une forme retirée qui reste écrite se rejoue : la session suit le texte, pas l'intention."""
    assert not porte_la_forme(fichier, forme), f"`{fichier}` porte encore « {forme} »"


def test_la_conversation_est_gardee_dans_chaque_fichier_des_skills_du_contexte_vivant() -> None:
    """Un fichier ajouté à `contradiction`, à `bug-vers-issue`, à `plan-qa`, à `execution-qa` ou à
    `audit-spec-ui` rougit ici tant que la table ne garde pas le mot chez lui : les critères
    « 6a, 6b », « 7a, 7b » et « Lot 8 » lisent le dossier entier."""
    gardes = {
        fichier for fichier, forme in RETIRES_DU_CONTEXTE_VIVANT.values() if forme == "conversation"
    }
    dossiers = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for skill in ("contradiction", "bug-vers-issue", "plan-qa", "execution-qa", "audit-spec-ui")
        for path in (REPOSITORY_ROOT / ".claude/skills" / skill).rglob("*")
        if path.is_file()
    }

    assert gardes == dossiers


# Lot 8b de #134 (2026-10-26) : un skill sans configuration ne lance plus `init-projet` dans sa
# propre session, il s'arrête et propose une session distincte (`init-projet`, « Note pour les
# autres skills ») ; « relancer », qui rejoue le même skill (`init-projet` étape 9), est hors
# classe. Une table de phrases ne voyait que la forme d'origine de chaque fichier (passe 1 de la
# PR #162, m2) : la forme se lit sur toute la population.
LANCER_INIT_PROJET = re.compile(r"(?<![\w-])lancer\b[^.;`]{0,25}`init-projet`", re.IGNORECASE)
LANCER_INIT_PROJET_FORMES = {
    "entre-parentheses": ("(lancer `init-projet`)", True),
    "majuscule-et-mots-intercales": ("Lancer le skill `init-projet`", True),
    "relancer-hors-classe": ("relancer `init-projet`", False),
}


@pytest.mark.parametrize(
    ("texte", "lance"), LANCER_INIT_PROJET_FORMES.values(), ids=LANCER_INIT_PROJET_FORMES.keys()
)
def test_la_forme_lancer_init_projet_se_reconnait(texte: str, lance: bool) -> None:
    """Le témoin des deux côtés : une forme qui lance appariée, « relancer » laissé."""
    assert bool(LANCER_INIT_PROJET.search(texte)) is lance


def test_aucun_texte_du_harnais_ne_lance_init_projet() -> None:
    """**Population** : la prose suivie du harnais (`HARNESS_PROSE_GLOBS`), texte aux espaces
    normalisés (`texte_normalise`, obs 124). Sur `0c408db`, base du lot : **6** — `cycle-pr`,
    `init-projet` (« Note »), `pr-paralleles`, `triage`, `vers-issues`, `vers-prd` (« lancer le
    skill ») ; un `git grep -P` du motif, ligne par ligne, n'en rend que 5 : celle de `cycle-pr`
    y est coupée en fin de ligne. **0** sur la tête. Commande : ce test, sur une copie de travail
    de `0c408db` — rouge sur ces 6, mesuré le 2026-10-26.
    """
    sites = [
        f"{fichier} : {forme.group(0)}"
        for fichier, texte in prose_du_harnais()
        for forme in LANCER_INIT_PROJET.finditer(texte)
    ]

    assert not sites, f"un texte lance encore `init-projet` au lieu de le proposer : {sites}"


# --- Les marques qui règlent une case de plan de QA (#134, lot 7b2) -----------------------------

# Chaque marque de `SETTLED_MARKS` (`ecriture-relue.py`) — une case laissée `[ ]` qui la porte,
# `checkbox next` ne la rend plus — avec l'annotation qu'`execution-qa/SKILL.md` prescrit pour
# elle, en littéraux, lue dans tout le fichier — l'étape qui l'écrit est épinglée à part
# (`7b2-execution-qa-accepte`, `7b2-execution-qa-echec-annote-et-intake-ecrit`) : une marque réglée
# qu'aucune étape n'écrit laisse la case en attente pour toujours. Contrainte V1 du lot 7b1 : rouge
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
# sa puce `- **<nom>** — ` : un bloc clôturé `bash`, ou un segment `grep …` entre accents graves.
PASSE_COMPTABLE = re.compile(r"^### 1\. Passe comptable.*?(?=^### )", re.MULTILINE | re.DOTALL)
PUCE_DE_LA_PASSE = re.compile(r"^- \*\*", re.MULTILINE)
COMMANDE_EN_BLOC = re.compile(r"```bash\n(.+?)\n")
COMMANDE_EN_LIGNE = re.compile(r"`(grep [^`]+)`")
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


@pytest.fixture(scope="module")
def bash_de_ce_systeme() -> str:
    """Le `bash` du `PATH`, par `shutil.which` (doc `subprocess`, avertissement de `Popen`), s'il lit
    les chemins de ce système ; sinon, le test qui le prend est sauté.

    Sous Windows, le test ne prend qu'un `bash` MSYS, dont `uname -s` commence par `MINGW` ou
    `MSYS` (les deux mesurés sous Git Bash, selon `MSYSTEM`). Celui de WSL — le lanceur de
    `System32` comme l'alias de `WindowsApps`, tous deux sur le poste — rend `Linux`, et la commande
    y échoue : mesuré le 2026-10-26, 37 cas sur 37 sur « unexpected EOF while looking for
    matching » avec un `PATH` de shell Windows où `shutil.which` le trouve d'abord. Un `"bash"` nu,
    résolu par `CreateProcess`, le trouve même sous Git Bash. Ailleurs — en CI Linux, le test
    tourne — le `bash` du `PATH` sert tel quel.
    """
    bash = shutil.which("bash")
    if bash is not None and sys.platform == "win32":
        uname = subprocess.run(
            [bash, "-c", "uname -s"], capture_output=True, text=True, check=False
        )
        if not uname.stdout.startswith(("MINGW", "MSYS")):
            bash = None
    if bash is None:
        pytest.skip(
            "pas de `bash` POSIX (absent, ou celui de WSL) : la commande de la passe comptable ne"
            " se joue pas ici"
        )
    return bash


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


# --- Chaque sortie d'une `contradiction` relance ce qu'elle doit (#134, lot 6b2) -----------------

# Les deux relances de `contradiction` étape 5, que la table des sorties suit dans le texte : à
# chaque sortie quand `repercussions` l'a démarrée, et sans origine à chaque sortie qui merge une
# PR, seule à laisser un delta à propager.
RELANCE_AVEC_ORIGINE = (
    "**avec `origine : #<N>`** reçue à l'étape 1, à **chaque** sortie, pas seulement à celle qui"
    " amende — la passe de `#<N>` s'est arrêtée avant son étape 2 et rien d'autre ne la reprend :"
    f" `title: <préfixe> › repercussions` {RENVOI_A_L_IDENTITE}, prompt"
    " `/repercussions #<N>` suivi du bloc d'arrêt reçu et de la ligne `contradiction soldée :"
    " <sortie>` de la table"
)
RELANCE_SANS_ORIGINE = (
    "**sans origine** : à chaque sortie qui merge une PR, et à elle seule, au merge de cette PR,"
    f" `title: <préfixe> › repercussions #<m>` {RENVOI_A_L_IDENTITE}, prompt"
    " `/repercussions #<m>`, où `<m>` est son numéro (mode « PR d'amendement ») — les autres"
    " sorties n'ont aucun delta mergé, rien à démarrer"
)
# La carte de proposition, qui suit la table des sorties.
CARTE_DE_LA_RELANCE = "Hors d'un tour du mainteneur, une carte de proposition"
# L'arrêt de `repercussions` étape 1 : la consigne d'une ligne `contradiction soldée` se lit avant
# lui, sinon la session redémarrée relève l'arrêt soldé avant de la lire (obs 30).
ARRET_DE_REPERCUSSIONS = "Une contradiction avérée → **s'arrêter avant l'étape 2**"
# Les deux consignes de `repercussions` étape 1 : l'effet mergé qu'un document gagnant laisse en
# place se trace, puis la passe suit ; sinon elle suit directement.
REPRISE_APRES_TRACE = (
    "Avec `document gagne`, suivi ou non de `— PR #<m>`, l'effet mergé qui contredit le document"
    " est un **vide à tracer**"
)
REPRISE_DIRECTE = (
    "Avec `amendement PR #<m>`, `amendement reporté — #<k>`, que `#<k>` porte déjà, ou `écartée —"
    " <raison>`, elles suivent directement"
)
# Une entrée par sortie, en littéraux (obs 80) : sa ligne de la table de `contradiction` étape 5 —
# tour de la relance, relance sans origine, ligne `contradiction soldée`, message de fin —, puis sa
# consigne de reprise. Une table plutôt que des épingles groupées : chaque sortie y garde son texte
# entier sous son id, et l'autre sens — une ligne de la table du skill sans entrée ici — se compte
# contre elle.
SORTIES_DE_CONTRADICTION = {
    "1-amendement-merge": (
        (
            "| amendement mergé | son merge | `/repercussions #<m>` | `contradiction soldée :"
            " amendement PR #<m>` | « terminé — amendement PR #<m> mergé » |"
        ),
        REPRISE_DIRECTE,
    ),
    "2-document-gagne-effet-abandonne": (
        (
            "| document gagne, effet abandonné | la décision de l'étape 3 | rien, aucun delta mergé |"
            " `contradiction soldée : document gagne` | « terminé — aucune PR, le document gagne » |"
        ),
        REPRISE_APRES_TRACE,
    ),
    "3-document-gagne-effet-deplace-par-une-pr": (
        (
            "| document gagne, effet déplacé dans le dépôt par une PR | son merge |"
            " `/repercussions #<m>` | `contradiction soldée : document gagne — PR #<m>` | « terminé —"
            " PR #<m> mergée, le document gagne » |"
        ),
        REPRISE_APRES_TRACE,
    ),
    "4-document-gagne-effet-deplace-hors-du-depot": (
        (
            "| document gagne, effet déplacé hors du dépôt | la décision de l'étape 3 | rien, aucun"
            " delta mergé | `contradiction soldée : document gagne` | « terminé — aucune PR, le"
            " document gagne » |"
        ),
        REPRISE_APRES_TRACE,
    ),
    "5-contradiction-ecartee": (
        (
            "| pas de contradiction | son constat | rien, aucun delta mergé | `contradiction soldée :"
            " écartée — <raison>` | « terminé — contradiction écartée » |"
        ),
        REPRISE_DIRECTE,
    ),
    "6-amendement-reporte": (
        (
            "| décision gagne, amendement reporté | l'ouverture de `#<k>` | rien, aucun delta mergé |"
            " `contradiction soldée : amendement reporté — #<k>` | « terminé — amendement reporté à"
            " #<k> » |"
        ),
        REPRISE_DIRECTE,
    ),
}


@pytest.mark.parametrize(
    ("ligne", "reprise"),
    SORTIES_DE_CONTRADICTION.values(),
    ids=SORTIES_DE_CONTRADICTION.keys(),
)
def test_chaque_sortie_de_contradiction_relance_ce_qu_elle_doit(ligne: str, reprise: str) -> None:
    """Relecture de la PR #155, passe 2, I1. Classe : une sortie de `contradiction` démarrée avec
    `origine : #<N>` qui ne fait pas reprendre la passe de `#<N>`, arrêtée par `repercussions`
    « avant l'étape 2 ». **6** sorties : 5 dans le texte du skill, dénombrées par la session PR sur
    `02c513b`, et 1 dans la règle qui régit ses sorties, `decisions-vs-doc.md`, « Deux sorties »,
    relevée à la relance qui suit `37b0021`. Sur `02c513b`, **5** fuyaient ; à `37b0021`, **1**.

    1. Amendement mergé — redémarrait la passe.
    2. Le document gagne, effet abandonné (`decisions-vs-doc`, sortie 1a) — fuyait.
    3. Le document gagne, effet déplacé dans le dépôt par une PR (1b) — fuyait : ce n'est pas une
       PR d'amendement, et « terminé — amendement PR #<m> mergé » l'aurait nommée à tort.
    4. Le document gagne, effet déplacé hors du dépôt (1b) — fuyait.
    5. Pas de contradiction après vérification, « On se tait » — fuyait.
    6. La décision gagne, amendement trop gros pour maintenant : un critère ou une issue ouverts
       sur-le-champ (`decisions-vs-doc`, « Deux sorties ») — fuyait jusqu'à `37b0021` compris.

    Sans origine (même passe, hors-périmètre du `developpeur` ; classe : une PR mergée par
    `contradiction` que rien ne propage), sur `189a13f` : **2** sorties mergent une PR, 1 et 3 ;
    **1** fuyait, la 3. Les sorties 2, 4 et 5 ne mergent rien : aucun delta à propager.

    Chaque sortie a sa ligne dans la table de l'étape 5, après les deux relances et avant la carte
    de proposition, et sa consigne dans `repercussions` étape 1, avant l'arrêt.
    """
    assert_dans_l_ordre(CONTRADICTION_SKILL, RELANCE_AVEC_ORIGINE, ligne)
    assert_dans_l_ordre(CONTRADICTION_SKILL, RELANCE_SANS_ORIGINE, ligne)
    assert_dans_l_ordre(CONTRADICTION_SKILL, ligne, CARTE_DE_LA_RELANCE)
    assert_dans_l_ordre(REPERCUSSIONS_SKILL, reprise, ARRET_DE_REPERCUSSIONS)


def test_la_table_des_sorties_de_contradiction_est_celle_du_test() -> None:
    """L'autre sens (obs 138) : une ligne ajoutée à la table de l'étape 5 rougit ici tant que
    `SORTIES_DE_CONTRADICTION` ne la porte pas, avec sa consigne de reprise."""
    texte = (REPOSITORY_ROOT / CONTRADICTION_SKILL).read_text(encoding="utf-8")
    lignes = [
        " ".join(ligne.split())
        for ligne in texte.splitlines()
        if "| `contradiction soldée :" in ligne
    ]

    assert sorted(lignes) == sorted(ligne for ligne, _ in SORTIES_DE_CONTRADICTION.values())


# Ce que la passe 2 retire : la relance au seul merge d'un amendement, la reprise annoncée « contre
# la doc amendée » à toute sortie, et la forme de fin qui confondait la PR d'un document gagnant
# avec l'absence de PR — chacune présente sur `02c513b` —, puis la relance sans origine bornée à
# l'amendement, présente sur `189a13f`.
RETIRES_DES_SORTIES_DE_CONTRADICTION = {
    "contradiction-relance-sans-origine-a-l-amendement-seul": (
        CONTRADICTION_SKILL,
        "à la seule sortie qui amende",
    ),
    "contradiction-relance-au-seul-merge": (
        CONTRADICTION_SKILL,
        "au merge de la PR d'amendement, dans le tour du go du mainteneur",
    ),
    "contradiction-reprise-contre-la-doc-amendee": (CONTRADICTION_SKILL, "contre la doc amendée"),
    "contradiction-fin-sans-amendement": (
        CONTRADICTION_SKILL,
        "aucun amendement, le document gagne",
    ),
    "repercussions-reprise-au-seul-merge": (REPERCUSSIONS_SKILL, "à son merge, elle redémarre"),
    "repercussions-reprise-contre-la-doc-amendee": (REPERCUSSIONS_SKILL, "contre la doc amendée"),
}


@pytest.mark.parametrize(
    ("fichier", "forme"),
    RETIRES_DES_SORTIES_DE_CONTRADICTION.values(),
    ids=RETIRES_DES_SORTIES_DE_CONTRADICTION.keys(),
)
def test_une_sortie_de_contradiction_retiree_ne_revient_pas(fichier: str, forme: str) -> None:
    """Une condition ou une forme retirée qui reste écrite se rejoue."""
    assert not porte_la_forme(fichier, forme), f"`{fichier}` porte encore « {forme} »"


# Deux exceptions de la relance, chacune avant le geste qu'elle suspend ou complète (obs 30) : le
# report de l'amendement, avant la PR de l'étape 4 ; le diff d'une PR soldée, avant la capture du
# delta réel de `repercussions`, où il serait lu trop tard au paragraphe soldé.
EXCEPTIONS_DE_LA_RELANCE = {
    "contradiction-report-avant-la-pr": (
        CONTRADICTION_SKILL,
        (
            "Quand le mainteneur retient à l'étape 3 que la décision gagne mais que l'amendement est"
            " trop gros pour maintenant, aucune PR ne part : l'échappatoire de"
            " `.claude/rules/decisions-vs-doc.md` (« Deux sorties ») ouvre sur-le-champ un critère"
            " ou une issue `#<k>` portant les deux citations, par « Création d'issues en cours de"
            " cycle » (`.claude/rules/contraintes.md`), barreau 2 ou 4, le brouillon en session"
            " distincte — ce skill n'ouvre rien lui-même"
        ),
        "Sur « go », l'amendement part par une PR",
    ),
    "repercussions-pr-soldee-avant-le-delta": (
        REPERCUSSIONS_SKILL,
        (
            "Démarrée avec `contradiction soldée : amendement PR #<m>` ou `document gagne — PR #<m>`,"
            " le diff de la PR #<m> s'ajoute à ces sources : sans lui, les §§ amendés en cascade et"
            " le bloc déplacé ne se confronteraient qu'aux ancres de `#<N>`"
        ),
        "Restituer sous `## 📦 Delta réel`",
    ),
}


@pytest.mark.parametrize(
    ("fichier", "exception", "geste"),
    EXCEPTIONS_DE_LA_RELANCE.values(),
    ids=EXCEPTIONS_DE_LA_RELANCE.keys(),
)
def test_une_exception_de_la_relance_se_lit_avant_son_geste(
    fichier: str, exception: str, geste: str
) -> None:
    """L'exception présente, et lue avant le geste : placée après, elle n'est jamais appliquée."""
    assert_dans_l_ordre(fichier, exception, geste)


# L'**ordre** du protocole de la coordinatrice : chaque couple d'ancres, la première avant la
# seconde. Une phrase gardée seule dit qu'un geste existe, pas où il se place — et c'est sa place
# qui le rend vrai : une branche d'intégration poussée après les sessions laisse le premier lot sans
# base, une dérive lue après « ouvre » ne garde plus rien (relance de la PR #122, N1 : deux
# mutations VERTES sur la table de phrases). **Population** : les 8 sites d'ordre ou de condition
# recensés dans `coordinatrice.md` à la passe 1 ; 4 sont des conditions, gardées par la table de
# phrases (attente des lots suivants, deux preuves, arrêt sur un code non nul, premier geste pas
# avant « ouvre »), 4 des ordres, gardés ici — gestes au go, dérive avant « ouvre », relais,
# passation avant le message de fin.
ORDRE_DE_LA_COORDINATRICE = {
    "branche-avant-la-pr-d-integration": (
        "1. **La branche d'intégration**",
        "2. **La PR d'intégration**",
    ),
    "pr-d-integration-avant-les-sessions": (
        "2. **La PR d'intégration**",
        "3. **Les sessions de lot**",
    ),
    "deux-preuves-avant-la-derive": (
        "Elle ouvre le lot k+1 sur deux preuves",
        "Puis la dérive, après chaque merge de lot",
    ),
    "derive-avant-ouvre": (
        "Puis la dérive, après chaque merge de lot",
        "Puis seulement, par `SendMessage` à la session du lot k+1",
    ),
    "relais-detache-avant-de-prevenir": (
        "pousse sa branche, détache sa tête",
        "envoie « relais demandé",
    ),
    "relais-passation-avant-de-prevenir": ("écrit la variante relais", "envoie « relais demandé"),
    "passation-avant-le-message-de-fin": (
        "et écrire sa passation",
        "puis le message de fin à la coordinatrice",
    ),
}


@pytest.mark.parametrize(
    ("avant", "apres"),
    ORDRE_DE_LA_COORDINATRICE.values(),
    ids=ORDRE_DE_LA_COORDINATRICE.keys(),
)
def test_la_coordinatrice_garde_l_ordre_de_son_protocole(avant: str, apres: str) -> None:
    """Les deux ancres présentes, et dans cet ordre — une ancre absente rougit aussi."""
    assert_dans_l_ordre(COORDINATRICE_REF, avant, apres)


def assert_dans_l_ordre(fichier: str, avant: str, apres: str) -> None:
    """Échoue si l'une des deux ancres manque au texte normalisé, ou si `ordre_respecte` le refuse."""
    texte = texte_normalise(fichier)

    assert avant in texte, f"`{fichier}` ne porte plus « {avant} »"
    assert apres in texte, f"`{fichier}` ne porte plus « {apres} »"
    assert ordre_respecte(texte, avant, apres), f"« {apres} » précède « {avant} »"


def ordre_respecte(texte: str, avant: str, apres: str) -> bool:
    """Vrai si toute occurrence d'`avant` précède toute occurrence d'`apres` : la **dernière**
    d'`avant` se compare à la **première** d'`apres`, les deux ancres étant présentes.

    Comparer les premières laissait passer une copie ajoutée plus loin — un geste réécrit à
    l'étape suivante sans être retiré de la sienne (relecture de la PR #130, mutation VERTE).
    **Borne** : une ancre `avant` ne se cite plus après son `apres`, rappel compris ; la rougeur
    est voulue — reformuler le rappel, jamais l'ancre.
    """
    return texte.rindex(avant) < texte.index(apres)


# Le comparateur sur des textes témoins, dans les deux sens : c'est lui qui distingue une copie
# tardive d'un ordre juste, et revenir à `index` le laissait vert sur le dépôt (passe 2, N4).
ORDRES_TEMOINS = {
    "ordre-juste": ("A puis B", True),
    "ordre-inverse": ("B puis A", False),
    "copie-tardive": ("A puis B puis A", False),
}


@pytest.mark.parametrize(("texte", "attendu"), ORDRES_TEMOINS.values(), ids=ORDRES_TEMOINS.keys())
def test_l_ordre_rougit_sur_une_copie_tardive(texte: str, attendu: bool) -> None:
    """« A » doit précéder « B » partout, pas seulement à sa première occurrence."""
    assert ordre_respecte(texte, "A", "B") is attendu


# L'**ordre** de `pr-paralleles` que le lot 3 de #107 écrit : un geste dont une étape antérieure
# doit préparer l'entrée. **Population** : les 4 sites d'ordre recensés à la passe 1 de la
# relecture de la PR #130 (I-3, I-5 ; mutations M2 et M11 VERTES sur la table de phrases) — le
# plafond demandé à la question qui ouvre le tour des démarrages, le relevé `get_session` avant
# l'archivage qui le rend nécessaire, l'archivage avant le retrait du worktree (obs 42, re-mesurée
# le 2026-10-18), le retrait avant l'échafaudage. Le lot 4 ajoute les 5 de l'étape 0 : l'accord
# avant chacun des deux démarrages (sans worktree, et la session d'un bug), le démarrage avant la
# vérification dans GitHub, qui précède le passage à l'étape 1, et dans le brief la transition
# avant le message (relecture, I-2).
ORDRE_DE_PR_PARALLELES = {
    "etape-0-accord-avant-le-demarrage": (
        "Rien ne s'ouvre avant l'accord",
        "`context: fresh`, `use_worktree: false` écrit en clair",
    ),
    "etape-0-demarrage-avant-la-verification": (
        "`context: fresh`, `use_worktree: false` écrit en clair",
        "il ne prouve rien seul",
    ),
    # Relecture de la PR #133, passe 2, m-1 : la session d'un bug aussi attend l'accord.
    "etape-0-accord-avant-le-bug": (
        "Rien ne s'ouvre avant l'accord",
        "son propre worktree, `use_worktree: true`, les autres paramètres inchangés",
    ),
    # Relecture de la PR #133, passe 1, I-2 : le message part après la transition, pas avant.
    "etape-0-transition-avant-le-message": (
        "applique-la par `triage`",
        "puis envoie à ton parent « interrogatoire #N terminé",
    ),
    "etape-0-verification-avant-la-carte-de-la-vague": (
        "il ne prouve rien seul",
        "propose une carte « démarrer la vague »",
    ),
    "plafond-avant-le-demarrage": (
        "si la session lead est en dessous d'Opus 5.5",
        # Le texte normalisé perd un `#` de tête : l'ancre ne porte pas les dièses du titre.
        "3. Démarrer une session par issue",
    ),
    "releve-avant-l-archivage": (
        "relever par `get_session` son `worktreePath`",
        "**archiver la session d'abord**",
    ),
    "archivage-avant-le-retrait": (
        "**archiver la session d'abord**",
        "git worktree remove <worktreePath de la session>",
    ),
    "retrait-avant-l-echafaudage": (
        "git worktree remove <worktreePath de la session>",
        "Puis l'**échafaudage**",
    ),
}


@pytest.mark.parametrize(
    ("avant", "apres"),
    ORDRE_DE_PR_PARALLELES.values(),
    ids=ORDRE_DE_PR_PARALLELES.keys(),
)
def test_pr_paralleles_garde_l_ordre_de_ses_sessions(avant: str, apres: str) -> None:
    """Une étape qui agit avant que l'agent sache ce qu'une étape suivante exige se rejoue mal."""
    assert_dans_l_ordre(PR_PARALLELES_SKILL, avant, apres)


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


# Les portes à base d'avis (obs 56) lisent une base qui change sans commit. La prose qui prescrit
# un geste sur elles a fui deux fois à la relecture du lot 4b de #77, dans deux sens opposés :
# vérifier un avis sur le trunk en **rejouant** un de ses runs relance les jobs qui en dépendent —
# `publish`, puis `deploy` (REST : « Re-run a job and its dependent jobs ») ; et réserver
# l'horloge à ces portes en excluant **toute autre étape** retire l'installation et la
# construction dont elles dépendent, si bien que le run planifié rougit chaque jour. À la relance,
# le remède du premier fuyait à son tour pour un scan : lancé dans un worktree du trunk sous le
# nom d'image par défaut, il lit, sur le démon partagé, les images construites depuis la branche.
#
# Dénombrement, écrit avant le correctif : les passages de la prose du harnais
# (`.claude/**/*.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `.github/`) qui nomment une porte d'avis —
# motif `base d'avis|rouge d'avis|portes? d'avis|portes? à base d'avis`, insensible à la casse —
# sont 5 ; 3 prescrivent un geste, 2 fuyaient, le troisième (une case de checklist) portait la
# même ambiguïté que le second. Les 2 autres décrivent sans prescrire : l'écart de ce projet
# (`pipeline.config.md`, « Qualité ») et la règle des populations vivantes (`cleanup-verbatim.md`).
#
# Un défaut se garde sous **toutes** ses tournures, pas sous celle qui l'a révélé : la relance a
# réintroduit chacun des trois sous une autre forme, et les trois sont restées vertes contre un
# interdit qui n'en visait qu'une orthographe. D'où un interdit par racine (`rejou`, `build`) et une
# exigence par phrase entière.
# Cas : (fichier, début du passage, fin du passage, ce qu'il ne cite pas, ce qu'il dit).
ADVISORY_GATE_RULES = {
    "cycle-pr-rouge-d-avis": (
        CYCLE_PR_SKILL,
        "*Rouge d'avis*",
        "*Rouge de code*",
        ("gh run rerun", "rejou"),
        ("Jamais un rerun d'un run du trunk", "sous un nom propre au trunk"),
    ),
    "init-projet-horloge": (
        INIT_PROJET_SKILL,
        "**Donner une horloge",
        "Sans porte d'avis",
        ("build",),
        ("installation et construction",),
    ),
    "init-projet-checklist": (
        INIT_PROJET_SKILL,
        "- [ ] portes à base d'avis",
        "\n",
        (),
        ("réservés à elles et à ce dont elles dépendent",),
    ),
}


@pytest.mark.parametrize(
    ("fichier", "debut", "fin", "interdits", "exiges"),
    ADVISORY_GATE_RULES.values(),
    ids=ADVISORY_GATE_RULES.keys(),
)
def test_une_regle_de_porte_d_avis_ne_relance_ni_ne_retire_ce_dont_elle_depend(
    fichier: str, debut: str, fin: str, interdits: tuple[str, ...], exiges: tuple[str, ...]
) -> None:
    """Le passage qui prescrit un geste sur une porte d'avis ne rejoue aucun run du trunk, ne lit
    pas les images de la branche, et garde ce dont la porte dépend. Le début du passage doit
    apparaître **une** fois : un passage renommé fait rougir ici au lieu de rendre le test
    vacant."""
    texte = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8-sig").replace("\r\n", "\n")

    assert texte.count(debut) == 1, f"`{debut}` apparaît {texte.count(debut)} fois dans `{fichier}`"
    passage = texte[texte.index(debut) :]
    passage = passage[: passage.index(fin, len(debut))]
    presents = [interdit for interdit in interdits if interdit in passage]
    absents = [exige for exige in exiges if exige not in passage]
    assert not presents, f"`{fichier}` prescrit encore {presents} : {passage!r}"
    assert not absents, f"`{fichier}` ne dit plus {absents} : {passage!r}"


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

# Le protocole de la session de relecture et celui qu'elle suit — un énoncé par geste, chacun
# épinglé sur sa moitié restrictive autant que sur celle qui fait (critère en tête de
# `INVARIANTS_DU_CONTEXTE_COURT`, obs 126). **Population** : les morceaux de `session-relecture.md`
# — `morceaux_du_texte`, qui découpe le texte normalisé après `.`, `;` ou `:` hors du code en
# ligne — et les 13 phrases que ce lot réécrit dans `relecteur.md`. Le dénombrement n'est pas écrit
# ici : il sort de `test_chaque_morceau_du_protocole_tient_une_ancre`, qui exige que chaque morceau
# tienne une ancre ou figure dans `MORCEAUX_SANS_PRESCRIPTION`. Relecture de la PR #141 : un
# « 55 morceaux » écrit en commentaire ne se reproduisait pas par sa propre règle (92), et deux
# passes ont trouvé chacune des énoncés nus — la classe d'obs 107, 124 et 126. Chaque ancre vue
# rouge en retirant sa moitié restrictive ou son élément (Notes de la PR #141) ; l'ordre du réveil
# est gardé à part (`ORDRE_DU_REVEIL`), la porte d'ancêtre du repli par `PORTES_PRESCRITES`.
INVARIANTS_DE_LA_SESSION_DE_RELECTURE = {
    "source-unique": (SESSION_RELECTURE_REF, "y renvoient sans le recopier"),
    "demarrage-tour-du-mainteneur": (
        SESSION_RELECTURE_REF,
        "`start_session` ne part que dans un tour ouvert par le mainteneur",
    ),
    "demarrage-par-la-session-pr": (
        SESSION_RELECTURE_REF,
        "La session PR la démarre **elle-même** et en est le **parent**",
    ),
    "jamais-le-lead-ni-la-coordinatrice": (
        SESSION_RELECTURE_REF,
        "Jamais le lead ni la coordinatrice",
    ),
    "parametres-de-demarrage": (
        SESSION_RELECTURE_REF,
        "`initiation: user_asked`, `context: fresh`, `use_worktree: true`",
    ),
    "effort-high": (SESSION_RELECTURE_REF, "`effort: high`, `model` omis"),
    "premier-geste-sans-branche": (SESSION_RELECTURE_REF, "— aucune branche à créer —"),
    "observations-tenues-par-la-session-pr": (
        SESSION_RELECTURE_REF,
        "ses candidates partent dans ses messages de constats",
    ),
    "pousser-avant-le-reveil": (SESSION_RELECTURE_REF, "La session PR **pousse**, puis envoie"),
    "forme-du-reveil": (
        SESSION_RELECTURE_REF,
        "relis <SHA>, passe <k> — plage <début>..<fin>",
    ),
    "plage-et-sha-a-chaque-reveil": (
        SESSION_RELECTURE_REF,
        "Plage et SHA arrivent à chaque réveil, jamais au lancement",
    ),
    "securite-sous-condition": (
        SESSION_RELECTURE_REF,
        "`/security-review`, **seulement** si le diff touche une zone sensible ou une surface exposée",
    ),
    "reprise-apres-une-fin-de-tour": (SESSION_RELECTURE_REF, "répond « reprends la passe <k> »"),
    "note-jamais-un-constat": (
        SESSION_RELECTURE_REF,
        "La note de fin de tour n'est jamais un constat",
    ),
    "aucune-session-ni-sous-tache": (
        SESSION_RELECTURE_REF,
        (
            "ne démarre aucune session et ne lance d'autre sous-tâche que celles que"
            " `/security-review` prescrit"
        ),
    ),
    "ne-commit-ne-pousse-ne-merge": (
        SESSION_RELECTURE_REF,
        "Elle ne commit pas, ne pousse pas, ne merge pas",
    ),
    "tour-du-mainteneur-ne-reveille-pas": (
        SESSION_RELECTURE_REF,
        "un tour qu'il y pilote ne réveille pas la session PR",
    ),
    "nettoyage-jamais-avant-la-boucle": (
        SESSION_RELECTURE_REF,
        "et jamais avant : tant qu'une relance peut s'ouvrir",
    ),
    "nettoyage-sur-l-accord-du-go": (SESSION_RELECTURE_REF, "L'archivage sur l'accord donné au go"),
    "echafaudage-avant-la-branche-de-pr": (
        SESSION_RELECTURE_REF,
        "avant que celle-ci ne soit supprimée",
    ),
    "repli-commandes-jouees-par-la-session-pr": (
        SESSION_RELECTURE_REF,
        "joue elle-même les deux commandes intégrées avant lui",
    ),
    "repli-agent-neuf-seulement-injoignable": (
        SESSION_RELECTURE_REF,
        "un agent neuf seulement s'il n'est plus joignable",
    ),
    "repli-pas-sur-la-tete": (SESSION_RELECTURE_REF, "pas sur la tête de la PR"),
    "repli-jamais-restaurer-avant-les-verifications": (
        SESSION_RELECTURE_REF,
        "ne demande jamais de restaurer une mutation avant elles",
    ),
    "repli-verrou-ne-dit-rien": (
        SESSION_RELECTURE_REF,
        "son absence ne dit rien de la vitalité de l'agent",
    ),
    "repli-retrait-termine": (SESSION_RELECTURE_REF, "Retirer le worktree **termine** l'agent"),
    "repli-humain-jamais-silencieux": (SESSION_RELECTURE_REF, "jamais de saut silencieux"),
    "relecteur-au-lancement-rien-que-la-pr": (
        RELECTEUR_ROLE,
        "Au lancement, tu ne reçois que la PR, son issue et sa base",
    ),
    "relecteur-plage-a-chaque-reveil": (
        RELECTEUR_ROLE,
        "jamais tu ne relis celle du lancement",
    ),
    "relecteur-pas-le-worktree-de-la-session-pr": (
        RELECTEUR_ROLE,
        "jamais celui de la session PR, qui vit aussi là",
    ),
    "relecteur-n-ecrit-rien-du-depot": (
        RELECTEUR_ROLE,
        "Tu n'écris aucun fichier du dépôt hors d'une mutation restaurée",
    ),
    "relecteur-seule-sous-tache": (
        RELECTEUR_ROLE,
        (
            "aucune session démarrée : en session, la seule sous-tâche admise est celle que"
            " `/security-review` prescrit"
        ),
    ),
    "relecteur-ne-merge-pas": (
        RELECTEUR_ROLE,
        "Tu ne commits pas, tu ne pousses pas, tu ne merges pas, tu ne corriges pas",
    ),
    # Passe 1 de la relecture de la PR #141 — I1 : `origin/HEAD` n'est pas la base d'une PR de lot.
    "securite-constats-hors-plage-ecartes": (
        SESSION_RELECTURE_REF,
        (
            "elle relit aussi ce que la branche d'intégration a déjà reçu, et ses constats hors de la"
            " plage s'écartent"
        ),
    ),
    "config-securite-constats-hors-plage-ecartes": (
        ".claude/pipeline.config.md",
        "vers `origin/main` : ses constats hors de la plage s'écartent",
    ),
    # I2 : le niveau passé à `/code-review` n'est pas garanti.
    "code-review-niveau-lu-dans-l-en-tete": (
        SESSION_RELECTURE_REF,
        (
            "le niveau qu'elle applique se lit dans l'en-tête de son prompt rendu et se rapporte dans le"
            " message de constats, la commande ne garantissant pas celui qu'on lui passe"
        ),
    ),
    "config-relecture-niveau-non-garanti": (
        ".claude/pipeline.config.md",
        "Le niveau passé n'est pas garanti",
    ),
    # I3 : la population entière (comptage en tête de cette table).
    "lue-a-chaque-reveil-dans-son-worktree": (
        SESSION_RELECTURE_REF,
        "par la session de relecture à chaque réveil, dans son worktree",
    ),
    "seule-source": (SESSION_RELECTURE_REF, "C'est la **seule** source de ce protocole"),
    "source-branch-de-la-pr": (
        SESSION_RELECTURE_REF,
        "`source_branch` = la branche de la PR, déjà poussée",
    ),
    "contenu-du-brief": (
        SESSION_RELECTURE_REF,
        (
            "Le brief nomme la PR, l'issue et sa base, donne le premier geste ci-dessous et renvoie à ce"
            " fichier"
        ),
    ),
    "premier-geste-detache": (
        SESSION_RELECTURE_REF,
        "`git fetch origin && git switch --detach origin/<branche de la PR>`",
    ),
    "piles-du-brief": (
        SESSION_RELECTURE_REF,
        "pour les piles que le brief nomme, `hooks` exceptée",
    ),
    "valeurs-de-k": (SESSION_RELECTURE_REF, "`<k>` vaut `1`, `2` ou `relance`"),
    "plage-de-la-passe-1": (
        SESSION_RELECTURE_REF,
        "`<base>..<SHA>` à la passe 1, `<base>` étant `git merge-base origin/<base de la PR> HEAD`",
    ),
    "plage-de-la-passe-2": (
        SESSION_RELECTURE_REF,
        "`<SHA de fin de la passe 1>..<SHA>` à la passe 2",
    ),
    "plage-de-la-relance": (
        SESSION_RELECTURE_REF,
        "`<sha avant>..<sha après>` des commits de correction à la relance",
    ),
    "constats-precedents-dans-le-reveil": (
        SESSION_RELECTURE_REF,
        (
            "À partir de la passe 2, le message porte aussi les constats précédents, corrigés (commit,"
            " test qui tient la fermeture) ou écartés (raison)"
        ),
    ),
    "deux-verifications-dans-l-ordre": (
        SESSION_RELECTURE_REF,
        "Les deux vérifications de `relecteur.md` — où suis-je, puis détachement sur le SHA reçu",
    ),
    "commentaires-relus": (
        SESSION_RELECTURE_REF,
        "Ses commentaires se relisent sur la PR après écriture",
    ),
    "protocole-sans-redite-des-commandes": (
        SESSION_RELECTURE_REF,
        "ce qu'une commande vient de trouver n'y est plus à chercher",
    ),
    "constats-a-l-emetteur-du-reveil": (
        SESSION_RELECTURE_REF,
        (
            "Le message de constats à l'émetteur du réveil — la session PR, ou son relais —, par"
            " `SendMessage`"
        ),
    ),
    "forme-des-constats": (
        SESSION_RELECTURE_REF,
        (
            "`constats passe <k> (<SHA court>) — <b> bloquants, <i> importants, <m> mineurs`, puis le"
            " rapport que `relecteur.md` ordonne, les constats de chaque commande intégrée et les"
            " observations candidates"
        ),
    ),
    "commande-integree-peut-clore": (
        SESSION_RELECTURE_REF,
        "**Une commande intégrée peut clore le tour**",
    ),
    "branche-jamais-commitee-ancetre": (
        SESSION_RELECTURE_REF,
        "Une branche née de la PR et jamais commitée en est ancêtre quel que soit le trunk",
    ),
    "repli-un-seul-sous-agent": (
        SESSION_RELECTURE_REF,
        (
            "Un seul sous-agent pour la PR : la seconde passe et la relance lui reviennent par"
            " `SendMessage`, contexte intact"
        ),
    ),
    "repli-trois-gestes": (SESSION_RELECTURE_REF, "Son worktree a trois gestes"),
    "repli-retrait-par-qui-l-a-lance": (
        SESSION_RELECTURE_REF,
        "**Retrait — à la fermeture de la boucle**, par la session qui l'a lancé",
    ),
    "repli-unlock-d-abord": (SESSION_RELECTURE_REF, "`git worktree unlock` d'abord s'il refuse"),
    "relecteur-protocole-de-session": (
        RELECTEUR_ROLE,
        (
            "Tu suis ce protocole en **session de relecture**, démarrée par la session PR dans un"
            " worktree de l'application"
        ),
    ),
    "relecteur-plage-recue-au-reveil": (
        RELECTEUR_ROLE,
        (
            "**À chaque réveil** — passe 1, passe 2, relance — tu reçois de la session PR la plage de"
            " commits à relire"
        ),
    ),
    "relecteur-ne-nait-pas-sur-le-sha": (
        RELECTEUR_ROLE,
        "Ton worktree ne naît pas sur le SHA à relire",
    ),
    "relecteur-rejoue-a-chaque-reveil": (
        RELECTEUR_ROLE,
        (
            "**À chaque réveil** — seconde passe comme relance —, rejoue les deux gestes dans cet ordre"
            " sur le SHA reçu"
        ),
    ),
    "relecteur-sous-agent-sans-write": (RELECTEUR_ROLE, "Le sous-agent n'a pas de `Write`"),
    "relecteur-retire-par-la-session-pr": (RELECTEUR_ROLE, "C'est la session PR qui le retire"),
    "relecteur-rend-a-la-session-pr": (
        RELECTEUR_ROLE,
        "Tu rends à la session PR — par message en session",
    ),
    "relecteur-corriger-revient-a-la-session-pr": (
        RELECTEUR_ROLE,
        "Il ne contient pas celle de corriger, qui revient à la session PR",
    ),
    # Relance de la PR #141, m6 : morceaux tenus en partie dont une mutation restait VERTE.
    "reprise-a-l-etape-suivante": (
        SESSION_RELECTURE_REF,
        (
            "la session PR, réveillée par la fin de tour sans message de constats, répond"
            " « reprends la passe <k> », et la session de relecture reprend à l'étape suivante, son"
            " contexte intact."
        ),
    ),
    "commandes-qui-closent-le-tour": (
        SESSION_RELECTURE_REF,
        (
            "**Une commande intégrée peut clore le tour** — `/code-review` par son outil de rapport,"
            " `/security-review` par « Your final reply must contain the markdown report and nothing"
            " else »."
        ),
    ),
    "repli-humain-avec-le-diff": (
        SESSION_RELECTURE_REF,
        (
            "la main passe au relecteur humain, avec le diff et le prompt de `cleanup-verbatim.md`"
            " verbatim, noté dans « Relecture indépendante » du body — jamais de saut silencieux."
        ),
    ),
    # Passe 2 de la relecture de la PR #141 — I4 : en relais, rien ne réveille l'émetteur.
    "relais-notify-when-idle": (
        SESSION_RELECTURE_REF,
        (
            "il envoie chaque réveil, et chaque « reprends », avec `notify_when_idle: true` — un avis"
            " par abonnement — et répond « reprends la passe <k> » à l'avis d'inactivité arrivé sans"
            " constats"
        ),
    ),
    # Relance de la PR #141, I5 : la sortante d'un relais ne relance plus.
    "relais-la-sortante-ne-relance-plus": (
        SESSION_RELECTURE_REF,
        (
            "La session sortante, elle, ne répond plus aux notes de la session de relecture dès sa"
            " passation remise : seul le relais relance, sinon une étape se rejouerait deux fois."
        ),
    ),
    "relais-ne-recoit-pas-la-note": (
        SESSION_RELECTURE_REF,
        "Un relais de la session PR, qui n'est pas le parent, ne reçoit pas cette note",
    ),
    "prompt-lot-suivant-relais-notify-when-idle": (
        PROMPT_LOT_SUIVANT,
        "envoie chaque réveil avec `notify_when_idle: true`",
    ),
    # m1, m3, m4.
    "code-review-pas-rendu-a-nouveau": (
        SESSION_RELECTURE_REF,
        (
            "aux réveils suivants, le skill n'est pas rendu à nouveau (« already loaded above »,"
            " mesuré le 2026-10-20, PR #141), donc le niveau ne se lit plus : se rapporte celui du"
            " premier rendu."
        ),
    ),
    "decision-du-mainteneur-a-l-emetteur": (
        SESSION_RELECTURE_REF,
        "ce qui s'y décide part par message à l'émetteur du dernier réveil",
    ),
    "config-securite-deux-prerequis": (
        ".claude/pipeline.config.md",
        (
            "Deux prérequis. Le répertoire courant = un worktree détaché sur la tête de la PR, que la"
            " session de relecture tient par construction"
        ),
    ),
    # I3, seconde passe : les morceaux prescriptifs que la première population laissait nus.
    "lue-par-la-session-pr": (
        SESSION_RELECTURE_REF,
        "Lue par la session PR à son go (`cycle-pr` Étape 1), à chaque passe de 4.2 et à son Étape 8",
    ),
    "ce-qu-elle-verifie-dans-relecteur": (
        SESSION_RELECTURE_REF,
        "Ce que la session vérifie et ce qu'elle rend sont dans `.claude/agents/relecteur.md`",
    ),
    "protocole-commun-dans-sessions-liees": (
        SESSION_RELECTURE_REF,
        (
            "ce qu'elle partage avec toute session liée — héritage, identité, messages, nettoyage — dans"
            " [sessions-liees.md](sessions-liees.md)"
        ),
    ),
    "go-du-briefing-en-lots-comme-hors-vague": (
        SESSION_RELECTURE_REF,
        (
            "le go du briefing est ce tour, en vague, en lots comme hors vague, et sa question nomme"
            " l'accord de démarrer la session et celui de l'archiver (`cycle-pr` Étape 1)"
        ),
    ),
    "le-parent-recoit-et-nettoie": (
        SESSION_RELECTURE_REF,
        "elle reçoit ses notes de fin de tour et ses messages, et la nettoie",
    ),
    "ne-charge-pas-task-observer": (
        SESSION_RELECTURE_REF,
        "Elle ne charge pas `task-observer` et n'écrit aucune entrée au journal",
    ),
    "en-attente-et-fin-de-tour": (SESSION_RELECTURE_REF, "Puis « en attente », et fin de tour."),
    "code-review-medium-seul-mesure": (
        SESSION_RELECTURE_REF,
        (
            "`/code-review medium <n> --comment` — `medium`, le seul niveau mesuré"
            " (`pipeline.config.md`, ligne « relecture »)"
        ),
    ),
    "securite-sinon-une-ligne": (SESSION_RELECTURE_REF, "sinon une ligne le dit"),
    "securite-diffe-le-trunk": (
        SESSION_RELECTURE_REF,
        "Elle diffe `origin/HEAD...`, donc le trunk",
    ),
    "mainteneur-peut-parler": (
        SESSION_RELECTURE_REF,
        "Le mainteneur peut lui parler dans sa fenêtre",
    ),
    "nettoyage-apres-la-fermeture": (
        SESSION_RELECTURE_REF,
        (
            "Après la fermeture de la boucle — relance faite, ou dernier constat traité s'il n'y en a"
            " pas —, et jamais avant"
        ),
    ),
    "relance-destinataire": (
        SESSION_RELECTURE_REF,
        "tant qu'une relance peut s'ouvrir, la session de relecture en est le destinataire",
    ),
    "branch-d-hors-jeu": (
        SESSION_RELECTURE_REF,
        "`git branch -d`, qui compare à `HEAD`, n'est plus en jeu (obs 86)",
    ),
    "repli-enchaine-dans-le-meme-tour": (
        SESSION_RELECTURE_REF,
        "leur fin de tour est alors la sienne, et elle enchaîne dans le même tour (obs 94, 98)",
    ),
    "repli-detache-isolation-d-abord": (
        SESSION_RELECTURE_REF,
        "le sous-agent s'y détache sur le SHA complet reçu, isolation vérifiée d'abord",
    ),
    "repli-reutilisation": (
        SESSION_RELECTURE_REF,
        "**Réutilisation.** Le même worktree sert aux deux passes et à la relance",
    ),
    "repli-verrou-initial-seulement": (
        SESSION_RELECTURE_REF,
        "Le verrou (`.git/worktrees/<id>/locked`) ne tient que pendant l'invocation initiale",
    ),
    "repli-branche-jamais-commitee": (
        SESSION_RELECTURE_REF,
        (
            "la branche naît sur le trunk et ne commite jamais, et `-d` refuse dès que le trunk a avancé"
            " (obs 86)"
        ),
    ),
    "repli-humain-si-pas-de-sous-agent": (
        SESSION_RELECTURE_REF,
        "Si le harness ne permet pas même le sous-agent",
    ),
    # Les renvois : chaque texte qui fait démarrer, réveiller ou nettoyer la session de relecture.
    "cycle-pr-question-du-go": (
        CYCLE_PR_SKILL,
        (
            "l'accord pour démarrer sa session de relecture et l'archiver à l'Étape 8 en fait partie,"
            " puisque `start_session` ne part que dans ce tour"
        ),
    ),
    "cycle-pr-go-d-une-session-de-lot": (
        BRIEFING_REF,
        "Une session de lot attend le go ci-dessous dans sa fenêtre comme toute session PR",
    ),
    "cycle-pr-sauf-go-delegue": (
        BRIEFING_REF,
        (
            "comme toute session PR, et y démarre sa session de relecture — sauf go délégué à la"
            " coordinatrice, qui lève l'attente et passe la relecture au repli `relecteur`"
        ),
    ),
    "cycle-pr-echec-de-porte-jamais-silencieux": (
        CYCLE_PR_SKILL,
        "se dit dans « Relecture indépendante » du body, jamais en saut silencieux (obs 84)",
    ),
    "cycle-pr-passe-1-ne-lit-que-le-brief": (
        CYCLE_PR_SKILL,
        "À la première passe, celle-ci ne lit **que** le corps de l'issue",
    ),
    "cycle-pr-seconde-passe-a-la-meme-session": (
        CYCLE_PR_SKILL,
        "jamais à une session ni à un agent neufs",
    ),
    "cycle-pr-jamais-l-arbre-de-la-session-pr": (
        CYCLE_PR_SKILL,
        "**Un worktree de relecture par PR, jamais l'arbre de la session PR.**",
    ),
    "cycle-pr-pousser-avant-chaque-reveil": (CYCLE_PR_SKILL, "**Pousser avant chaque réveil**"),
    # Attente de la CI (décision du mainteneur, 2026-10-20) : le moniteur ne réveille pas sur un
    # succès, mesuré — attendre, borné, par une commande de fond dont la fin réveille la session ;
    # cette commande est `attente-ci.py` depuis le lot 4b de #134, son délai par défaut celui de
    # l'intérim, que `test_attente_ci.py` épingle côté script.
    "cycle-pr-attendre-la-ci": (
        CYCLE_PR_SKILL,
        (
            "**l'attend** avant de passer à la suite, par une commande lancée en fond, dont la fin"
            " réveille la session"
        ),
    ),
    "cycle-pr-attente-bornee": (CYCLE_PR_SKILL, "bornée : 1800 s par défaut"),
    "cycle-pr-appel-d-attente-ci": (
        CYCLE_PR_SKILL,
        "python <répertoire de ce skill>/scripts/attente-ci.py <numéro>",
    ),
    "cycle-pr-delai-depasse": (
        CYCLE_PR_SKILL,
        "sortie 124, délai dépassé : Étape 6, « CI qui ne démarre pas »",
    ),
    "cycle-pr-jamais-une-fin-de-tour-nue": (
        CYCLE_PR_SKILL,
        (
            "Jamais une fin de tour nue : le moniteur de PR de l'application ne réveille que sur un"
            " échec, un conflit ou un commentaire"
        ),
    ),
    "cycle-pr-seule-surveillance-de-la-ci": (
        CYCLE_PR_SKILL,
        (
            "C'est la seule surveillance de la CI que la session lance elle-même, le moniteur ne"
            " couvrant pas le succès ; jamais une sonde planifiée"
        ),
    ),
    "cycle-pr-nettoyage-a-l-etape-8": (
        CYCLE_PR_SKILL,
        "Puis **nettoyer la session de relecture**",
    ),
    "coordinatrice-jamais-parente-de-la-relecture": (
        COORDINATRICE_REF,
        (
            "jamais la coordinatrice, qui serait réveillée à chaque fin de tour de la session de"
            " relecture pour rien"
        ),
    ),
    "pr-paralleles-le-lead-ne-demarre-aucune-relecture": (
        PR_PARALLELES_SKILL,
        "Le lead ne démarre aucune session de relecture : chaque session PR démarre la sienne",
    ),
    "pr-paralleles-brief-relecture-a-la-session": (
        PR_PARALLELES_SKILL,
        "c'est toi qui la démarres, la réveilles et la nettoies",
    ),
    "pr-paralleles-retrait-par-la-session-pr-seule": (
        PR_PARALLELES_SKILL,
        "Seule la session PR qui l'a démarré ou lancé le retire",
    ),
    "prompt-lot-suivant-relecture-a-la-session": (
        PROMPT_LOT_SUIVANT,
        "c'est toi qui la démarres, la réveilles et la nettoies",
    ),
    "prompt-lot-suivant-relais-et-relecture": (
        PROMPT_LOT_SUIVANT,
        "tu la réveilles par message, et elle répond à l'émetteur du réveil",
    ),
    "sessions-liees-forme-des-constats": (
        SESSIONS_LIEES_REF,
        "Une session de relecture rend ses constats sous la forme de",
    ),
    # D-10 : préparer la vague et la conduire sont deux sessions.
    "pr-paralleles-preparation-se-termine": (
        PR_PARALLELES_SKILL,
        "la préparation **se termine** : préparer la vague et la conduire sont deux sessions",
    ),
    "pr-paralleles-lead-neuf-avec-la-seule-liste": (
        PR_PARALLELES_SKILL,
        "brief : le skill `pr-paralleles` invoqué avec cette seule liste en argument",
    ),
    "pr-paralleles-lead-detache-de-la-preparation": (
        PR_PARALLELES_SKILL,
        "son premier geste le détache d'elle (`detach_session` sur `self`)",
    ),
    "contributing-deux-sessions": (
        "CONTRIBUTING.md",
        "un lead neuf la conduit — préparer et conduire sont deux sessions",
    ),
    # E7 : la mesure, une fois, dans la source ; les trois autres textes y renvoient.
    "sessions-liees-reception-en-fin-de-tour": (
        SESSIONS_LIEES_REF,
        (
            "ne le reçoit qu'à la fin de ce tour, comme un tour neuf — jamais à son appel d'outil"
            " suivant. Un message n'interrompt donc jamais un tour en cours."
        ),
    ),
    "cycle-pr-message-du-lead-en-fin-de-tour": (
        BRIEFING_REF,
        "son message n'arrive qu'à la fin du tour en cours (même référence, « Messages »)",
    ),
    "pr-paralleles-signalement-en-fin-de-tour": (
        PR_PARALLELES_SKILL,
        (
            "elle ne le reçoit qu'à la fin de son tour en cours"
            " (`.claude/skills/cycle-pr/references/sessions-liees.md`, « Messages », mesuré)"
        ),
    ),
    "coordinatrice-message-de-lot-en-fin-de-tour": (
        COORDINATRICE_REF,
        "attend la fin de ce tour (même référence)",
    ),
}


@pytest.mark.parametrize(
    ("fichier", "phrase"),
    INVARIANTS_DE_LA_SESSION_DE_RELECTURE.values(),
    ids=INVARIANTS_DE_LA_SESSION_DE_RELECTURE.keys(),
)
def test_chaque_invariant_de_la_session_de_relecture_garde_sa_phrase(
    fichier: str, phrase: str
) -> None:
    """Même lecture que les invariants des sessions liées : texte aux espaces normalisés."""
    assert phrase in texte_normalise(fichier), f"`{fichier}` ne porte plus « {phrase} »"


# L'ordre d'un réveil : les commandes avant le protocole du `relecteur`, qui n'a plus à chercher ce
# qu'une commande a trouvé (`cycle-pr` 4.2, « Les portes bon marché d'abord »), et le message de
# constats en dernier — c'est lui qui réveille la session PR. **Population** : les 5 étapes
# numérotées du réveil, 4 couples consécutifs.
ORDRE_DU_REVEIL = {
    "verifications-avant-code-review": (
        "1. Les deux vérifications de `relecteur.md`",
        "2. `/code-review medium <n> --comment`",
    ),
    "code-review-avant-security-review": (
        "2. `/code-review medium <n> --comment`",
        "3. `/security-review`, **seulement**",
    ),
    "security-review-avant-le-protocole": (
        "3. `/security-review`, **seulement**",
        "4. Le protocole de `relecteur.md` sur la plage",
    ),
    "protocole-avant-le-message": (
        "4. Le protocole de `relecteur.md` sur la plage",
        "5. Le message de constats à l'émetteur du réveil",
    ),
}


@pytest.mark.parametrize(("avant", "apres"), ORDRE_DU_REVEIL.values(), ids=ORDRE_DU_REVEIL.keys())
def test_la_session_de_relecture_garde_l_ordre_de_son_reveil(avant: str, apres: str) -> None:
    """Les deux ancres présentes, et dans cet ordre — une ancre absente rougit aussi."""
    assert_dans_l_ordre(SESSION_RELECTURE_REF, avant, apres)


def morceaux_du_texte(texte: str) -> list[str]:
    """Le texte découpé après chaque `.`, `;` ou `:` suivi d'un blanc, hors du code en ligne.

    Un passage entre accents graves n'est jamais coupé : `name: relecture-pr-<n>` reste un seul
    morceau. Les morceaux vides sont retirés.
    """
    morceaux: list[str] = []
    courant = ""
    for rang, bout in enumerate(re.split(r"(`[^`]*`)", texte)):
        if rang % 2:
            courant += bout
            continue
        parties = re.split(r"(?<=[.;:])\s+", bout)
        courant += parties[0]
        for partie in parties[1:]:
            morceaux.append(courant)
            courant = partie
    morceaux.append(courant)
    return [morceau.strip() for morceau in morceaux if morceau.strip()]


# Les morceaux du protocole qui ne prescrivent rien, par catégorie, en littéraux : un intitulé, un
# motif, un relevé daté. Tout autre morceau tient une ancre.
MORCEAUX_SANS_PRESCRIPTION: dict[str, list[str]] = {
    "intitulé": [
        "**Premier geste de la session de relecture** :",
        "La plage :",
        "Paramètres de `start_session` :",
        "À chaque réveil, dans cet ordre :",
    ],
    "motif": [
        "Une session, et non un sous-agent, pour trois raisons :",
        "le mainteneur la **joint** dans sa fenêtre ;",
        (
            "ses commandes intégrées, `/code-review` et `/security-review`, closent **son** tour et non"
            " celui de la session PR (obs 94, 98, 115) ;"
        ),
        "son contexte tient les deux passes et la relance.",
        "un autre parent serait réveillé à chaque fin de tour de la session de relecture pour rien.",
        "la tête bouge entre deux passes.",
        "C'est sans coût ici :",
        "un constat se rapporte.",
        "un agent repris peut reprendre dans l'arbre vivant de la session PR.",
    ],
    "relevé daté": [
        "Mesuré le 2026-10-20 sur la PR #141 :",
        (
            "`get_session` rend un worktree sous `.claude/worktrees/<slug>`, la branche"
            " `claude/<slug>`, la `sourceBranch` demandée et le parent."
        ),
        "la seconde l'a clos, la première non.",
        "Ce qu'elle rapporte à nouveau à la passe 2, sur une PR qu'elle a déjà commentée :",
        "non mesuré.",
        "non mesuré).",
    ],
}


def test_chaque_morceau_du_protocole_tient_une_ancre() -> None:
    """Le dénombrement de la population sort d'ici, jamais d'un commentaire.

    Un morceau tient une ancre quand une phrase de `INVARIANTS_DE_LA_SESSION_DE_RELECTURE` sur ce
    fichier, ou de `ORDRE_DU_REVEIL`, le contient, ou qu'il la contient. Les morceaux nus doivent être exactement
    ceux de `MORCEAUX_SANS_PRESCRIPTION` : un énoncé ajouté sans ancre rougit, une exemption
    périmée aussi. **Borne** : un morceau tenu en partie — il contient une ancre plus courte que
    lui — n'est gardé que sur elle, le reste peut changer en vert ; c'est le cas de la plupart, dont
    beaucoup ne perdent que leur ponctuation. Les prescriptions qu'une mutation partielle a laissées
    vertes (relance de la PR #141 : reprise à l'étape suivante, outil de rapport de `/code-review`,
    repli humain avec le diff) sont ancrées en entier, comme toute ancre qui ferme la classe.
    """
    ancres = [
        phrase
        for fichier, phrase in INVARIANTS_DE_LA_SESSION_DE_RELECTURE.values()
        if fichier == SESSION_RELECTURE_REF
    ]
    ancres += [ancre for couple in ORDRE_DU_REVEIL.values() for ancre in couple]
    nus = {
        morceau
        for morceau in morceaux_du_texte(texte_normalise(SESSION_RELECTURE_REF))
        if not any(ancre in morceau or morceau in ancre for ancre in ancres)
    }
    exemptes = {morceau for liste in MORCEAUX_SANS_PRESCRIPTION.values() for morceau in liste}

    assert nus == exemptes, (
        f"sans ancre ni exemption : {sorted(nus - exemptes)} ; exemptions périmées :"
        f" {sorted(exemptes - nus)}"
    )


def test_le_decoupage_ne_coupe_pas_le_code_en_ligne() -> None:
    """Témoin du découpage : un `:` dans le code reste dans son morceau, un `;` de prose coupe."""
    assert morceaux_du_texte("Paramètres : `name: x` ; puis la suite.") == [
        "Paramètres :",
        "`name: x` ;",
        "puis la suite.",
    ]


# Ce que le lot 3 retire, et qui ne doit pas revenir. Chaque forme a été vue présente sur
# `c92fcf5`, la base du lot, où chaque cas rougit.
RETIRES_PAR_LA_SESSION_DE_RELECTURE = {
    # `/security-review` prescrit des sous-tâches (critère 4 du bloc : 1 occurrence au 2026-10-20).
    "relecteur-pas-de-sous-agent": (RELECTEUR_ROLE, "pas de sous-agent"),
    # D-10 (critère 1 du bloc : 2 lignes au 2026-10-20, une par fichier).
    "preparation-devient-le-lead": (PR_PARALLELES_SKILL, "devient le lead"),
    "contributing-meme-session-sur-la-vague": ("CONTRIBUTING.md", "enchaîne sur la vague"),
    # E7 (critère 6 du bloc : 5 lignes dans 4 fichiers au 2026-10-20 ; les deux de `fin de ce
    # tour`, dans `sessions-liees.md` et `coordinatrice.md`, disent vrai et restent).
    "cycle-pr-arret-apres-l-outil-en-cours": (CYCLE_PR_SKILL, "après l'outil en cours"),
    "pr-paralleles-arret-apres-l-outil-en-cours": (PR_PARALLELES_SKILL, "après l'outil en cours"),
    "pr-paralleles-messages-entre-deux-appels": (
        PR_PARALLELES_SKILL,
        "entre deux appels d'outils",
    ),
}


@pytest.mark.parametrize(
    ("fichier", "forme"),
    RETIRES_PAR_LA_SESSION_DE_RELECTURE.values(),
    ids=RETIRES_PAR_LA_SESSION_DE_RELECTURE.keys(),
)
def test_rien_de_ce_que_retire_la_session_de_relecture_ne_reste(fichier: str, forme: str) -> None:
    """Une phrase retirée qui reste écrite se rejoue : la session suit le texte, pas l'intention."""
    assert not porte_la_forme(fichier, forme), f"`{fichier}` porte encore « {forme} »"


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
RENVOIS_AUX_BARREAUX = {
    CONTRAINTES_RULE: [4],
    BUG_VERS_ISSUE_SKILL: [1, 3],
    CONTRADICTION_SKILL: [2, 4],
    CYCLE_PR_SKILL: [3, 2, 3, 2],
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
