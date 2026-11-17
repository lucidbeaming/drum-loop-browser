import sqlite3
from pathlib import Path

import pytest

from groom.curation import CurationError, load_curation
from groom.fixtures import FIXTURES
from groom.paths import REPO_ROOT, Paths
from groom.pipeline import CURATION_DB, RunResult, run

# the dashboard owns the curation schema; groom is tested against the same file
CURATION_SQL = REPO_ROOT / "dashboard" / "src" / "lib" / "server" / "curation.sql"


def curate(data: Path, sql: str) -> None:
    data.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(data / CURATION_DB)
    con.executescript(CURATION_SQL.read_text() + sql)
    con.commit()
    con.close()


def ids(result: RunResult) -> dict[str, str]:
    return {lp.rel_path: lp.loop_id for lp in result.loops}


@pytest.fixture
def before(paths: Paths, fixture_rules: Path) -> dict[str, str]:
    return ids(run(paths, fixture_rules, audio=False))


def test_no_curation_file() -> None:
    assert load_curation(Path("/nonexistent/curation.sqlite")).fixes == {}


def test_fixes_tags_and_decisions(
    paths: Paths, fixture_rules: Path, before: dict[str, str]
) -> None:
    grit, roll, groove, angles = (
        before[FIXTURES[3].rel_path],
        before[FIXTURES[8].rel_path],
        before[FIXTURES[6].rel_path],
        before[FIXTURES[1].rel_path],
    )
    curate(
        paths.data,
        f"""
        INSERT INTO loop_fixes VALUES ('{grit}', 'bpm', '96'), ('{roll}', 'kind', 'ending'),
            ('{groove}', 'status', 'ok'), ('{groove}', 'meter', '6/8');
        INSERT INTO loop_tags VALUES ('{grit}', 'dusty', 'add'), ('{grit}', 'grit', 'remove');
        INSERT INTO loop_curation (loop_id, rejected) VALUES ('{angles}', 1);
        """,
    )
    result = run(paths, fixture_rules, audio=False)
    by_path = {lp.rel_path: lp for lp in result.loops}
    assert ids(result) == before  # a meter fix keeps the loop's ID

    lp = by_path[FIXTURES[3].rel_path]
    assert (lp.bpm, lp.bpm_source, lp.bpm_check) == (96, "curation", "confirmed")
    assert {(t.tag, t.source) for t in lp.tags} >= {("dusty", "curation")}
    assert "grit" not in {t.tag for t in lp.tags}

    assert by_path[FIXTURES[8].rel_path].kind == "ending"
    lp = by_path[FIXTURES[6].rel_path]
    assert (lp.meter, lp.meter_source, lp.status) == ((6, 8), "curation", "ok")
    assert lp.bars == 11  # the 32 beats of 8 bars of 4/4 need 11 bars of 6/8
    assert by_path[FIXTURES[1].rel_path].status == "rejected"

    con = sqlite3.connect(paths.data / "catalogue.sqlite")
    assert con.execute("SELECT bpm_source FROM loops WHERE loop_id = ?", (grit,)).fetchone() == (
        "curation",
    )


def test_bad_fix_is_reported(paths: Paths, fixture_rules: Path, before: dict[str, str]) -> None:
    grit = before[FIXTURES[3].rel_path]
    curate(paths.data, f"INSERT INTO loop_fixes VALUES ('{grit}', 'meter', '7/9');")
    lp = next(lp for lp in run(paths, fixture_rules, audio=False).loops if lp.loop_id == grit)
    assert lp.status == "review"
    assert "curation fix not understood: meter = '7/9'" in lp.issues


def test_schema_version_is_checked(paths: Paths) -> None:
    curate(paths.data, "UPDATE meta SET value = '99' WHERE key = 'schema_version';")
    with pytest.raises(CurationError, match="schema version 99"):
        load_curation(paths.data / CURATION_DB)
