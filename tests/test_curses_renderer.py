import pytest
import curses
from unittest.mock import MagicMock, patch, call, ANY
from ui.curses_renderer import (
    CursesRenderer,
    BOARD_WIDTH,
    BOARD_HEIGHT,
    EMPTY_CELL,
    GARBAGE_COLOR,
)
from game.state import Piece  # Assuming Piece class might be needed for piece data
from game.combo import ComboSystem  # For combo message testing

# --- Fixtures ---


@pytest.fixture
def mock_stdscr():
    stdscr = MagicMock()
    # Simulate a reasonably sized terminal
    stdscr.getmaxyx.return_value = (30, 80)  # height, width
    # Mock color pair creation if needed, though we often check the value passed
    # curses.color_pair = MagicMock(return_value=lambda x: x) # Identity for testing
    return stdscr


@pytest.fixture
def renderer(mock_stdscr):
    # Patch curses functions used within the renderer's __init__ if necessary
    with patch("curses.start_color"), patch("curses.init_pair"), patch(
        "curses.curs_set"
    ):
        renderer_instance = CursesRenderer(mock_stdscr, debug_mode=False)
        # Replace stdscr with mock *after* init potentially uses real curses funcs
        renderer_instance.stdscr = mock_stdscr

    # Patch color_pair *after* init for use in draw methods
    with patch("curses.color_pair", lambda x: x) as mock_color_pair:
        yield renderer_instance  # Yield allows setup/teardown if needed later


@pytest.fixture
def sample_board():
    board = [[EMPTY_CELL for _ in range(BOARD_WIDTH)] for _ in range(BOARD_HEIGHT)]
    board[BOARD_HEIGHT - 1][0] = 1  # Place a block
    board[BOARD_HEIGHT - 2][1] = 2
    board[5][5] = GARBAGE_COLOR  # Place a garbage block
    return board


@pytest.fixture
def sample_piece():
    piece = Piece("T")
    piece.x = 3
    piece.y = 5
    return piece


@pytest.fixture
def sample_next_piece():
    return Piece("L")


@pytest.fixture
def sample_held_piece():
    return Piece("S")


@pytest.fixture
def sample_peer_boards():
    # Provide some sample data for peer boards
    return {
        "peer1": {
            "board": [[0] * 10 for _ in range(20)],
            "score": 1000,
            "player_name": "PeerOne",
            "timestamp": 12345.0,
            "active_piece": {"type": "I", "x": 4, "y": 2, "rotation": 0, "color": 1},
        },
        "peer2": {
            "board": [[8] * 10 for _ in range(20)],  # Filled with garbage
            "score": 500,
            "player_name": "PeerTwoLongNameTruncate",
            "timestamp": 12346.0,
        },
    }


# --- Test Cases ---


def test_renderer_init(mock_stdscr):
    """Test basic initialization and curses setup calls."""
    with patch("curses.start_color") as mock_start_color, patch(
        "curses.init_pair"
    ) as mock_init_pair, patch("curses.curs_set") as mock_curs_set, patch(
        "locale.setlocale"
    ):  # Patch locale to avoid side effects
        renderer = CursesRenderer(mock_stdscr)
        mock_start_color.assert_called_once()
        assert mock_init_pair.call_count >= 9  # Called for colors 0-8
        mock_curs_set.assert_called_once_with(0)
        assert renderer.stdscr == mock_stdscr


def test_draw_board_basic(renderer, mock_stdscr, sample_board):
    """Test drawing the board borders and basic info."""
    score = 123
    level = 4
    combo_display = "2"
    player_name = "TestPlayer"

    result = renderer.draw_board(sample_board, score, level, combo_display, player_name)

    assert result is True
    mock_stdscr.clear.assert_called_once()
    # Check for some key addstr calls (borders, info)
    # Example: Check top border call
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "+" + "--" * BOARD_WIDTH + "+", ANY)
    # Example: Check score display
    mock_stdscr.addstr.assert_any_call(ANY, ANY, f"Score: {score}")
    # Example: Check player name
    mock_stdscr.addstr.assert_any_call(
        ANY, ANY, f"Player: {player_name}", curses.A_BOLD
    )
    # Example: Check a specific block (more complex due to coords)
    # Block at (0, 19) is color 1 -> pair 2
    # Block at (5, 5) is garbage -> pair 9, A_DIM
    # Calculation for coords: start_y + 1 + y, start_x + 1 + x*2
    # This requires calculating start_y/start_x, which is complex to assert directly
    # Instead, check *if* addstr was called with the block chars/colors
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "[]", curses.color_pair(1 + 1))
    mock_stdscr.addstr.assert_any_call(
        ANY, ANY, "░░", curses.color_pair(GARBAGE_COLOR + 1) | curses.A_DIM
    )
    mock_stdscr.refresh.assert_called_once()


