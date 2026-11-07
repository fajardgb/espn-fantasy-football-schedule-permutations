"""
Robustness tests for the schedule simulator across league shapes.

Leagues are synthetic: random weekly scores for any number of teams and weeks.
The key oracle is the *all-play* win %: if each week a team faces a uniformly
random opponent, its expected win % equals the share of opponents it outscored
each week, averaged over weeks. The simulation's 'Expected Win %' must match it.
"""

import random
from collections import Counter
from itertools import combinations

import numpy as np
import pandas as pd
import pytest

from simulate_schedule_permutations import (
    PlayoffSimulator,
    ScheduleGenerator,
    disambiguate_names,
    record_to_win_pct,
    standardize_name,
)

EVEN_SIZES = [4, 6, 8, 10, 12, 14, 16]
ODD_SIZES = [5, 7, 9, 11, 13]
SEASON_LENGTHS = [8, 13, 14, 17]  # shorter than, equal to, and longer than one cycle


ALL_SIZES = EVEN_SIZES + ODD_SIZES


# --------------------------------------------------------------------------- helpers

def make_league(n_teams: int, n_weeks: int, seed: int = 0) -> pd.DataFrame:
    """Synthetic league with distinct random weekly scores (no ties)."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        'Player': [f'T{i}' for i in range(n_teams)],
        'Record': ['0-0'] * n_teams,
    })
    for week in range(n_weeks):
        df[f'W{week + 1}'] = rng.permutation(n_teams) * 10.0 + rng.uniform(0, 5, n_teams)
    return df


def all_play_win_pct(df: pd.DataFrame) -> pd.Series:
    """Exact expected win % under a uniformly random opponent each week."""
    scores = df[[c for c in df.columns if c.startswith('W')]].to_numpy()
    beaten = (scores[:, None, :] > scores[None, :, :]).sum(axis=1)
    pct = beaten.sum(axis=1) / ((len(df) - 1) * scores.shape[1]) * 100
    return pd.Series(pct, index=df['Player'])


def cycle_length(n_teams: int) -> int:
    """Weeks in one full round-robin: n-1 for even leagues, n for odd (one bye each)."""
    return n_teams - 1 if n_teams % 2 == 0 else n_teams


def generate(n_teams: int, n_weeks: int, seed: int = 0):
    random.seed(seed)
    gen = ScheduleGenerator([f'T{i}' for i in range(n_teams)], n_weeks)
    return gen, gen.generate_schedule()


def run(df: pd.DataFrame, num_schedules: int = 1500, **kwargs) -> pd.DataFrame:
    return PlayoffSimulator(df, **kwargs).run_simulation(num_schedules).set_index('Player')


# --------------------------------------------------------------- schedule structure

@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', ALL_SIZES)
def test_schedule_has_requested_number_of_weeks(n_teams, n_weeks):
    _, schedule = generate(n_teams, n_weeks)
    assert len(schedule) == n_weeks


@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', ALL_SIZES)
def test_each_team_plays_at_most_once_per_week(n_teams, n_weeks):
    _, schedule = generate(n_teams, n_weeks)
    for week in schedule:
        appearances = Counter(team for match in week for team in match)
        assert max(appearances.values()) == 1


@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', EVEN_SIZES)
def test_even_league_every_team_plays_every_week(n_teams, n_weeks):
    gen, schedule = generate(n_teams, n_weeks)
    for week in schedule:
        assert {team for match in week for team in match} == set(gen.teams)


@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', ODD_SIZES)
def test_odd_league_exactly_one_bye_per_week(n_teams, n_weeks):
    gen, schedule = generate(n_teams, n_weeks)
    for week in schedule:
        playing = {team for match in week for team in match}
        assert len(set(gen.teams) - playing) == 1


@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', ALL_SIZES)
def test_no_pair_meets_twice_within_a_cycle(n_teams, n_weeks):
    _, schedule = generate(n_teams, n_weeks)
    length = cycle_length(n_teams)
    for start in range(0, n_weeks, length):
        pairs = Counter(frozenset(m) for week in schedule[start:start + length] for m in week)
        assert max(pairs.values()) == 1


@pytest.mark.parametrize('n_teams', ALL_SIZES)
def test_full_cycle_pairs_every_team_exactly_once(n_teams):
    gen, schedule = generate(n_teams, cycle_length(n_teams))
    pairs = Counter(frozenset(m) for week in schedule for m in week)
    assert set(pairs) == {frozenset(p) for p in combinations(gen.teams, 2)}


@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', ALL_SIZES)
def test_games_per_team_differ_by_at_most_one(n_teams, n_weeks):
    gen, schedule = generate(n_teams, n_weeks)
    games = Counter(team for week in schedule for match in week for team in match)
    counts = [games[team] for team in gen.teams]
    assert max(counts) - min(counts) <= 1


@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', ALL_SIZES)
def test_validate_schedule_accepts_generated_schedules(n_teams, n_weeks):
    gen, schedule = generate(n_teams, n_weeks)
    assert gen.validate_schedule(schedule)


# ----------------------------------------------------------------- win bookkeeping

@pytest.mark.parametrize('n_weeks', SEASON_LENGTHS)
@pytest.mark.parametrize('n_teams', ALL_SIZES)
def test_wins_equal_games_and_records_match_schedule(n_teams, n_weeks):
    _, schedule = generate(n_teams, n_weeks)
    sim = PlayoffSimulator(make_league(n_teams, n_weeks))
    records = sim.simulate_schedule(schedule)

    games = Counter(team for week in schedule for match in week for team in match)
    n_matches = sum(len(week) for week in schedule)
    assert sum(r['wins'] for r in records.values()) == n_matches
    for team, record in records.items():
        assert record['wins'] + record['losses'] + record['ties'] == games[team]


@pytest.mark.parametrize('n_teams', [8, 9, 11])
def test_points_for_counts_every_week_including_byes(n_teams):
    # Points-for is the playoff tiebreaker; a bye shouldn't erase that week's score
    df = make_league(n_teams, 14)
    _, schedule = generate(n_teams, 14)
    records = PlayoffSimulator(df).simulate_schedule(schedule)

    season_totals = df.set_index('Player')[[f'W{w}' for w in range(1, 15)]].sum(axis=1)
    for team, record in records.items():
        assert record['points_for'] == pytest.approx(season_totals[team])


# ------------------------------------------------------------ exact-answer oracle

@pytest.mark.parametrize('n_teams,n_weeks', [
    (4, 14), (6, 14), (8, 8), (10, 13), (12, 14), (16, 17),
    (5, 14),
    (9, 13),
    (11, 14),
])
def test_expected_win_pct_matches_all_play(n_teams, n_weeks):
    df = make_league(n_teams, n_weeks, seed=n_teams)
    results = run(df)
    gap = (results['Expected Win %'] - all_play_win_pct(df)).abs().max()
    assert gap < 1.5, f'max gap {gap:.2f} pp'


# ----------------------------------------------------------------- obvious cases

@pytest.mark.parametrize('n_teams', [8, 12, 9])
def test_best_and_worst_teams(n_teams):
    df = make_league(n_teams, 14)
    week_cols = [c for c in df.columns if c.startswith('W')]
    df.loc[0, week_cols] = 1000.0   # T0 outscores everyone every week
    df.loc[1, week_cols] = -1000.0  # T1 is outscored by everyone every week

    results = run(df, num_schedules=300)
    assert results.loc['T0', 'Expected Win %'] == 100
    assert results.loc['T0', 'Playoff %'] == 100
    assert results.loc['T1', 'Expected Win %'] == 0
    assert results.loc['T1', 'Playoff %'] == 0


def test_playoff_seeding_uses_win_pct_when_games_differ():
    # In odd leagues teams can play different numbers of games; a 6-6 team
    # should rank above a 6-7 team even with fewer points.
    sim = PlayoffSimulator(make_league(4, 1), n_playoff_teams=1)
    records = {
        'A': {'wins': 6, 'losses': 6, 'points_for': 100.0},
        'B': {'wins': 6, 'losses': 7, 'points_for': 200.0},
    }
    assert sim.get_playoff_teams(records) == ['A']


# ------------------------------------------------------------------ input parsing

@pytest.mark.parametrize('record,expected', [
    ('7-1', 87.5), ('0-8', 0.0), ('5-4-1', 55.0), ('0-0', 0.0),
])
def test_record_to_win_pct(record, expected):
    assert record_to_win_pct(record) == pytest.approx(expected)


def test_standardize_name_capitalizes_only_first_letters():
    assert standardize_name('jason wu') == 'Jason Wu'
    assert standardize_name('pat McDonald') == 'Pat McDonald'
    assert standardize_name('  extra   spaces ') == 'Extra Spaces'


def test_disambiguate_names_suffixes_repeats():
    names = pd.Series(['MM', 'BK', 'MM', 'MM'])
    assert disambiguate_names(names).tolist() == ['MM', 'BK', 'MM (2)', 'MM (3)']


# ------------------------------------------------------------------------- ties

def two_team_league(scores_a, scores_b, records=('0-0', '0-0')):
    df = pd.DataFrame({'Player': ['A', 'B'], 'Record': list(records)})
    for week, (a, b) in enumerate(zip(scores_a, scores_b), start=1):
        df[f'W{week}'] = [a, b]
    return df


def test_equal_scores_are_a_tie_for_both_teams():
    sim = PlayoffSimulator(two_team_league([100.0, 90.0], [100.0, 80.0]))
    records = sim.simulate_schedule([[('A', 'B')], [('A', 'B')]])
    assert (records['A']['wins'], records['A']['losses'], records['A']['ties']) == (1, 0, 1)
    assert (records['B']['wins'], records['B']['losses'], records['B']['ties']) == (0, 1, 1)


def test_ties_count_as_half_a_win_in_expected_win_pct():
    df = two_team_league([100.0, 100.0, 120.0, 90.0], [100.0, 100.0, 110.0, 95.0])
    results = PlayoffSimulator(df).run_simulation(50).set_index('Player')
    # A: 2 ties + 1 win + 1 loss = 2 wins out of 4 -> 50%
    assert results.loc['A', 'Expected Win %'] == pytest.approx(50.0)
    assert results.loc['B', 'Expected Win %'] == pytest.approx(50.0)


def test_playoff_seeding_counts_ties_as_half_a_win():
    sim = PlayoffSimulator(make_league(4, 1), n_playoff_teams=1)
    records = {
        # Ties as half a win: A = 6.5/14 = 46.4% beats B = 6/13 = 46.2%.
        # Ignoring ties would rank A at 5/11 = 45.5%, below B.
        'A': {'wins': 5, 'losses': 6, 'ties': 3, 'points_for': 100.0},
        'B': {'wins': 6, 'losses': 7, 'ties': 0, 'points_for': 200.0},
    }
    assert sim.get_playoff_teams(records) == ['A']
