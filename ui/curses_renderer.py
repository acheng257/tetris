import curses
import locale
from game.state import (
    BOARD_HEIGHT,
    BOARD_WIDTH,
    EMPTY_CELL,
    GARBAGE_COLOR,
    get_piece_shape,
)

# Initialize locale for better character display
locale.setlocale(locale.LC_ALL, "")

# Color definitions
COLORS = {
    0: curses.COLOR_BLACK,
    1: curses.COLOR_CYAN,  # I piece
    2: curses.COLOR_YELLOW,  # O piece
    3: curses.COLOR_MAGENTA,  # T piece
    4: curses.COLOR_GREEN,  # S piece
    5: curses.COLOR_RED,  # Z piece
    6: curses.COLOR_BLUE,  # J piece
    7: curses.COLOR_WHITE,  # L piece
    8: curses.COLOR_WHITE,  # Border and garbage blocks
    GARBAGE_COLOR: curses.COLOR_WHITE,  # Ensure the garbage color is defined
}


class CursesRenderer:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.init_curses()

    def init_curses(self):
        """Initialize curses settings and colors"""
        self.stdscr.keypad(True)
        curses.curs_set(0)  # Hide cursor
        self.stdscr.nodelay(True)  # Non-blocking input
        self.stdscr.timeout(10)  # Input timeout in ms

        # Initialize colors
        curses.start_color()
        for i, color in COLORS.items():
            curses.init_pair(i + 1, color, curses.COLOR_BLACK)

    def draw_board(self, board, score, level, combo_display, player_name=None):
        """Draw the main Tetris board and game information"""
        self.stdscr.clear()
        h, w = self.stdscr.getmaxyx()
        board_height = BOARD_HEIGHT + 2  # +2 for border
        board_width = BOARD_WIDTH * 2 + 2  # *2 for character width, +2 for border

        # Check if terminal is too small
        if h < board_height or w < board_width + 15:
            self.stdscr.clear()
            error_msg = "Terminal too small! Resize and restart."
            try:
                self.stdscr.addstr(h // 2, max(0, (w - len(error_msg)) // 2), error_msg)
                self.stdscr.refresh()
            except curses.error:
                pass
            return False

        # Calculate starting position to center the board
        start_y = max(0, (h - board_height) // 2)
        start_x = max(0, (w - board_width) // 2)
        border_color = curses.color_pair(8 + 1)  # White for border

        try:
            # Display player name if provided
            if player_name:
                name_text = f"Player: {player_name}"
                name_x = start_x + (board_width - len(name_text)) // 2
                self.stdscr.addstr(
                    start_y - 2, max(0, name_x), name_text, curses.A_BOLD
                )

            # Draw top border
            self.stdscr.addstr(
                start_y, start_x, "+" + "--" * BOARD_WIDTH + "+", border_color
            )

            # Draw side borders
            for y in range(BOARD_HEIGHT):
                self.stdscr.addstr(start_y + 1 + y, start_x, "|", border_color)
                self.stdscr.addstr(
                    start_y + 1 + y, start_x + BOARD_WIDTH * 2 + 1, "|", border_color
                )

            # Draw bottom border
            self.stdscr.addstr(
                start_y + BOARD_HEIGHT + 1,
                start_x,
                "+" + "--" * BOARD_WIDTH + "+",
                border_color,
            )

            # Draw board contents
            for y, row in enumerate(board):
                for x, cell in enumerate(row):
                    if cell != EMPTY_CELL:
                        # Special rendering for garbage blocks
                        if cell == GARBAGE_COLOR:
                            color_pair = curses.color_pair(cell + 1) | curses.A_DIM
                            self.stdscr.addstr(
                                start_y + 1 + y, start_x + 1 + x * 2, "░░", color_pair
                            )
                        else:
                            # Normal rendering for regular tetromino blocks
                            color_pair = curses.color_pair(cell + 1)
                            self.stdscr.addstr(
                                start_y + 1 + y, start_x + 1 + x * 2, "[]", color_pair
                            )
                    else:
                        self.stdscr.addstr(start_y + 1 + y, start_x + 1 + x * 2, "  ")

            # Draw game information
            self.stdscr.addstr(
                start_y + 2, start_x + board_width + 2, f"Score: {score}"
            )
            self.stdscr.addstr(
                start_y + 4, start_x + board_width + 2, f"Level: {level}"
            )
            self.stdscr.addstr(
                start_y + 6, start_x + board_width + 2, f"Combo: {combo_display}"
            )

            # Draw controls
            controls_y = start_y + 8
            self.stdscr.addstr(controls_y, start_x + board_width + 2, "Controls:")
            self.stdscr.addstr(controls_y + 1, start_x + board_width + 2, "← → : Move")
            self.stdscr.addstr(controls_y + 2, start_x + board_width + 2, "↑ : Rotate")
            self.stdscr.addstr(
                controls_y + 3, start_x + board_width + 2, "↓ : Soft drop"
            )
            self.stdscr.addstr(
                controls_y + 4, start_x + board_width + 2, "Space: Hard drop"
            )
            self.stdscr.addstr(
                controls_y + 5, start_x + board_width + 2, "c : Hold piece"
            )
            self.stdscr.addstr(controls_y + 6, start_x + board_width + 2, "q : Quit")

            self.stdscr.refresh()
            return True

        except curses.error:
            # Handle any errors during drawing
            try:
                self.stdscr.clear()
                self.stdscr.addstr(0, 0, "Terminal too small! Resize and restart.")
                self.stdscr.refresh()
            except curses.error:
                pass
            return False

    def draw_piece(self, piece, board, ghost=False):
        """Draw the active piece and optionally its ghost (landing position)"""
        print("[RENDER DEBUG] Calling draw_piece")
        h, w = self.stdscr.getmaxyx()
        board_height = BOARD_HEIGHT + 2
        board_width = BOARD_WIDTH * 2 + 2
        start_y = max(0, (h - board_height) // 2)
        start_x = max(0, (w - board_width) // 2)

        # Calculate ghost position
        ghost_y = piece.y
        if ghost:
            drop_distance = 0
            # Find how far the piece can drop
            while not self._check_collision(board, piece, 0, drop_distance + 1):
                drop_distance += 1
            ghost_y = piece.y + drop_distance

        # Draw the actual piece
        for y, row in enumerate(piece.shape):
            for x, cell in enumerate(row):
                if cell:
                    if piece.y + y >= 0:  # Only draw if it's in the visible area
                        color_pair = curses.color_pair(piece.color + 1)
                        try:
                            self.stdscr.addstr(
                                start_y + 1 + piece.y + y,
                                start_x + 1 + (piece.x + x) * 2,
                                "[]",
                                color_pair,
                            )
                        except curses.error:
                            pass

                    # Draw ghost piece (landing position indicator)
                    if ghost and piece.y != ghost_y:
                        ghost_display_y = ghost_y + y
                        if 0 <= ghost_display_y < BOARD_HEIGHT:
                            try:
                                self.stdscr.addstr(
                                    start_y + 1 + ghost_display_y,
                                    start_x + 1 + (piece.x + x) * 2,
                                    "[]",
                                    curses.A_DIM,
                                )
                            except curses.error:
                                pass

    def _check_collision(self, board, piece, dx=0, dy=0):
        """Helper method for ghost piece calculation"""
        print("[RENDER DEBUG] Calling _check_collision")
        shape = piece.shape
        for y, row in enumerate(shape):
            for x, cell in enumerate(row):
                if cell:
                    new_x = piece.x + x + dx
                    new_y = piece.y + y + dy
                    if new_x < 0 or new_x >= BOARD_WIDTH or new_y >= BOARD_HEIGHT:
                        print(f"[RENDER DEBUG] Collision detected at {new_x}, {new_y}")
                        return True
                    if new_y < 0:
                        continue  # Allow pieces to start above the board
                    if board[new_y][new_x] != EMPTY_CELL:
                        print(f"[RENDER DEBUG] Collision detected at {new_x}, {new_y}")
                        return True
        print("[RENDER DEBUG] No collision detected")
        return False

    def draw_next_and_held(self, next_piece, held_piece):
        """Draw the next and held pieces"""
        print("[RENDER DEBUG] Calling draw_next_and_held")
        h, w = self.stdscr.getmaxyx()
        board_height = BOARD_HEIGHT + 2
        board_width = BOARD_WIDTH * 2 + 2
        start_y = max(0, (h - board_height) // 2)
        start_x = max(0, (w - board_width) // 2)
        preview_y = start_y + 15
        preview_x = start_x + board_width + 2

        try:
            # Draw next piece
            self.stdscr.addstr(preview_y, preview_x, "Next:")
            next_preview_y = preview_y + 1
            next_preview_x = preview_x + 4
            for y, row in enumerate(next_piece.shape):
                for x, cell in enumerate(row):
                    if cell:
                        color_pair = curses.color_pair(next_piece.color + 1)
                        self.stdscr.addstr(
                            next_preview_y + y, next_preview_x + x * 2, "[]", color_pair
                        )

            # Draw held piece if exists
            self.stdscr.addstr(preview_y + 5, preview_x, "Hold:")
            if held_piece:
                held_preview_y = preview_y + 6
                held_preview_x = preview_x + 4
                for y, row in enumerate(held_piece.shape):
                    for x, cell in enumerate(row):
                        if cell:
                            color_pair = curses.color_pair(held_piece.color + 1)
                            self.stdscr.addstr(
                                held_preview_y + y,
                                held_preview_x + x * 2,
                                "[]",
                                color_pair,
                            )
        except curses.error:
            pass

    def draw_other_players_boards(self, peer_boards, peer_boards_lock):
        """Draw miniature versions of other players' boards"""
        print("[RENDER DEBUG] Calling draw_other_players_boards")
        h, w = self.stdscr.getmaxyx()
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

            # Deduplicate boards by player name
            seen_player_names = set()
            deduplicated_peers = []

            for peer_id, peer_data in sorted_peers:
                player_name = peer_data.get("player_name", "")
                # Remove any numeric suffix that might have been added
                base_name = player_name.rstrip("S")

                if base_name and base_name not in seen_player_names:
                    seen_player_names.add(base_name)
                    deduplicated_peers.append((peer_id, peer_data))

            # Draw header
            try:
                header_y = start_y - 2
                if header_y >= 0:
                    self.stdscr.addstr(
                        header_y, other_boards_x, "OTHER PLAYERS", curses.A_BOLD
                    )
            except curses.error:
                pass

            # Draw up to 9 peer boards (3x3 grid) from deduplicated list
            max_peer_boards = min(9, len(deduplicated_peers))

            for i, (peer_id, peer_data) in enumerate(
                deduplicated_peers[:max_peer_boards]
            ):
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
                    self.stdscr.addstr(
                        board_y - 2, board_x, f"{player_name}", name_attr
                    )
                    # self.stdscr.addstr(board_y - 1, board_x, f"Score: {peer_score}")

                    # Draw mini board border
                    border_color = curses.color_pair(8 + 1)
                    self.stdscr.addstr(
                        board_y,
                        board_x,
                        "+" + "-" * mini_board_width + "+",
                        border_color,
                    )
                    for y in range(mini_board_height):
                        self.stdscr.addstr(board_y + y + 1, board_x, "|", border_color)
                        self.stdscr.addstr(
                            board_y + y + 1,
                            board_x + mini_board_width + 1,
                            "|",
                            border_color,
                        )
                    self.stdscr.addstr(
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
                                        self.stdscr.addstr(
                                            board_y + mini_y + 1,
                                            board_x + 1 + x,
                                            "░",
                                            color_pair,
                                        )
                                    else:
                                        color_pair = curses.color_pair(cell + 1)
                                        self.stdscr.addstr(
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

                        # Get the shape for this piece type and rotation
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
                                        self.stdscr.addstr(
                                            board_y + mini_y_pos + 1,
                                            board_x + 1 + board_x_pos,
                                            "#",
                                            color_pair,
                                        )
                except curses.error:
                    # Handle errors when drawing outside window bounds
                    pass

    def draw_combo_message(self, combo_system, current_time):
        """Draw the combo message if there is one active"""
        print("[RENDER DEBUG] Calling draw_combo_message")
        # Update combo debug message timeout
        combo_system.check_debug_timeout(current_time)

        # Draw debug message if it exists
        if combo_system.debug_message:
            try:
                h, w = self.stdscr.getmaxyx()
                board_height = BOARD_HEIGHT + 2
                board_width = BOARD_WIDTH * 2 + 2
                start_y = max(0, (h - board_height) // 2)

                # Display at the top of the screen in a highlighted style
                debug_y = max(0, start_y - 4)
                debug_x = max(0, (w - len(combo_system.debug_message)) // 2)

                # Add a visual highlight to make it stand out
                self.stdscr.addstr(
                    debug_y,
                    debug_x,
                    combo_system.debug_message,
                    curses.A_BOLD | curses.A_REVERSE,
                )
            except curses.error:
                pass  # Handle potential out-of-bounds errors

    def draw_game_over(self, stats_list):
        """Draw the final multi-player game over results screen."""
        h, w = self.stdscr.getmaxyx()
        self.stdscr.clear()

        title = "   --- FINAL RESULTS ---   "
        try:
            self.stdscr.addstr(2, (w - len(title)) // 2, title, curses.A_BOLD)

            # Define column headers and approximate positions/widths
            headers = ["Rank", "Player", "Survival", "Sent", "Received", "Score"]
            # Adjust positions based on typical lengths
            col_x = [4, 10, 28, 42, 50, 65]

            # Draw headers
            for idx, hdr in enumerate(headers):
                self.stdscr.addstr(4, col_x[idx], hdr, curses.A_UNDERLINE)

            # Sort stats by survival time descending before displaying
            # The lobby should ideally pass a pre-sorted list, but we can sort here too
            sorted_stats = sorted(
                stats_list, key=lambda x: x.get("survival_time", 0), reverse=True
            )

            # Draw each player's row
            for row_idx, stats in enumerate(sorted_stats):
                y = 5 + row_idx

                # Prepare data strings
                rank = str(row_idx + 1)
                name = stats.get("player_name", "Unknown")[:16]  # Truncate name
                survival = f"{stats.get('survival_time', 0):.1f}s"
                sent = str(stats.get("attacks_sent", 0))
                received = str(stats.get("attacks_received", 0))
                score_val = str(stats.get("score", 0))

                # Draw columns
                self.stdscr.addstr(y, col_x[0], rank)
                self.stdscr.addstr(y, col_x[1], name)
                self.stdscr.addstr(y, col_x[2], survival)
                self.stdscr.addstr(y, col_x[3], sent)
                self.stdscr.addstr(y, col_x[4], received)
                self.stdscr.addstr(y, col_x[5], score_val)

            footer = "Press any key to return to lobby..."
            self.stdscr.addstr(h - 2, (w - len(footer)) // 2, footer)

        except curses.error:
            # Handle potential errors during drawing (e.g., small terminal)
            self.stdscr.clear()
            self.stdscr.addstr(0, 0, "Error displaying results (Terminal too small?)")

        # Wait for user input before returning to lobby
        self.stdscr.nodelay(False)  # Switch to blocking input
        self.stdscr.getch()
        self.stdscr.nodelay(True)  # Switch back to non-blocking

    def draw_pending_garbage_indicator(self, pending_garbage_amount):
        """Draw the pending garbage indicator bar on the right side."""
        print(
            f"[RENDER DEBUG] Calling draw_pending_garbage_indicator with amount: {pending_garbage_amount}"
        )
        if pending_garbage_amount <= 0:
            return

        h, w = self.stdscr.getmaxyx()
        board_height = BOARD_HEIGHT + 2
        board_width = BOARD_WIDTH * 2 + 2
        start_y = max(0, (h - board_height) // 2) + 1  # Align with board content
        indicator_x = start_x = (
            max(0, (w - board_width) // 2) - 2
        )  # Position to the left of the board

        # Ensure x is not negative
        indicator_x = max(0, indicator_x)

        # Max height of the indicator is the board height
        indicator_height = min(pending_garbage_amount, BOARD_HEIGHT)
        garbage_color = curses.color_pair(curses.COLOR_RED + 1) | curses.A_REVERSE

        try:
            for y in range(indicator_height):
                draw_y = start_y + (BOARD_HEIGHT - 1 - y)
                # Check bounds before drawing
                if start_y <= draw_y < start_y + BOARD_HEIGHT:
                    self.stdscr.addstr(draw_y, indicator_x, """""", garbage_color)
        except curses.error:
            pass  # Ignore errors if drawing out of bounds
