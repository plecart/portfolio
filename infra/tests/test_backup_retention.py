"""Tests de la rétention des sauvegardes : `retention.sh`, sur des jeux de noms datés, sans bucket
(brief de #23, décision 7).

La règle est celle de `borg prune --keep-daily 7 --keep-weekly 4` (doc « borg prune » ; source de
borg 1.4.5, `prune_split`). Chaque attendu est écrit en littéral, compté contre cette règle — jamais
tiré du script : un test dont les cas viennent de l'artefact ne peut le contredire sur rien.

Lancé par `make image-test`, sur l'image que `make build` a chargée. Le script est celui de la copie
de travail, joué par le shell d'un conteneur de cette image : ses outils — `date`, `sort`, `awk` de
busybox — sont ceux de la production, et une mutation du script se voit sans reconstruire l'image.
Que l'image porte ce script-là, c'est la purge dans la pile qui le montre (`test_backup_image.py`,
`test_la_purge_supprime_du_bucket_exactement_ce_que_la_retention_ecarte`).
"""

import subprocess
from collections.abc import Callable, Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
from test_infra import loaded_image

SCRIPT = Path(__file__).parents[1] / "backup" / "retention.sh"
# La base des noms de ces jeux : le script la reçoit en argument, comme `backup.sh` lui passe la
# sienne.
BASE = "portfolio"
# Le temps laissé à un lancement du script, en secondes ; une seconde suffit d'ordinaire.
RUN_DEADLINE = 60

type Expired = Callable[..., set[str]]


def name(stamp: str) -> str:
    """Le nom d'un objet de sauvegarde pris à `stamp` (`AAAAMMJJTHHMMSS`, UTC) : décision 6."""
    return f"{BASE}-{stamp}Z.dump.age"


def nightly(first: date, last: date) -> list[str]:
    """Une sauvegarde par nuit, à 03:00 UTC, du `first` au `last` inclus."""
    days = (last - first).days + 1
    return [name(f"{first + timedelta(days=offset):%Y%m%d}T030000") for offset in range(days)]


@pytest.fixture(scope="module")
def expired() -> Iterator[Expired]:
    """Ce que le script écarte d'une liste de noms, joué dans un conteneur de l'image `backup`
    démarré pour le module — une heure au plus, s'il survivait à son arrêt. Un `docker exec` par
    cas plutôt qu'un `docker run` : trois lancements de conteneur sur 159 se sont figés sur ce poste
    (mesuré le 2026-10-14), aucun des 93 `docker exec` qui ont suivi ; et un délai borne chaque
    appel, pour qu'un blocage échoue au lieu de suspendre la suite."""
    started = subprocess.run(
        ["docker", "run", "--detach", "--rm", loaded_image("backup"), "sleep", "3600"],
        capture_output=True,
        text=True,
        check=True,
    )
    container = started.stdout.strip()

    def run(names: Iterable[str], timezone: str = "UTC") -> set[str]:
        printed = subprocess.run(
            ["docker", "exec", "-i", "-e", f"TZ={timezone}", container, "sh", "-c"]
            + [SCRIPT.read_text(encoding="utf-8"), "retention.sh", BASE],
            input="".join(f"{each}\n" for each in names).encode(),
            capture_output=True,
            check=False,
            timeout=RUN_DEADLINE,
        )
        assert printed.returncode == 0, printed.stderr.decode()
        return set(printed.stdout.decode().splitlines())

    try:
        yield run
    finally:
        subprocess.run(["docker", "rm", "--force", container], capture_output=True, check=False)


# Le régime établi : soixante-quinze nuits jusqu'au mercredi 14 octobre 2026, et ce qu'elles gardent.
ESTABLISHED = nightly(date(2026, 8, 1), date(2026, 10, 14))
ESTABLISHED_KEPT = {
    name("20261014T030000"),
    name("20261013T030000"),
    name("20261012T030000"),
    name("20261011T030000"),
    name("20261010T030000"),
    name("20261009T030000"),
    name("20261008T030000"),
    name("20261004T030000"),
    name("20260927T030000"),
    name("20260920T030000"),
    name("20260913T030000"),
}


