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
    # « Tu n'as pas de `Write` » (`relecteur.md`) — et `Edit` reste : une mutation modifie un
    # fichier existant, elle n'en crée pas.
    ("relecteur", "tools", "Write"),
    # « tu n'écris rien » (`verificateur.md`) : le mandat est un verdict, pas un correctif.
    ("verificateur", "tools", "Write"),
    # « Tu n'as **pas** de worktree » (`verificateur.md`) : c'est ce qui le garde bon marché, et un
    # `isolation` déclaré en ferait créer un à chaque (PR, go).
    ("verificateur", "isolation", None),
]


# Les identifiants de cas se **dérivent** des valeurs, jamais d'une clé saisie à la main : sous une
# clé écrite à part, remplacer `("verificateur", "isolation", None)` par un autre rôle laissait le
# cas vert sous un nom qui annonçait toujours `verificateur` (mesuré, mutation VERTE). Un
# identifiant qui ne dérive pas de ce qu'il nomme est un commentaire, pas une étiquette.
@pytest.mark.parametrize(
    ("role", "field", "forbidden"),
    ROLE_FRONTMATTER_CLAIMS,
    ids=[f"{role}-{field}" for role, field, _ in ROLE_FRONTMATTER_CLAIMS],
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
        f"{Path(skill).parent.name}-{action.replace(' ', '-')}"
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
    par `GESTES_RETIRES_DE_PR_PARALLELES`.

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
# ailleurs : les trois renvois (`SKILLS_DES_SESSIONS_LIEES`), le point de départ `origin/`
# (`DEPARTS_EXPLICITES`), la porte du nettoyage (`PORTES_PRESCRITES`). Restent en lecture, à
# dessein : les quatre formes du message de fin autres que celle d'un lot, que rien ne consomme.
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
SESSIONS_LIEES_REF = ".claude/skills/cycle-pr/references/sessions-liees.md"
COORDINATRICE_REF = ".claude/skills/cycle-pr/references/coordinatrice.md"
PROMPT_LOT_SUIVANT = ".claude/skills/cycle-pr/references/prompt-lot-suivant.md"
PR_PARALLELES_SKILL = ".claude/skills/pr-paralleles/SKILL.md"
INTERROGE_MOI_SKILL = ".claude/skills/interroge-moi/SKILL.md"
CYCLE_PR_SKILL = ".claude/skills/cycle-pr/SKILL.md"
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
    "etape-7-sans-confirmation": (
        CYCLE_PR_SKILL,
        "**envoyer** l'état de la PR au lead, sans confirmation",
    ),
    "etape-7-renvoi-sans-confirmation": (
        CYCLE_PR_SKILL,
        "push, puis renvoyer l'état au lead pour re-vérification du delta",
    ),
    "pr-paralleles-sans-confirmation": (
        PR_PARALLELES_SKILL,
        "chaque session envoie au lead l'état de sa PR, sans confirmation",
    ),
    "pr-paralleles-renvoi-sans-confirmation": (
        PR_PARALLELES_SKILL,
        "Après corrections, la session renvoie l'état ; le lead refait la passe sur le delta.",
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
    # Commandes intégrées (obs 94, 98).
    "commandes-integrees-sans-fin-de-tour": (
        CYCLE_PR_SKILL,
        "**Ces deux commandes ne terminent pas le tour.**",
    ),
    "config-relecture-sans-fin-de-tour": (
        ".claude/pipeline.config.md",
        "termine pas le tour (`cycle-pr` 4.2, obs 94).",
    ),
    "config-securite-sans-fin-de-tour": (
        ".claude/pipeline.config.md",
        "termine pas le tour (`cycle-pr` 4.2, obs 98).",
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
        "Une issue à un seul lot ne change rien : la session fait le cycle elle-même.",
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
        "La coordinatrice y tourne en Opus 5.5, effort `max`",
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
        "« bloquant : `[V]` en attente dans cette fenêtre »",
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
    "go-du-briefing-conditionnel": (COORDINATRICE_REF, "« plan confirmé, aucune `[V]` »"),
    "base-de-la-pr-de-lot": (COORDINATRICE_REF, "se lit `origin/<type>/<slug>`"),
    "verification-jamais-a-la-coordinatrice": (
        COORDINATRICE_REF,
        "au lead que son brief nomme, jamais à la coordinatrice",
    ),
    "etape-8-du-lot-bornee": (
        COORDINATRICE_REF,
        "Son Étape 8 se borne à cocher ses critères et à écrire sa passation",
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
    "passation-en-dernier": (CYCLE_PR_SKILL, "**La passation s'écrit en dernier.**"),
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
        ".claude/skills/repercussions/SKILL.md",
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
}


# `use_worktree` omis, `start_session` donne à l'enfant le dossier de son parent quand celui-ci
# travaille dans un dossier simple (description de l'outil, lue le 2026-10-18) : deux sessions y
# basculeraient tour à tour la même branche. **Dénombrement, écrit avant le correctif** (relecture
# de la PR #130, passe 2, R-1) : `grep -rn start_session .claude CLAUDE.md CONTRIBUTING.md` rend
# 5 sites qui démarrent une session devant avoir son worktree — `pr-paralleles` Étape 3 (fermé par
# `ef0b3a8`), son repli d'Étape 8 (renvoi à l'Étape 3, fermé avec elle), sa carte de relais, et
# dans `coordinatrice.md` les sessions de lot et la carte de relais : **3 fuyaient**. Un site
# nouveau n'entre pas ici de lui-même : la garde lit des phrases, le grep re-dérive la population.
USE_WORKTREE_EXPLICITE = {
    "pr-paralleles-etape-3": (
        PR_PARALLELES_SKILL,
        "Le worktree se demande en clair, `use_worktree: true`",
    ),
    "pr-paralleles-carte-de-relais": (
        PR_PARALLELES_SKILL,
        "(`start_session`, `initiation: own_initiative`, `use_worktree: true`, brief : la passation)",
    ),
    "coordinatrice-sessions-de-lot": (
        COORDINATRICE_REF,
        "worktree de l'application, `wake_when_done: true`, `use_worktree: true`",
    ),
    "coordinatrice-carte-de-relais": (
        COORDINATRICE_REF,
        "(`start_session`, `initiation: own_initiative`, `use_worktree: true`, brief : la passation",
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
    texte = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8-sig")

    assert forme not in texte, f"`{fichier}` porte encore « {forme} »"


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


def texte_normalise(fichier: str) -> str:
    """Le texte du fichier, espaces normalisés et marges `# ` de tête de ligne retirées."""
    brut = (REPOSITORY_ROOT / fichier).read_text(encoding="utf-8-sig")
    return " ".join(re.sub(r"(?m)^[ \t]*#[ \t]?", "", brut).split())


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
        "à écrire sa passation",
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
# le 2026-10-18), le retrait avant l'échafaudage.
ORDRE_DE_PR_PARALLELES = {
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
QUESTIONS_DU_GO = {"accord pour le vérificateur hors vague": "l'accord pour lancer soi-même"}


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
