import random
import copy

# ------------------ Constants ------------------ #
BOARD_WIDTH = 10
BOARD_HEIGHT = 20
EMPTY_CELL = 0
GARBAGE_COLOR = 8  # Color index for gray garbage blocks

TETROMINOES = {
    "I": {"shape": [[1, 1, 1, 1]], "color": 1},
    "O": {"shape": [[2, 2], [2, 2]], "color": 2},
    "T": {"shape": [[0, 3, 0], [3, 3, 3]], "color": 3},
    "S": {"shape": [[0, 4, 4], [4, 4, 0]], "color": 4},
    "Z": {"shape": [[5, 5, 0], [0, 5, 5]], "color": 5},
    "J": {"shape": [[6, 0, 0], [6, 6, 6]], "color": 6},
    "L": {"shape": [[0, 0, 7], [7, 7, 7]], "color": 7},
}

LEFT = {"x": -1, "y": 0}
RIGHT = {"x": 1, "y": 0}
DOWN = {"x": 0, "y": 1}


# -------------------------- Piece Class -------------------------- #
class Piece:
    def __init__(self, tetromino_type):
        self.type = tetromino_type
        self.shape = copy.deepcopy(TETROMINOES[tetromino_type]["shape"])
        self.color = TETROMINOES[tetromino_type]["color"]
        self.x = BOARD_WIDTH // 2 - len(self.shape[0]) // 2
        self.y = 0
        if tetromino_type == "I":
            self.y = -1  # I pieces start one row higher

    def rotate(self):
        rows, cols = len(self.shape), len(self.shape[0])
        rotated = [[0 for _ in range(rows)] for _ in range(cols)]
        for r in range(rows):
            for c in range(cols):
                rotated[c][rows - 1 - r] = self.shape[r][c]
        return rotated

    def get_positions(self):
        positions = []
        for y, row in enumerate(self.shape):
            for x, cell in enumerate(row):
                if cell:
                    positions.append({"x": self.x + x, "y": self.y + y})
        return positions


# --------------------- Piece Generation ---------------------- #
def create_piece_generator(seed):
    rng = random.Random(seed)

    def get_next_piece():
        tetromino_type = rng.choice(list(TETROMINOES.keys()))
        return Piece(tetromino_type)

    return get_next_piece


