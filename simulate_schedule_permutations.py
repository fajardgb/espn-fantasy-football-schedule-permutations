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
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import Bbox
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

        # Season may be shorter than a full round-robin (e.g. still in progress)
        return schedule[:self.n_weeks]

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
        total_wins = {team: 0 for team in self.teams}
        
        generator = ScheduleGenerator(self.teams, self.n_weeks)
        
        for i in range(num_schedules):
            if i % 1000 == 0:
                print(f"Processing schedule {i}/{num_schedules}")
            
            schedule = generator.generate_schedule()
            team_records = self.simulate_schedule(schedule)
            for team, record in team_records.items():
                total_wins[team] += record['wins']
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
            
            # Mean win % across every simulated schedule permutation
            expected_win_pct = total_wins[team] / (num_schedules * self.n_weeks) * 100

            results.append({
                'Player': team,
                'Actual Record': actual_record,
                'Points For': points_for,
                'Actual Win %': record_to_win_pct(actual_record),
                'Expected Win %': expected_win_pct,
                'Luck (pp)': record_to_win_pct(actual_record) - expected_win_pct,
                'Playoff %': playoff_percentages[team]
            })
        
        return pd.DataFrame(results).sort_values('Playoff %', ascending=False)


def standardize_name(name: str) -> str:
    """Capitalize the first letter of each name part ('jason wu' -> 'Jason Wu').

    Only the first letter is changed, so names like 'McDonald' keep their casing.
    """
    return ' '.join(part[:1].upper() + part[1:] for part in str(name).split())


def disambiguate_names(names: pd.Series) -> pd.Series:
    """
    Make player names unique by suffixing repeats: ['MM', 'BK', 'MM'] ->
    ['MM', 'BK', 'MM (2)']. Teams are keyed by name throughout the simulation,
    so duplicates would otherwise be silently merged into one team.
    """
    counts: Dict[str, int] = {}
    unique = []
    for name in names:
        counts[name] = counts.get(name, 0) + 1
        unique.append(name if counts[name] == 1 else f"{name} ({counts[name]})")
    return pd.Series(unique, index=names.index)


def record_to_win_pct(record: str) -> float:
    """Convert a 'W-L' or 'W-L-T' record string to a win percentage (ties count as half)."""
    parts = [int(p) for p in str(record).split('-')]
    wins, losses = parts[0], parts[1]
    ties = parts[2] if len(parts) > 2 else 0
    games = wins + losses + ties
    return (wins + 0.5 * ties) / games * 100 if games else 0.0