def test_en_regime_etabli_la_retention_garde_7_quotidiennes_et_4_hebdomadaires(
    expired: Expired,
) -> None:
    """Les 7 derniers jours, puis la fin des 4 semaines précédentes. La semaine du 5 au 11 octobre
    ne garde rien de plus : sa fin, le dimanche 11, est déjà gardée par la règle quotidienne."""
    assert set(ESTABLISHED) - expired(ESTABLISHED) == ESTABLISHED_KEPT


def test_un_jour_qui_a_deux_sauvegardes_ne_garde_que_la_plus_recente(expired: Expired) -> None:
    """Deux sauvegardes lancées à la main, le 10 et le 14 octobre, en plus de celles des nuits du
    1ᵉʳ au 14 : chacun de ces jours ne garde que la plus récente. La règle hebdomadaire n'atteint pas
    son compte — deux semaines seulement avant celle du 14 —, elle garde donc aussi la plus ancienne,
    le 1ᵉʳ octobre (« As of Borg 1.2.0 », doc « borg prune »)."""
    names = [
        *nightly(date(2026, 10, 1), date(2026, 10, 14)),
        name("20261010T090000"),
        name("20261014T152000"),
    ]

    kept = set(names) - expired(names)

    assert kept == {
        name("20261014T152000"),
        name("20261013T030000"),
        name("20261012T030000"),
        name("20261011T030000"),
        name("20261010T090000"),
        name("20261009T030000"),
        name("20261008T030000"),
        name("20261004T030000"),
        name("20261001T030000"),
    }


def test_les_regles_ne_comptent_que_les_jours_qui_ont_une_sauvegarde(expired: Expired) -> None:
    """Une nuit sur trois sans sauvegarde, du 1ᵉʳ août au 14 octobre 2026 : les 7 jours gardés
    remontent au 5 octobre, sur dix jours de calendrier — une série d'échecs ne vide jamais le
    bucket. La semaine du 5 au 11 a sa fin déjà gardée ; viennent ensuite les 4 suivantes, chacune
    par la plus récente qu'elle a."""
    names = [
        each
        for offset, each in enumerate(nightly(date(2026, 8, 1), date(2026, 10, 14)))
        if offset % 3 != 1
    ]

    kept = set(names) - expired(names)

    assert kept == {
        name("20261014T030000"),
        name("20261012T030000"),
        name("20261011T030000"),
        name("20261009T030000"),
        name("20261008T030000"),
        name("20261006T030000"),
        name("20261005T030000"),
        name("20261003T030000"),
        name("20260927T030000"),
        name("20260920T030000"),
        name("20260912T030000"),
    }


def test_une_semaine_a_cheval_sur_deux_annees_reste_une_semaine(expired: Expired) -> None:
    """Les nuits du 1ᵉʳ décembre 2026 au 12 janvier 2027 : la semaine du lundi 28 décembre au
    dimanche 3 janvier est une seule semaine ISO, 2026-W53, qui garde le seul 3 janvier. Une semaine
    lue dans l'année civile la couperait en deux, et garderait aussi le 31 décembre."""
    names = nightly(date(2026, 12, 1), date(2027, 1, 12))

    kept = set(names) - expired(names)

    assert kept == {
        name("20270112T030000"),
        name("20270111T030000"),
        name("20270110T030000"),
        name("20270109T030000"),
        name("20270108T030000"),
        name("20270107T030000"),
        name("20270106T030000"),
        name("20270103T030000"),
        name("20261227T030000"),
        name("20261220T030000"),
        name("20261213T030000"),
    }


# La première de huit nuits, un jour de chaque jour de la semaine.
FIRST_NIGHTS = {
    "lundi": date(2026, 10, 12),
    "mardi": date(2026, 10, 13),
    "mercredi": date(2026, 10, 14),
    "jeudi": date(2026, 10, 15),
    "vendredi": date(2026, 10, 16),
    "samedi": date(2026, 10, 17),
    "dimanche": date(2026, 10, 18),
}


@pytest.mark.parametrize("first", FIRST_NIGHTS.values(), ids=FIRST_NIGHTS.keys())
def test_huit_nuits_ou_moins_ne_suppriment_rien(expired: Expired, first: date) -> None:
    """Les huit premières nuits d'un bucket neuf, quel que soit le jour de la première : la règle
    quotidienne garde les sept dernières, et la plus ancienne reste — fin de sa semaine, ou gardée
    parce que la règle hebdomadaire n'atteint pas son compte. Dès la neuvième nuit, la purge peut en
    écarter (brief de #23, décision 7)."""
    names = nightly(first, first + timedelta(days=7))

    assert expired(names) == set()