# ---------------------- Game State Class ---------------------- #
class GameState:
    def __init__(self, seed, debug_mode=False):
        self.board = self._create_board()
        self.score = 0
        self.level = 1
        self.lines_cleared_total = 0
        self.game_over = False
        self.pending_garbage = 0  # Queue for incoming garbage
        self._get_next_piece_func = create_piece_generator(seed)
        self.current_piece = self._get_next_piece_func()
        self.next_piece = self._get_next_piece_func()
        self.held_piece = None
        self.can_hold = True
        self.debug_mode = debug_mode  # Store debug mode

    def _create_board(self):
        return [[EMPTY_CELL for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

    def check_collision(self, piece, dx=0, dy=0, rotated_shape=None):
        shape = piece.shape if rotated_shape is None else rotated_shape
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    new_x = piece.x + x + dx
                    new_y = piece.y + y + dy
                    if new_x < 0 or new_x >= BOARD_WIDTH or new_y >= BOARD_HEIGHT:
                        return True
                    if new_y < 0:
                        continue  # Allow pieces to start above the board
                    if self.board[new_y][new_x] != EMPTY_CELL:
                        return True
        return False

    def merge_piece(self, piece):
        for y, row in enumerate(piece.shape):
            for x, cell in enumerate(row):
                if cell and piece.y + y >= 0:  # Only merge visible parts
                    self.board[piece.y + y][piece.x + x] = piece.color

    def clear_lines(self):
        lines_cleared = 0
        y = BOARD_HEIGHT - 1
        new_board = []
        for current_y in range(BOARD_HEIGHT - 1, -1, -1):
            if EMPTY_CELL in self.board[current_y]:
                new_board.append(self.board[current_y])
            else:
                lines_cleared += 1

        # Add new empty lines at the top
        for _ in range(lines_cleared):
            new_board.append([EMPTY_CELL] * BOARD_WIDTH)

        self.board = new_board[::-1]  # Reverse to correct order
        self.lines_cleared_total += lines_cleared
        return lines_cleared

    def calculate_score(self, lines_cleared, level):
        if lines_cleared == 0:
            return 0
        points_per_line = {1: 40, 2: 100, 3: 300, 4: 1200}
        base_score = points_per_line.get(lines_cleared, 0) * level
        self.score += base_score
        return base_score

    def queue_garbage(self, count):
        """Add incoming garbage to the pending queue."""
        if count > 0:
            self.pending_garbage += count
            if self.debug_mode:
                print(
                    f"[GARBAGE QUEUE] Queued {count} lines. Total pending: {self.pending_garbage}"
                )

    def reduce_pending_garbage(self, reduction_amount):
        """Reduce pending garbage by the specified amount (e.g., due to line clears)."""
        if reduction_amount <= 0:
            return 0

        actual_reduction = min(self.pending_garbage, reduction_amount)
        self.pending_garbage -= actual_reduction
        if self.debug_mode:
            print(
                f"[GARBAGE QUEUE] Reduced pending by {actual_reduction} (tried {reduction_amount}). Remaining: {self.pending_garbage}"
            )
        return actual_reduction  # Return how much was actually reduced

    def apply_pending_garbage(self):
        """Add the currently pending garbage lines to the board."""
        count = self.pending_garbage
        if count <= 0:
            return False

        if self.debug_mode:
            print(f"[GARBAGE APPLY] Applying {count} pending garbage lines")
            print(f"[GARBAGE APPLY] Board before: {len(self.board)} rows")

        for _ in range(count):
            gap = random.randint(0, BOARD_WIDTH - 1)
            garbage_line = [GARBAGE_COLOR] * BOARD_WIDTH
            garbage_line[gap] = EMPTY_CELL

            # Remove top row and add garbage to bottom
            if len(self.board) > 0:
                self.board.pop(0)
            self.board.append(garbage_line)

        # Reset pending garbage after applying
        lines_applied = count
        self.pending_garbage = 0

        if self.debug_mode:
            print(
                f"[GARBAGE APPLY] Board after: {len(self.board)} rows. Applied {lines_applied} lines."
            )

        return True  # Indicate success

    def is_game_over(self):
        """Check for game over conditions.

        Game over occurs if a newly spawned piece collides immediately
        AND cannot move down (block out), or if blocks have reached the
        very top row (less common, but a fail-safe).
        """
        # Check collision at spawn position
        if self.check_collision(self.current_piece, 0, 0):
            # Check if it *also* collides one step down (true block out)
            if self.check_collision(self.current_piece, 0, 1):
                if self.debug_mode:
                    print(
                        "[GAME OVER CHECK] New piece collided immediately AND cannot move down (Block Out)."
                    )
                self.game_over = True
                return True
            # It collided, but can potentially move down. The game isn't technically over yet,
            # although it's likely a "Top Out" situation if the player can't clear space fast.
            if self.debug_mode:
                print(
                    "[GAME OVER CHECK] New piece collided at spawn, but can move down (Top Out). Game continues."
                )
            return False  # Not a definite game over yet

        # Original check: Blocks are already static in the topmost visible rows (less common)
        # This might be too aggressive, relying on spawn collision is usually sufficient.
        # Let's comment this out for now to rely purely on spawn collision.
        # for row in self.board[:1]: # Check only the very top visible row
        #     if any(cell != EMPTY_CELL for cell in row):
        #         print("[GAME OVER CHECK] Static block found in top visible row.")
        #         self.game_over = True
        #         return True

        return False  # No game over condition met

    def spawn_next_piece(self):
        self.current_piece = self.next_piece
        self.next_piece = self._get_next_piece_func()
        self.can_hold = True
        if self.is_game_over():
            return False  # Game over on spawn
        return True

    def hold_piece(self):
        if not self.can_hold:
            return False

        if self.held_piece is None:
            self.held_piece = Piece(self.current_piece.type)
            self.spawn_next_piece()
        else:
            # Swap current and held
            held_type = self.held_piece.type
            self.held_piece = Piece(self.current_piece.type)
            self.current_piece = Piece(held_type)
            # Reset position for the previously held piece
            self.current_piece.x = (
                BOARD_WIDTH // 2 - len(self.current_piece.shape[0]) // 2
            )
            self.current_piece.y = 0
            if self.current_piece.type == "I":
                self.current_piece.y = -1

        self.can_hold = False
        return True

    def attempt_move(self, dx, dy):
        if not self.check_collision(self.current_piece, dx, dy):
            self.current_piece.x += dx
            self.current_piece.y += dy
            return True
        return False

    def attempt_rotation(self):
        rotated_shape = self.current_piece.rotate()

        # Basic check (no kick)
        if not self.check_collision(self.current_piece, 0, 0, rotated_shape):
            self.current_piece.shape = rotated_shape
            return True

        # Wall kicks (simple left/right)
        kick_offsets = [(1, 0), (-1, 0), (2, 0), (-2, 0), (0, -1)]  # Basic kicks
        for dx, dy in kick_offsets:
            if not self.check_collision(self.current_piece, dx, dy, rotated_shape):
                self.current_piece.x += dx
                self.current_piece.y += dy
                self.current_piece.shape = rotated_shape
                return True
        return False

    def hard_drop(self):
        drop_distance = 0
        while not self.check_collision(self.current_piece, 0, drop_distance + 1):
            drop_distance += 1
        self.current_piece.y += drop_distance
        # Score for hard drop (2 points per row dropped)
        self.score += drop_distance * 2
        return drop_distance

    def add_garbage_lines(self, count):
        # THIS METHOD IS NOW DEPRECATED - Use queue_garbage and apply_pending_garbage
        if self.debug_mode:
            print(
                f"[DEPRECATED] add_garbage_lines called with {count} - Should use queue/apply"
            )
        # For safety, let's route it to the new queueing method
        self.queue_garbage(count)
        return True


# Helper function to get rotated shape (could be part of Piece class too)
# Keeping it separate for now as it's used by renderer as well.
def get_piece_shape(piece_type, rotation):
    # Base shapes for each piece type
    # Using colors from TETROMINOES to fill the shapes
    color = TETROMINOES.get(piece_type, {}).get("color", 1)  # Default to 1 if not found

    shape_templates = {
        "I": [
            [[0, 0, 0, 0], [color, color, color, color], [0, 0, 0, 0], [0, 0, 0, 0]],
            [[0, 0, color, 0], [0, 0, color, 0], [0, 0, color, 0], [0, 0, color, 0]],
            [[0, 0, 0, 0], [0, 0, 0, 0], [color, color, color, color], [0, 0, 0, 0]],
            [[0, color, 0, 0], [0, color, 0, 0], [0, color, 0, 0], [0, color, 0, 0]],
        ],
        "O": [[[color, color], [color, color]]],
        "T": [
            [[0, color, 0], [color, color, color], [0, 0, 0]],
            [[0, color, 0], [0, color, color], [0, color, 0]],
            [[0, 0, 0], [color, color, color], [0, color, 0]],
            [[0, color, 0], [color, color, 0], [0, color, 0]],
        ],
        "S": [
            [[0, color, color], [color, color, 0], [0, 0, 0]],
            [[0, color, 0], [0, color, color], [0, 0, color]],
            [[0, 0, 0], [0, color, color], [color, color, 0]],
            [[color, 0, 0], [color, color, 0], [0, color, 0]],
        ],
        "Z": [
            [[color, color, 0], [0, color, color], [0, 0, 0]],
            [[0, 0, color], [0, color, color], [0, color, 0]],
            [[0, 0, 0], [color, color, 0], [0, color, color]],
            [[0, color, 0], [color, color, 0], [color, 0, 0]],
        ],
        "J": [
            [[color, 0, 0], [color, color, color], [0, 0, 0]],
            [[0, color, color], [0, color, 0], [0, color, 0]],
            [[0, 0, 0], [color, color, color], [0, 0, color]],
            [[0, color, 0], [0, color, 0], [color, color, 0]],
        ],
        "L": [
            [[0, 0, color], [color, color, color], [0, 0, 0]],
            [[0, color, 0], [0, color, 0], [0, color, color]],
            [[0, 0, 0], [color, color, color], [color, 0, 0]],
            [[color, color, 0], [0, color, 0], [0, color, 0]],
        ],
    }

    if piece_type not in shape_templates:
        return [[0]]  # Return empty if type is unknown

    shapes = shape_templates[piece_type]
    rot_index = rotation % len(shapes)
    return shapes[rot_index]
