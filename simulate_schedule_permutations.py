"""
Fantasy Football Playoff Probability Simulator

This module simulates random schedules to calculate playoff probabilities
for each team in a fantasy football league.
"""

import json
import random
from pathlib import Path
from itertools import groupby
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import Bbox
import numpy as np
import pandas as pd

from get_espn_league_data import SetupError, league_data_paths, load_league_and_year, run_cli


def games_played(record: Dict[str, float]) -> int:
    """Games in a simulated record (wins + losses + ties)."""
    return record['wins'] + record['losses'] + record.get('ties', 0)


def win_pct(record: Dict[str, float]) -> float:
    """Win fraction of a simulated record; ties count as half a win."""
    games = games_played(record)
    return (record['wins'] + 0.5 * record.get('ties', 0)) / games if games else 0.0


def is_head_to_head_rule(rule: Optional[str]) -> bool:
    """Whether an ESPN playoffSeedingRule means head-to-head record breaks ties."""
    return bool(rule) and ('H2H' in rule.upper() or 'HEAD' in rule.upper())


def seeding_rule_note(rule: Optional[str]) -> Optional[str]:
    """User-facing note when a league's tiebreaker can't be modeled exactly."""
    if rule in (None, 'TOTAL_POINTS_SCORED') or is_head_to_head_rule(rule):
        return None
    return f"Playoff tiebreaker '{rule}' isn't modeled; ties are broken by total points."


