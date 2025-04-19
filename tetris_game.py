import curses
import time
import random
import copy

# Constants
BOARD_WIDTH = 10
BOARD_HEIGHT = 20
EMPTY_CELL = 0

# Tetromino shapes with corresponding color indices (1-7)
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
    0: curses.COLOR_BLACK,  # Background
    1: curses.COLOR_CYAN,  # I
    2: curses.COLOR_YELLOW,  # O
    3: curses.COLOR_MAGENTA,  # T
    4: curses.COLOR_GREEN,  # S
    5: curses.COLOR_RED,  # Z
    6: curses.COLOR_BLUE,  # J
    7: curses.COLOR_WHITE,  # L (using white instead of orange for better visibility)
    8: curses.COLOR_WHITE,  # Border
}

# Movement directions
LEFT = {"x": -1, "y": 0}
RIGHT = {"x": 1, "y": 0}
DOWN = {"x": 0, "y": 1}


class Piece:
    def __init__(self, tetromino_type=None):
        if tetromino_type is None:
            tetromino_type = random.choice(list(TETROMINOES.keys()))

        self.type = tetromino_type
        self.shape = copy.deepcopy(TETROMINOES[tetromino_type]["shape"])
        self.color = TETROMINOES[tetromino_type]["color"]

        # Position on board (top center)
        self.x = BOARD_WIDTH // 2 - len(self.shape[0]) // 2
        self.y = 0

        # Handle I piece special case (needs to start higher)
        if tetromino_type == "I":
            self.y = -1

    def rotate(self):
        """Rotate the piece 90 degrees clockwise."""
        # Create a new rotated shape
        rows, cols = len(self.shape), len(self.shape[0])
        rotated = [[0 for _ in range(rows)] for _ in range(cols)]

        for r in range(rows):
            for c in range(cols):
                rotated[c][rows - 1 - r] = self.shape[r][c]

        return rotated

    def get_positions(self):
        """Get the board positions occupied by the piece."""
        positions = []
        for y, row in enumerate(self.shape):
            for x, cell in enumerate(row):
                if cell:
                    positions.append({"x": self.x + x, "y": self.y + y})
        return positions


def init_colors():
    curses.start_color()
    for i, color in COLORS.items():
        # Use color pair i+1 (0 is reserved for default background)
        curses.init_pair(i + 1, color, curses.COLOR_BLACK)