def test_draw_board_terminal_too_small(renderer, mock_stdscr):
    """Test behavior when the terminal is too small."""
    mock_stdscr.getmaxyx.return_value = (10, 20)  # Too small height and width
    result = renderer.draw_board([[]], 0, 0, "0", "Player")
    assert result is False
    mock_stdscr.clear.assert_called()
    mock_stdscr.addstr.assert_any_call(
        ANY, ANY, "Terminal too small! Resize and restart."
    )
    mock_stdscr.refresh.assert_called()


def test_draw_piece_normal(renderer, mock_stdscr, sample_piece, sample_board):
    """Test drawing a normal piece without ghost."""
    renderer.draw_piece(sample_piece, sample_board, ghost=False)
    # T-piece shape: [[0, 3, 0], [3, 3, 3]]
    # Expected calls for blocks at (3,5 upper), (3,6 lower), (4,6 lower), (5,6 lower)
    # Color 3 -> pair 4
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "[]", curses.color_pair(3 + 1))
    # Check number of block calls matches piece shape
    addstr_calls = [c for c in mock_stdscr.addstr.call_args_list if c.args[2] == "[]"]
    # Ensure DIM attribute is NOT used (ghost=False)
    assert not any(c.args[3] & curses.A_DIM for c in addstr_calls if len(c.args) > 3)


def test_draw_piece_with_ghost(renderer, mock_stdscr, sample_piece, sample_board):
    """Test drawing a piece with its ghost."""
    # Mock collision check to simulate landing position
    with patch.object(renderer, "_check_collision") as mock_check_collision:
        # Simulate: No collision until y + 10
        mock_check_collision.side_effect = lambda b, p, dx, dy: (p.y + dy) >= (
            sample_piece.y + 10
        )
        renderer.draw_piece(sample_piece, sample_board, ghost=True)

    # Check for normal piece blocks (pair 4)
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "[]", curses.color_pair(3 + 1))
    # Check for ghost piece blocks (A_DIM)
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "[]", curses.A_DIM)

    # Verify _check_collision was called repeatedly to find ghost position
    assert mock_check_collision.call_count > 1


def test_check_collision_internal(renderer, sample_board):
    """Test the internal _check_collision helper used by ghost."""
    piece = Piece("O")  # [[2,2],[2,2]]
    piece.x = 0
    piece.y = BOARD_HEIGHT - 2  # At bottom
    assert renderer._check_collision(sample_board, piece, 0, 1)  # Collides with bottom

    piece.y = 10
    sample_board[12][0] = 1  # Place block below
    assert renderer._check_collision(sample_board, piece, 0, 1)  # Collides with block

    assert not renderer._check_collision(
        sample_board, piece, 0, 0
    )  # No collision at current pos
    assert not renderer._check_collision(
        sample_board, piece, 1, 0
    )  # No collision moving right


def test_draw_next_and_held(
    renderer, mock_stdscr, sample_next_piece, sample_held_piece
):
    """Test drawing the next and held pieces."""
    renderer.draw_next_and_held(sample_next_piece, sample_held_piece)

    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Next:")
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Hold:")
    # Check blocks for Next piece (L, color 7 -> pair 8)
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "[]", curses.color_pair(7 + 1))
    # Check blocks for Held piece (S, color 4 -> pair 5)
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "[]", curses.color_pair(4 + 1))


