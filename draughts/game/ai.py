"""AI module for Russian draughts — faithful port from Borland Pascal 7.0.

The AI has three priority levels, called sequentially:
1. SeeBeat  — mandatory captures (Monte Carlo evaluation)
2. Combination — tactical sacrifices
3. Action — normal moves (heuristic scoring; Monte Carlo for kings)

Original constants:
    maxrnd = 1000   (Monte Carlo iterations)
    depth0 = 1      (lookahead depth)
    NeedToSave = 1  (minimum score change for learning)
    dir[1..4] = ((-1,1),(1,1),(1,-1),(-1,-1))  — 4 diagonal directions
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from draughts.game.board import Board

if TYPE_CHECKING:
    from draughts.game.learning import LearningDB

# ---------------------------------------------------------------------------
# Constants (matching original Pascal)
# ---------------------------------------------------------------------------

MAXRND = 1000
DEPTH0 = 1
NEED_TO_SAVE = 1

# dir[1..4] — (dx, dy) diagonal directions
DIRS = [(-1, 1), (1, 1), (1, -1), (-1, -1)]

BLACKS = frozenset(('b', 'B'))
WHITES = frozenset(('w', 'W'))

BOARD_SIZE = 8


# ---------------------------------------------------------------------------
# Move representation
# ---------------------------------------------------------------------------

class AIMove:
    """Result returned by the AI.

    Attributes:
        kind: 'capture', 'move', or 'sacrifice'
        path: For captures — list of (x,y) positions the piece visits.
              For moves/sacrifices — [(x1,y1), (x2,y2)].
    """

    def __init__(self, kind: str, path: list[tuple[int, int]]):
        self.kind = kind
        self.path = path

    def __repr__(self):
        return f"AIMove({self.kind!r}, {self.path})"


# ---------------------------------------------------------------------------
# Helper: in-bounds
# ---------------------------------------------------------------------------

def _between(x: int, y: int) -> bool:
    return 1 <= x <= BOARD_SIZE and 1 <= y <= BOARD_SIZE


def _maximum(x: int, y: int) -> int:
    """Maximum diagonal distance from (x, y) to any board edge."""
    return max(BOARD_SIZE - y, y - 1, BOARD_SIZE - x, x - 1)


# ---------------------------------------------------------------------------
# Helper: exist — count pieces on a diagonal between two squares
# ---------------------------------------------------------------------------

def _exist(x1: int, y1: int, x2: int, y2: int,
           color: str, field: list[list[str]]) -> tuple[int, int, int]:
    """Check how many pieces lie on diagonal (x1,y1)→(x2,y2) exclusive.

    Args:
        color: 'b' (black) or 'w' (white) — the side whose piece we look for.

    Returns:
        (count, bx, by) where count is total non-empty cells on the path,
        bx/by is the position of the found *color* piece (if exactly one).
        count=0 means the path is clear.
        count=1 and the piece belongs to *color* → capturable.
    """
    if x2 == x1 or y2 == y1:
        return (0, 0, 0)
    if abs(x2 - x1) != abs(y2 - y1):
        return (0, 0, 0)  # not on same diagonal
    dx = 1 if x2 > x1 else -1
    dy = 1 if y2 > y1 else -1
    cx, cy = x1 + dx, y1 + dy
    n = 0
    bx, by = 0, 0
    ok = False
    target = BLACKS if color == 'b' else WHITES
    # Walk from (x1,y1) toward (x2,y2) exclusive of both endpoints
    while (cx, cy) != (x2, y2):
        if not _between(cx, cy):
            return (0, 0, 0)  # off board
        if field[cy][cx] != 'n':
            n += 1
        if field[cy][cx] in target:
            ok = True
            bx, by = cx, cy
        cx += dx
        cy += dy
    if ok and n == 1:
        return (1, bx, by)
    if n == 0:
        return (0, 0, 0)
    return (2, 0, 0)


def _freeway(x1: int, y1: int, x2: int, y2: int,
             field: list[list[str]]) -> bool:
    """Check if diagonal path between two squares is clear."""
    if x1 == x2 and y1 == y2:
        return True
    dx = 1 if x2 > x1 else -1
    dy = 1 if y2 > y1 else -1
    cx, cy = x1 + dx, y1 + dy
    while not (abs(cx - x2) <= 1 and abs(cy - y2) <= 1):
        if field[cy][cx] != 'n':
            return False
        cx += dx
        cy += dy
    return True


# ---------------------------------------------------------------------------
# Helper: dangerous_position (matching original Pascal logic precisely)
# ---------------------------------------------------------------------------

def _dangerous_position(x: int, y: int,
                        field: list[list[str]], color: str) -> bool:
    """Check if piece at (x,y) is under attack.

    Faithfully reproduces the original DangerousPosition() from Pascal.
    """
    enemies = WHITES if color == 'b' else BLACKS
    friends = BLACKS if color == 'b' else WHITES
    enemy_king = 'W' if color == 'b' else 'B'

    close = [False, False, False, False]

    for rr in range(1, _maximum(x, y) + 1):
        for di in range(4):
            dx, dy = DIRS[di]
            # Behind position (escape square for attacker)
            bx, by = x - dx, y - dy
            # Attack position
            ax, ay = x + rr * dx, y + rr * dy

            if not _between(bx, by):
                continue
            if not _between(ax, ay):
                continue

            if field[by][bx] != 'n':
                continue

            if rr == 1:
                attacker = field[ay][ax]
                if attacker in enemies:
                    return True
                elif attacker in friends:
                    close[di] = True
            else:  # rr > 1
                cell = field[ay][ax]
                # Check blocking for long-range king attack
                if color == 'b':
                    if cell in ('b', 'B', 'w'):
                        close[di] = True
                    elif not close[di] and cell == enemy_king:
                        return True
                else:
                    if cell in ('w', 'W', 'b'):
                        close[di] = True
                    elif not close[di] and cell == enemy_king:
                        return True
    return False


# ---------------------------------------------------------------------------
# Helper: dangerous_beat — will the piece be under attack after a capture?
# ---------------------------------------------------------------------------

def _dangerous_beat(x1: int, y1: int, x2: int, y2: int,
                    bx: int, by: int,
                    field: list[list[str]], color: str) -> bool:
    """Check if piece landing at (x2,y2) after capturing piece at (bx,by)
    will be under attack. Original DangerousBeat()."""
    enemies = WHITES if color == 'b' else BLACKS
    enemy_king = 'W' if color == 'b' else 'B'

    close = [False, False, False, False]

    for rr in range(1, _maximum(x2, y2) + 1):
        for di in range(4):
            dx, dy = DIRS[di]
            ax, ay = x2 + rr * dx, y2 + rr * dy
            ex, ey = x2 - rr * dx, y2 - rr * dy

            if not _between(ax, ay):
                continue
            if not _between(ex, ey):
                continue

            if rr == 1:
                attacker = field[ay][ax]
                # Check landing square (behind us from attacker's perspective)
                landing = field[ey][ex]
                landing_free = (landing == 'n' or (ex == bx and ey == by))
                if attacker in enemies and landing_free:
                    return True
            else:
                cell = field[ay][ax]
                if cell != enemy_king and cell != 'n' and not (ax == bx and ay == by):
                    close[di] = True
                elif not close[di] and cell == enemy_king:
                    landing = field[y2 - dy][x2 - dx]
                    landing_free = (landing == 'n' or
                                    (x2 - dx == bx and y2 - dy == by))
                    if landing_free:
                        return True
    return False


# ---------------------------------------------------------------------------
# Helper: danger — does any piece of given color have a dangerous position?
# ---------------------------------------------------------------------------

def _danger(color: str, field: list[list[str]]) -> bool:
    pieces = BLACKS if color == 'b' else WHITES
    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if x % 2 != y % 2:
                if field[y][x] in pieces:
                    if _dangerous_position(x, y, field, color):
                        return True
    return False


# ---------------------------------------------------------------------------
# Helper: neighbour — is the square "near" an edge or friendly piece?
# ---------------------------------------------------------------------------

def _neighbour(x: int, y: int, field: list[list[str]]) -> bool:
    """Original neighbour() — checks if position is near edge or friendly."""
    for di in range(2, 4):  # directions 3 and 4 (index 2,3)
        dx, dy = DIRS[di]
        nx, ny = x + 2 * dx, y + 2 * dy
        if _between(nx, ny):
            adj = field[y + dy][x + dx]
            far = field[ny][nx]
            behind = field[y - 2][x] if _between(x, y - 2) else 'n'
            if (adj == 'n' and (far in BLACKS or behind in BLACKS)):
                return True
    if x in (1, BOARD_SIZE) or y in (1, BOARD_SIZE):
        return True
    return False


# ---------------------------------------------------------------------------
# Helper: side — is a pawn on column 2 or 7 with white threatening edge?
# ---------------------------------------------------------------------------

def _side(x: int, y: int, field: list[list[str]]) -> bool:
    """Original side() function."""
    if y + 2 > BOARD_SIZE:
        return False
    if x == 2:
        if field[y + 2][2] in WHITES:
            if field[y + 1][1] == 'n':
                return True
    elif x == BOARD_SIZE - 1:
        if field[y + 2][x] in WHITES:
            if field[y + 1][BOARD_SIZE] == 'n':
                return True
    return False


# ---------------------------------------------------------------------------
# Helper: one_beat — does white have exactly one capture available?
# ---------------------------------------------------------------------------

def _one_beat(field: list[list[str]]) -> bool:
    """Return True if white has exactly one capturable piece (for Combination).

    Original OneBeat() — checks if blacks can be captured in exactly one place.
    Actually, it checks if among all black pieces, exactly one is capturable
    by a white piece jumping over it.
    """
    first = False
    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if field[y][x] in BLACKS:
                for di in range(4):
                    dx, dy = DIRS[di]
                    for rr in range(1, _maximum(x, y) + 1):
                        bx, by = x - dx, y - dy
                        ax, ay = x + rr * dx, y + rr * dy
                        if not _between(bx, by) or not _between(ax, ay):
                            continue
                        if field[by][bx] != 'n':
                            continue
                        cell = field[ay][ax]
                        if rr == 1 and cell == 'w':
                            if first:
                                return False
                            first = True
                            break
                        elif cell == 'W' and (rr == 1 or _freeway(x, y, ax, ay, field)):
                            if first:
                                return False
                            first = True
                            break
    return True  # zero or one captures found


# ---------------------------------------------------------------------------
# Helper: count pieces
# ---------------------------------------------------------------------------

def _number(color: str, field: list[list[str]]) -> int:
    pieces = BLACKS if color == 'b' else WHITES
    count = 0
    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if field[y][x] in pieces:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Helper: copy field (list of lists)
# ---------------------------------------------------------------------------

def _copy_field(field: list[list[str]]) -> list[list[str]]:
    return [row[:] for row in field]


# ---------------------------------------------------------------------------
# Virtual captures — simulate best capture for a side on model board
# ---------------------------------------------------------------------------

def _virtual_black_beat(model: list[list[str]], use_base: bool,
                        learning_db: LearningDB | None) -> int:
    """Simulate best black capture on model board (Monte Carlo).

    Modifies model in-place if a capture is found.
    Returns the score of the best capture, 0 if none.
    """
    best_score = 0
    found = False
    best_opt = None

    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if model[y][x] != 'b':
                continue
            # Check if this pawn can capture
            can = False
            for di in range(4):
                dx, dy = DIRS[di]
                nx, ny = x + 2 * dx, y + 2 * dy
                if _between(nx, ny) and model[ny][nx] == 'n' and model[y + dy][x + dx] in WHITES:
                    can = True
                    break
            if not can:
                continue

            for _ in range(MAXRND):
                trial = [0] * 11  # trial[1]=start_x, trial[2]=start_y, trial[3..]=dirs
                trial[1] = x
                trial[2] = y
                x1, y1 = x, y
                count = 2
                mas = _copy_field(model)
                score = 0
                promoted = False

                eob = False
                while not eob:
                    d = random.randint(0, 3)
                    dx, dy = DIRS[d]
                    nx, ny = x1 + 2 * dx, y1 + 2 * dy
                    if _between(nx, ny) and mas[ny][nx] == 'n' and mas[y1 + dy][x1 + dx] in WHITES:
                        found = True
                        count += 1
                        if count < len(trial):
                            trial[count] = d + 1  # 1-based direction
                        if mas[y1 + dy][x1 + dx] == 'W':
                            score += 2
                        mas[y1][x1] = 'n'
                        mas[y1 + dy][x1 + dx] = 'n'
                        mas[ny][nx] = 'b'
                        x1, y1 = nx, ny
                        if y1 == BOARD_SIZE and not promoted:
                            score += 2
                            promoted = True
                        # Check if more captures possible
                        eob = True
                        for dd in range(4):
                            ddx, ddy = DIRS[dd]
                            nnx, nny = x1 + 2 * ddx, y1 + 2 * ddy
                            if _between(nnx, nny) and mas[nny][nnx] == 'n' and mas[y1 + ddy][x1 + ddx] in WHITES:
                                eob = False
                                break
                    else:
                        # Random direction didn't work, keep trying
                        # In original Pascal this just loops until eob via until
                        # We need to ensure the loop terminates with Monte Carlo
                        eob = True
                        for dd in range(4):
                            ddx, ddy = DIRS[dd]
                            nnx, nny = x1 + 2 * ddx, y1 + 2 * ddy
                            if _between(nnx, nny) and mas[nny][nnx] == 'n' and mas[y1 + ddy][x1 + ddx] in WHITES:
                                eob = False
                                break

                score += count - 2
                if not _dangerous_position(x1, y1, mas, 'b'):
                    score += 1
                if score > best_score:
                    best_score = score
                    best_opt = (trial[:], count, _copy_field(mas))

    # Execute the best capture on model
    if found and best_opt is not None:
        trial, count, _ = best_opt
        cx, cy = trial[1], trial[2]
        for i in range(3, count + 1):
            if i >= len(trial) or trial[i] == 0:
                break
            d = trial[i] - 1  # 0-based
            dx, dy = DIRS[d]
            # Promote if reaching last row
            if cy + 2 * dy == BOARD_SIZE:
                model[cy + 2 * dy][cx + 2 * dx] = 'B'
            else:
                model[cy + 2 * dy][cx + 2 * dx] = model[cy][cx]
            model[cy][cx] = 'n'
            model[cy + dy][cx + dx] = 'n'
            cx = cx + 2 * dx
            cy = cy + 2 * dy

    return best_score


def _virtual_white_beat(model: list[list[str]], use_base: bool,
                        learning_db: LearningDB | None) -> int:
    """Simulate best white capture on model board (Monte Carlo).

    Modifies model in-place if a capture is found.
    Returns the score of the best capture, 0 if none.
    """
    best_score = 0
    found = False
    best_opt = None

    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if model[y][x] != 'w':
                continue
            can = False
            for di in range(4):
                dx, dy = DIRS[di]
                nx, ny = x + 2 * dx, y + 2 * dy
                if _between(nx, ny) and model[ny][nx] == 'n' and model[y + dy][x + dx] in BLACKS:
                    can = True
                    break
            if not can:
                continue

            for _ in range(MAXRND):
                trial = [0] * 11
                trial[1] = x
                trial[2] = y
                x1, y1 = x, y
                count = 2
                mas = _copy_field(model)
                score = 0
                promoted = False

                eob = False
                while not eob:
                    d = random.randint(0, 3)
                    dx, dy = DIRS[d]
                    nx, ny = x1 + 2 * dx, y1 + 2 * dy
                    if _between(nx, ny) and mas[ny][nx] == 'n' and mas[y1 + dy][x1 + dx] in BLACKS:
                        found = True
                        count += 1
                        if count < len(trial):
                            trial[count] = d + 1
                        if mas[y1 + dy][x1 + dx] == 'B':
                            score += 2
                        mas[y1][x1] = 'n'
                        mas[y1 + dy][x1 + dx] = 'n'
                        mas[ny][nx] = 'w'
                        x1, y1 = nx, ny
                        if y1 == 1 and not promoted:
                            score += 2
                            promoted = True
                        eob = True
                        for dd in range(4):
                            ddx, ddy = DIRS[dd]
                            nnx, nny = x1 + 2 * ddx, y1 + 2 * ddy
                            if _between(nnx, nny) and mas[nny][nnx] == 'n' and mas[y1 + ddy][x1 + ddx] in BLACKS:
                                eob = False
                                break
                    else:
                        eob = True
                        for dd in range(4):
                            ddx, ddy = DIRS[dd]
                            nnx, nny = x1 + 2 * ddx, y1 + 2 * ddy
                            if _between(nnx, nny) and mas[nny][nnx] == 'n' and mas[y1 + ddy][x1 + ddx] in BLACKS:
                                eob = False
                                break

                score += count - 2
                if not _dangerous_position(x1, y1, mas, 'w'):
                    score += 2  # white gets +2 for safe position (original)
                if score > best_score:
                    best_score = score
                    best_opt = (trial[:], count, _copy_field(mas))

    # Execute best capture on model
    if found and best_opt is not None:
        trial, count, _ = best_opt
        cx, cy = trial[1], trial[2]
        for i in range(3, count + 1):
            if i >= len(trial) or trial[i] == 0:
                break
            d = trial[i] - 1
            dx, dy = DIRS[d]
            if cy + 2 * dy == 1:
                model[cy + 2 * dy][cx + 2 * dx] = 'W'
            else:
                model[cy + 2 * dy][cx + 2 * dx] = model[cy][cx]
            model[cy][cx] = 'n'
            model[cy + dy][cx + dx] = 'n'
            cx = cx + 2 * dx
            cy = cy + 2 * dy

    return best_score


# ---------------------------------------------------------------------------
# get_string from field (matching Board.get_string but for raw field)
# ---------------------------------------------------------------------------

def _get_string(field: list[list[str]]) -> str:
    result = []
    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if x % 2 != y % 2:
                result.append(field[y][x])
    return ''.join(result)


# ---------------------------------------------------------------------------
# _search_db — lookup position in learning database
# ---------------------------------------------------------------------------

def _search_db(learning_db: LearningDB | None, position: str) -> str | None:
    if learning_db is None:
        return None
    return learning_db.search(position)


# ===========================================================================
# SEEBEAT — mandatory captures with Monte Carlo evaluation
# ===========================================================================

def _see_beat(board: Board, color: str, use_base: bool,
              learning_db: LearningDB | None) -> AIMove | None:
    """Find the best mandatory capture using Monte Carlo simulation.

    Matches the original SeeBeat() function.
    """
    field = board.field
    my_pawn = 'b' if color == 'b' else 'w'
    my_king = 'B' if color == 'b' else 'W'
    enemies = WHITES if color == 'b' else BLACKS
    promote_row = BOARD_SIZE if color == 'b' else 1

    max_score = -100
    best_optimum = None
    best_start = None
    found_any = False

    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            piece = field[y][x]

            if piece == my_pawn:
                # Check if pawn can capture at all
                can_capture = False
                for di in range(4):
                    dx, dy = DIRS[di]
                    nx, ny = x + 2 * dx, y + 2 * dy
                    if (_between(nx, ny) and
                            field[y + dy][x + dx] in enemies and
                            field[ny][nx] == 'n'):
                        can_capture = True
                        break
                if not can_capture:
                    continue

                # Monte Carlo: try random capture sequences
                for _ in range(MAXRND):
                    opt = []  # list of (direction_index, distance)
                    x1, y1 = x, y
                    model = _copy_field(field)
                    score = 0
                    promoted = False

                    eob = False
                    while not eob:
                        d = random.randint(0, 3)
                        dx, dy = DIRS[d]
                        nx, ny = x1 + 2 * dx, y1 + 2 * dy
                        if (_between(nx, ny) and
                                model[y1 + dy][x1 + dx] in enemies and
                                model[ny][nx] == 'n'):
                            found_any = True
                            opt.append((d, 2))
                            # Score for capturing king or near-promotion
                            cap_piece = model[y1 + dy][x1 + dx]
                            if cap_piece == my_king or (y1 + dy == promote_row - (1 if color == 'b' else -1)):
                                pass
                            if cap_piece in (my_king,):
                                pass
                            # Original: +2 for capturing king(W) or if y+dir = 2
                            # For black: y+dir[d,2] is y+dy which is y1+dy
                            if cap_piece == ('W' if color == 'b' else 'B'):
                                score += 2
                            if y1 + dy == (2 if color == 'b' else BOARD_SIZE - 1):
                                score += 2
                            model[y1 + dy][x1 + dx] = 'n'
                            if ny == promote_row:
                                model[ny][nx] = my_king
                            else:
                                model[ny][nx] = model[y1][x1]
                            model[y1][x1] = 'n'
                            x1, y1 = nx, ny
                            if y1 == promote_row and not promoted:
                                score += 2
                                promoted = True

                            # Check if more captures available
                            eob = True
                            if model[y1][x1] == my_pawn:
                                for dd in range(4):
                                    ddx, ddy = DIRS[dd]
                                    nnx, nny = x1 + 2 * ddx, y1 + 2 * ddy
                                    if (_between(nnx, nny) and
                                            model[y1 + ddy][x1 + ddx] in enemies and
                                            model[nny][nnx] == 'n'):
                                        eob = False
                                        break
                            elif model[y1][x1] == my_king:
                                # King can capture at longer range
                                for rr in range(2, BOARD_SIZE - 1 + 1):
                                    for dd in range(4):
                                        ddx, ddy = DIRS[dd]
                                        nnx, nny = x1 + rr * ddx, y1 + rr * ddy
                                        if (_between(nnx, nny) and
                                                model[nny][nnx] == 'n'):
                                            ec, ebx, eby = _exist(x1, y1, nnx, nny,
                                                                   'w' if color == 'b' else 'b',
                                                                   model)
                                            if ec == 1:
                                                eob = False
                                                break
                                    if not eob:
                                        break
                        else:
                            # Random direction didn't work; check if any capture exists
                            eob = True
                            if model[y1][x1] == my_pawn:
                                for dd in range(4):
                                    ddx, ddy = DIRS[dd]
                                    nnx, nny = x1 + 2 * ddx, y1 + 2 * ddy
                                    if (_between(nnx, nny) and
                                            model[y1 + ddy][x1 + ddx] in enemies and
                                            model[nny][nnx] == 'n'):
                                        eob = False
                                        break
                            elif model[y1][x1] == my_king:
                                for rr in range(2, BOARD_SIZE - 1 + 1):
                                    for dd in range(4):
                                        ddx, ddy = DIRS[dd]
                                        nnx, nny = x1 + rr * ddx, y1 + rr * ddy
                                        if (_between(nnx, nny) and model[nny][nnx] == 'n'):
                                            ec, _, _ = _exist(x1, y1, nnx, nny,
                                                              'w' if color == 'b' else 'b',
                                                              model)
                                            if ec == 1:
                                                eob = False
                                                break
                                    if not eob:
                                        break

                    # Score the result
                    score += len(opt)  # +1 per captured piece
                    if use_base:
                        pos_str = _get_string(model)
                        db_result = _search_db(learning_db, pos_str)
                        if db_result == 'good':
                            score += 3
                        elif db_result == 'bad':
                            score -= 3
                    if not _dangerous_position(x1, y1, model, color):
                        score += 1
                    if score > max_score:
                        max_score = score
                        best_optimum = opt
                        best_start = (x, y)

            elif piece == my_king:
                # King captures
                can_capture = False
                enemy_color = 'w' if color == 'b' else 'b'
                for rr in range(2, BOARD_SIZE - 1 + 1):
                    for di in range(4):
                        dx, dy = DIRS[di]
                        nx, ny = x + rr * dx, y + rr * dy
                        if _between(nx, ny) and field[ny][nx] == 'n':
                            ec, _, _ = _exist(x, y, nx, ny, enemy_color, field)
                            if ec == 1:
                                can_capture = True
                                break
                    if can_capture:
                        break
                if not can_capture:
                    continue

                for _ in range(MAXRND):
                    opt = []  # list of (direction_index, distance)
                    x1, y1 = x, y
                    model = _copy_field(field)
                    init_dangerous = _dangerous_position(x, y, field, color)
                    score = 1 if init_dangerous else 0

                    eob = False
                    while not eob:
                        rr = random.randint(2, BOARD_SIZE - 2 + 1)
                        d = random.randint(0, 3)
                        dx, dy = DIRS[d]
                        nx, ny = x1 + rr * dx, y1 + rr * dy
                        if _between(nx, ny) and model[ny][nx] == 'n':
                            ec, bx, by = _exist(x1, y1, nx, ny, enemy_color, model)
                            if ec == 1:
                                found_any = True
                                opt.append((d, rr))
                                model[y1][x1] = 'n'
                                # Score for capturing king or near-promotion row
                                cap = model[by][bx]
                                if by == (2 if color == 'b' else BOARD_SIZE - 1):
                                    if cap == ('w' if color == 'b' else 'b'):
                                        score += 1
                                if by == (2 if color == 'b' else BOARD_SIZE - 1) or cap == ('W' if color == 'b' else 'B'):
                                    score += 2
                                model[by][bx] = 'n'
                                model[ny][nx] = my_king
                                x1, y1 = nx, ny

                        # Check end of beat
                        eob = True
                        for rrr in range(2, _maximum(x1, y1) + 1):
                            for dd in range(4):
                                ddx, ddy = DIRS[dd]
                                nnx, nny = x1 + rrr * ddx, y1 + rrr * ddy
                                if _between(nnx, nny) and model[nny][nnx] == 'n':
                                    ec2, _, _ = _exist(x1, y1, nnx, nny, enemy_color, model)
                                    if ec2 == 1:
                                        eob = False
                                        break
                            if not eob:
                                break

                    score += len(opt)  # +1 per capture
                    if use_base:
                        pos_str = _get_string(model)
                        db_result = _search_db(learning_db, pos_str)
                        if db_result == 'good':
                            score += 3
                        elif db_result == 'bad':
                            score -= 3
                    if not _dangerous_position(x1, y1, model, color):
                        score += 1
                    if score > max_score:
                        max_score = score
                        best_optimum = opt
                        best_start = (x, y)

    if not found_any or best_optimum is None or best_start is None:
        return None

    # Build the capture path
    path = [best_start]
    cx, cy = best_start
    piece = field[cy][cx]
    for d_idx, dist in best_optimum:
        dx, dy = DIRS[d_idx]
        nx, ny = cx + dist * dx, cy + dist * dy

        # For king's last move, find safest landing
        if piece == my_king and (d_idx, dist) == best_optimum[-1]:
            # Try to find the actual landing that avoids danger
            enemy_color = 'w' if color == 'b' else 'b'
            ec, bx, by = _exist(cx, cy, nx, ny, enemy_color, field)
            if ec == 1:
                # Try to find a safe landing along this direction
                for r_try in range(2, BOARD_SIZE - 1 + 1):
                    tnx, tny = cx + r_try * dx, cy + r_try * dy
                    if _between(tnx, tny) and field[tny][tnx] == 'n':
                        tec, tbx, tby = _exist(cx, cy, tnx, tny, enemy_color, field)
                        if tec == 1:
                            if not _dangerous_beat(cx, cy, tnx, tny, tbx, tby, field, color):
                                nx, ny = tnx, tny
                                break

        path.append((nx, ny))
        cx, cy = nx, ny

    return AIMove('capture', path)


# ===========================================================================
# COMBINATION — tactical sacrifices
# ===========================================================================

def _combination(board: Board, color: str, use_base: bool,
                 learning_db: LearningDB | None) -> AIMove | None:
    """Find a profitable sacrifice move.

    Matches the original Combination() procedure.
    Only considers regular pieces (not kings), only if we have > 1 piece.
    """
    field = board.field
    my_pawn = 'b' if color == 'b' else 'w'
    enemies = WHITES if color == 'b' else BLACKS

    if _number(color, field) <= 1:
        return None

    max_score = -100
    best_move = None

    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            if field[y][x] != my_pawn:
                continue

            # Only forward directions for sacrifice (dirs 0,1 for black; 2,3 for white)
            forward_dirs = range(0, 2) if color == 'b' else range(2, 4)

            for di in forward_dirs:
                dx, dy = DIRS[di]
                # Check: target square is empty, and beyond it is an enemy
                tx, ty = x + dx, y + dy
                ex, ey = x + 2 * dx, y + 2 * dy
                if not _between(ex, ey):
                    continue
                if not _between(tx, ty):
                    continue
                if field[ty][tx] != 'n':
                    continue
                if field[ey][ex] not in enemies:
                    continue

                # Simulate the sacrifice
                score = 0
                model = _copy_field(field)
                model[y][x] = 'n'
                model[ty][tx] = my_pawn

                if not _one_beat(model):
                    continue

                # Lookahead: white captures, then black captures
                for _depth in range(DEPTH0):
                    delta_w = _virtual_white_beat(model, use_base, learning_db)
                    if delta_w == 0:
                        break
                    score -= delta_w
                    delta_b = _virtual_black_beat(model, use_base, learning_db)
                    if delta_b == 0:
                        break
                    score += delta_b

                if score > max_score:
                    max_score = score
                    best_move = ((x, y), (tx, ty))

    if best_move is not None and max_score > 2 and _number(color, field) > 1:
        return AIMove('sacrifice', [best_move[0], best_move[1]])
    return None


# ===========================================================================
# ACTION — normal move with heuristic scoring
# ===========================================================================

def _action(board: Board, color: str, use_base: bool,
            learning_db: LearningDB | None) -> AIMove | None:
    """Find the best normal (non-capture) move.

    Matches the original Action() procedure.
    """
    field = board.field
    my_pawn = 'b' if color == 'b' else 'w'
    my_king = 'B' if color == 'b' else 'W'
    promote_row = BOARD_SIZE if color == 'b' else 1
    enemy_color = 'w' if color == 'b' else 'b'

    max_score = -100.0
    best_move = None
    found = False

    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            piece = field[y][x]

            if piece == my_pawn:
                # Forward directions only (dirs 0,1 for black moving down; 2,3 for white moving up)
                forward_dirs = range(0, 2) if color == 'b' else range(2, 4)

                for di in forward_dirs:
                    dx, dy = DIRS[di]
                    nx, ny = x + dx, y + dy
                    if not _between(nx, ny):
                        continue
                    if field[ny][nx] != 'n':
                        continue

                    score = 0.0
                    model = _copy_field(field)

                    was_side = _side(x, y, model)
                    was_danger = _danger(color, model)

                    model[y][x] = 'n'
                    model[ny][nx] = my_pawn

                    if _neighbour(nx, ny, model):
                        score += 0.5
                    if was_side and not _side(nx, ny, model):
                        score += 1.0
                    if ny == promote_row:
                        score += 2.0
                    if was_danger and not _danger(color, model):
                        score += 1.0
                    if not _dangerous_position(nx, ny, model, color):
                        score += 1.5
                    else:
                        score -= 2.0

                    if use_base:
                        pos_str = _get_string(model)
                        db_result = _search_db(learning_db, pos_str)
                        if db_result == 'good':
                            score += 3.0
                        elif db_result == 'bad':
                            score -= 3.0

                    # Lookahead
                    for _depth in range(DEPTH0):
                        delta_w = _virtual_white_beat(model, use_base, learning_db)
                        if delta_w == 0:
                            break
                        score -= delta_w
                        delta_b = _virtual_black_beat(model, use_base, learning_db)
                        if delta_b == 0:
                            break
                        score += delta_b

                    if score > max_score or (score == max_score and random.randint(0, 1) == 1):
                        found = True
                        max_score = score
                        best_move = ((x, y), (nx, ny))

            elif piece == my_king:
                # King moves — Monte Carlo sampling of direction/distance
                for _ in range(MAXRND):
                    r = random.randint(1, BOARD_SIZE - 2)
                    d = random.randint(0, 3)
                    dx, dy = DIRS[d]
                    nx, ny = x + r * dx, y + r * dy

                    if not _between(nx, ny):
                        continue

                    model = _copy_field(field)
                    if model[ny][nx] != 'n':
                        continue

                    # Check path is clear (no pieces in the way)
                    ec, _, _ = _exist(x, y, nx, ny, enemy_color, model)
                    if ec != 0:
                        continue

                    found = True
                    score = 0.0

                    white_danger_before = _danger(enemy_color, model)
                    black_danger_before = _danger(color, model)

                    model[y][x] = 'n'
                    model[ny][nx] = my_king

                    white_danger_after = _danger(enemy_color, model)
                    black_danger_after = _danger(color, model)
                    new_pos_dangerous = _dangerous_position(nx, ny, model, color)

                    # Heuristic scoring matching original
                    if (not white_danger_before and white_danger_after and
                            not new_pos_dangerous and not black_danger_after):
                        score += 1.0
                    elif (not white_danger_before and white_danger_after and
                          not new_pos_dangerous):
                        score += 1.0

                    if not black_danger_after and not new_pos_dangerous:
                        score += 1.0

                    if black_danger_before and not black_danger_after:
                        score += 2.0

                    if new_pos_dangerous:
                        score -= 3.0

                    if use_base:
                        pos_str = _get_string(model)
                        db_result = _search_db(learning_db, pos_str)
                        if db_result == 'good':
                            score += 3.0
                        elif db_result == 'bad':
                            score -= 3.0

                    # Lookahead
                    for _depth in range(DEPTH0):
                        delta_w = _virtual_white_beat(model, use_base, learning_db)
                        if delta_w == 0:
                            break
                        score -= delta_w
                        delta_b = _virtual_black_beat(model, use_base, learning_db)
                        if delta_b == 0:
                            break
                        score += delta_b

                    if score > max_score:
                        max_score = score
                        best_move = ((x, y), (nx, ny))

    if not found or best_move is None:
        return None

    return AIMove('move', [best_move[0], best_move[1]])


# ===========================================================================
# MAIN ENTRY POINT
# ===========================================================================

def computer_move(board: Board,
                  difficulty: int = 2,
                  use_base: bool = False,
                  learning_db: LearningDB | None = None,
                  color: str = 'b') -> AIMove | None:
    """Compute the AI's move.

    Priority:
        1. SeeBeat — mandatory captures (always checked first)
        2. Combination — tactical sacrifices (difficulty >= 2)
        3. Action — normal moves

    Args:
        board: Current board state.
        difficulty: 1=amateur, 2=normal, 3=professional.
        use_base: Whether to use the learning database.
        learning_db: LearningDB instance or None.
        color: 'b' or 'w' — which side the computer plays.

    Returns:
        An AIMove describing the chosen move, or None if no legal move exists.
    """
    # 1. Mandatory captures (SeeBeat)
    move = _see_beat(board, color, use_base, learning_db)
    if move is not None:
        return move

    # 2. Tactical sacrifices (Combination) — only on higher difficulties
    if difficulty >= 2:
        move = _combination(board, color, use_base, learning_db)
        if move is not None:
            return move

    # 3. Normal moves (Action)
    move = _action(board, color, use_base, learning_db)
    if move is not None:
        return move

    return None


# ===========================================================================
# LEARNING: record positions after game outcome
# ===========================================================================

def record_learning(learning_db: LearningDB,
                    board_before: Board,
                    board_after: Board,
                    color: str,
                    won: bool) -> None:
    """Record a position in the learning database after a game outcome.

    Args:
        learning_db: The database to update.
        board_before: Board state before the move.
        board_after: Board state after the move.
        color: The AI's color.
        won: True if the AI won, False if it lost.
    """
    from draughts.game.learning import invertstr

    pos_str = board_after.get_string()

    # Calculate score change
    score = _appreciate(board_before.field, board_after.field, color)

    if won and score > NEED_TO_SAVE:
        learning_db.add_good(pos_str)
        learning_db.save()
    elif not won and score < -NEED_TO_SAVE:
        learning_db.add_bad(invertstr(pos_str))
        learning_db.save()


def _appreciate(field1: list[list[str]], field2: list[list[str]],
                color: str) -> int:
    """Evaluate how much the position changed in favor of a given color.

    Matches the original appreciate() function.
    """
    k = -1 if color == 'b' else 1
    score = 0
    for y in range(1, BOARD_SIZE + 1):
        for x in range(1, BOARD_SIZE + 1):
            p1 = field1[y][x]
            p2 = field2[y][x]
            for p, sign in [(p1, 1), (p2, -1)]:
                if p == 'b':
                    score += sign * k
                elif p == 'w':
                    score -= sign * k
                elif p == 'B':
                    score += sign * 2 * k
                elif p == 'W':
                    score -= sign * 2 * k
    return score
