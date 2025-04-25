import curses
import time
import random
import copy
import locale
import queue

from proto import tetris_pb2
locale.setlocale(locale.LC_ALL, '')

# ------------------ Constants and Tetrimino Definitions ------------------ #
BOARD_WIDTH = 10
BOARD_HEIGHT = 20
EMPTY_CELL = 0

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
    8: curses.COLOR_WHITE,
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
    for i, color in COLORS.items():
        curses.init_pair(i + 1, color, curses.COLOR_BLACK)

def create_board():
    return [[EMPTY_CELL for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]

def draw_board(stdscr, board, score, level, combo_display):
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
        stdscr.addstr(start_y, start_x, "+" + "--" * BOARD_WIDTH + "+", border_color)
        for y in range(BOARD_HEIGHT):
            stdscr.addstr(start_y + 1 + y, start_x, "|", border_color)
            stdscr.addstr(start_y + 1 + y, start_x + BOARD_WIDTH * 2 + 1, "|", border_color)
        stdscr.addstr(start_y + BOARD_HEIGHT + 1, start_x, "+" + "--" * BOARD_WIDTH + "+", border_color)

        for y, row in enumerate(board):
            for x, cell in enumerate(row):
                if cell != EMPTY_CELL:
                    color_pair = curses.color_pair(cell + 1)
                    stdscr.addstr(start_y + 1 + y, start_x + 1 + x * 2, "[]", color_pair)
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
                        stdscr.addstr(start_y + 1 + piece.y + y, start_x + 1 + (piece.x + x) * 2, "[]", color_pair)
                    except curses.error:
                        pass
                if ghost and piece.y != ghost_y:
                    ghost_display_y = ghost_y + y
                    if 0 <= ghost_display_y < BOARD_HEIGHT:
                        try:
                            stdscr.addstr(start_y + 1 + ghost_display_y, start_x + 1 + (piece.x + x) * 2, "[]", curses.A_DIM)
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
                    stdscr.addstr(next_preview_y + y, next_preview_x + x * 2, "[]", color_pair)
        stdscr.addstr(preview_y + 5, preview_x, "Hold:")
        if held_piece:
            held_preview_y = preview_y + 6
            held_preview_x = preview_x + 4
            for y, row in enumerate(held_piece.shape):
                for x, cell in enumerate(row):
                    if cell:
                        color_pair = curses.color_pair(held_piece.color + 1)
                        stdscr.addstr(held_preview_y + y, held_preview_x + x * 2, "[]", color_pair)
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
    """
    for _ in range(count):
        gap = random.randint(0, BOARD_WIDTH - 1)
        garbage_line = [random.randint(1, 7) for _ in range(BOARD_WIDTH)]
        garbage_line[gap] = EMPTY_CELL
        board.pop(0)
        board.append(garbage_line)

# ---------------------- Main Game Loop ---------------------- #
def run_game(get_next_piece, client_socket=None, net_queue=None, listen_port=None):
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

    prev_cleared = False
    combo_count = 0

    current_piece = get_next_piece()
    next_piece = get_next_piece()
    held_piece = None
    can_hold = True

    garbage_sent = False
    my_addr = None
    if listen_port:
        my_addr = f"[::]:{listen_port}"

    last_fall_time = time.time()
    fall_speed = 1.0
    soft_drop = False

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

    try:
        while not game_over:
            if net_queue is not None:
                try:
                    while True:
                        net_msg = net_queue.get_nowait()
                        if isinstance(net_msg, str) and net_msg.startswith("GARBAGE:"):
                            try:
                                garbage_amount = int(net_msg.split(":", 1)[1].strip())
                                add_garbage_lines(board, garbage_amount)
                                # Immediately redraw the board to show the garbage.
                                draw_board(stdscr, board, score, level, f"{combo_count}" if prev_cleared else "-")
                                draw_piece(stdscr, current_piece, board, ghost=True)
                                draw_next_and_held(stdscr, next_piece, held_piece, board)
                            except ValueError:
                                pass
                        # Handle gRPC messages (TetrisMessage objects).
                        elif hasattr(net_msg, "type") and net_msg.type == tetris_pb2.GARBAGE:
                            sender = getattr(net_msg, "sender", None)
                            
                            if sender != my_addr and not (sender and "localhost" in sender and f":{listen_port}" in sender):
                                garbage_amount = net_msg.garbage
                                add_garbage_lines(board, garbage_amount)
                                draw_board(stdscr, board, score, level, f"{combo_count}" if prev_cleared else "-")
                                draw_piece(stdscr, current_piece, board, ghost=True)
                                draw_next_and_held(stdscr, next_piece, held_piece, board)
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
                            if not check_collision(board, current_piece, kick["x"], kick["y"], rotated):
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
                    if not check_collision(board, current_piece, RIGHT["x"], RIGHT["y"]):
                        current_piece.x += RIGHT["x"]
                        if touching_ground:
                            lock_timer = current_time
                            landing_y = current_piece.y
                        last_move_time = current_time

            if touching_ground:
                if not garbage_sent:
                    temp_board = [row.copy() for row in board]
                    merge_piece(temp_board, current_piece)
                    simulated_lines = clear_lines(temp_board)
                    if simulated_lines > 0:
                        if prev_cleared:
                            combo_count += 1
                        else:
                            combo_count = 0
                        prev_cleared = True
                        if client_socket and combo_count > 0:
                            try:
                                client_socket.sendall(f"GARBAGE:{combo_count}\n".encode())
                            except Exception:
                                pass
                    else:
                        prev_cleared = False
                    garbage_sent = True

                if lock_timer is None:
                    lock_timer = current_time
                    landing_y = current_piece.y
                elif current_piece.y != landing_y:
                    lock_timer = current_time
                    landing_y = current_piece.y

                if current_time - lock_timer >= lock_delay:
                    merge_piece(board, current_piece)
                    lines = clear_lines(board)
                    score += calculate_score(lines, level)
                    lines_cleared_total += lines
                    garbage_sent = False
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
                        draw_board(stdscr, board, score, level, f"{combo_count}" if prev_cleared else "-")
                        h, w = stdscr.getmaxyx()
                        msg = "GAME OVER! Press any key..."
                        stdscr.addstr(h//2, max(0, (w - len(msg)) // 2), msg, curses.A_BOLD)
                        stdscr.refresh()
                        stdscr.nodelay(False)
                        stdscr.getch()
                        game_over = True
                        if client_socket:
                            try:
                                client_socket.sendall(f"LOSE:{score}\n".encode())
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
                    while not check_collision(board, current_piece, 0, 1):
                        current_piece.y += 1
                        score += 2
                    merge_piece(board, current_piece)
                    lines = clear_lines(board)
                    if lines > 0:
                        if prev_cleared:
                            combo_count += 1
                        else:
                            combo_count = 0
                        prev_cleared = True
                        if client_socket and combo_count > 0:
                            try:
                                client_socket.sendall(f"GARBAGE:{combo_count}\n".encode())
                            except Exception:
                                pass
                    else:
                        prev_cleared = False
                    score += calculate_score(lines, level)
                    lines_cleared_total += lines
                    garbage_sent = False
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
                        draw_board(stdscr, board, score, level, f"{combo_count}" if prev_cleared else "-")
                        h, w = stdscr.getmaxyx()
                        msg = "GAME OVER! Press any key..."
                        stdscr.addstr(h//2, max(0, (w - len(msg)) // 2), msg, curses.A_BOLD)
                        stdscr.refresh()
                        stdscr.nodelay(False)
                        stdscr.getch()
                        game_over = True
                        break
                elif key == ord("c"):
                    if can_hold:
                        if held_piece is None:
                            held_piece = Piece(current_piece.type)
                            current_piece = next_piece
                            next_piece = get_next_piece()
                        else:
                            current_piece, held_piece = Piece(held_piece.type), Piece(current_piece.type)
                        can_hold = False
                        lock_timer = None
                        landing_y = None
                        last_fall_time = current_time

            if not touching_ground:
                fall_delay = fall_speed / level
                if soft_drop:
                    fall_delay *= 0.1
                if current_time - last_fall_time > fall_delay:
                    current_piece.y += 1
                    if soft_drop:
                        score += 1
                    last_fall_time = current_time

            combo_display = f"{combo_count}" if prev_cleared else "-"
            if not draw_board(stdscr, board, score, level, combo_display):
                time.sleep(1)
                continue

            draw_piece(stdscr, current_piece, board, ghost=True)
            draw_next_and_held(stdscr, next_piece, held_piece, board)
        return score
    finally:
        curses.endwin()

if __name__ == "__main__":
    seed = random.randint(0, 1000000)
    get_next_piece = create_piece_generator(seed)
    final_score = run_game(get_next_piece)
    print("Game Over!")
    print(f"Final Score: {final_score}")
