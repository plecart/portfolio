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
import subprocess
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

# Les **trois** formes sous lesquelles un renvoi vers un script de skill apparaît :
#
# 1. **relative** (`<répertoire de ce skill>/scripts/x.py`, ou `scripts/x.py` nu) — la forme des
#    fichiers d'un skill, qui est recopié dans le seed où son chemin absolu diffère ; elle se
#    résout contre le dossier du skill qui porte le fichier citant ;
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
    r"(?:\.claude/skills/(?P<skill>[\w-]+)/|<répertoire de ce skill>/|(?P<prefix>[\w.-]+)/)?"
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
    if skill := reference.group("skill"):
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
    """**Dénombrement de la classe** : 3 formes en 5 orthographes, 4 globs, 9 témoins.

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

# Les skills maison qui ne délèguent encore à personne, chacun avec le lot de #134 qui l'en sort :
# au 2026-10-20 sur `e70e279`, onze, dont `init-projet`, qui ne nomme les cinq rôles que dans sa
# liste de fichiers ; dix au 2026-10-23 sur `34604c7` (lot 6a2, bloc 1), qui en sort `triage` ;
# sept au commit suivant (bloc 2), qui en sort `interroge-moi`, `vers-prd` et `vers-issues` ; six
# au 2026-10-23 (lot 6b, bloc 1), qui en sort `repercussions` ; quatre au 2026-10-25 (lot 6b2),
# qui en sort `bug-vers-issue` et `contradiction`. La liste se vide lot par lot ; #134 l'exige vide.
EXECUTOR_WAITING_LIST = {
    "plan-qa": "7a",
    "execution-qa": "7b",
    "audit-spec-ui": "8",
    "init-projet": "8",
}


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
    liste de fichiers d'`init-projet`, qui nomme tous les rôles, n'est jamais comptée."""
    assert skills_citing("fantome") == []
    assert not [
        role for role in ROLE_NAMES if ".claude/skills/init-projet/SKILL.md" in skills_citing(role)
    ]
    init_projet = (REPOSITORY_ROOT / ".claude/skills/init-projet/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert ROLE_FILE_LIST.search(init_projet), (
        "la liste de fichiers d'`init-projet` a changé de forme : `ROLE_FILE_LIST` ne la voit plus"
    )
    assert not cites_an_executor(skill_prose("init-projet"), ROLE_NAMES)


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


@pytest.mark.parametrize(
    "skill", [skill for skill in HOUSE_SKILLS if skill not in EXECUTOR_WAITING_LIST]
)
def test_chaque_skill_maison_nomme_ses_executants(skill: str) -> None:
    """Second paramétrage de D5 : un skill maison hors liste d'attente nomme un rôle ou un script.

    Au 2026-10-20 sur `e70e279`, deux sur treize (`cycle-pr`, `pr-paralleles`) ; trois au
    2026-10-23 sur `34604c7` avec `triage` (lot 6a2, bloc 1), six au commit suivant avec
    `interroge-moi`, `vers-prd` et `vers-issues` (bloc 2), sept le 2026-10-23 avec `repercussions`
    (lot 6b, bloc 1), neuf le 2026-10-25 avec `bug-vers-issue` et `contradiction` (lot 6b2) ; les
    quatre autres — `plan-qa`, `execution-qa`, `audit-spec-ui`, `init-projet` — sont dans
    `EXECUTOR_WAITING_LIST` avec le lot qui les en sort.
    """
    assert cites_an_executor(skill_prose(skill), ROLE_NAMES), (
        f"`{skill}` ne nomme aucun rôle ni aucun script, et n'est pas en liste d'attente"
    )


@pytest.mark.parametrize("skill", EXECUTOR_WAITING_LIST, ids=EXECUTOR_WAITING_LIST.keys())
def test_un_skill_en_liste_d_attente_ne_nomme_encore_aucun_executant(skill: str) -> None:
    """Le cliquet : un skill qui se met à déléguer sort de la liste d'attente dans le même commit,
    sinon son entrée l'exempterait en silence du test précédent."""
    assert not cites_an_executor(skill_prose(skill), ROLE_NAMES), (
        f"`{skill}` nomme un exécutant : retire-le d'`EXECUTOR_WAITING_LIST` "
        f"(lot {EXECUTOR_WAITING_LIST[skill]} de #134)"
    )


