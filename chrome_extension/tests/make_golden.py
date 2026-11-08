"""
Write reference results from the Python tool for the JavaScript port to match.

For each anonymized ESPN response in tests/fixtures/, this runs the real Python
pipeline (CSV files -> load_scores -> load_league_structure) and saves:
  - the parsed league (teams, divisions, weekly scores, schedule, settings)
  - exact results: actual records and the schedule-swap matrix at every week cutoff
  - simulated results (playoff % and expected win %) with many simulations, which
    the JavaScript simulation must match within sampling error

Run from the project root whenever the Python logic changes:
    uv run python chrome_extension/tests/make_golden.py
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from get_espn_league_data import (  # noqa: E402
    parse_league_settings,
    write_league_settings,
    write_schedule_csv,
    write_scores_csv,
)
from simulate_schedule_permutations import (  # noqa: E402
    format_record,
    load_league_structure,
    load_scores,
    schedule_swap_matrix,
    simulator_through_week,
)

FIXTURES = ROOT / 'tests' / 'fixtures'
GOLDEN = Path(__file__).parent / 'golden'
SIMULATIONS = 20000


def golden_for(fixture: Path, simulate: bool = True) -> dict:
    data = json.loads(fixture.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        write_scores_csv(data, tmp / 'scores.csv')
        write_schedule_csv(data, tmp / 'schedule.csv')
        write_league_settings(data, tmp / 'settings.json')
        scores = load_scores(tmp / 'scores.csv')
        structure = load_league_structure(scores, tmp / 'schedule.csv', tmp / 'settings.json')

    week_columns = [c for c in scores.columns if c.startswith('W')]
    n_weeks = len(week_columns)
    # Simulating is slow-ish in Python, so only the first, middle and last weeks
    simulated = {1, (n_weeks + 1) // 2, n_weeks}

    cutoffs = []
    for week in range(1, n_weeks + 1):
        sim = simulator_through_week(scores, structure, week)
        swap = schedule_swap_matrix(sim.scores_df, structure['actual_schedule'][:week])
        entry = {
            'week': week,
            'actual_records': sim.actual_records(),
            'swap': {x: {y: format_record(r) for y, r in row.items()} for x, row in swap.items()},
        }
        if simulate and week in simulated:
            results = sim.run_simulation(SIMULATIONS, seed=7).set_index('Team')
            entry['simulated'] = {
                team: {'playoff': round(float(row['Playoff %']), 3),
                       'expected': round(float(row['Expected Win %']), 3)}
                for team, row in results.iterrows()
            }
        cutoffs.append(entry)

    return {
        'fixture': fixture.name,
        'simulations': SIMULATIONS,
        'teams': [{'id': int(i), 'name': n, 'division': d}
                  for i, n, d in zip(scores['Team ID'], scores['Team'], scores['Division'])],
        'weeks': [int(c[1:]) for c in week_columns],
        'scores': {name: [None if s != s else float(s) for s in scores.loc[i, week_columns]]
                   for i, name in zip(scores.index, scores['Team'])},
        'schedule': [[list(pair) for pair in week] for week in structure['actual_schedule']],
        'settings': parse_league_settings(data),
        'n_playoff_teams': structure['n_playoff_teams'],
        'notes': structure['notes'],
        'cutoffs': cutoffs,
    }


def main():
    GOLDEN.mkdir(exist_ok=True)
    for fixture in sorted(FIXTURES.glob('espn_*.json')):
        out = GOLDEN / fixture.name
        out.write_text(json.dumps(golden_for(fixture), indent=1) + '\n')
        print(f'Wrote {out.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
