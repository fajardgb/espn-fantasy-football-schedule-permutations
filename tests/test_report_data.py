"""
Tests for the data behind the HTML report: week cutoffs, seed distributions,
the schedule-swap matrix, head-to-head tiebreaks, and the histogram grid.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from build_report import build_report_data, grid_shape
from get_espn_league_data import write_league_settings, write_schedule_csv, write_scores_csv
from simulate_schedule_permutations import (
    PlayoffSimulator,
    load_league_structure,
    load_scores,
    schedule_swap_matrix,
    simulator_through_week,
)

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def league(tmp_path):
    """In-progress season (12 teams, 8 weeks played) loaded as the scripts do."""
    data = json.loads((FIXTURES / 'espn_in_progress_season.json').read_text())
    write_scores_csv(data, tmp_path / 'scores.csv')
    write_schedule_csv(data, tmp_path / 'schedule.csv')
    write_league_settings(data, tmp_path / 'settings.json')
    scores = load_scores(tmp_path / 'scores.csv')
    structure = load_league_structure(scores, tmp_path / 'schedule.csv',
                                      tmp_path / 'settings.json')
    return scores, structure


def wins(record_str):
    return int(record_str.split('-')[0])


# ------------------------------------------------------------------ week cutoff

def test_full_season_actual_records_match_scores_file(league):
    scores, structure = league
    sim = simulator_through_week(scores, structure)
    assert sim.actual_records() == dict(zip(scores['Team'], scores['Record']))


def test_cutoff_records_count_only_weeks_so_far(league):
    scores, structure = league
    for week in (1, 3, 5):
        records = simulator_through_week(scores, structure, week).actual_records()
        games = [sum(int(p) for p in r.split('-')) for r in records.values()]
        assert set(games) == {week}


def test_cutoff_points_for_sum_weeks_so_far(league):
    scores, structure = league
    results = simulator_through_week(scores, structure, 3).run_simulation(200)
    expected = scores.set_index('Team')[['W1', 'W2', 'W3']].sum(axis=1)
    got = results.set_index('Team')['Points For']
    pd.testing.assert_series_equal(got.sort_index(), expected.sort_index(),
                                   check_names=False)


def test_cutoff_out_of_range(league):
    scores, structure = league
    with pytest.raises(ValueError):
        simulator_through_week(scores, structure, 9)


def test_partial_season_needs_schedule(league):
    scores, structure = league
    no_schedule = {**structure, 'generator': None, 'actual_schedule': None}
    with pytest.raises(ValueError):
        simulator_through_week(scores, no_schedule, 3)


# ---------------------------------------------------------- seed distribution

def test_seed_counts_are_a_full_distribution(league):
    scores, structure = league
    sim = simulator_through_week(scores, structure)
    results = sim.run_simulation(500).set_index('Team')
    counts = sim.seed_counts
    n = len(scores)
    assert counts.shape == (n, n)
    assert (counts.sum(axis=1) == 500).all()   # every team gets one seed per sim
    assert (counts.sum(axis=0) == 500).all()   # every seed goes to one team per sim
    playoff = counts.loc[:, 1:structure['n_playoff_teams']].sum(axis=1) / 500 * 100
    pd.testing.assert_series_equal(playoff.sort_index(), results['Playoff %'].sort_index(),
                                   check_names=False)


# ----------------------------------------------------------- schedule swap

def toy_league():
    scores = pd.DataFrame({
        'Team': ['A', 'B', 'C', 'D'],
        'W1': [100.0, 90.0, 80.0, 70.0],
        'W2': [60.0, 95.0, 85.0, 75.0],
    })
    schedule = [[('A', 'B'), ('C', 'D')], [('A', 'C'), ('B', 'D')]]
    return scores, schedule


def test_swap_matrix_by_hand():
    scores, schedule = toy_league()
    m = schedule_swap_matrix(scores, schedule)
    # Diagonal is the real record: A beat B, lost to C
    assert m['A']['A'] == {'wins': 1, 'losses': 1, 'ties': 0}
    # A with D's schedule: W1 vs C (100>80), W2 vs B (60<95)
    assert m['A']['D'] == {'wins': 1, 'losses': 1, 'ties': 0}
    # D with A's schedule: W1 vs B (70<90), W2 vs C (75<85)
    assert m['D']['A'] == {'wins': 0, 'losses': 2, 'ties': 0}
    # A with B's schedule: W1 B faced A -> A faces B (100>90); W2 vs D (60<75)
    assert m['A']['B'] == {'wins': 1, 'losses': 1, 'ties': 0}


def test_swap_matrix_diagonal_is_actual_record(league):
    scores, structure = league
    m = schedule_swap_matrix(scores, structure['actual_schedule'])
    for team, record in zip(scores['Team'], scores['Record']):
        assert f"{m[team][team]['wins']}-{m[team][team]['losses']}" == record


def test_swap_matrix_respects_byes():
    scores = pd.DataFrame({'Team': ['A', 'B', 'C'], 'W1': [3.0, 2.0, 1.0],
                           'W2': [3.0, 2.0, 1.0]})
    schedule = [[('A', 'B')], [('B', 'C')]]  # C bye week 1, A bye week 2
    m = schedule_swap_matrix(scores, schedule)
    assert sum(m['C']['A'].values()) == 1   # A's schedule has one game
    assert m['C']['A'] == {'wins': 0, 'losses': 1, 'ties': 0}


# ------------------------------------------------------------ H2H tiebreak

def h2h_record(wins, losses, points, h2h):
    return {'wins': wins, 'losses': losses, 'ties': 0, 'points_for': points, 'h2h': h2h}


def blank_sim(rule, n=2):
    df = pd.DataFrame({'Team': ['x'], 'Record': ['0-0'], 'W1': [0.0]})
    return PlayoffSimulator(df, n_playoff_teams=n, seeding_rule=rule)


def test_h2h_rule_beats_points():
    records = {'A': h2h_record(7, 7, 1500, {'B': [0.0, 1]}),
               'B': h2h_record(7, 7, 1000, {'A': [1.0, 1]})}
    assert blank_sim('H2H_RECORD').rank_teams(records) == ['B', 'A']
    assert blank_sim('TOTAL_POINTS_SCORED').rank_teams(records) == ['A', 'B']


def test_h2h_skipped_when_meetings_unequal():
    # A-B met once, A-C and B-C never: ESPN skips H2H and uses points
    records = {'A': h2h_record(7, 7, 1500, {'B': [0.0, 1]}),
               'B': h2h_record(7, 7, 1000, {'A': [1.0, 1]}),
               'C': h2h_record(7, 7, 1200, {})}
    assert blank_sim('H2H_RECORD').rank_teams(records) == ['A', 'C', 'B']


def test_h2h_tracked_during_simulation():
    df = pd.DataFrame({'Team': ['A', 'B'], 'Record': ['0-0'] * 2,
                       'W1': [10.0, 5.0], 'W2': [5.0, 10.0]})
    sim = PlayoffSimulator(df, seeding_rule='H2H_RECORD')
    records = sim.simulate_schedule([[('A', 'B')], [('A', 'B')]])
    assert records['A']['h2h'] == {'B': [1.0, 2]}


def test_unmodeled_rule_is_noted(league, tmp_path):
    scores, _ = league
    (tmp_path / 's.json').write_text(json.dumps({'playoff_team_count': 4,
                                                 'playoff_seeding_rule': 'SOMETHING_NEW'}))
    structure = load_league_structure(scores, tmp_path / 'none.csv', tmp_path / 's.json')
    assert any('SOMETHING_NEW' in n for n in structure['notes'])


# ------------------------------------------------------------- report data

@pytest.mark.parametrize('n,shape', [(8, (2, 4)), (10, (2, 5)), (12, (2, 6)),
                                     (14, (2, 7)), (16, (3, 6)), (5, (1, 5))])
def test_grid_shape(n, shape):
    assert grid_shape(n) == shape


def test_report_data_has_every_week(league):
    scores, structure = league
    data = build_report_data(scores, structure, num_schedules=100)
    assert [w['week'] for w in data['weeks']] == list(range(1, 9))
    last = data['weeks'][-1]
    assert len(last['results']) == 12
    assert len(last['seeds']) == 12 and all(len(r) == 12 for r in last['seeds'].values())
    assert len(last['swap']['wins']) == 12


def test_report_data_describes_league_format(league):
    scores, structure = league
    data = build_report_data(scores, structure, num_schedules=100)
    assert data['league']['seeding_rule'] == structure['seeding_rule']
    assert data['league']['real_schedule'] is True