def create_board():
    # Create an empty board (list of lists)
    return [[EMPTY_CELL for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]


def draw_board(stdscr, board, score, level):
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    # Calculate dimensions needed
    board_height = BOARD_HEIGHT + 2  # Board + borders
    board_width = BOARD_WIDTH * 2 + 2  # Each cell is 2 chars wide + borders

    # Check if terminal is big enough
    if h < board_height or w < board_width + 15:  # +15 for score and other text
        stdscr.clear()
        error_msg = "Terminal too small! Resize and restart."
        try:
            stdscr.addstr(h // 2, max(0, (w - len(error_msg)) // 2), error_msg)
            stdscr.refresh()
            stdscr.getch()  # Wait for key press
        except curses.error:
            pass  # Even this message might not fit
        return False

    # Calculate start position for the board (centered)
    start_y = max(0, (h - board_height) // 2)
    start_x = max(0, (w - board_width) // 2)

    # Draw border
    border_color = curses.color_pair(8 + 1)  # White border
    # Top border
    try:
        stdscr.addstr(start_y, start_x, "+" + "--" * BOARD_WIDTH + "+", border_color)
        # Side borders
        for y in range(BOARD_HEIGHT):
            stdscr.addstr(start_y + 1 + y, start_x, "|", border_color)
            stdscr.addstr(
                start_y + 1 + y, start_x + BOARD_WIDTH * 2 + 1, "|", border_color
            )
        # Bottom border
        stdscr.addstr(
            start_y + BOARD_HEIGHT + 1,
            start_x,
            "+" + "--" * BOARD_WIDTH + "+",
            border_color,
        )

        # Draw board content
        for y, row in enumerate(board):
            for x, cell in enumerate(row):
                if cell != EMPTY_CELL:
                    color_pair = curses.color_pair(cell + 1)
                    stdscr.addstr(
                        start_y + 1 + y, start_x + 1 + x * 2, "[]", color_pair
                    )
                else:
                    stdscr.addstr(
                        start_y + 1 + y, start_x + 1 + x * 2, "  "
                    )  # Empty space

        # Draw Score and Level
        stdscr.addstr(start_y + 2, start_x + board_width + 2, f"Score: {score}")
        stdscr.addstr(start_y + 4, start_x + board_width + 2, f"Level: {level}")

        # Draw controls
        controls_y = start_y + 7
        stdscr.addstr(controls_y, start_x + board_width + 2, "Controls:")
        stdscr.addstr(controls_y + 1, start_x + board_width + 2, "← → : Move")
        stdscr.addstr(controls_y + 2, start_x + board_width + 2, "↑ : Rotate")
        stdscr.addstr(controls_y + 3, start_x + board_width + 2, "↓ : Soft drop")
        stdscr.addstr(controls_y + 4, start_x + board_width + 2, "Space : Hard drop")
        stdscr.addstr(controls_y + 5, start_x + board_width + 2, "c : Hold piece")
        stdscr.addstr(controls_y + 6, start_x + board_width + 2, "q : Quit")

        stdscr.refresh()
        return True
    except curses.error:
        # If any error occurs, try with a simpler display
        try:
            stdscr.clear()
            stdscr.addstr(0, 0, "Terminal too small! Resize and restart.")
            stdscr.refresh()
        except curses.error:
            pass  # Give up if even this fails
        return False


def check_collision(board, piece, dx=0, dy=0, rotated_shape=None):
    """Check if piece would collide with board boundaries or other pieces."""
    # Use provided rotated shape or current shape
    shape = piece.shape if rotated_shape is None else rotated_shape

    for y, row in enumerate(shape):
        for x, cell in enumerate(row):
            if cell:
                # Check board boundaries
                new_x = piece.x + x + dx
                new_y = piece.y + y + dy

                # Out of bounds check
                if new_x < 0 or new_x >= BOARD_WIDTH or new_y >= BOARD_HEIGHT:
                    return True

                # Skip collision check for cells above board
                if new_y < 0:
                    continue

                # Check collision with other pieces on board
                if board[new_y][new_x] != EMPTY_CELL:
                    return True

    return False


def merge_piece(board, piece):
    """Merge piece into the board."""
    for y, row in enumerate(piece.shape):
        for x, cell in enumerate(row):
            if cell and piece.y + y >= 0:  # Only merge visible cells
                board[piece.y + y][piece.x + x] = piece.color


def clear_lines(board):
    """Clear completed lines and return number of lines cleared."""
    lines_cleared = 0
    y = BOARD_HEIGHT - 1
    while y >= 0:
        if EMPTY_CELL not in board[y]:  # Line is full
            lines_cleared += 1
            # Move all lines above down
            for move_y in range(y, 0, -1):
                board[move_y] = board[move_y - 1].copy()
            # Create new empty line at top
            board[0] = [EMPTY_CELL] * BOARD_WIDTH
        else:
            y -= 1

    return lines_cleared


def calculate_score(lines_cleared, level):
    """Calculate score based on lines cleared and level."""
    if lines_cleared == 0:
        return 0

    # Classic NES Tetris scoring system
    points_per_line = {1: 40, 2: 100, 3: 300, 4: 1200}
    return points_per_line.get(lines_cleared, 0) * level


def draw_piece(stdscr, piece, board, ghost=False):
    """Draw the current active piece on the board."""
    h, w = stdscr.getmaxyx()
    board_height = BOARD_HEIGHT + 2
    board_width = BOARD_WIDTH * 2 + 2

    # Calculate board position
    start_y = max(0, (h - board_height) // 2)
    start_x = max(0, (w - board_width) // 2)

    # Calculate ghost piece position (drop preview)
    ghost_y = piece.y
    if ghost:
        # Find where the piece would land if dropped
        drop_distance = 0
        while not check_collision(board, piece, 0, drop_distance + 1):
            drop_distance += 1
        ghost_y = piece.y + drop_distance

    # Draw piece
    for y, row in enumerate(piece.shape):
        for x, cell in enumerate(row):
            if cell:
                # Only draw if on screen
                if piece.y + y >= 0:
                    # Normal piece display
                    color_pair = curses.color_pair(piece.color + 1)
                    try:
                        stdscr.addstr(
                            start_y + 1 + piece.y + y,
                            start_x + 1 + (piece.x + x) * 2,
                            "[]",
                            color_pair,
                        )
                    except curses.error:
                        pass  # Ignore errors for off-screen drawing

                # Draw ghost piece (drop preview) if enabled
                if ghost and piece.y != ghost_y:
                    ghost_display_y = ghost_y + y
                    if ghost_display_y >= 0 and ghost_display_y < BOARD_HEIGHT:
                        try:
                            # Ghost piece should be visible but less intense
                            stdscr.addstr(
                                start_y + 1 + ghost_display_y,
                                start_x + 1 + (piece.x + x) * 2,
                                "[]",
                                curses.A_DIM,
                            )
                        except curses.error:
                            pass


def draw_next_and_held(stdscr, next_piece, held_piece, board):
    """Draw the next piece and held piece previews."""
    h, w = stdscr.getmaxyx()
    board_height = BOARD_HEIGHT + 2
    board_width = BOARD_WIDTH * 2 + 2

    # Calculate board position
    start_y = max(0, (h - board_height) // 2)
    start_x = max(0, (w - board_width) // 2)

    # Area for next piece preview
    preview_y = start_y + 10
    preview_x = start_x + board_width + 2

    try:
        # Next piece preview
        stdscr.addstr(preview_y, preview_x, "Next:")

        # Draw next piece
        next_preview_y = preview_y + 1
        next_preview_x = preview_x + 4

        for y, row in enumerate(next_piece.shape):
            for x, cell in enumerate(row):
                if cell:
                    color_pair = curses.color_pair(next_piece.color + 1)
                    stdscr.addstr(
                        next_preview_y + y, next_preview_x + x * 2, "[]", color_pair
                    )

        # Hold piece preview
        stdscr.addstr(preview_y + 5, preview_x, "Hold:")

        # Draw held piece if exists
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
        pass  # Ignore errors for drawing off-screen


def main(stdscr):
    # Curses setup
    curses.curs_set(0)  # Hide cursor
    stdscr.nodelay(True)  # Non-blocking input
    stdscr.timeout(50)  # Refresh delay - reduced for responsive controls
    init_colors()

    board = create_board()
    score = 0
    level = 1
    lines_cleared_total = 0

    # Game variables
    current_piece = Piece()
    next_piece = Piece()
    held_piece = None
    can_hold = True

    # Timing variables
    last_fall_time = time.time()
    fall_speed = 1.0  # Seconds per step
    soft_drop = False

    # Lock delay variables
    lock_delay = 0.5  # Time in seconds before piece locks in place
    lock_timer = None  # Will be set when piece touches ground
    landing_y = None  # Position of the piece when it first touches ground

    # Input state tracking
    key_left_pressed = False
    key_right_pressed = False
    key_down_pressed = False
    last_key_time = time.time()  # Track time of last key input
    last_move_time = time.time()  # Track last movement time
    move_delay = 0.15  # Delay between movements (for key repeat)

    # Key press flags - to detect the first press of a key
    key_left_first_press = False
    key_right_first_press = False
    key_up_first_press = False

    # Initialize previous key to None
    previous_key = None

    game_over = False

    while not game_over:
        # Get user input
        current_time = time.time()
        key = stdscr.getch()

        # Check if piece is touching ground
        touching_ground = check_collision(board, current_piece, 0, 1)

        # Reset first press flags if different key is pressed
        if key != -1 and key != previous_key:
            # Only reset flags for the specific key type
            if key == curses.KEY_LEFT or key == curses.KEY_RIGHT:
                key_left_first_press = False
                key_right_first_press = False
            elif key == curses.KEY_UP:
                key_up_first_press = False

            previous_key = key

        # Update key press state
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

        # Handle key release detection (terminal limitation)
        # If no key input for a short time, assume keys are released
        if (
            current_time - last_key_time > 0.1
        ):  # Increased timeout to detect key release
            if key_left_pressed:
                key_left_pressed = False
                key_left_first_press = False
            if key_right_pressed:
                key_right_pressed = False
                key_right_first_press = False
            if key_down_pressed:
                key_down_pressed = False

        # Update soft drop state
        soft_drop = key_down_pressed

        # Handle rotation (immediately, before movement)
        if key_up_first_press:
            rotated = current_piece.rotate()
            rotation_successful = False

            if not check_collision(board, current_piece, 0, 0, rotated):
                current_piece.shape = rotated
                rotation_successful = True
            else:
                # Try wall kicks (move piece when rotation causes collision)
                for kick in [LEFT, RIGHT]:
                    if not check_collision(
                        board, current_piece, kick["x"], kick["y"], rotated
                    ):
                        current_piece.x += kick["x"]
                        current_piece.shape = rotated
                        rotation_successful = True
                        break

            # Reset lock timer if rotated while landing
            if rotation_successful and touching_ground:
                lock_timer = current_time
                landing_y = (
                    current_piece.y
                )  # Update landing y to prevent immediate lock

            key_up_first_press = False

        # Handle initial key press - move only once on initial press
        if key_left_first_press:
            if not check_collision(board, current_piece, LEFT["x"], LEFT["y"]):
                current_piece.x += LEFT["x"]
                if touching_ground:
                    lock_timer = current_time
                    landing_y = current_piece.y  # Update landing y
            key_left_first_press = False
            last_move_time = current_time

        if key_right_first_press:
            if not check_collision(board, current_piece, RIGHT["x"], RIGHT["y"]):
                current_piece.x += RIGHT["x"]
                if touching_ground:
                    lock_timer = current_time
                    landing_y = current_piece.y  # Update landing y
            key_right_first_press = False
            last_move_time = current_time

        # Handle repeating movement (left/right) with delay to prevent double moves
        if current_time - last_move_time > move_delay:
            if (
                key_left_pressed and not key_left_first_press
            ):  # Only for repeating moves
                if not check_collision(board, current_piece, LEFT["x"], LEFT["y"]):
                    current_piece.x += LEFT["x"]
                    # Reset lock timer if moved while landing
                    if touching_ground:
                        lock_timer = current_time
                        landing_y = current_piece.y  # Update landing y
                    last_move_time = current_time
            elif (
                key_right_pressed and not key_right_first_press
            ):  # Only for repeating moves
                if not check_collision(board, current_piece, RIGHT["x"], RIGHT["y"]):
                    current_piece.x += RIGHT["x"]
                    # Reset lock timer if moved while landing
                    if touching_ground:
                        lock_timer = current_time
                        landing_y = current_piece.y  # Update landing y
                    last_move_time = current_time

        # Handle lock delay
        if touching_ground:
            # If just landed, start lock timer
            if lock_timer is None:
                lock_timer = current_time
                landing_y = current_piece.y
            # If moved horizontally or rotated after landing, reset lock timer
            elif current_piece.y != landing_y:
                lock_timer = current_time
                landing_y = current_piece.y

            # If lock delay expired, lock the piece
            if current_time - lock_timer >= lock_delay:
                # Piece landed, merge it
                merge_piece(board, current_piece)
                lines = clear_lines(board)
                score += calculate_score(lines, level)
                lines_cleared_total += lines

                # Level up every 10 lines
                level = lines_cleared_total // 10 + 1

                # Reset for next piece
                current_piece = next_piece
                next_piece = Piece()
                can_hold = True
                soft_drop = False
                lock_timer = None
                landing_y = None
                key_left_pressed = False
                key_right_pressed = False
                key_down_pressed = False

                # Check if game over (new piece collides immediately)
                if check_collision(board, current_piece):
                    game_over = True

                # Reset fall timer
                last_fall_time = current_time
        else:
            # Not touching ground, clear lock timer
            lock_timer = None
            landing_y = None

        # Handle input - instant actions (single press)
        if key != -1:
            if key == ord("q"):  # Quit game
                break

            elif key == ord(" "):  # Hard drop
                # Move piece down until collision
                while not check_collision(board, current_piece, 0, 1):
                    current_piece.y += 1
                    score += 2  # 2 points per cell dropped

                # Merge immediately without lock delay
                merge_piece(board, current_piece)
                lines = clear_lines(board)
                score += calculate_score(lines, level)
                lines_cleared_total += lines

                # Level up every 10 lines
                level = lines_cleared_total // 10 + 1

                # Reset for next piece
                current_piece = next_piece
                next_piece = Piece()
                can_hold = True
                soft_drop = False
                lock_timer = None
                landing_y = None
                key_left_pressed = False
                key_right_pressed = False
                key_down_pressed = False
                last_fall_time = current_time

                # Check if game over (new piece collides immediately)
                if check_collision(board, current_piece):
                    game_over = True

            elif key == ord("c"):  # Hold piece
                if can_hold:
                    if held_piece is None:
                        held_piece = Piece(current_piece.type)
                        current_piece = next_piece
                        next_piece = Piece()
                    else:
                        current_piece, held_piece = Piece(held_piece.type), Piece(
                            current_piece.type
                        )
                    can_hold = False
                    lock_timer = None
                    landing_y = None
                    last_fall_time = current_time

        # Handle automatic falling (only if not already waiting to lock)
        if not touching_ground:
            fall_delay = fall_speed / level
            if soft_drop:
                fall_delay *= (
                    0.1  # Fall 10x faster with soft drop (was 0.2 - 5x faster)
                )

            if current_time - last_fall_time > fall_delay:
                # Move piece down
                current_piece.y += 1
                if soft_drop:
                    score += 1  # 1 point per cell dropped (soft drop)
                last_fall_time = current_time

        # --- Drawing ---
        # First draw the static board
        if not draw_board(stdscr, board, score, level):
            # Terminal too small, wait for user to resize
            time.sleep(1)  # Throttle refresh attempts
            continue

        # Then draw the active piece with ghost (drop preview)
        draw_piece(stdscr, current_piece, board, ghost=True)

        # Draw next and held piece previews
        draw_next_and_held(stdscr, next_piece, held_piece, board)

    return score  # Return the score for game over display


if __name__ == "__main__":
    final_score = curses.wrapper(main)
    print("Game Over!")
    print(f"Final Score: {final_score}")
