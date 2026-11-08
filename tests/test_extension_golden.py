"""
The Chrome extension's JavaScript port is tested against reference results
from this Python code (chrome_extension/tests/golden/). This fails when the
Python logic changes without regenerating them, so the two can't drift apart.

To fix a failure, run:
    uv run python chrome_extension/tests/make_golden.py
then run the extension's tests (cd chrome_extension && npm test).
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'make_golden', ROOT / 'chrome_extension' / 'tests' / 'make_golden.py')
make_golden = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make_golden)


def without_simulated(golden: dict) -> dict:
    for cutoff in golden['cutoffs']:
        cutoff.pop('simulated', None)
    return golden


@pytest.mark.parametrize('fixture', sorted((ROOT / 'tests' / 'fixtures').glob('espn_*.json')),
                         ids=lambda p: p.name)
def test_extension_reference_results_are_current(fixture):
    saved = json.loads((make_golden.GOLDEN / fixture.name).read_text())
    current = make_golden.golden_for(fixture, simulate=False)
    assert without_simulated(saved) == current, (
        'Python results changed: run `uv run python chrome_extension/tests/make_golden.py` '
        'and then the extension tests')
