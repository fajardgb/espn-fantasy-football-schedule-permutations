"""
Tests for parsing ESPN API responses (no network).

Fixtures are anonymized real responses for a 12-team, 2-division league:
- espn_completed_season.json: full season, including playoff weeks 15-17
- espn_in_progress_season.json: through week 8, with future weeks scheduled
"""

import json
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

from get_espn_league_data import (
    parse_divisions,
    parse_league_settings,
    parse_schedule,
    parse_team_records,
    parse_weekly_scores,
    regular_season_length,
    write_league_settings,
    write_schedule_csv,
    write_scores_csv,
)

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def completed():
    return json.loads((FIXTURES / 'espn_completed_season.json').read_text())


@pytest.fixture
def in_progress():
    return json.loads((FIXTURES / 'espn_in_progress_season.json').read_text())


# ------------------------------------------------------------ regular season only

def test_regular_season_length_comes_from_settings(completed):
    assert regular_season_length(completed) == 14


def test_weekly_scores_exclude_playoff_weeks(completed):
    # The completed fixture has playoff matchups in weeks 15-17
    assert max(m['matchupPeriodId'] for m in completed['schedule']) == 17
    assert sorted(parse_weekly_scores(completed)) == list(range(1, 15))


def test_weekly_scores_exclude_unplayed_weeks(in_progress):
    weeks = parse_weekly_scores(in_progress)
    assert sorted(weeks) == list(range(1, 9))
    assert all(len(teams) == 12 for teams in weeks.values())


def test_week_in_progress_is_excluded(in_progress):
    # Mid-week, the current matchups have partial scores but no result yet
    for m in in_progress['schedule']:
        if m['matchupPeriodId'] == 9:
            m['home']['totalPoints'], m['away']['totalPoints'] = 61.2, 48.9
            assert m['winner'] == 'UNDECIDED'
    assert 9 not in parse_weekly_scores(in_progress)
    assert sum(r['wins'] + r['losses'] for r in parse_team_records(in_progress).values()) == 8 * 12


def test_team_records_ignore_playoff_games(completed):
    records = parse_team_records(completed)
    for team in completed['teams']:
        espn = team['record']['overall']
        mine = records[team['id']]
        assert (mine['wins'], mine['losses'], mine['ties']) == \
               (espn['wins'], espn['losses'], espn['ties'])


# ---------------------------------------------------------------------- divisions

def test_parse_divisions_maps_team_to_division_name(in_progress):
    divisions = parse_divisions(in_progress)
    assert set(divisions) == {t['id'] for t in in_progress['teams']}
    assert Counter(divisions.values()) == {'East': 6, 'West': 6}


# ----------------------------------------------------------------------- schedule

def test_schedule_includes_future_regular_season_weeks(in_progress):
    schedule = parse_schedule(in_progress)
    assert sorted({week for week, _, _ in schedule}) == list(range(1, 15))
    assert len(schedule) == 84


def test_schedule_excludes_playoff_weeks(completed):
    schedule = parse_schedule(completed)
    assert max(week for week, _, _ in schedule) == 14
    assert len(schedule) == 84


def test_schedule_each_team_plays_once_per_week(in_progress):
    by_week = Counter()
    for week, team1, team2 in parse_schedule(in_progress):
        by_week[(week, team1)] += 1
        by_week[(week, team2)] += 1
    assert set(by_week.values()) == {1}
    assert len(by_week) == 14 * 12


# ----------------------------------------------------------------------- settings

def test_parse_league_settings(in_progress):
    assert parse_league_settings(in_progress) == {
        'playoff_team_count': 6,
        'playoff_seeding_rule': 'TOTAL_POINTS_SCORED',
        'regular_season_weeks': 14,
        'matchup_tie_rule': 'NONE',
        'divisions': ['East', 'West'],
    }


# ------------------------------------------------------------------- file outputs

def test_scores_csv_has_team_id_and_division(in_progress, tmp_path):
    path = tmp_path / 'scores.csv'
    write_scores_csv(in_progress, path)
    df = pd.read_csv(path)
    assert list(df.columns[:4]) == ['Team ID', 'Team', 'Division', 'Record']
    assert [c for c in df.columns if c.startswith('W')] == [f'W{w}' for w in range(1, 9)]
    assert Counter(df['Division']) == {'East': 6, 'West': 6}
    assert df['Team'].str.startswith('Owner').all()


def test_schedule_csv_round_trips(in_progress, tmp_path):
    path = tmp_path / 'schedule.csv'
    write_schedule_csv(in_progress, path)
    df = pd.read_csv(path)
    assert list(df.columns) == ['Week', 'Team 1 ID', 'Team 1', 'Team 2 ID', 'Team 2']
    assert sorted(zip(df['Week'], df['Team 1 ID'], df['Team 2 ID'])) == \
           sorted(parse_schedule(in_progress))


def test_league_settings_json_round_trips(in_progress, tmp_path):
    path = tmp_path / 'settings.json'
    write_league_settings(in_progress, path)
    assert json.loads(path.read_text()) == parse_league_settings(in_progress)
