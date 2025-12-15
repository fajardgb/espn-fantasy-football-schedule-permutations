"""
Fantasy Football Playoff Probability Simulator

This module simulates random schedules to calculate playoff probabilities
for each team in a fantasy football league.
"""

import os
import random
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from dotenv import load_dotenv


class ScheduleGenerator:
    """Generates round-robin fantasy football schedules."""
    
    def __init__(self, teams: List[str], n_weeks: int):
        """
        Initialize the schedule generator.
        
        Args:
            teams: List of team names
            n_weeks: Number of weeks in the season
        """
        self.teams = teams.copy()
        self.n_teams = len(teams)
        self.n_weeks = n_weeks
        
    def generate_schedule(self) -> List[List[Tuple[str, str]]]:
        """
        Generate a single round-robin schedule.
        
        Returns:
            List of weeks, where each week contains matchup tuples
        """
        schedule = []
        teams = self.teams.copy()
        random.shuffle(teams)
        
        # Generate round-robin for n_teams - 1 weeks
        for week in range(self.n_teams - 1):
            week_matches = []
            for i in range(self.n_teams // 2):
                team1 = teams[i]
                team2 = teams[self.n_teams - 1 - i]
                week_matches.append((team1, team2))
            schedule.append(week_matches)
            
            # Rotate teams (keep first fixed)
            teams = [teams[0]] + [teams[-1]] + teams[1:-1]
        
        # Repeat early weeks for remaining schedule
        remaining_weeks = self.n_weeks - (self.n_teams - 1)
        for week in range(remaining_weeks):
            schedule.append(schedule[week])
        
        return schedule
    
    def validate_schedule(self, schedule: List[List[Tuple[str, str]]]) -> bool:
        """
        Validate that each team plays every other team exactly once
        in the first n_teams - 1 weeks.
        
        Args:
            schedule: Schedule to validate
            
        Returns:
            True if schedule is valid
        """
        for team in self.teams:
            opponents = set()
            for week_idx in range(self.n_teams - 1):
                for match in schedule[week_idx]:
                    if team in match:
                        opponent = match[1] if match[0] == team else match[0]
                        opponents.add(opponent)
            
            if len(opponents) != self.n_teams - 1:
                return False
        return True


class PlayoffSimulator:
    """Simulates playoff outcomes based on different schedules."""
    
    def __init__(self, scores_df: pd.DataFrame, n_playoff_teams: int = 6):
        """
        Initialize the simulator.
        
        Args:
            scores_df: DataFrame with weekly scores (Player, Record, W1, W2, ...)
            n_playoff_teams: Number of teams that make playoffs
        """
        self.scores_df = scores_df
        self.n_playoff_teams = n_playoff_teams
        self.teams = scores_df['Player'].tolist()
        self.week_columns = [col for col in scores_df.columns if col.startswith('W')]
        self.n_weeks = len(self.week_columns)
    
    def simulate_schedule(self, schedule: List[List[Tuple[str, str]]]) -> Dict[str, Dict[str, float]]:
        """
        Simulate a season with the given schedule.
        
        Args:
            schedule: Weekly matchups
            
        Returns:
            Dictionary of team records with wins, losses, and points_for
        """
        team_records = {
            team: {'wins': 0, 'losses': 0, 'points_for': 0.0}
            for team in self.teams
        }
        
        for week_idx, week_matchups in enumerate(schedule):
            week_col = self.week_columns[week_idx]
            
            for team1, team2 in week_matchups:
                score1 = self.scores_df[self.scores_df['Player'] == team1][week_col].values[0]
                score2 = self.scores_df[self.scores_df['Player'] == team2][week_col].values[0]
                
                team_records[team1]['points_for'] += score1
                team_records[team2]['points_for'] += score2
                
                if score1 > score2:
                    team_records[team1]['wins'] += 1
                    team_records[team2]['losses'] += 1
                else:
                    team_records[team2]['wins'] += 1
                    team_records[team1]['losses'] += 1
        
        return team_records
    
    def get_playoff_teams(self, team_records: Dict[str, Dict[str, float]]) -> List[str]:
        """
        Determine which teams make the playoffs.
        
        Args:
            team_records: Dictionary of team records
            
        Returns:
            List of playoff team names
        """
        sorted_teams = sorted(
            team_records.items(),
            key=lambda x: (x[1]['wins'], x[1]['points_for']),
            reverse=True
        )
        return [team for team, _ in sorted_teams[:self.n_playoff_teams]]
    
    def run_simulation(self, num_schedules: int, seed: int = 42) -> pd.DataFrame:
        """
        Run full playoff probability simulation.
        
        Args:
            num_schedules: Number of random schedules to simulate
            seed: Random seed for reproducibility
            
        Returns:
            DataFrame with playoff probabilities for each team
        """
        random.seed(seed)
        playoff_count = {team: 0 for team in self.teams}
        
        generator = ScheduleGenerator(self.teams, self.n_weeks)
        
        for i in range(num_schedules):
            if i % 1000 == 0:
                print(f"Processing schedule {i}/{num_schedules}")
            
            schedule = generator.generate_schedule()
            team_records = self.simulate_schedule(schedule)
            playoff_teams = self.get_playoff_teams(team_records)
            
            for team in playoff_teams:
                playoff_count[team] += 1
        
        # Calculate playoff percentages
        playoff_percentages = {
            team: (count / num_schedules) * 100
            for team, count in playoff_count.items()
        }
        
        # Create results DataFrame
        results = []
        for team in self.teams:
            actual_record = self.scores_df[self.scores_df['Player'] == team]['Record'].values[0]
            points_for = self.scores_df[self.scores_df['Player'] == team][self.week_columns].sum(axis=1).values[0]
            
            results.append({
                'Player': team,
                'Actual Record': actual_record,
                'Points For': points_for,
                'Playoff %': playoff_percentages[team]
            })
        
        return pd.DataFrame(results).sort_values('Playoff %', ascending=False)


def create_visualization(results_df: pd.DataFrame, league_id: str, year: int, 
                        num_schedules: int, output_dir: Path) -> None:
    """
    Create and save playoff probability visualization.
    
    Args:
        results_df: DataFrame with playoff probabilities
        league_id: League identifier
        year: Season year
        num_schedules: Number of simulations run
        output_dir: Directory to save the plot
    """
    plt.figure(figsize=(12, 8))
    
    # Sort by playoff percentage for better visualization
    sorted_results = results_df.sort_values('Playoff %', ascending=True)
    
    # Create color gradient
    colors = plt.cm.RdYlGn(np.linspace(0.2, 0.8, len(sorted_results)))
    
    # Create horizontal bar chart
    bars = plt.barh(range(len(sorted_results)), sorted_results['Playoff %'], color=colors)
    
    # Create y-axis labels with player name and stats
    y_labels = [
        f"{row['Player']}\n{row['Actual Record']}| {row['Points For']:.1f} PF"
        for _, row in sorted_results.iterrows()
    ]
    plt.yticks(range(len(sorted_results)), y_labels, fontsize=9)
    
    # Labels and title
    plt.xlabel('Playoff Probability (%)', fontsize=12, fontweight='bold')
    plt.ylabel('Player', fontsize=12, fontweight='bold')
    plt.title(
        f'Fantasy Football Playoff Probability\n({num_schedules:,} Schedule Simulations)',
        fontsize=14, fontweight='bold', pad=20
    )
    plt.xlim(0, 100)
    plt.grid(axis='x', alpha=0.3, linestyle='--')
    
    # Add percentage labels on bars
    for i, (_, row) in enumerate(sorted_results.iterrows()):
        plt.text(
            row['Playoff %'] + 1, i, f"{row['Playoff %']:.1f}%",
            va='center', fontsize=10, fontweight='bold'
        )
    
    plt.tight_layout()
    
    # Save figure
    output_path = output_dir / f'league{league_id}_year{year}_playoff_probabilities.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Visualization saved to {output_path}")
    plt.close()
    # plt.show()


def main():
    """Main execution function."""
    # Load environment variables
    load_dotenv()
    league_id = os.getenv('LEAGUE_ID')
    year = os.getenv('YEAR')
    
    if not league_id or not year:
        raise ValueError("LEAGUE_ID and YEAR must be set in environment variables")
    
    # Set up paths
    data_dir = Path(f'./output/league{league_id}_year{year}/data')
    csv_path = data_dir / f'fantasy_scores_wide_league{league_id}_y{year}.csv'
    
    if not csv_path.exists():
        raise FileNotFoundError(f"Data file not found: {csv_path}")
    
    # Load data
    print(f"Loading data for league {league_id} year {year}...")
    df = pd.read_csv(csv_path)
    
    print(f"Number of teams: {len(df)}")
    print(f"Number of weeks: {len([col for col in df.columns if col.startswith('W')])}")
    
    # Run simulation
    num_schedules = 10000
    simulator = PlayoffSimulator(df)
    
    print(f"\nRunning {num_schedules:,} schedule simulations...")
    results_df = simulator.run_simulation(num_schedules)
    
    # Display results
    print("\nPlayoff Probabilities:")
    print(results_df.to_string(index=False))
    
    # Create visualization
    print("\nCreating visualization...")
    create_visualization(results_df, league_id, year, num_schedules, data_dir.parent)
    
    # Save results to CSV
    results_path = data_dir / f'playoff_probabilities_league{league_id}_y{year}.csv'
    results_df.to_csv(results_path, index=False)
    print(f"Results saved to {results_path}")


if __name__ == "__main__":
    main()