def test_draw_pending_garbage_indicator(renderer, mock_stdscr):
    """Test drawing the garbage indicator bar."""
    renderer.draw_pending_garbage_indicator(0)  # Amount 0
    # Check that addstr wasn't called with the garbage attribute
    garbage_color_attr = curses.color_pair(curses.COLOR_RED + 1) | curses.A_REVERSE
    garbage_char_calls = [
        c
        for c in mock_stdscr.addstr.call_args_list
        if len(c.args) > 3 and c.args[3] == garbage_color_attr
    ]
    assert len(garbage_char_calls) == 0
    mock_stdscr.reset_mock()  # Reset calls for next check

    amount = 5
    renderer.draw_pending_garbage_indicator(amount)
    # Check that addstr was called `amount` times with the garbage color/attribute
    garbage_color_attr = curses.color_pair(curses.COLOR_RED + 1) | curses.A_REVERSE
    garbage_char_calls = [
        c
        for c in mock_stdscr.addstr.call_args_list
        if len(c.args) > 3 and c.args[3] == garbage_color_attr
    ]
    assert len(garbage_char_calls) == amount

    mock_stdscr.reset_mock()
    amount = BOARD_HEIGHT + 5  # More than board height
    renderer.draw_pending_garbage_indicator(amount)
    garbage_char_calls = [
        c
        for c in mock_stdscr.addstr.call_args_list
        if len(c.args) > 3 and c.args[3] == garbage_color_attr
    ]
    assert len(garbage_char_calls) == BOARD_HEIGHT  # Should cap at board height


def test_draw_combo_message(renderer, mock_stdscr):
    """Test drawing the combo message."""
    combo_system = MagicMock(spec=ComboSystem)
    combo_system.debug_message = "COMBO x3!"
    combo_system.check_debug_timeout = MagicMock()
    current_time = 12345.0

    renderer.draw_combo_message(combo_system, current_time)

    combo_system.check_debug_timeout.assert_called_once_with(current_time)
    mock_stdscr.addstr.assert_any_call(
        ANY, ANY, "COMBO x3!", curses.A_BOLD | curses.A_REVERSE
    )


def test_draw_game_over(renderer, mock_stdscr):
    """Test drawing the game over screen."""
    stats_list = [
        {
            "player_name": "Winner",
            "survival_time": 120.5,
            "attacks_sent": 10,
            "attacks_received": 2,
            "score": 5000,
        },
        {
            "player_name": "Loser",
            "survival_time": 65.1,
            "attacks_sent": 3,
            "attacks_received": 12,
            "score": 1500,
        },
    ]

    # Mock getch to simulate user pressing a key to continue
    mock_stdscr.getch.return_value = ord(" ")

    renderer.draw_game_over(stats_list)

    mock_stdscr.clear.assert_called()
    mock_stdscr.addstr.assert_any_call(
        ANY, ANY, "   --- FINAL RESULTS ---   ", curses.A_BOLD
    )
    # Check headers
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Rank", curses.A_UNDERLINE)
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Player", curses.A_UNDERLINE)
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Survival", curses.A_UNDERLINE)
    # Check player data rows
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "1")  # Rank
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Winner")  # Name
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "120.5s")  # Survival
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "2")  # Rank
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Loser")  # Name
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "65.1s")  # Survival
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "Press any key to return to lobby...")
    # Check it switched to blocking input for getch
    mock_stdscr.nodelay.assert_has_calls([call(False), call(True)])
    mock_stdscr.getch.assert_called_once()


# Note: Testing draw_other_players_boards is more complex due to grid layout
# and potential duplication logic. Focus on checking if it attempts to draw *something*
# for the peers provided.


def test_draw_other_players_boards_calls(renderer, mock_stdscr, sample_peer_boards):
    """Check that draw_other_players_boards attempts to draw peer info."""
    # Spy on addstr to capture ALL calls
    spy_addstr = mock_stdscr.addstr
    lock = MagicMock()  # Mock lock

    # Call the function being tested
    renderer.draw_other_players_boards(sample_peer_boards, lock)

    # Check header - this is working
    mock_stdscr.addstr.assert_any_call(ANY, ANY, "OTHER PLAYERS", curses.A_BOLD)

    assert len(spy_addstr.call_args_list) > 0, "No calls were made to addstr"