def _place_name_labels(fig, ax, results_df: pd.DataFrame,
                       text_color: str, leader_color: str) -> None:
    """
    Label each point with the player's name, avoiding overlaps.

    Actual win % is discrete, so many players share a row. Each label tries
    vertical offsets (above/below the dot, in widening tiers) and takes the
    first one whose rendered box doesn't collide with an already-placed label,
    a dot, or existing text on the axes (region boxes, diagonal label).
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    # Obstacles: existing axes text plus a small box around every dot
    obstacles = [t.get_window_extent(renderer).expanded(1.05, 1.15) for t in ax.texts]
    dot_radius = 9 * fig.dpi / 72
    for x, y in zip(results_df['Expected Win %'], results_df['Actual Win %']):
        px, py = ax.transData.transform((x, y))
        obstacles.append(Bbox.from_extents(px - dot_radius, py - dot_radius,
                                           px + dot_radius, py + dot_radius))

    tiers = [10, 24, 38, 52, 66]
    for _, group in results_df.groupby('Actual Win %'):
        for i, (_, row) in enumerate(group.sort_values('Expected Win %').iterrows()):
            x, y = row['Expected Win %'], row['Actual Win %']
            ha = 'left' if x < 15 else 'right' if x > 85 else 'center'
            # Alternate the preferred side so crowded rows fan out both ways
            first, second = (1, -1) if i % 2 == 0 else (-1, 1)
            candidates = [s * t for t in tiers for s in (first, second)]

            def make_label(dy, leader=False):
                return ax.annotate(
                    row['Player'], (x, y),
                    xytext=(0, dy), textcoords='offset points',
                    ha=ha, va='bottom' if dy > 0 else 'top',
                    fontsize=10.5, color=text_color, zorder=4,
                    arrowprops=dict(arrowstyle='-', color=leader_color, lw=0.6,
                                    shrinkA=0, shrinkB=6) if leader else None,
                )

            # Probe each candidate offset; keep the first that fits
            # (or the last one if nothing fits)
            for dy in candidates:
                probe = make_label(dy)
                box = probe.get_window_extent(renderer).expanded(1.04, 1.1)
                probe.remove()
                if not any(box.overlaps(o) for o in obstacles):
                    break

            obstacles.append(box)
            # Leader line from dot when the label was pushed past the first tier
            make_label(dy, leader=abs(dy) > tiers[0])


def create_luck_scatterplot(results_df: pd.DataFrame, league_id: str, year: int,
                            num_schedules: int, output_dir: Path) -> None:
    """
    Scatterplot of expected win % (averaged over all simulated schedules) vs
    actual win %. Points above the y = x line are lucky; below are unlucky.

    Args:
        results_df: DataFrame with 'Expected Win %' and 'Actual Win %' columns
        league_id: League identifier
        year: Season year
        num_schedules: Number of simulations run
        output_dir: Directory to save the plot
    """
    surface = '#fcfcfb'
    text_primary = '#0b0b0b'
    text_secondary = '#52514e'
    neutral = '#9a9993'
    unlucky_red = '#d03b3b'
    lucky_green = '#1a9b4b'

    # Diverging colormap: red (unlucky) -> yellow (0) -> green (lucky),
    # symmetric around zero so equal luck magnitudes get equal color intensity.
    # The yellow is a deep gold so near-zero dots stay visible on the light surface.
    luck_cmap = LinearSegmentedColormap.from_list(
        'luck', [unlucky_red, '#f08a24', '#f2c200', '#8cc63f', lucky_green]
    )
    luck_limit = max(results_df['Luck (pp)'].abs().max(), 1.0)
    luck_norm = Normalize(vmin=-luck_limit, vmax=luck_limit)

    fig, ax = plt.subplots(figsize=(11, 10))
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)

    # y = x reference line: actual record matches schedule-neutral expectation
    ax.plot([0, 100], [0, 100], color=neutral, linestyle='--', linewidth=1.5, zorder=1)
    ax.text(8, 6, 'Actual = Expected', color=text_secondary, fontsize=9,
            ha='left', va='top', rotation=45, rotation_mode='anchor')

    # Region labels: black text in a box outlined with the region's color
    ax.text(3, 97, 'LUCKY\nWon more than schedule-neutral', color=text_primary,
            fontsize=8.5, fontweight='bold', ha='left', va='top',
            bbox=dict(boxstyle='square,pad=0.4', facecolor=surface,
                      edgecolor=lucky_green, linewidth=2))
    ax.text(97, 3, 'UNLUCKY\nWon fewer than schedule-neutral', color=text_primary,
            fontsize=8.5, fontweight='bold', ha='right', va='bottom',
            bbox=dict(boxstyle='square,pad=0.4', facecolor=surface,
                      edgecolor=unlucky_red, linewidth=2))

    points = ax.scatter(
        results_df['Expected Win %'], results_df['Actual Win %'],
        c=results_df['Luck (pp)'], cmap=luck_cmap, norm=luck_norm,
        s=140, edgecolor=surface, linewidth=2, zorder=3,
    )

    # Small headroom so labels at 0% / 100% stay inside the plot
    ax.set_xlim(-2, 102)
    ax.set_ylim(-2, 106)
    ax.set_xticks(range(0, 101, 20))
    ax.set_yticks(range(0, 101, 20))
    ax.set_aspect('equal')
    ax.set_xlabel('Expected Win % (avg. over all simulated schedules)',
                  fontsize=12, color=text_primary)
    ax.set_ylabel('Actual Win %', fontsize=12, color=text_primary)
    ax.set_title(
        f'Schedule Luck: Actual vs. Expected Win %\n'
        f'({num_schedules:,} schedule simulations)',
        fontsize=14, fontweight='bold', color=text_primary, pad=16
    )
    ax.grid(alpha=0.25, linestyle='-', linewidth=0.8)
    ax.tick_params(colors=text_secondary)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    for spine in ('left', 'bottom'):
        ax.spines[spine].set_color(neutral)

    # Luck index colorbar on the right
    cbar = fig.colorbar(points, ax=ax, location='right', shrink=0.8, pad=0.04, aspect=30)
    cbar.set_label('Luck Index (actual − expected win %, pct. points)',
                   fontsize=11, color=text_primary)
    cbar.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:+.0f}'))
    cbar.ax.tick_params(colors=text_secondary)
    cbar.outline.set_visible(False)

    # Label every player by name (luck is carried by color). Done last, once the
    # layout (incl. colorbar) is final, so collision checks use real positions.
    _place_name_labels(fig, ax, results_df, text_primary, neutral)

    output_path = output_dir / f'league{league_id}_year{year}_luck_scatterplot.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Luck scatterplot saved to {output_path}")
    plt.close(fig)


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
    df['Player'] = df['Player'].map(standardize_name)
    duplicates = sorted(df.loc[df['Player'].duplicated(), 'Player'].unique())
    if duplicates:
        print(f"Warning: duplicate player names {duplicates}; adding numeric suffixes")
    df['Player'] = disambiguate_names(df['Player'])
    
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
    create_luck_scatterplot(results_df, league_id, year, num_schedules, data_dir.parent)
    
    # Save results to CSV
    results_path = data_dir / f'playoff_probabilities_league{league_id}_y{year}.csv'
    results_df.to_csv(results_path, index=False)
    print(f"Results saved to {results_path}")


if __name__ == "__main__":
    main()
