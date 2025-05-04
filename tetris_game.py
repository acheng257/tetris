import curses
import random
import copy
import locale


from game.state import GameState, Piece, create_piece_generator
from game.combo import ComboSystem
from game.controller import GameController
from ui.curses_renderer import CursesRenderer
from ui.input_handler import InputHandler

locale.setlocale(locale.LC_ALL, "")

# ------------------ Constants and Tetrimino Definitions ------------------ #
BOARD_WIDTH = 10
BOARD_HEIGHT = 20
EMPTY_CELL = 0
# Define a specific color for garbage blocks - 8 is used for the border
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

COLORS = {
    0: curses.COLOR_BLACK,
    1: curses.COLOR_CYAN,
    2: curses.COLOR_YELLOW,
    3: curses.COLOR_MAGENTA,
    4: curses.COLOR_GREEN,
    5: curses.COLOR_RED,
    6: curses.COLOR_BLUE,
    7: curses.COLOR_WHITE,
    8: curses.COLOR_WHITE,  # Used for borders and now also for garbage blocks
    GARBAGE_COLOR: curses.COLOR_WHITE,  # Ensure the garbage color is defined
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
            self.y = -1

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


# ------------------ Drawing and Utility Functions ------------------ #
def init_colors():
    curses.start_color()
    # Initialize standard colors for pieces
    for i, color in COLORS.items():
        curses.init_pair(i + 1, color, curses.COLOR_BLACK)

    # Special color for garbage blocks - gray on black
    # Use dim white (or if supported, a true gray color)
    curses.init_pair(GARBAGE_COLOR + 1, curses.COLOR_WHITE, curses.COLOR_BLACK)


def create_board():
    return [[EMPTY_CELL for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]


def draw_board(stdscr, board, score, level, combo_display, player_name=None):
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    board_height = BOARD_HEIGHT + 2
    board_width = BOARD_WIDTH * 2 + 2

    if h < board_height or w < board_width + 15:
        stdscr.clear()
        error_msg = "Terminal too small! Resize and restart."
        try:
            stdscr.addstr(h // 2, max(0, (w - len(error_msg)) // 2), error_msg)
            stdscr.refresh()
            stdscr.getch()
        except curses.error:
            pass
        return False

    start_y = max(0, (h - board_height) // 2)
    start_x = max(0, (w - board_width) // 2)
    border_color = curses.color_pair(8 + 1)

    try:
        # Display player name if provided (centered above the board)
        if player_name:
            name_text = f"Player: {player_name}"
            name_x = start_x + (board_width - len(name_text)) // 2
            stdscr.addstr(start_y - 2, max(0, name_x), name_text, curses.A_BOLD)

        stdscr.addstr(start_y, start_x, "+" + "--" * BOARD_WIDTH + "+", border_color)
        for y in range(BOARD_HEIGHT):
            stdscr.addstr(start_y + 1 + y, start_x, "|", border_color)
            stdscr.addstr(
                start_y + 1 + y, start_x + BOARD_WIDTH * 2 + 1, "|", border_color
            )
        stdscr.addstr(
            start_y + BOARD_HEIGHT + 1,
            start_x,
            "+" + "--" * BOARD_WIDTH + "+",
            border_color,
        )

        for y, row in enumerate(board):
            for x, cell in enumerate(row):
                if cell != EMPTY_CELL:
                    # Use special rendering for garbage blocks
                    if cell == GARBAGE_COLOR:
                        # Use white color with dim attribute for gray appearance
                        color_pair = curses.color_pair(cell + 1) | curses.A_DIM
                        stdscr.addstr(
                            start_y + 1 + y, start_x + 1 + x * 2, "░░", color_pair
                        )
                    else:
                        # Normal rendering for regular tetromino blocks
                        color_pair = curses.color_pair(cell + 1)
                        stdscr.addstr(
                            start_y + 1 + y, start_x + 1 + x * 2, "[]", color_pair
                        )
                else:
                    stdscr.addstr(start_y + 1 + y, start_x + 1 + x * 2, "  ")

        stdscr.addstr(start_y + 2, start_x + board_width + 2, f"Score: {score}")
        stdscr.addstr(start_y + 4, start_x + board_width + 2, f"Level: {level}")
        stdscr.addstr(start_y + 6, start_x + board_width + 2, f"Combo: {combo_display}")

        controls_y = start_y + 7
        stdscr.addstr(controls_y, start_x + board_width + 2, "Controls:")
        stdscr.addstr(controls_y + 1, start_x + board_width + 2, "← → : Move")
        stdscr.addstr(controls_y + 2, start_x + board_width + 2, "↑ : Rotate")
        stdscr.addstr(controls_y + 3, start_x + board_width + 2, "↓ : Soft drop")
        stdscr.addstr(controls_y + 4, start_x + board_width + 2, "Space: Hard drop")
        stdscr.addstr(controls_y + 5, start_x + board_width + 2, "c : Hold piece")
        stdscr.addstr(controls_y + 6, start_x + board_width + 2, "q : Quit")

        stdscr.refresh()
        return True
    except curses.error:
        try:
            stdscr.clear()
            stdscr.addstr(0, 0, "Terminal too small! Resize and restart.")
            stdscr.refresh()
        except curses.error:
            pass
        return False


def is_game_over(board):
    print("[GAME OVER DEBUG] Checking if game is over")
    print(f"[GAME OVER DEBUG] Board: {board}")
    for row in board[:2]:
        if any(cell != EMPTY_CELL for cell in row):
            return True
    return False


def check_collision(board, piece, dx=0, dy=0, rotated_shape=None):
    shape = piece.shape if rotated_shape is None else rotated_shape
    for y, row in enumerate(shape):
        for x, cell in enumerate(row):
            if cell:
                new_x = piece.x + x + dx
                new_y = piece.y + y + dy
                if new_x < 0 or new_x >= BOARD_WIDTH or new_y >= BOARD_HEIGHT:
                    return True
                if new_y < 0:
                    continue
                if board[new_y][new_x] != EMPTY_CELL:
                    return True
    return False


def merge_piece(board, piece):
    for y, row in enumerate(piece.shape):
        for x, cell in enumerate(row):
            if cell and piece.y + y >= 0:
                board[piece.y + y][piece.x + x] = piece.color


def clear_lines(board):
    lines_cleared = 0
    y = BOARD_HEIGHT - 1
    while y >= 0:
        if EMPTY_CELL not in board[y]:
            lines_cleared += 1
            for move_y in range(y, 0, -1):
                board[move_y] = board[move_y - 1].copy()
            board[0] = [EMPTY_CELL] * BOARD_WIDTH
        else:
            y -= 1
    return lines_cleared


def calculate_score(lines_cleared, level):
    if lines_cleared == 0:
        return 0
    points_per_line = {1: 40, 2: 100, 3: 300, 4: 1200}
    return points_per_line.get(lines_cleared, 0) * level


def draw_piece(stdscr, piece, board, ghost=False):
    h, w = stdscr.getmaxyx()
    board_height = BOARD_HEIGHT + 2
    board_width = BOARD_WIDTH * 2 + 2
    start_y = max(0, (h - board_height) // 2)
    start_x = max(0, (w - board_width) // 2)
    ghost_y = piece.y
    if ghost:
        drop_distance = 0
        while not check_collision(board, piece, 0, drop_distance + 1):
            drop_distance += 1
        ghost_y = piece.y + drop_distance

    for y, row in enumerate(piece.shape):
        for x, cell in enumerate(row):
            if cell:
                if piece.y + y >= 0:
                    color_pair = curses.color_pair(piece.color + 1)
                    try:
                        stdscr.addstr(
                            start_y + 1 + piece.y + y,
                            start_x + 1 + (piece.x + x) * 2,
                            "[]",
                            color_pair,
                        )
                    except curses.error:
                        pass
                if ghost and piece.y != ghost_y:
                    ghost_display_y = ghost_y + y
                    if 0 <= ghost_display_y < BOARD_HEIGHT:
                        try:
                            stdscr.addstr(
                                start_y + 1 + ghost_display_y,
                                start_x + 1 + (piece.x + x) * 2,
                                "[]",
                                curses.A_DIM,
                            )
                        except curses.error:
                            pass


def draw_next_and_held(stdscr, next_piece, held_piece, board):
    h, w = stdscr.getmaxyx()
    board_height = BOARD_HEIGHT + 2
    board_width = BOARD_WIDTH * 2 + 2
    start_y = max(0, (h - board_height) // 2)
    start_x = max(0, (w - board_width) // 2)
    preview_y = start_y + 15
    preview_x = start_x + board_width + 2
    try:
        stdscr.addstr(preview_y, preview_x, "Next:")
        next_preview_y = preview_y + 1
        next_preview_x = preview_x + 4
        for y, row in enumerate(next_piece.shape):
            for x, cell in enumerate(row):
                if cell:
                    color_pair = curses.color_pair(next_piece.color + 1)
                    stdscr.addstr(
                        next_preview_y + y, next_preview_x + x * 2, "[]", color_pair
                    )
        stdscr.addstr(preview_y + 5, preview_x, "Hold:")
        if held_piece:
            held_preview_y = preview_y + 6
            held_preview_x = preview_x + 4
            for y, row in enumerate(held_piece.shape):
                for x, cell in enumerate(row):
                    if cell:
                        color_pair = curses.color_pair(held_piece.color + 1)
                        stdscr.addstr(
                            held_preview_y + y, held_preview_x + x * 2, "[]", color_pair
                        )
    except curses.error:
        pass


def create_piece_generator(seed):
    rng = random.Random(seed)

    def get_next_piece():
        tetromino_type = rng.choice(list(TETROMINOES.keys()))
        return Piece(tetromino_type)

    return get_next_piece


def add_garbage_lines(board, count):
    """
    Remove count rows from the top and append count garbage rows with one random gap.
    The garbage lines are filled with gray blocks except for one random gap in each row.
    """
    print(f"[GARBAGE DEBUG] Adding {count} garbage lines to board")
    print(f"[GARBAGE DEBUG] Board before: {len(board)} rows, should be {BOARD_HEIGHT}")

    for i in range(count):
        # Create a visually distinct garbage line
        gap = random.randint(0, BOARD_WIDTH - 1)

        # Use the gray color for garbage blocks to make them visually distinct
        garbage_line = [GARBAGE_COLOR for _ in range(BOARD_WIDTH)]
        garbage_line[gap] = EMPTY_CELL  # Add random gap

        # Remove top row and add garbage to bottom
        board.pop(0)
        board.append(garbage_line)

        print(
            f"[GARBAGE DEBUG] Added garbage line {i+1}/{count} with gap at position {gap}, using gray color"
        )

    print(f"[GARBAGE DEBUG] Board after: {len(board)} rows, should be {BOARD_HEIGHT}")
    return True


def draw_other_players_boards(stdscr, peer_boards, board, peer_boards_lock):
    """Draw miniature versions of other players' boards in a grid layout"""
    h, w = stdscr.getmaxyx()
    main_board_width = BOARD_WIDTH * 2 + 2
    main_board_height = BOARD_HEIGHT + 2

    start_y = max(0, (h - main_board_height) // 2)
    start_x = max(0, (w - main_board_width) // 2)

    # Position for other player boards (to the right of the main board)
    other_boards_x = start_x + main_board_width + 25

    # Set dimensions for the mini boards
    mini_board_width = 10
    mini_board_height = 10
    board_spacing_x = mini_board_width + 5
    board_spacing_y = mini_board_height + 5

    # Calculate how many boards per row based on screen width
    max_boards_per_row = max(1, min(3, (w - other_boards_x) // board_spacing_x))

    with peer_boards_lock:
        # Sort peers by score (highest first)
        sorted_peers = sorted(
            peer_boards.items(), key=lambda x: x[1]["score"], reverse=True
        )

        # Deduplicate boards by player name to avoid duplicates from multiple connections
        seen_player_names = set()
        deduplicated_peers = []

        for peer_id, peer_data in sorted_peers:
            player_name = peer_data.get("player_name", "")
            # Remove any numeric suffix that might have been added (like QuickWarriorS)
            base_name = player_name.rstrip("S")

            if base_name and base_name not in seen_player_names:
                seen_player_names.add(base_name)
                deduplicated_peers.append((peer_id, peer_data))

        # Draw header
        try:
            header_y = start_y - 2
            if header_y >= 0:
                stdscr.addstr(header_y, other_boards_x, "OTHER PLAYERS", curses.A_BOLD)
        except curses.error:
            pass

        # Draw up to 9 peer boards (3x3 grid) from deduplicated list
        max_peer_boards = min(9, len(deduplicated_peers))

        for i, (peer_id, peer_data) in enumerate(deduplicated_peers[:max_peer_boards]):
            if i >= max_peer_boards:
                break

            # Calculate position in the grid
            row = i // max_boards_per_row
            col = i % max_boards_per_row

            board_y = start_y + row * board_spacing_y
            board_x = other_boards_x + col * board_spacing_x

            # Make sure we have room to draw
            if board_y + mini_board_height >= h or board_x + mini_board_width >= w:
                continue

            # Extract peer info
            peer_board = peer_data["board"]
            peer_score = peer_data["score"]
            player_name = peer_data["player_name"]
            if len(player_name) > 12:  # Truncate long names
                player_name = player_name[-12:]

            try:
                # Draw player name and score with different colors for clarity
                name_attr = curses.A_BOLD
                stdscr.addstr(board_y - 2, board_x, f"{player_name}", name_attr)
                # stdscr.addstr(board_y - 1, board_x, f"Score: {peer_score}")

                # Draw mini board border
                border_color = curses.color_pair(8 + 1)
                stdscr.addstr(
                    board_y, board_x, "+" + "-" * mini_board_width + "+", border_color
                )
                for y in range(mini_board_height):
                    stdscr.addstr(board_y + y + 1, board_x, "|", border_color)
                    stdscr.addstr(
                        board_y + y + 1,
                        board_x + mini_board_width + 1,
                        "|",
                        border_color,
                    )
                stdscr.addstr(
                    board_y + mini_board_height + 1,
                    board_x,
                    "+" + "-" * mini_board_width + "+",
                    border_color,
                )

                # Draw mini board content - shows bottom part of board for better visibility
                board_start = max(0, BOARD_HEIGHT - mini_board_height)
                for y in range(board_start, BOARD_HEIGHT):
                    mini_y = y - board_start
                    for x in range(BOARD_WIDTH):
                        if y < len(peer_board) and x < len(peer_board[y]):
                            cell = peer_board[y][x]
                            if cell != EMPTY_CELL:
                                # Special rendering for garbage blocks
                                if cell == GARBAGE_COLOR:
                                    color_pair = (
                                        curses.color_pair(cell + 1) | curses.A_DIM
                                    )
                                    stdscr.addstr(
                                        board_y + mini_y + 1,
                                        board_x + 1 + x,
                                        "░",
                                        color_pair,
                                    )
                                else:
                                    color_pair = curses.color_pair(cell + 1)
                                    stdscr.addstr(
                                        board_y + mini_y + 1,
                                        board_x + 1 + x,
                                        "#",
                                        color_pair,
                                    )

                # Draw active piece if available
                if "active_piece" in peer_data:
                    piece_info = peer_data["active_piece"]
                    piece_type = piece_info["type"]
                    piece_x = piece_info["x"]
                    piece_y = piece_info["y"]
                    piece_rotation = piece_info["rotation"]
                    piece_color = piece_info["color"]

                    # Create a representation of the piece based on its type and rotation
                    # This is simplified; in a real implementation, you'd use the rotation to determine shape
                    piece_shape = get_piece_shape(piece_type, piece_rotation)

                    # Draw the piece blocks
                    for block_y, row in enumerate(piece_shape):
                        for block_x, cell in enumerate(row):
                            if cell:
                                # Calculate board position of this block
                                board_x_pos = piece_x + block_x
                                board_y_pos = piece_y + block_y

                                # Check if the block is visible on our mini board
                                if (
                                    board_y_pos >= board_start
                                    and 0 <= board_x_pos < BOARD_WIDTH
                                ):
                                    mini_y_pos = board_y_pos - board_start

                                    # Draw the piece block
                                    color_pair = curses.color_pair(piece_color + 1)
                                    stdscr.addstr(
                                        board_y + mini_y_pos + 1,
                                        board_x + 1 + board_x_pos,
                                        "#",
                                        color_pair,
                                    )
            except curses.error:
                # Handle errors when drawing outside window bounds
                pass


# Helper function to convert piece type and rotation to shape
def get_piece_shape(piece_type, rotation):
    """Get the shape of a piece based on type and rotation"""
    # Base shapes for each piece type
    shape_templates = {
        "I": [
            [[0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0], [0, 0, 0, 0]],
            [[0, 0, 1, 0], [0, 0, 1, 0], [0, 0, 1, 0], [0, 0, 1, 0]],
            [[0, 0, 0, 0], [0, 0, 0, 0], [1, 1, 1, 1], [0, 0, 0, 0]],
            [[0, 1, 0, 0], [0, 1, 0, 0], [0, 1, 0, 0], [0, 1, 0, 0]],
        ],
        "O": [[[2, 2], [2, 2]]],
        "T": [
            [[0, 3, 0], [3, 3, 3], [0, 0, 0]],
            [[0, 3, 0], [0, 3, 3], [0, 3, 0]],
            [[0, 0, 0], [3, 3, 3], [0, 3, 0]],
            [[0, 3, 0], [3, 3, 0], [0, 3, 0]],
        ],
        "S": [
            [[0, 4, 4], [4, 4, 0], [0, 0, 0]],
            [[0, 4, 0], [0, 4, 4], [0, 0, 4]],
            [[0, 0, 0], [0, 4, 4], [4, 4, 0]],
            [[4, 0, 0], [4, 4, 0], [0, 4, 0]],
        ],
        "Z": [
            [[5, 5, 0], [0, 5, 5], [0, 0, 0]],
            [[0, 0, 5], [0, 5, 5], [0, 5, 0]],
            [[0, 0, 0], [5, 5, 0], [0, 5, 5]],
            [[0, 5, 0], [5, 5, 0], [5, 0, 0]],
        ],
        "J": [
            [[6, 0, 0], [6, 6, 6], [0, 0, 0]],
            [[0, 6, 6], [0, 6, 0], [0, 6, 0]],
            [[0, 0, 0], [6, 6, 6], [0, 0, 6]],
            [[0, 6, 0], [0, 6, 0], [6, 6, 0]],
        ],
        "L": [
            [[0, 0, 7], [7, 7, 7], [0, 0, 0]],
            [[0, 7, 0], [0, 7, 0], [0, 7, 7]],
            [[0, 0, 0], [7, 7, 7], [7, 0, 0]],
            [[7, 7, 0], [0, 7, 0], [0, 7, 0]],
        ],
    }

    # Safety checks
    if piece_type not in shape_templates:
        return [[0]]

    shapes = shape_templates[piece_type]
    rot_index = rotation % len(shapes)

    return shapes[rot_index]


# ComboSystem class to handle combo logic
class ComboSystem:
    def __init__(self):
        self.combo_count = 0
        self.debug_message = ""
        self.debug_time = 0
        self.debug_display_time = 5.0  # Display debug message for 5 seconds
        # Track if we've cleared lines in the last placement
        self.last_placement_cleared_lines = False
        # Track total garbage lines sent in this combo
        self.total_combo_garbage_sent = 0
        print("[COMBO DEBUG] Initialized combo system")

    def update(self, lines_cleared, current_time):
        """Update combo state based on lines cleared at current time"""
        debug_message = None

        # Add detailed logging at the start of the update
        print(
            f"[COMBO DEBUG] update called: lines_cleared={lines_cleared}, time={current_time:.2f}"
        )
        print(f"[COMBO DEBUG]  - Before: count={self.combo_count}")

        if lines_cleared > 0:
            # Lines cleared in this placement
            if self.last_placement_cleared_lines:
                # Previous placement also cleared lines, so increment combo
                self.combo_count += 1
                print(
                    f"[COMBO DEBUG]  - Previous placement cleared lines too. Incrementing combo to {self.combo_count}"
                )

                # Show combo message if 2 or more in combo count
                if (
                    self.combo_count >= 1
                ):  # In Jstris, even the first combo (consecutive clears) gets a message
                    debug_message = f"COMBO x{self.combo_count}!"
            elif lines_cleared > 1:
                debug_message = f"COMBO x{lines_cleared}!"
                self.combo_count = lines_cleared
                print(f"[COMBO DEBUG]  - New combo started with {lines_cleared} lines")
            else:
                # First line clear in a potential combo
                self.combo_count = (
                    0  # Reset to 0 as this is potentially the first part of a new combo
                )
                print(
                    f"[COMBO DEBUG]  - First line clear, setting combo to {self.combo_count}"
                )

            # Remember that this placement cleared lines
            self.last_placement_cleared_lines = True
        else:
            # No lines cleared, reset combo
            if self.combo_count > 0 or self.last_placement_cleared_lines:
                print(
                    f"[COMBO DEBUG]  - No lines cleared, resetting combo from {self.combo_count} to 0"
                )
            self.combo_count = 0
            self.last_placement_cleared_lines = False
            self.total_combo_garbage_sent = 0  # Reset garbage tracking for the combo

        # Set debug message if one was generated
        if debug_message:
            self.debug_message = debug_message
            self.debug_time = current_time

        # Add detailed logging at the end of the update
        print(
            f"[COMBO DEBUG]  - After: count={self.combo_count}, last_cleared={self.last_placement_cleared_lines}"
        )

        # Return current combo count (for display) and any debug message
        return {
            "combo_count": self.combo_count,
            "debug_message": debug_message,
            "is_combo_active": self.last_placement_cleared_lines,
        }

    def get_display(self):
        """Get the string to display for the current combo state"""
        if self.combo_count > 0:
            return f"{self.combo_count}"
        elif self.last_placement_cleared_lines:
            return "0"  # Show 0 when we've cleared lines but no combo yet
        else:
            return "-"  # Show dash when no active combo

    def get_garbage_count(self):
        """Get the number of garbage lines to send to opponents based on Jstris rules"""
        # In Jstris, combo garbage follows this pattern: 0, 1, 1, 2, 2, 3, 3, ...
        # This is different from "combo count - 1" formula
        if self.combo_count >= 1:
            garbage_count = (self.combo_count + 1) // 2  # Integer division
            print(
                f"[COMBO DEBUG] get_garbage_count: count={self.combo_count}, returning={garbage_count}"
            )
            return garbage_count
        return 0

    def check_debug_timeout(self, current_time):
        """Check if debug message should be cleared due to timeout"""
        if (
            self.debug_message
            and current_time - self.debug_time > self.debug_display_time
        ):
            self.debug_message = ""
            return True
        return False


# ---------------------- Main Game Loop ---------------------- #
def run_game(
    stdscr,
    get_next_piece,
    client_socket=None,
    net_queue=None,
    listen_port=None,
    peer_boards=None,
    peer_boards_lock=None,
    player_name=None,
    debug_mode=False,
):
    """Main game function that handles game loop and input/output"""
    if debug_mode:
        print("[RUN GAME] Entered.")

    try:
        # Ensure curses settings are appropriate for the game phase
        stdscr.nodelay(True)  # Ensure non-blocking input for game loop
        curses.curs_set(0)  # Ensure cursor is hidden
        stdscr.keypad(True)  # Ensure special keys are enabled

        # Initialize game components
        game_state = GameState(
            0, debug_mode=debug_mode
        )  # Seed is now managed externally, just need a placeholder
        if debug_mode:
            print("[RUN GAME] Initializing CursesRenderer...")
        renderer = CursesRenderer(
            stdscr, debug_mode=debug_mode
        )  # Pass the existing stdscr object and debug mode
        if debug_mode:
            print("[RUN GAME] Initializing InputHandler...")
        input_handler = InputHandler(
            stdscr, debug_mode=debug_mode
        )  # Pass the existing stdscr object and debug mode

        # Override the game's piece generator with the provided one
        if debug_mode:
            print("[RUN GAME] Setting initial pieces...")
        game_state.current_piece = get_next_piece()
        game_state.next_piece = get_next_piece()

        # Create the game controller and inject the get_next_piece function
        if debug_mode:
            print("[RUN GAME] Initializing GameController...")
        controller = GameController(
            game_state=game_state,
            renderer=renderer,
            input_handler=input_handler,
            client_socket=client_socket,
            net_queue=net_queue,
            listen_port=listen_port,
            peer_boards=peer_boards,
            peer_boards_lock=peer_boards_lock,
            player_name=player_name,
            debug_mode=debug_mode,
        )

        # Add the piece generator function to the controller
        controller.get_next_piece_func = get_next_piece

        # Main game loop
        while True:
            # Update game state
            result = controller.update()

            # Check for quit or game over
            if result == "quit" or result == "game_over":
                break

            # Render the game
            controller.render()

        if debug_mode:
            print("[RUN GAME] Exiting game loop.")

        # Return final game stats
        final_stats = controller.get_stats()
        if debug_mode:
            print(f"[RUN GAME] Returning final stats: {final_stats}")
        return final_stats

    except Exception as e:
        # Log any exceptions that occur within the game loop specifically
        print(f"[RUN GAME] CRITICAL ERROR: {e}")
        import traceback

        print(traceback.format_exc())
        # Re-raise the exception so the main wrapper can handle curses cleanup
        raise


if __name__ == "__main__":
    # This block is primarily for testing the game logic standalone,
    # not the full P2P experience which runs via peer.py
    print("Running tetris_game.py directly (standalone test mode).")

    # Need to use curses.wrapper if running standalone
    def standalone_game(stdscr):
        print("Initializing standalone game...")
        # Setup necessary components for standalone run
        init_colors()  # Need colors for standalone
        seed = random.randint(0, 1000000)
        get_next_piece_func = create_piece_generator(seed)
        # Run the game, passing the stdscr from the wrapper
        # Enable debug mode for standalone testing if desired
        final_stats = run_game(stdscr, get_next_piece_func, debug_mode=True)
        print("Standalone game finished.")
        print(f"Final Stats: {final_stats}")
        print("Press any key to exit.")
        stdscr.nodelay(False)  # Make getch blocking
        stdscr.getch()

    curses.wrapper(standalone_game)
    print("Standalone execution complete.")
