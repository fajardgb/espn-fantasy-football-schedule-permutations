"""ESPN Fantasy Football API Client with improved structure and error handling."""

import csv
import json
import os
import re
import sys
from typing import Callable, Dict, List, Optional, Tuple
from pathlib import Path

import requests
from dotenv import load_dotenv


# Views requested from the ESPN API: league settings, teams, and all matchups
API_VIEWS = ["mSettings", "mTeam", "mMatchup"]

README_HINT = 'See "Configure your league" in the README for help.'


class SetupError(Exception):
    """A problem the user can fix (settings, credentials, missing files).

    The message is shown as-is, without a Python traceback.
    """


def run_cli(main_func: Callable[[], None]) -> None:
    """Run a script's main(), showing setup problems as a plain message."""
    try:
        main_func()
    except SetupError as error:
        print(f"\nError: {error}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Parsing helpers (pure functions over an ESPN API response)
# ---------------------------------------------------------------------------

def parse_team_names(data: dict) -> Dict[int, str]:
    """
    Extract team ID to owner name mapping from API response.

    Args:
        data: API response data

    Returns:
        Dictionary mapping team IDs to owner names
    """
    teams = {}
    members = {m['id']: m for m in data.get('members', [])}

    for team in data.get('teams', []):
        team_id = team['id']
        owner_name = None

        if team.get('owners'):
            owner_id = team['owners'][0]
            member = members.get(owner_id)
            if member:
                first = member.get('firstName', '')
                last = member.get('lastName', '')
                owner_name = f"{first} {last}".strip()

        teams[team_id] = owner_name or team.get('name', f"Team {team_id}")

    return teams


def regular_season_length(data: dict) -> int:
    """Number of regular-season matchup periods; later periods are playoffs."""
    return data['settings']['scheduleSettings']['matchupPeriodCount']


def _regular_season_matchups(data: dict) -> List[dict]:
    """All regular-season matchups (played or not), excluding playoff weeks."""
    last_week = regular_season_length(data)
    return [m for m in data.get('schedule', []) if 1 <= m['matchupPeriodId'] <= last_week]


def _is_played(matchup: dict) -> bool:
    """A matchup is final once ESPN records a result (in-progress games are UNDECIDED)."""
    return matchup.get('winner', 'UNDECIDED') != 'UNDECIDED'


def parse_weekly_scores(data: dict) -> Dict[int, List[Dict]]:
    """
    Get scores for all teams for each completed regular-season week.

    Returns:
        Dictionary with week numbers as keys and list of dicts as values.
        Each dict contains: team_id, owner_name, score
    """
    teams = parse_team_names(data)
    weekly_scores: Dict[int, List[Dict]] = {}

    for matchup in _regular_season_matchups(data):
        if not _is_played(matchup):
            continue

        week = matchup['matchupPeriodId']
        for side in ('home', 'away'):
            if side in matchup:
                team_id = matchup[side]['teamId']
                weekly_scores.setdefault(week, []).append({
                    'team_id': team_id,
                    'owner_name': teams.get(team_id, f"Team {team_id}"),
                    'score': matchup[side].get('totalPoints', 0),
                })

    return weekly_scores


def parse_team_records(data: dict) -> Dict[int, Dict]:
    """
    Get regular-season win-loss records for all teams.

    Returns:
        Dictionary with team IDs as keys and record dicts as values.
        Each dict contains: team_id, owner_name, wins, losses, ties
    """
    teams = parse_team_names(data)
    records = {
        team_id: {'team_id': team_id, 'owner_name': owner_name,
                  'wins': 0, 'losses': 0, 'ties': 0}
        for team_id, owner_name in teams.items()
    }

    for matchup in _regular_season_matchups(data):
        if not _is_played(matchup) or 'home' not in matchup or 'away' not in matchup:
            continue

        home_id = matchup['home']['teamId']
        away_id = matchup['away']['teamId']
        home_score = matchup['home'].get('totalPoints', 0)
        away_score = matchup['away'].get('totalPoints', 0)

        if home_score > away_score:
            records[home_id]['wins'] += 1
            records[away_id]['losses'] += 1
        elif away_score > home_score:
            records[away_id]['wins'] += 1
            records[home_id]['losses'] += 1
        else:
            records[home_id]['ties'] += 1
            records[away_id]['ties'] += 1

    return records


def parse_divisions(data: dict) -> Dict[int, str]:
    """Map each team ID to its division name."""
    names = {d['id']: d['name']
             for d in data['settings']['scheduleSettings'].get('divisions', [])}
    return {t['id']: names.get(t.get('divisionId'), str(t.get('divisionId')))
            for t in data.get('teams', [])}


def parse_schedule(data: dict) -> List[Tuple[int, int, int]]:
    """
    Full regular-season schedule, including weeks not yet played.

    Returns:
        List of (week, team1_id, team2_id). One-sided entries (byes) are omitted.
    """
    return [
        (m['matchupPeriodId'], m['home']['teamId'], m['away']['teamId'])
        for m in _regular_season_matchups(data)
        if 'home' in m and 'away' in m
    ]


def parse_league_settings(data: dict) -> dict:
    """League rules the simulation needs (playoff format, season length, ties)."""
    schedule = data['settings']['scheduleSettings']
    scoring = data['settings'].get('scoringSettings', {})
    return {
        'playoff_team_count': schedule['playoffTeamCount'],
        'playoff_seeding_rule': schedule.get('playoffSeedingRule'),
        'regular_season_weeks': schedule['matchupPeriodCount'],
        'matchup_tie_rule': scoring.get('matchupTieRule'),
        'divisions': [d['name'] for d in schedule.get('divisions', [])],
    }


# ---------------------------------------------------------------------------
# File outputs
# ---------------------------------------------------------------------------

def write_scores_csv(data: dict, filepath: Path) -> None:
    """
    Save weekly scores in wide format (teams as rows, weeks as columns),
    with each team's ESPN ID, division, and record.
    """
    scores = parse_weekly_scores(data)
    records = parse_team_records(data)
    divisions = parse_divisions(data)
    weeks = sorted(scores)

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Team ID', 'Team', 'Division', 'Record'] + [f'W{w}' for w in weeks])

        for team_id in sorted(records):
            record = records[team_id]
            record_str = f"{record['wins']}-{record['losses']}"
            if record['ties'] > 0:
                record_str += f"-{record['ties']}"

            row = [team_id, record['owner_name'], divisions.get(team_id, ''), record_str]
            for week in weeks:
                score = next((s['score'] for s in scores[week] if s['team_id'] == team_id), None)
                row.append(f"{score:.2f}" if score is not None else '')
            writer.writerow(row)


def write_schedule_csv(data: dict, filepath: Path) -> None:
    """Save the full regular-season schedule (one row per matchup)."""
    names = parse_team_names(data)
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Week', 'Team 1 ID', 'Team 1', 'Team 2 ID', 'Team 2'])
        for week, team1, team2 in sorted(parse_schedule(data)):
            writer.writerow([week, team1, names.get(team1, ''), team2, names.get(team2, '')])


def write_league_settings(data: dict, filepath: Path) -> None:
    """Save the league rules used by the simulation as JSON."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(parse_league_settings(data), indent=2))


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class ESPNFantasyFootball:
    """Client for interacting with ESPN Fantasy Football API."""

    def __init__(
        self,
        league_id: int,
        year: int,
        espn_s2: Optional[str] = None,
        swid: Optional[str] = None
    ):
        """
        Initialize ESPN Fantasy Football API client.

        Args:
            league_id: Your ESPN league ID
            year: Season year (e.g., 2024)
            espn_s2: ESPN_S2 cookie (required for private leagues)
            swid: SWID cookie (required for private leagues)
        """
        self.league_id = league_id
        self.year = year
        self.base_url = (
            f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/"
            f"seasons/{year}/segments/0/leagues/{league_id}"
        )
        self.cookies = {}
        if espn_s2 and swid:
            self.cookies = {"espn_s2": espn_s2, "SWID": swid}
        self._data: Optional[dict] = None

    def _make_request(self, views: List[str]) -> dict:
        """
        Make authenticated request to ESPN API.

        Args:
            views: List of API views to retrieve

        Returns:
            JSON response data

        Raises:
            requests.RequestException: If the API request fails
        """
        params = {"view": views}
        try:
            response = requests.get(
                self.base_url,
                params=params,
                cookies=self.cookies,
                timeout=30
            )
        except requests.ConnectionError:
            raise SetupError("Couldn't reach ESPN. Check your internet connection and try again.")
        except requests.Timeout:
            raise SetupError("ESPN took too long to respond. Try again in a minute.")

        if response.status_code == 401:
            if self.cookies:
                raise SetupError(
                    "ESPN refused access to this league (401 Unauthorized). Your ESPN_S2 or "
                    "SWID is probably wrong or expired: make sure you copied all of ESPN_S2 "
                    "and SWID exactly as shown in your browser, and haven't logged out of ESPN since "
                    f"copying them. {README_HINT}")
            raise SetupError(
                "This league is private (401 Unauthorized), so ESPN_S2 and SWID are needed "
                f"in your .env file. {README_HINT}")
        if response.status_code == 404:
            raise SetupError(
                f"ESPN couldn't find league {self.league_id} for the {self.year} season "
                f"(404 Not Found). Check LEAGUE_ID and YEAR in your .env file. {README_HINT}")
        if 400 <= response.status_code < 500:
            raise SetupError(
                f"ESPN rejected the request for league {self.league_id}, {self.year} season "
                f"(error {response.status_code}). Check LEAGUE_ID and YEAR in your .env file. "
                f"{README_HINT}")
        if response.status_code >= 500:
            raise SetupError(
                f"ESPN's servers had a problem (error {response.status_code}). "
                "This is on ESPN's side: try again in a few minutes.")
        response.raise_for_status()
        return response.json()

    def fetch(self) -> dict:
        """Fetch settings, teams, and matchups once and cache the response."""
        if self._data is None:
            self._data = self._make_request(API_VIEWS)
        return self._data

    def get_weekly_scores(self) -> Dict[int, List[Dict]]:
        """Scores for every team in each completed regular-season week."""
        return parse_weekly_scores(self.fetch())

    def get_team_records(self) -> Dict[int, Dict]:
        """Regular-season win-loss records for all teams."""
        return parse_team_records(self.fetch())

    def print_weekly_scores(self) -> None:
        """Print formatted weekly scores for all teams."""
        scores = self.get_weekly_scores()

        for week in sorted(scores.keys()):
            print(f"\n{'='*60}")
            print(f"WEEK {week}")
            print(f"{'='*60}")

            # Sort teams by score for the week (descending)
            week_scores = sorted(scores[week], key=lambda x: x['score'], reverse=True)

            for team in week_scores:
                print(f"{team['owner_name']:30} {team['score']:6.2f} pts")

    def print_records(self) -> None:
        """Print team records sorted by wins."""
        records = self.get_team_records()

        print(f"\n{'='*60}")
        print("TEAM RECORDS")
        print(f"{'='*60}")

        # Sort by wins (descending), then losses (ascending)
        sorted_records = sorted(
            records.values(),
            key=lambda x: (x['wins'], -x['losses']),
            reverse=True
        )

        for record in sorted_records:
            record_str = f"{record['wins']}-{record['losses']}"
            if record['ties'] > 0:
                record_str += f"-{record['ties']}"
            print(f"{record['owner_name']:30} {record_str}")

    def save_to_csv_wide(self, filepath: Path) -> None:
        """Save weekly scores (with team IDs and divisions) to CSV."""
        write_scores_csv(self.fetch(), filepath)
        print(f"Scores saved to {filepath}")

    def save_schedule(self, filepath: Path) -> None:
        """Save the full regular-season schedule to CSV."""
        write_schedule_csv(self.fetch(), filepath)
        print(f"Schedule saved to {filepath}")

    def save_league_settings(self, filepath: Path) -> None:
        """Save playoff format and other league rules to JSON."""
        write_league_settings(self.fetch(), filepath)
        print(f"League settings saved to {filepath}")


def league_data_paths(league_id, year) -> Dict[str, Path]:
    """Where the data files for a league/season live."""
    data_dir = Path(f'./output/league{league_id}_year{year}/data')
    return {
        'dir': data_dir,
        'scores': data_dir / f'fantasy_scores_wide_league{league_id}_y{year}.csv',
        'schedule': data_dir / f'schedule_league{league_id}_y{year}.csv',
        'settings': data_dir / f'league_settings_league{league_id}_y{year}.json',
    }


PLACEHOLDER_PREFIX = 'your_'


def parse_league_input(value: str) -> Tuple[int, Optional[int]]:
    """
    Read a league ID from either a plain number or a pasted ESPN league URL.

    Returns:
        (league_id, season): season comes from the URL's seasonId, if present

    Example:
        'https://fantasy.espn.com/football/league?leagueId=123&seasonId=2025'
        -> (123, 2025)
    """
    value = value.strip().strip('"\'')
    if value.isdigit():
        return int(value), None
    league = re.search(r'leagueId=(\d+)', value)
    if not league:
        raise SetupError(
            f"LEAGUE_ID should be a number (or your league's web address), but it's "
            f"'{value}'. {README_HINT}")
    season = re.search(r'seasonId=(\d{4})', value)
    return int(league.group(1)), int(season.group(1)) if season else None


def _env(name: str) -> Optional[str]:
    """An environment variable, treating empty and example values as unset."""
    value = (os.getenv(name) or '').strip()
    return None if not value or value.startswith(PLACEHOLDER_PREFIX) else value


def load_league_and_year() -> Tuple[int, int]:
    """
    League ID and season from the .env file (or environment).

    LEAGUE_ID may be the league's ID or its full web address. YEAR may be left
    out when that address includes seasonId.

    Raises:
        SetupError: with a plain-language explanation of what to fix
    """
    load_dotenv()
    raw_league = _env('LEAGUE_ID')
    if raw_league is None:
        raise SetupError(
            "LEAGUE_ID isn't set. Make sure you've copied .env_example to a file named .env "
            f"in the project folder and filled in your league's details. {README_HINT}")
    league_id, url_season = parse_league_input(raw_league)

    raw_year = _env('YEAR')
    if raw_year is None:
        if url_season is None:
            raise SetupError(
                f"YEAR isn't filled in in your .env file (e.g. YEAR=2025). {README_HINT}")
        return league_id, url_season
    if not (raw_year.isdigit() and len(raw_year) == 4):
        raise SetupError(f"YEAR should be a 4-digit year like 2025, but it's '{raw_year}'.")
    return league_id, int(raw_year)


def load_config() -> tuple[int, int, Optional[str], Optional[str]]:
    """
    Load configuration from environment variables.

    Returns:
        Tuple of (league_id, year, espn_s2, swid); the cookies are None when
        not set (public leagues don't need them)

    Raises:
        SetupError: If required settings are missing or malformed
    """
    league_id, year = load_league_and_year()
    espn_s2, swid = _env('ESPN_S2'), _env('SWID')
    if bool(espn_s2) != bool(swid):
        missing = 'SWID' if espn_s2 else 'ESPN_S2'
        print(f"Warning: {missing} is empty, so ESPN_S2 and SWID will both be ignored. "
              "Private leagues need both.")
        espn_s2 = swid = None
    return league_id, year, espn_s2, swid


def fetch_league_data(league_id: int, year: int, espn_s2: Optional[str] = None,
                      swid: Optional[str] = None) -> Dict[str, Path]:
    """Download a league's scores, schedule and settings to its output folder."""
    client = ESPNFantasyFootball(league_id, year, espn_s2, swid)
    paths = league_data_paths(league_id, year)
    paths['dir'].mkdir(parents=True, exist_ok=True)
    client.save_to_csv_wide(paths['scores'])
    client.save_schedule(paths['schedule'])
    client.save_league_settings(paths['settings'])
    return paths


def main():
    """Main execution function."""
    league_id, year, espn_s2, swid = load_config()
    print(f"Downloading league {league_id}, {year} season, from ESPN...")
    fetch_league_data(league_id, year, espn_s2, swid)


if __name__ == "__main__":
    run_cli(main)
