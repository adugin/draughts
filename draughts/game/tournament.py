"""AI vs AI tournament — compare two AI configurations objectively.

Usage:
    from draughts.game.tournament import Tournament, AIConfig

    result = Tournament(
        config_a=AIConfig(difficulty=2, depth=5, label="baseline"),
        config_b=AIConfig(difficulty=2, depth=7, label="deeper"),
        games=50,
    ).run()
    print(result.summary())
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from draughts.config import Color
from draughts.game.ai import AIEngine
from draughts.game.headless import HeadlessGame


@dataclass
class AIConfig:
    """Configuration for one AI participant."""

    difficulty: int = 2
    depth: int = 0  # 0 = auto from difficulty
    label: str = ""

    def make_engine(self, color: Color) -> AIEngine:
        return AIEngine(difficulty=self.difficulty, color=color, search_depth=self.depth)


@dataclass
class GameRecord:
    """Record of one tournament game."""

    game_num: int
    winner: Color | None  # None = draw
    reason: str
    ply_count: int
    black_label: str
    white_label: str
    duration_s: float


@dataclass
class TournamentResult:
    """Aggregated tournament results."""

    config_a_label: str
    config_b_label: str
    total_games: int
    wins_a: int = 0
    wins_b: int = 0
    draws: int = 0
    games: list[GameRecord] = field(default_factory=list)
    total_duration_s: float = 0.0

    @property
    def win_rate_a(self) -> float:
        return self.wins_a / max(self.total_games, 1)

    @property
    def win_rate_b(self) -> float:
        return self.wins_b / max(self.total_games, 1)

    @property
    def draw_rate(self) -> float:
        return self.draws / max(self.total_games, 1)

    @property
    def avg_game_length(self) -> float:
        if not self.games:
            return 0.0
        return sum(g.ply_count for g in self.games) / len(self.games)

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Tournament: {self.config_a_label} vs {self.config_b_label}",
            f"Games: {self.total_games}",
            "",
            f"  {self.config_a_label}: {self.wins_a} wins ({self.win_rate_a:.1%})",
            f"  {self.config_b_label}: {self.wins_b} wins ({self.win_rate_b:.1%})",
            f"  Draws: {self.draws} ({self.draw_rate:.1%})",
            "",
            f"  Avg game length: {self.avg_game_length:.1f} plies",
            f"  Total time: {self.total_duration_s:.1f}s",
        ]
        return "\n".join(lines)


class Tournament:
    """Run a tournament between two AI configurations.

    Each pair of games alternates colors:
    - Game 1: A=black, B=white
    - Game 2: A=white, B=black
    This eliminates first-move advantage bias.
    """

    def __init__(
        self,
        config_a: AIConfig,
        config_b: AIConfig,
        games: int = 50,
        max_ply: int = 200,
        verbose: bool = False,
    ):
        self.config_a = config_a
        self.config_b = config_b
        self.games = games
        self.max_ply = max_ply
        self.verbose = verbose

        if not config_a.label:
            config_a.label = f"A(d{config_a.difficulty},dp{config_a.depth})"
        if not config_b.label:
            config_b.label = f"B(d{config_b.difficulty},dp{config_b.depth})"

    def run(self, progress_callback=None) -> TournamentResult:
        """Run the full tournament.

        Args:
            progress_callback: Optional callable(game_num, total, record)
                called after each game.

        Returns TournamentResult.
        """
        result = TournamentResult(
            config_a_label=self.config_a.label,
            config_b_label=self.config_b.label,
            total_games=self.games,
        )

        t_start = time.perf_counter()

        for i in range(self.games):
            # Alternate colors each game
            if i % 2 == 0:
                black_config, white_config = self.config_a, self.config_b
                a_is_black = True
            else:
                black_config, white_config = self.config_b, self.config_a
                a_is_black = False

            game = HeadlessGame(
                black_engine=black_config.make_engine(Color.BLACK),
                white_engine=white_config.make_engine(Color.WHITE),
                auto_ai=True,
            )

            g_start = time.perf_counter()
            game_result = game.play_full_game(max_ply=self.max_ply)
            g_duration = time.perf_counter() - g_start

            record = GameRecord(
                game_num=i + 1,
                winner=game_result.winner,
                reason=game_result.reason,
                ply_count=game_result.ply_count,
                black_label=black_config.label,
                white_label=white_config.label,
                duration_s=g_duration,
            )
            result.games.append(record)

            # Attribute win to config A or B
            if game_result.winner is None:
                result.draws += 1
            elif (game_result.winner == Color.BLACK) == a_is_black:
                result.wins_a += 1
            else:
                result.wins_b += 1

            if self.verbose:
                winner_label = "draw"
                if game_result.winner == Color.BLACK:
                    winner_label = black_config.label
                elif game_result.winner == Color.WHITE:
                    winner_label = white_config.label
                print(
                    f"  Game {i + 1}/{self.games}: "
                    f"{black_config.label}(B) vs {white_config.label}(W) "
                    f"→ {winner_label} ({game_result.reason}, {game_result.ply_count} plies, {g_duration:.1f}s)"
                )

            if progress_callback:
                progress_callback(i + 1, self.games, record)

        result.total_duration_s = time.perf_counter() - t_start
        return result
