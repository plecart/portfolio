"""Tests des sessions imbriquées : ce qu'elles écartent du shell, et ce qu'elles refusent."""

from pathlib import Path

import pytest
from nested_sessions import NESTED_SESSION, run_nested_session

# Un test rapide, qui ne touche aucune base : il sert de témoin à la session imbriquée.
WITNESS_TEST = "apps/api/tests/test_admin.py::test_l_admin_parle_francais"


def test_une_session_imbriquee_ignore_les_options_pytest_du_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Un `PYTEST_ADDOPTS` hérité changerait ce que la session lance — un `-x` l'arrêterait au
    premier échec, un `--collect-only` ne lancerait rien : la mesure serait faussée."""
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only")

    session = run_nested_session([WITNESS_TEST], tmp_path)

    assert session.outcomes == {WITNESS_TEST: "passed"}, session.report


def test_une_session_imbriquee_n_en_lance_pas_d_autre(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Une sélection qui se contiendrait elle-même se relancerait sans fin."""
    monkeypatch.setenv(NESTED_SESSION, "1")

    with pytest.raises(pytest.fail.Exception, match="imbriquée"):
        run_nested_session([WITNESS_TEST], tmp_path)
