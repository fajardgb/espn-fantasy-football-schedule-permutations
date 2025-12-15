"""ESPN Fantasy Football API Client with improved structure and error handling."""

import csv
import os
from typing import Dict, List, Optional
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv


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
        response = requests.get(
            self.base_url,
            params=params,
            cookies=self.cookies,
            timeout=30
        )
        response.raise_for_status()
        return response.json()

    def _extract_team_names(self, data: dict) -> Dict[int, str]:
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

    def _is_valid_matchup(self, matchup: dict) -> bool:
        """
        Check if a matchup is valid (completed and not a playoff matchup).
        
        Args:
            matchup: Matchup data from API
            
        Returns:
            True if matchup should be processed, False otherwise
        """
        # Skip playoff matchups
        if matchup.get('matchupPeriodId', 0) == 0:
            return False
        
        # Skip unplayed games (where points are 0)
        home = matchup.get('home', {})
        away = matchup.get('away', {})
        
        if home.get('totalPoints', 0) == 0 or away.get('totalPoints', 0) == 0:
            return False
        
        return True

    def get_weekly_scores(self) -> Dict[int, List[Dict]]:
        """
        Get scores for all teams for each week of the season.
        
        Returns:
            Dictionary with week numbers as keys and list of dicts as values.
            Each dict contains: team_id, owner_name, score
        """
        data = self._make_request(["mMatchup", "mTeam"])
        teams = self._extract_team_names(data)
        weekly_scores: Dict[int, List[Dict]] = {}
        
        for matchup in data.get('schedule', []):
            if not self._is_valid_matchup(matchup):
                continue
            
            week = matchup['matchupPeriodId']
            if week not in weekly_scores:
                weekly_scores[week] = []
            
            # Process home team
            if 'home' in matchup:
                home_id = matchup['home']['teamId']
                home_score = matchup['home'].get('totalPoints', 0)
                weekly_scores[week].append({
                    'team_id': home_id,
                    'owner_name': teams.get(home_id, f"Team {home_id}"),
                    'score': home_score
                })
            
            # Process away team
            if 'away' in matchup:
                away_id = matchup['away']['teamId']
                away_score = matchup['away'].get('totalPoints', 0)
                weekly_scores[week].append({
                    'team_id': away_id,
                    'owner_name': teams.get(away_id, f"Team {away_id}"),
                    'score': away_score
                })
        
        return weekly_scores

    def get_team_records(self) -> Dict[int, Dict]:
        """
        Get win-loss records for all teams.
        
        Returns:
            Dictionary with team IDs as keys and record dicts as values.
            Each dict contains: team_id, owner_name, wins, losses, ties
        """
        data = self._make_request(["mMatchup", "mTeam"])
        teams = self._extract_team_names(data)
        
        # Initialize records for all teams
        records = {
            team_id: {
                'team_id': team_id,
                'owner_name': owner_name,
                'wins': 0,
                'losses': 0,
                'ties': 0
            }
            for team_id, owner_name in teams.items()
        }
        
        # Calculate records from completed matchups
        for matchup in data.get('schedule', []):
            if not self._is_valid_matchup(matchup):
                continue
            
            if 'home' not in matchup or 'away' not in matchup:
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
        """
        Save weekly scores to CSV in wide format (teams as rows, weeks as columns).
        
        Args:
            filepath: Path object for output CSV file
        """
        scores = self.get_weekly_scores()
        records = self.get_team_records()
        
        # Get all teams and weeks
        all_teams = {
            team_id: record['owner_name']
            for team_id, record in records.items()
        }
        weeks = sorted(scores.keys())
        
        # Ensure parent directory exists
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header
            header = ['Player', 'Record'] + [f'W{w}' for w in weeks]
            writer.writerow(header)
            
            # Write data for each team
            for team_id in sorted(all_teams.keys()):
                record = records[team_id]
                record_str = f"{record['wins']}-{record['losses']}"
                if record['ties'] > 0:
                    record_str += f"-{record['ties']}"
                
                row = [record['owner_name'], record_str]
                
                for week in weeks:
                    # Find score for this team in this week
                    score_str = ''
                    for team_score in scores.get(week, []):
                        if team_score['team_id'] == team_id:
                            score_str = f"{team_score['score']:.2f}"
                            break
                    row.append(score_str)
                
                writer.writerow(row)
        
        print(f"Scores saved to {filepath}")


def load_config() -> tuple[int, int, Optional[str], Optional[str]]:
    """
    Load configuration from environment variables.
    
    Returns:
        Tuple of (league_id, year, espn_s2, swid)
        
    Raises:
        ValueError: If required environment variables are missing
    """
    load_dotenv()
    
    league_id = os.getenv('LEAGUE_ID')
    year = os.getenv('YEAR')
    
    if not league_id or not year:
        raise ValueError("LEAGUE_ID and YEAR must be set in environment variables (.env file).")
    
    return (
        int(league_id),
        int(year),
        os.getenv('ESPN_S2'),
        os.getenv('SWID')
    )


def main():
    """Main execution function."""
    # Load configuration
    league_id, year, espn_s2, swid = load_config()
    
    # Initialize client
    client = ESPNFantasyFootball(league_id, year, espn_s2, swid)
    
    # Print weekly scores to console
    # client.print_weekly_scores()
    # client.print_records()
    
    # Save to CSV
    output_dir = f'./output/league{league_id}_year{year}/data'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    csv_path = f'{output_dir}/fantasy_scores_wide_league{league_id}_y{year}.csv'
    client.save_to_csv_wide(csv_path)


if __name__ == "__main__":
    main()