def test_un_bucket_vide_ne_supprime_rien(expired: Expired) -> None:
    """Aucun nom en entrée, aucun en sortie — et le script réussit."""
    assert expired([]) == set()


# Les manières dont un nom peut s'écarter du format de la décision 6,
# `<base>-<AAAAMMJJ>T<HHMMSS>Z.dump.age` à une date qui existe — une forme chacune, toutes datées du
# 15 octobre 2026 ou d'avant le régime établi : comptée, chacune y déplacerait ce qui est gardé, ou
# serait elle-même supprimée.
FOREIGN_NAMES = {
    "sans-base": "20261015T030000Z.dump.age",
    "autre-base": "autre-20261015T030000Z.dump.age",
    "base-prolongee": "portfolio2-20261015T030000Z.dump.age",
    "base-suivie-d-un-mot": "portfolio-test-20261015T030000Z.dump.age",
    "dans-un-dossier": "sauvegardes/portfolio-20261015T030000Z.dump.age",
    "espace-en-tete": " portfolio-20261015T030000Z.dump.age",
    "espace-en-fin": "portfolio-20261015T030000Z.dump.age ",
    "sans-age": "portfolio-20261015T030000Z.dump",
    "suffixe-en-plus": "portfolio-20261015T030000Z.dump.age.part",
    "sans-z": "portfolio-20261015T030000.dump.age",
    "t-minuscule": "portfolio-20261015t030000Z.dump.age",
    "extension-en-majuscules": "portfolio-20261015T030000Z.DUMP.AGE",
    "date-a-sept-chiffres": "portfolio-2026105T030000Z.dump.age",
    "31-avril": "portfolio-20260431T030000Z.dump.age",
    "29-fevrier-hors-bissextile": "portfolio-20260229T030000Z.dump.age",
    "mois-13": "portfolio-20261315T030000Z.dump.age",
    "avant-1970": "portfolio-19691231T235959Z.dump.age",
    "heure-25": "portfolio-20261015T250000Z.dump.age",
    "minute-60": "portfolio-20261015T036000Z.dump.age",
    "ligne-vide": "",
}


@pytest.mark.parametrize("foreign", FOREIGN_NAMES.values(), ids=FOREIGN_NAMES.keys())
def test_un_nom_hors_format_n_est_ni_compte_ni_supprime(expired: Expired, foreign: str) -> None:
    """Un objet que la chaîne n'a pas écrit — déposé à la main, laissé par un autre outil — n'est
    pas une sauvegarde : il ne déplace rien de ce que garde le régime établi, et n'est jamais
    supprimé (décision 7). Une date qui n'existe pas en fait partie : `date` la normaliserait en
    une autre (un 31 avril devient un 1ᵉʳ mai, mesuré). En tête de l'entrée : le script ne peut
    s'arrêter sur lui sans perdre tout le reste."""
    assert expired([foreign, *ESTABLISHED]) == set(ESTABLISHED) - ESTABLISHED_KEPT


def test_un_nom_au_format_compte(expired: Expired) -> None:
    """Le témoin du test précédent : la nuit du jeudi 15 octobre, au format, entre dans les 7 jours
    gardés et en fait sortir le 8 — un ajout compté se voit."""
    assert expired([*ESTABLISHED, name("20261015T030000")]) == (
        set(ESTABLISHED) - ESTABLISHED_KEPT | {name("20261008T030000")}
    )


def test_le_fuseau_du_conteneur_ne_change_pas_ce_qui_compte(expired: Expired) -> None:
    """Les noms sont en UTC, et le script les lit en UTC quel que soit le fuseau du conteneur : sous
    l'heure d'Europe centrale, 02:30 le 28 mars 2027 n'existe pas — l'heure saute de 2 h à 3 h —, et
    une lecture locale ne compterait pas ce nom (mesuré à la relecture de la PR #96). Compté, il
    fait sortir le 8 octobre des 7 jours gardés, comme le témoin ci-dessus."""
    dst_gap = name("20270328T023000")

    assert expired([*ESTABLISHED, dst_gap], timezone="CET-1CEST,M3.5.0,M10.5.0/3") == (
        set(ESTABLISHED) - ESTABLISHED_KEPT | {name("20261008T030000")}
    )