def tie_rule_note(rule: Optional[str]) -> Optional[str]:
    """User-facing note when a league's matchup tie rule can't be modeled."""
    if rule in (None, 'NONE'):
        return None
    return f"Matchup tie rule '{rule}' isn't modeled; equal scores count as ties."


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
        # Weeks in one full round-robin. Odd leagues need one extra week so
        # that every team gets exactly one bye per cycle.
        self.cycle_length = self.n_teams - 1 if self.n_teams % 2 == 0 else self.n_teams
        
    def generate_schedule(self) -> List[List[Tuple[str, str]]]:
        """
        Generate a single round-robin schedule.

        Odd leagues are padded with a placeholder bye slot (the standard circle
        method), so each week exactly one team sits out, and every team gets
        exactly one bye per cycle. Bye matchups are dropped from the schedule.
        
        Returns:
            List of weeks, where each week contains matchup tuples
        """
        schedule = []
        teams = self.teams.copy()
        random.shuffle(teams)
        if self.n_teams % 2 == 1:
            teams.append(None)  # bye slot
        n_slots = len(teams)
        
        # Generate one full round-robin cycle
        for week in range(self.cycle_length):
            week_matches = []
            for i in range(n_slots // 2):
                team1 = teams[i]
                team2 = teams[n_slots - 1 - i]
                if team1 is not None and team2 is not None:
                    week_matches.append((team1, team2))
            schedule.append(week_matches)
            
            # Rotate teams (keep first fixed)
            teams = [teams[0]] + [teams[-1]] + teams[1:-1]
        
        # Repeat early weeks for remaining schedule
        remaining_weeks = self.n_weeks - self.cycle_length
        for week in range(remaining_weeks):
            schedule.append(schedule[week])

        # Season may be shorter than a full round-robin (e.g. still in progress)
        return schedule[:self.n_weeks]

    def generate(self) -> Tuple[List[List[Tuple[str, str]]], Dict[str, str]]:
        """Generate a schedule; round-robin leagues have no divisions."""
        return self.generate_schedule(), {}

    def validate_schedule(self, schedule: List[List[Tuple[str, str]]]) -> bool:
        """
        Validate a schedule:
        - each week, every team plays at most once (odd leagues: exactly one bye)
        - within each round-robin cycle, no pair of teams meets twice
        - every complete cycle pairs each team with every other team exactly once

        Partial cycles (e.g. a season still in progress) are allowed.
        
        Args:
            schedule: Schedule to validate
            
        Returns:
            True if schedule is valid
        """
        teams = set(self.teams)
        expected_byes = self.n_teams % 2
        for week in schedule:
            playing = [team for match in week for team in match]
            if len(playing) != len(set(playing)) or not set(playing) <= teams:
                return False
            if len(teams) - len(playing) != expected_byes:
                return False

        all_pairs = self.n_teams * (self.n_teams - 1) // 2
        for start in range(0, len(schedule), self.cycle_length):
            cycle = schedule[start:start + self.cycle_length]
            pairs = [frozenset(match) for week in cycle for match in week]
            if len(pairs) != len(set(pairs)):
                return False
            if len(cycle) == self.cycle_length and len(pairs) != all_pairs:
                return False
        return True


class TemplateScheduleGenerator:
    """
    Generates schedules by randomly assigning teams to the slots of the
    league's real schedule.

    Every simulated season has exactly the real schedule's structure (division
    games, repeat matchups, byes). Assignment is fully random, so a team can
    land in any slot, and takes on that slot's division: being in a tough or
    weak division is part of the luck being measured.
    """

    def __init__(self, template: List[List[Tuple]], slot_divisions: Dict,
                 teams: List[str], n_weeks: int):
        """
        Args:
            template: Real schedule as weeks of (slot, slot) matchups, week 1 first
            slot_divisions: Division of each slot (slots are the real team IDs)
            teams: Team names to assign to slots (one per slot)
            n_weeks: Number of weeks to simulate (weeks played so far)
        """
        self.slots = sorted(slot_divisions)
        if len(teams) != len(self.slots):
            raise ValueError(
                f"Schedule has {len(self.slots)} teams but scores have {len(teams)}"
            )
        if n_weeks > len(template):
            raise ValueError(f"Schedule has {len(template)} weeks but {n_weeks} were played")
        self.template = template[:n_weeks]
        self.slot_divisions = slot_divisions
        self.teams = list(teams)
        self.n_weeks = n_weeks

    def generate(self) -> Tuple[List[List[Tuple[str, str]]], Dict[str, str]]:
        """
        Returns:
            (schedule, divisions): weekly matchups by team name, and each
            team's division for this simulated season
        """
        shuffled = self.teams.copy()
        random.shuffle(shuffled)
        team_in_slot = dict(zip(self.slots, shuffled))

        schedule = [[(team_in_slot[a], team_in_slot[b]) for a, b in week]
                    for week in self.template]
        divisions = {team_in_slot[slot]: self.slot_divisions[slot] for slot in self.slots}
        return schedule, divisions

    def truncated(self, n_weeks: int) -> 'TemplateScheduleGenerator':
        """Same league structure, simulating only the first n_weeks weeks."""
        return TemplateScheduleGenerator(self.template, self.slot_divisions,
                                         self.teams, n_weeks)


class PlayoffSimulator:
    """Simulates playoff outcomes based on different schedules."""
    
    def __init__(self, scores_df: pd.DataFrame, n_playoff_teams: int = 6,
                 generator=None, seeding_rule: Optional[str] = None,
                 actual_schedule: Optional[List[List[Tuple[str, str]]]] = None):
        """
        Initialize the simulator.
        
        Args:
            scores_df: DataFrame with weekly scores (Team, Record, W1, W2, ...)
            n_playoff_teams: Number of teams that make playoffs
            generator: Schedule generator with a generate() -> (schedule, divisions)
                method. Defaults to a random round-robin with no divisions.
            seeding_rule: ESPN playoffSeedingRule. Head-to-head rules break
                win % ties by H2H record first; anything else uses total points.
            actual_schedule: The real weekly matchups (by team name) for the
                simulated weeks. When given, actual records are computed from it
                instead of the scores file's 'Record' column, so they match the
                simulated weeks (e.g. "through week N").
        """
        self.scores_df = scores_df
        self.n_playoff_teams = n_playoff_teams
        self.teams = scores_df['Team'].tolist()
        self.week_columns = [col for col in scores_df.columns if col.startswith('W')]
        self.n_weeks = len(self.week_columns)
        self.generator = generator or ScheduleGenerator(self.teams, self.n_weeks)
        self.season_points = dict(zip(self.teams, scores_df[self.week_columns].sum(axis=1)))
        # Weekly scores per team, for fast lookup inside the simulation loop
        self.weekly_scores = dict(zip(self.teams, scores_df[self.week_columns].to_numpy().tolist()))
        self.use_h2h = is_head_to_head_rule(seeding_rule)
        self.actual_schedule = actual_schedule
        # Filled by run_simulation: seed_counts[team][k] = times team finished seed k+1
        self.seed_counts: Optional[pd.DataFrame] = None
    
    def simulate_schedule(self, schedule: List[List[Tuple[str, str]]]) -> Dict[str, Dict[str, float]]:
        """
        Simulate a season with the given schedule.
        
        Args:
            schedule: Weekly matchups
            
        Returns:
            Dictionary of team records with wins, losses, ties, and points_for.
            Equal scores are a tie for both teams.
            points_for is the full season total (bye weeks included), which
            doesn't depend on the schedule.
        """
        team_records = {
            team: {'wins': 0, 'losses': 0, 'ties': 0, 'points_for': self.season_points[team]}
            for team in self.teams
        }
        if self.use_h2h:
            # h2h[opponent] = [wins (ties count half), games] against that opponent
            for record in team_records.values():
                record['h2h'] = {}
        
        for week_idx, week_matchups in enumerate(schedule):
            for team1, team2 in week_matchups:
                score1 = self.weekly_scores[team1][week_idx]
                score2 = self.weekly_scores[team2][week_idx]
                
                if score1 > score2:
                    team_records[team1]['wins'] += 1
                    team_records[team2]['losses'] += 1
                    result1 = 1.0
                elif score2 > score1:
                    team_records[team2]['wins'] += 1
                    team_records[team1]['losses'] += 1
                    result1 = 0.0
                else:
                    team_records[team1]['ties'] += 1
                    team_records[team2]['ties'] += 1
                    result1 = 0.5

                if self.use_h2h:
                    h1 = team_records[team1]['h2h'].setdefault(team2, [0.0, 0])
                    h2 = team_records[team2]['h2h'].setdefault(team1, [0.0, 0])
                    h1[0] += result1
                    h1[1] += 1
                    h2[0] += 1.0 - result1
                    h2[1] += 1
        
        return team_records
    
    def get_playoff_teams(self, team_records: Dict[str, Dict[str, float]],
                          divisions: Optional[Dict[str, str]] = None) -> List[str]:
        """
        Determine which teams make the playoffs, in seed order.

        Matches ESPN's format: each division winner gets a playoff spot and a
        top seed; remaining spots go to the best other teams. Teams are ranked
        by win % (not raw wins, since in odd leagues teams can play different
        numbers of games; ties count as half a win), with total points as the
        tiebreaker.
        
        Args:
            team_records: Dictionary of team records
            divisions: Each team's division; None or empty means no divisions
            
        Returns:
            List of playoff team names, best seed first
        """
        return self.get_seed_order(team_records, divisions)[:self.n_playoff_teams]

    def rank_teams(self, team_records: Dict[str, Dict[str, float]]) -> List[str]:
        """
        All teams, best first: by win %, then the league's tiebreaker.

        With a head-to-head rule, teams tied on win % are ordered by their
        record against each other, but only when every pair of tied teams met
        equally often (ESPN's condition); total points breaks remaining ties.
        """
        by_pct = sorted(team_records, key=lambda t: win_pct(team_records[t]), reverse=True)
        ranked = []
        for _, group in groupby(by_pct, key=lambda t: win_pct(team_records[t])):
            ranked.extend(self._break_tie(list(group), team_records))
        return ranked

    def _break_tie(self, tied: List[str], team_records) -> List[str]:
        """Order teams with equal win %."""
        def points(team):
            return team_records[team]['points_for']

        if len(tied) < 2 or not self.use_h2h:
            return sorted(tied, key=points, reverse=True)

        def meetings(a, b):
            return team_records[a]['h2h'].get(b, [0.0, 0])[1]

        counts = {meetings(a, b) for i, a in enumerate(tied) for b in tied[i + 1:]}
        if len(counts) != 1:
            return sorted(tied, key=points, reverse=True)

        def h2h_pct(team):
            results = [team_records[team]['h2h'].get(o, [0.0, 0]) for o in tied if o != team]
            games = sum(g for _, g in results)
            return sum(w for w, _ in results) / games if games else 0.0

        return sorted(tied, key=lambda t: (h2h_pct(t), points(t)), reverse=True)

    def get_seed_order(self, team_records: Dict[str, Dict[str, float]],
                       divisions: Optional[Dict[str, str]] = None) -> List[str]:
        """
        Every team's final seed, best first: division winners take the top
        seeds, then everyone else in ranking order.
        """
        ranked = self.rank_teams(team_records)
        if not divisions:
            return ranked

        winners = []
        for team in ranked:
            if divisions[team] not in {divisions[w] for w in winners}:
                winners.append(team)
        return winners + [team for team in ranked if team not in winners]
    
    def run_simulation(self, num_schedules: int, seed: int = 42,
                       verbose: bool = False) -> pd.DataFrame:
        """
        Run full playoff probability simulation.
        
        Args:
            num_schedules: Number of random schedules to simulate
            seed: Random seed for reproducibility
            verbose: Print progress every 1000 schedules
            
        Returns:
            DataFrame with playoff probabilities for each team. Also sets
            self.seed_counts (teams x seeds 1..n, number of simulations in
            which each team finished at each seed).
        """
        random.seed(seed)
        playoff_count = {team: 0 for team in self.teams}
        total_wins = {team: 0 for team in self.teams}
        total_games = {team: 0 for team in self.teams}
        team_index = {team: i for i, team in enumerate(self.teams)}
        seed_counts = np.zeros((len(self.teams), len(self.teams)), dtype=int)
        
        for i in range(num_schedules):
            if verbose and i % 1000 == 0:
                print(f"Processing schedule {i}/{num_schedules}")
            
            schedule, divisions = self.generator.generate()
            team_records = self.simulate_schedule(schedule)
            for team, record in team_records.items():
                total_wins[team] += record['wins'] + 0.5 * record['ties']
                total_games[team] += games_played(record)
            seed_order = self.get_seed_order(team_records, divisions)
            for seed_idx, team in enumerate(seed_order):
                seed_counts[team_index[team], seed_idx] += 1
            for team in seed_order[:self.n_playoff_teams]:
                playoff_count[team] += 1

        self.seed_counts = pd.DataFrame(seed_counts, index=self.teams,
                                        columns=range(1, len(self.teams) + 1))
        
        # Calculate playoff percentages
        playoff_percentages = {
            team: (count / num_schedules) * 100
            for team, count in playoff_count.items()
        }
        
        # Create results DataFrame
        actual_records = self.actual_records()
        results = []
        for team in self.teams:
            actual_record = actual_records[team]
            points_for = self.season_points[team]
            
            # Win % across every simulated schedule permutation
            # (byes excluded, ties count as half a win)
            games = total_games[team]
            expected_win_pct = total_wins[team] / games * 100 if games else 0.0

            results.append({
                'Team': team,
                'Actual Record': actual_record,
                'Points For': points_for,
                'Actual Win %': record_to_win_pct(actual_record),
                'Expected Win %': expected_win_pct,
                'Luck (pp)': record_to_win_pct(actual_record) - expected_win_pct,
                'Playoff %': playoff_percentages[team]
            })
        
        return pd.DataFrame(results).sort_values('Playoff %', ascending=False)

    def actual_records(self) -> Dict[str, str]:
        """Each team's real 'W-L' / 'W-L-T' record over the simulated weeks."""
        if self.actual_schedule is None:
            return dict(zip(self.teams, self.scores_df['Record']))
        h2h, self.use_h2h = self.use_h2h, False
        records = self.simulate_schedule(self.actual_schedule)
        self.use_h2h = h2h
        return {team: format_record(r) for team, r in records.items()}


def format_record(record: Dict[str, float]) -> str:
    """'W-L', or 'W-L-T' when there are ties."""
    text = f"{record['wins']}-{record['losses']}"
    return text + f"-{record['ties']}" if record.get('ties') else text


def schedule_swap_matrix(scores_df: pd.DataFrame,
                         actual_schedule: List[List[Tuple[str, str]]]) -> Dict[str, Dict[str, Dict]]:
    """
    Every team's record if it had played every other team's real schedule.

    matrix[x][y] is x's record using y's schedule: each week x faces y's
    opponent, and when y's opponent was x itself, x faces y instead. A week
    where y had a bye is a bye for x. matrix[x][x] is x's actual record.

    Args:
        scores_df: Weekly scores ('Team', W1..Wn) for the weeks in actual_schedule
        actual_schedule: Real weekly matchups by team name

    Returns:
        {x: {y: {'wins', 'losses', 'ties'}}}
    """
    week_columns = [c for c in scores_df.columns if c.startswith('W')]
    teams = scores_df['Team'].tolist()
    scores = dict(zip(teams, scores_df[week_columns].to_numpy().tolist()))

    opponents = []  # per week: team -> opponent
    for week in actual_schedule:
        lookup = {}
        for a, b in week:
            lookup[a], lookup[b] = b, a
        opponents.append(lookup)

    matrix = {}
    for x in teams:
        matrix[x] = {}
        for y in teams:
            record = {'wins': 0, 'losses': 0, 'ties': 0}
            for week_idx, lookup in enumerate(opponents):
                opponent = lookup.get(y)
                if opponent is None:
                    continue
                if opponent == x:
                    opponent = y
                mine, theirs = scores[x][week_idx], scores[opponent][week_idx]
                key = 'wins' if mine > theirs else 'losses' if mine < theirs else 'ties'
                record[key] += 1
            matrix[x][y] = record
    return matrix


def load_league_structure(scores_df: pd.DataFrame, schedule_path: Path,
                          settings_path: Path) -> dict:
    """
    Load the league's real schedule and playoff settings, if available.

    Args:
        scores_df: Scores with 'Team ID' and 'Team' columns (names final)
        schedule_path: Schedule CSV written by get_espn_league_data.py
        settings_path: League settings JSON written by get_espn_league_data.py

    Returns:
        {'generator': TemplateScheduleGenerator or None,
         'n_playoff_teams': int,
         'seeding_rule': ESPN playoffSeedingRule or None,
         'actual_schedule': real weekly matchups by team name, or None,
         'notes': user-facing notes about rules that can't be modeled}.
        generator and actual_schedule are None when the files (or team IDs)
        are missing; the simulator then falls back to a random round-robin
        with no divisions.
    """
    settings = {}
    if Path(settings_path).exists():
        settings = json.loads(Path(settings_path).read_text())
    rule = settings.get('playoff_seeding_rule')
    notes = [n for n in (seeding_rule_note(rule),
                         tie_rule_note(settings.get('matchup_tie_rule'))) if n]
    structure = {'generator': None, 'n_playoff_teams': settings.get('playoff_team_count', 6),
                 'seeding_rule': rule, 'actual_schedule': None, 'notes': notes}

    if not Path(schedule_path).exists() or 'Team ID' not in scores_df.columns:
        return structure

    schedule_df = pd.read_csv(schedule_path)
    weeks: Dict[int, List[Tuple[int, int]]] = {}
    for row in schedule_df.itertuples(index=False):
        weeks.setdefault(int(row[0]), []).append((int(row[1]), int(row[3])))

    # Align the template with the score columns (W1, W2, ... by week number)
    week_columns = [c for c in scores_df.columns if c.startswith('W')]
    missing = [col for col in week_columns if int(col[1:]) not in weeks]
    if missing:
        raise ValueError(f"Schedule file has no matchups for weeks {missing}")
    template = [weeks[int(col[1:])] for col in week_columns]

    # Slots are the real team IDs; each slot keeps its real division
    team_ids = scores_df['Team ID'].astype(int).tolist()
    divisions = (scores_df['Division'].fillna('').tolist()
                 if 'Division' in scores_df.columns else [''] * len(team_ids))
    slot_divisions = dict(zip(team_ids, divisions))

    generator = TemplateScheduleGenerator(template, slot_divisions,
                                          scores_df['Team'].tolist(), len(week_columns))
    name_of = dict(zip(team_ids, scores_df['Team']))
    actual_schedule = [[(name_of[a], name_of[b]) for a, b in week] for week in template]
    return {**structure, 'generator': generator, 'actual_schedule': actual_schedule}


def simulator_through_week(scores_df: pd.DataFrame, structure: dict,
                           week: Optional[int] = None) -> PlayoffSimulator:
    """
    A simulator for the season as if it ended after the first `week` weeks.

    Args:
        scores_df: Full scores (names final), as passed to load_league_structure
        structure: Output of load_league_structure
        week: Last week to include; None means every week played. Earlier
            cutoffs need the real schedule (to know actual records then).
    """
    week_columns = [c for c in scores_df.columns if c.startswith('W')]
    week = len(week_columns) if week is None else week
    if not 1 <= week <= len(week_columns):
        raise ValueError(f"week must be between 1 and {len(week_columns)}")
    if week < len(week_columns) and structure['actual_schedule'] is None:
        raise ValueError("Simulating part of the season needs the league's schedule file")

    other_columns = [c for c in scores_df.columns if not c.startswith('W')]
    df = scores_df[other_columns + week_columns[:week]]
    generator = structure['generator']
    actual = structure['actual_schedule']
    return PlayoffSimulator(
        df,
        n_playoff_teams=structure['n_playoff_teams'],
        generator=generator.truncated(week) if generator else None,
        seeding_rule=structure['seeding_rule'],
        actual_schedule=actual[:week] if actual else None,
    )


def load_scores(csv_path: Path) -> pd.DataFrame:
    """Read the scores CSV and make team names tidy and unique."""
    df = pd.read_csv(csv_path)
    if 'Team' not in df.columns and 'Player' in df.columns:
        df = df.rename(columns={'Player': 'Team'})  # files from older versions
    df['Team'] = df['Team'].map(standardize_name)
    duplicates = sorted(df.loc[df['Team'].duplicated(), 'Team'].unique())
    if duplicates:
        print(f"Warning: duplicate team names {duplicates}; adding numeric suffixes")
    df['Team'] = disambiguate_names(df['Team'])
    return df


def standardize_name(name: str) -> str:
    """Capitalize the first letter of each name part ('jason wu' -> 'Jason Wu').

    Only the first letter is changed, so names like 'McDonald' keep their casing.
    """
    return ' '.join(part[:1].upper() + part[1:] for part in str(name).split())


def disambiguate_names(names: pd.Series) -> pd.Series:
    """
    Make team names unique by suffixing repeats: ['MM', 'BK', 'MM'] ->
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
    Label each point with the team's name, avoiding overlaps.

    Actual win % is discrete, so many teams share a row. Each label tries
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
                    row['Team'], (x, y),
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
    ax.text(3, 97, 'LUCKY\nWon more than expected', color=text_primary,
            fontsize=8.5, fontweight='bold', ha='left', va='top',
            bbox=dict(boxstyle='square,pad=0.4', facecolor=surface,
                      edgecolor=lucky_green, linewidth=2))
    ax.text(97, 3, 'UNLUCKY\nWon fewer than expected', color=text_primary,
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

    # Label every team by name (luck is carried by color). Done last, once the
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
    
    # Create y-axis labels with team name and stats
    y_labels = [
        f"{row['Team']}\n{row['Actual Record']}| {row['Points For']:.1f} PF"
        for _, row in sorted_results.iterrows()
    ]
    plt.yticks(range(len(sorted_results)), y_labels, fontsize=9)
    
    # Labels and title
    plt.xlabel('Playoff Probability (%)', fontsize=12, fontweight='bold')
    plt.ylabel('Team', fontsize=12, fontweight='bold')
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


def run_league_simulation(league_id, year, num_schedules: int = 100000,
                          seed: int = 42) -> pd.DataFrame:
    """
    Simulate a league's season from its downloaded data, then save the
    playoff-probability and luck plots plus a results CSV.

    Raises:
        SetupError: if the league's data hasn't been downloaded yet
    """
    paths = league_data_paths(league_id, year)
    data_dir = paths['dir']
    csv_path = paths['scores']
    if not csv_path.exists():
        raise SetupError(f"No data found for league {league_id}, {year} season ({csv_path}). "
                         "Download it first with get_espn_league_data.py (or run run_all.py).")

    print(f"Loading data for league {league_id} year {year}...")
    df = load_scores(csv_path)
    print(f"Number of teams: {len(df)}")
    print(f"Number of weeks: {len([col for col in df.columns if col.startswith('W')])}")

    # Use the league's real schedule format and playoff rules when available
    structure = load_league_structure(df, paths['schedule'], paths['settings'])
    if structure['generator'] is None:
        print("No schedule file found: using random round-robin schedules without divisions")
    else:
        divisions = sorted(set(structure['generator'].slot_divisions.values()) - {''})
        print("Using the league's real schedule format"
              + (f" with divisions {divisions}" if divisions else ""))
    print(f"Playoff teams: {structure['n_playoff_teams']}")
    for note in structure['notes']:
        print(f"Note: {note}")

    simulator = simulator_through_week(df, structure)
    print(f"\nRunning {num_schedules:,} schedule simulations...")
    results_df = simulator.run_simulation(num_schedules, seed=seed, verbose=True)

    print("\nPlayoff Probabilities:")
    print(results_df.to_string(index=False))

    print("\nCreating visualization...")
    create_visualization(results_df, league_id, year, num_schedules, data_dir.parent)
    create_luck_scatterplot(results_df, league_id, year, num_schedules, data_dir.parent)

    results_path = data_dir / f'playoff_probabilities_league{league_id}_y{year}.csv'
    results_df.to_csv(results_path, index=False)
    print(f"Results saved to {results_path}")
    return results_df


def main():
    """Simulate the league named in the .env file."""
    league_id, year = load_league_and_year()
    run_league_simulation(league_id, year)


if __name__ == "__main__":
    run_cli(main)