# Les skills dont la prose n'écrit plus sur la forge que par l'écriture distante relue (#134,
# lot 4) : chaque lot de #134 y ajoute les siens — le lot 6a2 `triage`, `interroge-moi`, `vers-prd`
# et `vers-issues` ; le lot 6b `repercussions` (bloc 1) ; le lot 6b2 `bug-vers-issue` et
# `contradiction` ; les lots 7a à 8 les leurs.
SKILLS_SANS_ECRITURE_GH_DIRECTE = (
    "triage",
    "interroge-moi",
    "vers-prd",
    "vers-issues",
    "repercussions",
    "bug-vers-issue",
    "contradiction",
)
ECRITURE_RELUE = ".claude/skills/cycle-pr/scripts/ecriture-relue.py"
# Les skills de la table précédente qui n'écrivent sur aucune issue, chacun avec sa raison : le
# renvoi au script y serait sans objet (lot 6b2 de #134, 2026-10-25).
ECRITURE_RELUE_SANS_OBJET = {
    "contradiction": (
        "n'écrit sur aucune issue : ses PR d'amendement suivent les étapes 5 et 6 de"
        " `triage/hors-scope.md`, et la propagation aux issues passe par `repercussions`"
    ),
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
    `bug-vers-issue` deux (`gh issue create`, `gh label create`), `contradiction` aucune.

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
# ailleurs : les renvois (`SKILLS_DES_SESSIONS_LIEES`, neuf au 2026-10-25), le point de départ
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
TRIAGE_SKILL = ".claude/skills/triage/SKILL.md"
HORS_SCOPE_REF = ".claude/skills/triage/hors-scope.md"
RELEVEUR_ROLE = ".claude/agents/releveur.md"
VERS_PRD_SKILL = ".claude/skills/vers-prd/SKILL.md"
VERS_ISSUES_SKILL = ".claude/skills/vers-issues/SKILL.md"
REPERCUSSIONS_SKILL = ".claude/skills/repercussions/SKILL.md"
CONTRADICTION_SKILL = ".claude/skills/contradiction/SKILL.md"
BUG_VERS_ISSUE_SKILL = ".claude/skills/bug-vers-issue/SKILL.md"
COLLECTE_CONTEXTE_REF = ".claude/skills/bug-vers-issue/references/collecte-contexte.md"
GABARIT_BUG_REF = ".claude/skills/bug-vers-issue/references/gabarit-issue-bug.md"
GABARIT_DECOUPAGE_REF = ".claude/skills/bug-vers-issue/references/gabarit-issue-decoupage.md"
THEMES_MILESTONES_REF = ".claude/skills/triage/themes-milestones.md"
BRIEF_AGENT_REF = ".claude/skills/triage/brief-agent.md"
PATCH_CHECKBOX_REF = ".claude/skills/execution-qa/references/patch-checkbox-gh.md"
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
        CYCLE_PR_SKILL,
        "un message du lead n'est jamais une approbation",
    ),
    "lead-designe-par-le-prompt": (
        CYCLE_PR_SKILL,
        "est la session que ce prompt désigne comme tel, à défaut l'émettrice",
    ),
    "en-tete-sans-confirmation": (
        CYCLE_PR_SKILL,
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
        CYCLE_PR_SKILL,
        "la session devient la **coordinatrice** de ses lots",
    ),
    "issue-a-un-lot-inchangee": (
        CYCLE_PR_SKILL,
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
        CYCLE_PR_SKILL,
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
        CYCLE_PR_SKILL,
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
        CYCLE_PR_SKILL,
        "pour une session de lot, celle que son brief nomme, ou aucune",
    ),
    "go-du-briefing-humain": (
        COORDINATRICE_REF,
        "**Le go du briefing est humain, dans la fenêtre de la session de lot**",
    ),
    "go-du-briefing-toujours-un-arret": (
        COORDINATRICE_REF,
        "Elle s'arrête donc toujours à son Étape 1",
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
        "le lead démarre d'un coup une session par issue retenue, une par `start_session`",
    ),
    "demarrage-au-seul-tour-du-mainteneur": (
        PR_PARALLELES_SKILL,
        "Dans le tour où le mainteneur valide le lot (étape 2), et dans celui-là seulement",
    ),
    "start-session-d-une-issue": (
        PR_PARALLELES_SKILL,
        "`context: fresh`, worktree de l'application, `wake_when_done: true`, `name: issue-<N>`",
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
        "le nom et le `local_…` que `start_session` a rendu",
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
}


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
# le mot, et `bug-vers-issue` ne démarre aucune session — 20 sites. Un site nouveau n'entre pas ici
# de lui-même : la garde lit des phrases, le grep re-dérive la population.
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
        "`use_worktree: false` — elle lit le code et n'écrit que dans GitHub —, `name: interroge-<N>`",
    ),
    "interroge-moi-vers-le-tri-du-brief": (
        INTERROGE_MOI_SKILL,
        "`use_worktree: false`, `name: triage-<N>`",
    ),
    "vers-prd-vers-vers-issues": (
        VERS_PRD_SKILL,
        "`use_worktree: false`, `name: vers-issues-<n>`",
    ),
    "themes-milestones-vers-init-projet": (
        THEMES_MILESTONES_REF,
        "démarrée avec `use_worktree: true` : elle écrit sur une branche",
    ),
    "repercussions-vers-contradiction": (
        REPERCUSSIONS_SKILL,
        "`use_worktree: true`, `name: contradiction-<N>`",
    ),
    "repercussions-vers-contradiction-par-carte": (
        REPERCUSSIONS_SKILL,
        (
            "hors d'un tour du mainteneur, une carte de proposition (`initiation: own_initiative`,"
            " `context: fresh`, `use_worktree: true`, même nom et même prompt)"
        ),
    ),
    "repercussions-vers-plan-qa": (
        REPERCUSSIONS_SKILL,
        "`use_worktree: true`, `name: plan-qa-<slug du thème>`",
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
            " `context: fresh`, `use_worktree: true`, même nom et même prompt)"
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
        ".claude/rules/contraintes.md",
        "Un `developpeur` ne la pose pas : il note son hypothèse et rend la `[V]` dans son rapport",
    ),
    "porteur-voie-v-executant-et-releveur": (
        ".claude/rules/contraintes.md",
        "`executant` et `releveur` ne classent aucune question, ils remontent tout choix",
    ),
    "porteur-voie-c": (
        ".claude/rules/contraintes.md",
        "Un `developpeur` s'arrête et remonte les deux citations",
    ),
    "porteur-explorer-plutot-que-demander": (
        ".claude/rules/contraintes.md",
        (
            "par un `releveur` pour un relevé, l'`executant` pour une cartographie (`cycle-pr`"
            " Étape 1), la conclusion restant à la session"
        ),
    ),
    "porteur-creation-d-issues": (
        ".claude/rules/contraintes.md",
        "un sous-agent n'ouvre ni issue ni brouillon, le `developpeur` remonte le vide dans son rapport",
    ),
    "porteur-ecritures-distantes": (".claude/rules/contraintes.md", "La relecture est à qui écrit"),
    "porteur-maintenance-continue": (
        ".claude/rules/contraintes.md",
        "l'auteur du commit — le `developpeur` pour la doc descriptive de son bloc",
    ),
    "porteur-maintenance-amendement-reste-a-la-session": (
        ".claude/rules/contraintes.md",
        "l'amendement d'une source de vérité reste à la session de dialogue",
    ),
    "porteur-points-d-arret-humains": (
        ".claude/rules/contraintes.md",
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
            "un `developpeur` neuf par bloc : TDD red-green-refactor, cycle `modif → test → cleanup"
            " → test → commit` (relecture à contexte vierge au socle, par la session de relecture que"
            " la session PR démarre à son go) → cleanup holistique par un `developpeur` neuf →"
            " relecture à contexte vierge finale, par la même session"
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
    # l'est aussi. Gardés ailleurs : la sortie de liste d'attente (`EXECUTOR_WAITING_LIST`),
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
            "Avec une PR d'amendement — une PR mergée qui amende une source de vérité sans fermer"
            " d'issue, ouverte par une `contradiction` née d'une décision, sans issue fermée à"
            " l'origine —, le delta réel est l'amendement"
        ),
    ),
    "6b-repercussions-amendement-sans-qa": (REPERCUSSIONS_SKILL, "l'étape 7 est sans objet"),
    "6b-repercussions-journal-de-l-amendement": (
        REPERCUSSIONS_SKILL,
        "la ligne de journal cite l'amendement, pas une issue fermée",
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
            " `name: contradiction-<N>`, prompt `/contradiction` suivi du bloc d'arrêt — ses deux"
            " citations — et de `origine : #<N>`"
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
    # consignes par sortie : `SORTIES_D_UNE_CONTRADICTION_D_ORIGINE`.
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
    # Relecture de la PR #153, passe 1, CR2. Dénombrement (noms de session dérivés d'un texte
    # libre), `grep -rno "name: [a-z-]*<[^>]*>" .claude/skills` : **12** sites au 2026-10-23,
    # **1** fuyait (`plan-qa-<thème>`) ; les autres prennent un numéro, `coordinatrice.md` un
    # `<slug>`.
    "6b-repercussions-session-plan-qa": (
        REPERCUSSIONS_SKILL,
        (
            "`start_session`, `initiation: user_asked`, `context: fresh`, `use_worktree: true`,"
            ' `name: plan-qa-<slug du thème>`, prompt `/plan-qa "<thème>"` — `start_session` borne'
            " un nom à `[a-z0-9-]` et 24 caractères (description de l'outil, lue le 2026-10-23)"
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
    # premier jet, 4 au cleanup du bloc, vues rouges. Gardés ailleurs : la sortie de liste d'attente
    # (`EXECUTOR_WAITING_LIST`), l'absence d'écriture `gh` directe, le renvoi au script et son
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
    "6b2-contradiction-quatre-gestes-un-commit": (
        CONTRADICTION_SKILL,
        "La table des édits porte, dans le même commit, ces quatre gestes",
    ),
    "6b2-hors-scope-nomme-contradiction": (
        HORS_SCOPE_REF,
        (
            "ses étapes 5 et 6 valent pour toute PR qu'ouvre une session de `triage`,"
            " `interroge-moi`, `vers-prd` ou `contradiction`, qui y renvoient"
        ),
    ),
    "6b2-contradiction-mode-sans-copie": (
        CONTRADICTION_SKILL,
        "« PR d'amendement ») : ce skill ne le recopie pas",
    ),
    "6b2-contradiction-rien-a-demarrer-en-session-pr": (
        CONTRADICTION_SKILL,
        (
            "la passe `repercussions` de `cycle-pr` Étape 8 le confronte aux issues — rien à"
            " démarrer ici"
        ),
    ),
    # Relecture de la PR #155, passe 2, I1 : la relance part à la sortie, plus au seul merge d'un
    # amendement. La relance avec origine et sa table : `SORTIES_D_UNE_CONTRADICTION_D_ORIGINE`.
    "6b2-contradiction-repercussions-au-tour-de-la-sortie": (
        CONTRADICTION_SKILL,
        (
            "**Hors PR**, dans le tour du mainteneur où la sortie est connue, démarrer la session"
            " `repercussions`"
        ),
    ),
    "6b2-contradiction-repercussions-sans-origine": (
        CONTRADICTION_SKILL,
        (
            "**sans origine** : à la seule sortie qui amende, au merge de sa PR,"
            " `name: repercussions-<m>`, prompt `/repercussions #<m>`, où `<m>` est le numéro de la"
            " PR d'amendement"
        ),
    ),
    "6b2-contradiction-rend-la-passe-quelle-que-soit-la-sortie": (
        CONTRADICTION_SKILL,
        "et, démarré par une passe `repercussions`, la fait reprendre quelle que soit la sortie",
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
            "« Construire le patch en mémoire » et « Détecter les éditions concurrentes » — leurs"
            " règles de correspondance seules : sa lecture et son push sont ceux de cette étape"
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
            " sous la forme « terminé — BUG #<N> consigné » — la fin du tour ne le prévient pas"
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
    "6b2-cycle-pr-bug-vers-issue-nomme-la-famille": (
        CYCLE_PR_SKILL,
        (
            "`triage`, `interroge-moi`, `vers-prd`, `vers-issues`, `repercussions` et"
            " `bug-vers-issue` les nomment ; les skills des lots 7a à 8 de #134 les nommeront"
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
REECRITURES_DE_CORPS = {
    "bug-vers-issue-delegation-renvoi": BUG_VERS_ISSUE_SKILL,
    "bug-vers-issue-etape-7-lu-par-la-session": BUG_VERS_ISSUE_SKILL,
    "bug-vers-issue-erreurs-courantes-renvoi": BUG_VERS_ISSUE_SKILL,
    "cycle-pr-append-lu-par-le-script-hors-perimetre": CYCLE_PR_SKILL,
    "patch-checkbox-push-hors-perimetre-lot-7b": PATCH_CHECKBOX_REF,
    "patch-checkbox-etag-mention": PATCH_CHECKBOX_REF,
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
RETIRES_DU_CONTEXTE_VIVANT = {
    "contradiction-conversation": (CONTRADICTION_SKILL, "conversation"),
    "bug-vers-issue-conversation": (BUG_VERS_ISSUE_SKILL, "conversation"),
    "collecte-contexte-conversation": (COLLECTE_CONTEXTE_REF, "conversation"),
    "gabarit-issue-bug-conversation": (GABARIT_BUG_REF, "conversation"),
    "gabarit-issue-decoupage-conversation": (GABARIT_DECOUPAGE_REF, "conversation"),
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
}


@pytest.mark.parametrize(
    ("fichier", "forme"),
    RETIRES_DU_CONTEXTE_VIVANT.values(),
    ids=RETIRES_DU_CONTEXTE_VIVANT.keys(),
)
def test_le_contexte_vivant_retire_ne_revient_pas(fichier: str, forme: str) -> None:
    """Une forme retirée qui reste écrite se rejoue : la session suit le texte, pas l'intention."""
    assert not porte_la_forme(fichier, forme), f"`{fichier}` porte encore « {forme} »"


def test_la_conversation_est_gardee_dans_chaque_fichier_des_deux_skills() -> None:
    """Un fichier ajouté à `contradiction` ou à `bug-vers-issue` rougit ici tant que la table ne
    garde pas le mot chez lui : le critère « 6a, 6b » lit le dossier entier."""
    gardes = {
        fichier for fichier, forme in RETIRES_DU_CONTEXTE_VIVANT.values() if forme == "conversation"
    }
    dossiers = {
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for skill in ("contradiction", "bug-vers-issue")
        for path in (REPOSITORY_ROOT / ".claude/skills" / skill).rglob("*")
        if path.is_file()
    }

    assert gardes == dossiers


# --- Chaque sortie d'une `contradiction` d'origine fait reprendre sa passe (#134, lot 6b2) -------

# La relance que `contradiction` étape 5 doit à chaque sortie quand `repercussions` l'a démarrée,
# puis le cas sans origine, qui suit la table des sorties dans le texte.
RELANCE_AVEC_ORIGINE = (
    "**avec `origine : #<N>`** reçue à l'étape 1, à **chaque** sortie, pas seulement à celle qui"
    " amende — la passe de `#<N>` s'est arrêtée avant son étape 2 et rien d'autre ne la reprend :"
    " `name: repercussions-<N>`, prompt `/repercussions #<N>` suivi du bloc d'arrêt reçu et de la"
    " ligne `contradiction soldée : <sortie>` de la table"
)
RELANCE_SANS_ORIGINE = "**sans origine**"
# L'arrêt de `repercussions` étape 1 : la consigne d'une ligne `contradiction soldée` se lit avant
# lui, sinon la session redémarrée relève l'arrêt soldé avant de la lire (obs 30).
ARRET_DE_REPERCUSSIONS = "Une contradiction avérée → **s'arrêter avant l'étape 2**"
# Les deux consignes de `repercussions` étape 1 : l'effet mergé qu'un document gagnant laisse en
# place se trace, puis la passe suit ; sinon elle suit directement.
REPRISE_APRES_TRACE = (
    "Avec `document gagne`, suivi ou non de `— PR #<m>`, l'effet mergé qui contredit le document"
    " est un **vide à tracer**"
)
REPRISE_DIRECTE = "Avec `amendement PR #<m>` ou `écartée — <raison>`, elles suivent directement"
# Une entrée par sortie, en littéraux (obs 80) : sa ligne de la table de `contradiction` étape 5 —
# tour de la relance, ligne `contradiction soldée`, message de fin —, puis sa consigne de reprise.
# Une table plutôt que des épingles groupées : chaque sortie y garde son texte entier sous son id,
# et l'autre sens — une ligne de la table du skill sans entrée ici — se compte contre elle.
SORTIES_D_UNE_CONTRADICTION_D_ORIGINE = {
    "1-amendement-merge": (
        (
            "| amendement mergé | son merge | `contradiction soldée : amendement PR #<m>` |"
            " « terminé — amendement PR #<m> mergé » |"
        ),
        REPRISE_DIRECTE,
    ),
    "2-document-gagne-effet-abandonne": (
        (
            "| document gagne, effet abandonné | la décision de l'étape 3 | `contradiction soldée :"
            " document gagne` | « terminé — aucune PR, le document gagne » |"
        ),
        REPRISE_APRES_TRACE,
    ),
    "3-document-gagne-effet-deplace-par-une-pr": (
        (
            "| document gagne, effet déplacé dans le dépôt par une PR | son merge | `contradiction"
            " soldée : document gagne — PR #<m>` | « terminé — PR #<m> mergée, le document gagne » |"
        ),
        REPRISE_APRES_TRACE,
    ),
    "4-document-gagne-effet-deplace-hors-du-depot": (
        (
            "| document gagne, effet déplacé hors du dépôt | la décision de l'étape 3 |"
            " `contradiction soldée : document gagne` | « terminé — aucune PR, le document gagne » |"
        ),
        REPRISE_APRES_TRACE,
    ),
    "5-contradiction-ecartee": (
        (
            "| pas de contradiction | son constat | `contradiction soldée : écartée — <raison>` |"
            " « terminé — contradiction écartée » |"
        ),
        REPRISE_DIRECTE,
    ),
}


@pytest.mark.parametrize(
    ("ligne", "reprise"),
    SORTIES_D_UNE_CONTRADICTION_D_ORIGINE.values(),
    ids=SORTIES_D_UNE_CONTRADICTION_D_ORIGINE.keys(),
)
def test_chaque_sortie_d_une_contradiction_d_origine_fait_reprendre_sa_passe(
    ligne: str, reprise: str
) -> None:
    """Relecture de la PR #155, passe 2, I1. Classe : une sortie de `contradiction` démarrée avec
    `origine : #<N>` qui ne fait pas reprendre la passe de `#<N>`, arrêtée par `repercussions`
    « avant l'étape 2 ». Dénombrées par la session PR sur `02c513b`, avant le correctif : **5**
    sorties, **4** fuyaient.

    1. Amendement mergé — redémarrait la passe.
    2. Le document gagne, effet abandonné (`decisions-vs-doc`, sortie 1a) — fuyait.
    3. Le document gagne, effet déplacé dans le dépôt par une PR (1b) — fuyait : ce n'est pas une
       PR d'amendement, et « terminé — amendement PR #<m> mergé » l'aurait nommée à tort.
    4. Le document gagne, effet déplacé hors du dépôt (1b) — fuyait.
    5. Pas de contradiction après vérification, « On se tait » — fuyait.

    Chaque sortie a sa ligne dans la table de l'étape 5, sous la relance `repercussions-<N>` et
    avant le cas sans origine, et sa consigne dans `repercussions` étape 1, avant l'arrêt.
    """
    assert_dans_l_ordre(CONTRADICTION_SKILL, RELANCE_AVEC_ORIGINE, ligne)
    assert_dans_l_ordre(CONTRADICTION_SKILL, ligne, RELANCE_SANS_ORIGINE)
    assert_dans_l_ordre(REPERCUSSIONS_SKILL, reprise, ARRET_DE_REPERCUSSIONS)


def test_la_table_des_sorties_de_contradiction_est_celle_du_test() -> None:
    """L'autre sens (obs 138) : une ligne ajoutée à la table de l'étape 5 rougit ici tant que
    `SORTIES_D_UNE_CONTRADICTION_D_ORIGINE` ne la porte pas, avec sa consigne de reprise."""
    texte = (REPOSITORY_ROOT / CONTRADICTION_SKILL).read_text(encoding="utf-8")
    lignes = [
        " ".join(ligne.split())
        for ligne in texte.splitlines()
        if "| `contradiction soldée :" in ligne
    ]

    assert sorted(lignes) == sorted(
        ligne for ligne, _ in SORTIES_D_UNE_CONTRADICTION_D_ORIGINE.values()
    )


# Ce que la passe 2 retire : la relance au seul merge d'un amendement, la reprise annoncée « contre
# la doc amendée » à toute sortie, et la forme de fin qui confondait la PR d'un document gagnant
# avec l'absence de PR. Chacune présente sur `02c513b`.
RETIRES_DES_SORTIES_DE_CONTRADICTION = {
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
        ".claude/skills/cycle-pr/SKILL.md",
        "*Rouge d'avis*",
        "*Rouge de code*",
        ("gh run rerun", "rejou"),
        ("Jamais un rerun d'un run du trunk", "sous un nom propre au trunk"),
    ),
    "init-projet-horloge": (
        ".claude/skills/init-projet/SKILL.md",
        "**Donner une horloge",
        "Sans porte d'avis",
        ("build",),
        ("installation et construction",),
    ),
    "init-projet-checklist": (
        ".claude/skills/init-projet/SKILL.md",
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

CYCLE_PR = REPOSITORY_ROOT / ".claude/skills/cycle-pr/SKILL.md"

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
        "elle n'écrit aucune entrée, ses candidates partent dans ses messages de constats",
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
    "nom-de-la-session": (SESSION_RELECTURE_REF, "`name: relecture-pr-<n>`"),
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
    "charge-task-observer": (SESSION_RELECTURE_REF, "Elle charge `task-observer`"),
    "plafond-de-la-pr": (
        SESSION_RELECTURE_REF,
        "le plafond de 3 entrées est celui de la PR, tenu par la session PR",
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
        CYCLE_PR_SKILL,
        "Une session de lot attend le go ci-dessous dans sa fenêtre comme toute session PR",
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
        CYCLE_PR_SKILL,
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
    2 mentions sans l'option, dont 1 contrôle — `relecteur.md`, corrigé ; l'autre, à l'Étape 1 de
    `cycle-pr`, écarte la commande pour lire l'avance d'une branche. Vu rouge sur `relecteur.md`
    avant correction.
    """
    sans_l_option = re.compile(r"git status --porcelain(?! --untracked-files=normal)")
    sites = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path, _ in prose_citations(
            REPOSITORY_ROOT, tracked_files(), HARNESS_PROSE_GLOBS, sans_l_option
        )
    ]

    assert sites == [CYCLE_PR_SKILL], sites
