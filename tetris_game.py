import curses
import time
import random
import copy
import locale
import queue

from proto import tetris_pb2

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
    get_next_piece,
    client_socket=None,
    net_queue=None,
    listen_port=None,
    peer_boards=None,
    peer_boards_lock=None,
    player_name=None,
):
    stdscr = curses.initscr()
    stdscr.keypad(True)
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(10)
    init_colors()

    board = create_board()
    score = 0
    level = 1
    lines_cleared_total = 0

    # Attack tracking stats
    attacks_sent = 0
    attacks_received = 0
    start_time = time.time()
    survival_time = 0

    combo_system = ComboSystem()

    current_piece = get_next_piece()
    next_piece = get_next_piece()
    held_piece = None
    can_hold = True

    garbage_sent = False
    my_addr = None
    if listen_port:
        my_addr = f"[::]:{listen_port}"

    last_fall_time = time.time()
    game_start_time = time.time()  # Track when the game started
    fall_speed = 1.0
    initial_fall_speed = fall_speed  # Store initial fall speed for reference
    soft_drop = False

    # Parameters for gradual difficulty increase
    speed_increase_interval = 30.0  # Increase speed every 30 seconds
    speed_increase_rate = 0.05  # Reduce fall_speed by 5% every interval
    last_speed_increase_time = game_start_time

    lock_delay = 0.5
    lock_timer = None
    landing_y = None

    key_left_pressed = False
    key_right_pressed = False
    key_down_pressed = False
    last_key_time = time.time()
    last_move_time = time.time()
    move_delay = 0.1

    key_left_first_press = False
    key_right_first_press = False
    key_up_first_press = False

    previous_key = None
    game_over = False

    # For board state updates
    last_board_update_time = time.time()
    board_update_interval = 0.5

    try:
        while not game_over:
            current_time = time.time()

            # Check if it's time to increase the game speed
            if current_time - last_speed_increase_time >= speed_increase_interval:
                # Increase speed by reducing fall_speed (faster pieces)
                fall_speed = max(
                    fall_speed * (1 - speed_increase_rate), 0.1
                )  # Don't allow it to get too fast

                # Optional: Increase level every few speed increases
                if (current_time - game_start_time) / speed_increase_interval % 3 == 0:
                    level = min(level + 1, 10)  # Cap at level 10

                last_speed_increase_time = current_time

            # Clear combo debug message after the display time has elapsed
            combo_system.check_debug_timeout(current_time)

            if net_queue is not None:
                try:
                    while True:
                        net_msg = net_queue.get_nowait()
                        if isinstance(net_msg, str) and net_msg.startswith("GARBAGE:"):
                            try:
                                garbage_amount = int(net_msg.split(":", 1)[1].strip())
                                print(
                                    f"[GARBAGE RECEIVE DEBUG] Received string GARBAGE message: {garbage_amount} lines"
                                )
                                add_garbage_lines(board, garbage_amount)
                                attacks_received += garbage_amount

                                # Add debug message for opponent combo
                                combo_system.debug_message = (
                                    f"Opponent COMBO x{garbage_amount}!"
                                )
                                combo_system.debug_time = current_time

                                # Immediately redraw the board to show the garbage.
                                draw_board(
                                    stdscr,
                                    board,
                                    score,
                                    level,
                                    combo_system.get_display(),
                                    player_name,
                                )
                                draw_piece(stdscr, current_piece, board, ghost=True)
                                draw_next_and_held(
                                    stdscr, next_piece, held_piece, board
                                )
                            except ValueError:
                                pass
                        elif (
                            hasattr(net_msg, "type")
                            and net_msg.type == tetris_pb2.GARBAGE
                        ):
                            try:
                                garbage_amount = net_msg.garbage
                                print(
                                    f"[GARBAGE RECEIVE DEBUG] Received protobuf GARBAGE message: {garbage_amount} lines from {net_msg.sender}"
                                )
                                add_garbage_lines(board, garbage_amount)
                                attacks_received += garbage_amount

                                # Try to extract opponent name from extra if available
                                opponent_name = "Opponent"
                                if hasattr(net_msg, "extra") and net_msg.extra:
                                    try:
                                        opponent_name = net_msg.extra.decode().strip()
                                    except Exception:
                                        pass
                                elif hasattr(net_msg, "sender") and net_msg.sender:
                                    opponent_name = net_msg.sender

                                # Add debug message for opponent combo
                                combo_system.debug_message = (
                                    f"{opponent_name} COMBO x{garbage_amount}!"
                                )
                                combo_system.debug_time = current_time

                                draw_board(
                                    stdscr,
                                    board,
                                    score,
                                    level,
                                    combo_system.get_display(),
                                    player_name,
                                )
                                draw_piece(stdscr, current_piece, board, ghost=True)
                                draw_next_and_held(
                                    stdscr, next_piece, held_piece, board
                                )
                            except Exception as e:
                                print(
                                    f"[GARBAGE RECEIVE DEBUG] Error processing protobuf GARBAGE: {e}"
                                )
                                pass
                except queue.Empty:
                    pass

            current_time = time.time()
            key = stdscr.getch()
            touching_ground = check_collision(board, current_piece, 0, 1)

            if key != -1 and key != previous_key:
                if key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                    key_left_first_press = False
                    key_right_first_press = False
                elif key == curses.KEY_UP:
                    key_up_first_press = False
                previous_key = key

            if key != -1:
                if key == curses.KEY_LEFT:
                    if not key_left_pressed:
                        key_left_first_press = True
                    key_left_pressed = True
                    last_key_time = current_time
                elif key == curses.KEY_RIGHT:
                    if not key_right_pressed:
                        key_right_first_press = True
                    key_right_pressed = True
                    last_key_time = current_time
                elif key == curses.KEY_DOWN:
                    key_down_pressed = True
                    last_key_time = current_time
                elif key == curses.KEY_UP:
                    key_up_first_press = True
                    last_key_time = current_time

            if current_time - last_key_time > 0.1:
                if key_left_pressed:
                    key_left_pressed = False
                    key_left_first_press = False
                if key_right_pressed:
                    key_right_pressed = False
                    key_right_first_press = False
                if key_down_pressed:
                    key_down_pressed = False

            soft_drop = key_down_pressed

            if key_up_first_press:
                old_right = current_piece.x + len(current_piece.shape[0]) - 1
                rotated = current_piece.rotate()
                rotation_successful = False
                if old_right == BOARD_WIDTH - 1:
                    new_width = len(rotated[0])
                    adjusted_x = BOARD_WIDTH - new_width
                    old_x = current_piece.x
                    current_piece.x = adjusted_x
                    if not check_collision(board, current_piece, 0, 0, rotated):
                        current_piece.shape = rotated
                        rotation_successful = True
                    else:
                        current_piece.x = old_x
                if not rotation_successful:
                    if not check_collision(board, current_piece, 0, 0, rotated):
                        current_piece.shape = rotated
                        rotation_successful = True
                    else:
                        for kick in [LEFT, RIGHT]:
                            if not check_collision(
                                board, current_piece, kick["x"], kick["y"], rotated
                            ):
                                current_piece.x += kick["x"]
                                current_piece.shape = rotated
                                rotation_successful = True
                                break
                if rotation_successful and touching_ground:
                    lock_timer = current_time
                    landing_y = current_piece.y
                key_up_first_press = False

            if key_left_first_press:
                if not check_collision(board, current_piece, LEFT["x"], LEFT["y"]):
                    current_piece.x += LEFT["x"]
                    if touching_ground:
                        lock_timer = current_time
                        landing_y = current_piece.y
                key_left_first_press = False
                last_move_time = current_time

            if key_right_first_press:
                if not check_collision(board, current_piece, RIGHT["x"], RIGHT["y"]):
                    current_piece.x += RIGHT["x"]
                    if touching_ground:
                        lock_timer = current_time
                        landing_y = current_piece.y
                key_right_first_press = False
                last_move_time = current_time

            if current_time - last_move_time > move_delay:
                if key_left_pressed and not key_left_first_press:
                    if not check_collision(board, current_piece, LEFT["x"], LEFT["y"]):
                        current_piece.x += LEFT["x"]
                        if touching_ground:
                            lock_timer = current_time
                            landing_y = current_piece.y
                        last_move_time = current_time
                elif key_right_pressed and not key_right_first_press:
                    if not check_collision(
                        board, current_piece, RIGHT["x"], RIGHT["y"]
                    ):
                        current_piece.x += RIGHT["x"]
                        if touching_ground:
                            lock_timer = current_time
                            landing_y = current_piece.y
                        last_move_time = current_time

            if touching_ground:
                if lock_timer is None:
                    lock_timer = current_time
                    landing_y = current_piece.y
                elif current_piece.y != landing_y:
                    lock_timer = current_time
                    landing_y = current_piece.y

                if current_time - lock_timer >= lock_delay:
                    # Merge the piece to the board
                    merge_piece(board, current_piece)
                    lines = clear_lines(board)

                    # Update combo system with actual cleared lines
                    combo_result = combo_system.update(lines, current_time)

                    # Set the debug message for combo if there is one
                    if combo_result["debug_message"]:
                        player_display_name = player_name if player_name else "You"
                        combo_system.debug_message = (
                            f"{player_display_name} {combo_result['debug_message']}"
                        )

                    # Calculate score based on lines cleared
                    score += calculate_score(lines, level)
                    lines_cleared_total += lines

                    # Send garbage if we have a combo running and lines were cleared
                    if lines > 0:
                        # Send garbage to opponents if combo is active
                        garbage_count = combo_system.get_garbage_count()
                        if client_socket and garbage_count > 0:
                            try:
                                with peer_boards_lock:
                                    if peer_boards:
                                        # Find peer with lowest score (worst performer)
                                        worst_peer_id, worst_peer_data = min(
                                            peer_boards.items(),
                                            key=lambda item: item[1]["score"],
                                        )
                                        print(
                                            f"[STRATEGY] Targeting worst player {worst_peer_id} "
                                            f"(score: {worst_peer_data['score']})"
                                        )

                                        client_socket.send(
                                            worst_peer_id,
                                            f"GARBAGE:{garbage_count}\n".encode(),
                                        )
                                        attacks_sent += garbage_count
                            except Exception as e:
                                print(f"[ERROR] Failed to target worst player: {e}")

                    # Reset for next piece
                    current_piece = next_piece
                    next_piece = get_next_piece()
                    can_hold = True
                    soft_drop = False
                    lock_timer = None
                    landing_y = None
                    key_left_pressed = False
                    key_right_pressed = False
                    key_down_pressed = False
                    last_fall_time = current_time

                    if is_game_over(board):
                        merge_piece(board, current_piece)
                        # Calculate final survival time
                        survival_time = time.time() - start_time

                        # Display attacks stats instead of score
                        draw_board(
                            stdscr,
                            board,
                            score,
                            level,
                            combo_system.get_display(),
                            player_name,
                        )
                        h, w = stdscr.getmaxyx()

                        # Show attack stats
                        attacks_msg = f"Attacks - Sent: {attacks_sent}, Received: {attacks_received}"
                        survival_msg = f"Survival Time: {int(survival_time)} seconds"
                        game_over_msg = "GAME OVER! Press any key..."

                        try:
                            stdscr.addstr(
                                h // 2 - 2,
                                max(0, (w - len(attacks_msg)) // 2),
                                attacks_msg,
                                curses.A_BOLD,
                            )
                            stdscr.addstr(
                                h // 2 - 1,
                                max(0, (w - len(survival_msg)) // 2),
                                survival_msg,
                                curses.A_BOLD,
                            )
                            stdscr.addstr(
                                h // 2,
                                max(0, (w - len(game_over_msg)) // 2),
                                game_over_msg,
                                curses.A_BOLD,
                            )
                        except curses.error:
                            pass

                        stdscr.refresh()
                        stdscr.nodelay(False)
                        stdscr.getch()
                        game_over = True
                        if client_socket:
                            try:
                                # Send LOSE with survival time instead of score
                                client_socket.sendall(
                                    f"LOSE:{survival_time:.2f}:{attacks_sent}:{attacks_received}\n".encode()
                                )
                            except Exception as e:
                                print(f"Error sending LOSE message: {e}")
                        break
            else:
                lock_timer = None
                landing_y = None
                garbage_sent = False

            if key != -1:
                if key == ord("q"):
                    break
                elif key == ord(" "):
                    # Hard drop logic
                    while not check_collision(board, current_piece, 0, 1):
                        current_piece.y += 1
                        score += 2

                    # Merge the piece to the board immediately after hard drop
                    merge_piece(board, current_piece)
                    lines = clear_lines(board)

                    # Update combo system with actual cleared lines
                    combo_result = combo_system.update(lines, current_time)

                    # Set the debug message for combo if there is one
                    if combo_result["debug_message"]:
                        player_display_name = player_name if player_name else "You"
                        combo_system.debug_message = (
                            f"{player_display_name} {combo_result['debug_message']}"
                        )

                    # Calculate score based on lines cleared
                    score += calculate_score(lines, level)
                    lines_cleared_total += lines

                    # Send garbage if we have a combo running and lines were cleared
                    if lines > 0:
                        # Send garbage to opponents if combo is active
                        garbage_count = combo_system.get_garbage_count()
                        if client_socket and garbage_count > 0:
                            try:
                                with peer_boards_lock:
                                    if peer_boards:
                                        # Find peer with lowest score (worst performer)
                                        worst_peer_id, worst_peer_data = min(
                                            peer_boards.items(),
                                            key=lambda item: item[1]["score"],
                                        )
                                        print(
                                            f"[STRATEGY] Targeting worst player {worst_peer_id} "
                                            f"(score: {worst_peer_data['score']})"
                                        )

                                        client_socket.send(
                                            worst_peer_id,
                                            f"GARBAGE:{garbage_count}\n".encode(),
                                        )
                                        attacks_sent += garbage_count
                            except Exception as e:
                                print(f"[ERROR] Failed to target worst player: {e}")

                    # Reset for next piece
                    current_piece = next_piece
                    next_piece = get_next_piece()
                    can_hold = True
                    soft_drop = False
                    lock_timer = None
                    landing_y = None
                    key_left_pressed = False
                    key_right_pressed = False
                    key_down_pressed = False
                    last_fall_time = current_time

                    if check_collision(board, current_piece):
                        merge_piece(board, current_piece)
                        # Calculate final survival time
                        survival_time = time.time() - start_time

                        # Display attacks stats instead of score
                        draw_board(
                            stdscr,
                            board,
                            score,
                            level,
                            combo_system.get_display(),
                            player_name,
                        )
                        h, w = stdscr.getmaxyx()

                        # Show attack stats
                        attacks_msg = f"Attacks - Sent: {attacks_sent}, Received: {attacks_received}"
                        survival_msg = f"Survival Time: {int(survival_time)} seconds"
                        game_over_msg = "GAME OVER! Press any key..."

                        try:
                            stdscr.addstr(
                                h // 2 - 2,
                                max(0, (w - len(attacks_msg)) // 2),
                                attacks_msg,
                                curses.A_BOLD,
                            )
                            stdscr.addstr(
                                h // 2 - 1,
                                max(0, (w - len(survival_msg)) // 2),
                                survival_msg,
                                curses.A_BOLD,
                            )
                            stdscr.addstr(
                                h // 2,
                                max(0, (w - len(game_over_msg)) // 2),
                                game_over_msg,
                                curses.A_BOLD,
                            )
                        except curses.error:
                            pass

                        stdscr.refresh()
                        stdscr.nodelay(False)
                        stdscr.getch()
                        game_over = True
                        if client_socket:
                            try:
                                # Send LOSE with survival time instead of score
                                client_socket.sendall(
                                    f"LOSE:{survival_time:.2f}:{attacks_sent}:{attacks_received}\n".encode()
                                )
                            except Exception as e:
                                print(f"Error sending LOSE message: {e}")
                        break
                elif key == ord("c"):
                    if can_hold:
                        if held_piece is None:
                            held_piece = Piece(current_piece.type)
                            current_piece = next_piece
                            next_piece = get_next_piece()
                        else:
                            current_piece, held_piece = Piece(held_piece.type), Piece(
                                current_piece.type
                            )
                        can_hold = False
                        lock_timer = None
                        landing_y = None
                        last_fall_time = current_time

            if not touching_ground:
                # Use the updated fall_speed
                fall_delay = fall_speed / level
                if soft_drop:
                    fall_delay *= 0.1
                if current_time - last_fall_time > fall_delay:
                    current_piece.y += 1
                    if soft_drop:
                        score += 1
                    last_fall_time = current_time

            combo_display = combo_system.get_display()
            if not draw_board(stdscr, board, score, level, combo_display, player_name):
                time.sleep(1)
                continue

            draw_piece(stdscr, current_piece, board, ghost=True)
            draw_next_and_held(stdscr, next_piece, held_piece, board)

            # Draw other players' boards if available
            if peer_boards is not None and peer_boards_lock is not None:
                draw_other_players_boards(stdscr, peer_boards, board, peer_boards_lock)

            # Draw combo debug message if it exists
            if combo_system.debug_message:
                try:
                    h, w = stdscr.getmaxyx()
                    board_height = BOARD_HEIGHT + 2
                    board_width = BOARD_WIDTH * 2 + 2
                    start_y = max(0, (h - board_height) // 2)

                    # Display at the top of the screen in a highlighted style
                    debug_y = max(0, start_y - 4)
                    debug_x = max(0, (w - len(combo_system.debug_message)) // 2)

                    # Add a visual highlight to make it stand out
                    stdscr.addstr(
                        debug_y,
                        debug_x,
                        combo_system.debug_message,
                        curses.A_BOLD | curses.A_REVERSE,
                    )
                except curses.error:
                    pass  # Handle potential out-of-bounds errors

            # Send board state updates periodically
            if (
                client_socket is not None
                and current_time - last_board_update_time > board_update_interval
            ):
                # Flatten the board to a string for sending
                flattened_board = ",".join(str(cell) for row in board for cell in row)

                # Add active piece information
                if current_piece:
                    # Determine rotation state (0-3)
                    # This is simplified - you would need to track rotation properly in your game
                    rotation_state = 0

                    # For the example, we'll use the letter part of the type (e.g., "I" from "I")
                    piece_type = current_piece.type

                    piece_info = f"{piece_type},{current_piece.x},{current_piece.y},{rotation_state},{current_piece.color}"
                else:
                    piece_info = "NONE"

                board_state_msg = (
                    f"BOARD_STATE:{score}:{flattened_board}:{piece_info}".encode()
                )
                client_socket.sendall(board_state_msg)
                last_board_update_time = current_time

        # Return attack stats and survival time as a tuple instead of just score
        return {
            "survival_time": survival_time,
            "attacks_sent": attacks_sent,
            "attacks_received": attacks_received,
        }
    finally:
        curses.endwin()


if __name__ == "__main__":
    seed = random.randint(0, 1000000)
    get_next_piece = create_piece_generator(seed)
    final_stats = run_game(get_next_piece)
    print("Game Over!")
    print(f"Final Stats: {final_stats}")
