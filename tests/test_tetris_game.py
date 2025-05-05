import pytest
from game.tetris_game import (
    get_piece_shape,
    TETROMINOES,
    BOARD_WIDTH,
    BOARD_HEIGHT,
    EMPTY_CELL,
    GARBAGE_COLOR,
    create_board,
    check_collision,
    merge_piece,
    clear_lines,
    calculate_score,
    add_garbage_lines,
    Piece,
)
import random


# Test cases for get_piece_shape
@pytest.mark.parametrize(
    "piece_type, rotation, expected_first_row_sum",
    [
        # Test multiple rotations for a non-symmetrical piece like T
        ("T", 0, 3),  # [[0, 3, 0], ...]
        ("T", 1, 3),  # [[0, 3, 0], ...]
        ("T", 2, 0),  # [[0, 0, 0], ...]
        ("T", 3, 3),  # [[0, 3, 0], ...]
        ("T", 4, 3),  # Rotation wraps around (4 % 4 == 0)
        # Test symmetrical piece like O (only one shape)
        ("O", 0, 4),  # [[2, 2], ...]
        ("O", 1, 4),  # [[2, 2], ...]
        # Test I piece
        ("I", 0, 0),  # [[0, 0, 0, 0], ...]
        ("I", 1, 1),  # [[0, 0, 1, 0], ...]
        ("I", 2, 0),  # [[0, 0, 0, 0], ...]
        ("I", 3, 1),  # [[0, 1, 0, 0], ...]
    ],
)
def test_get_piece_shape(piece_type, rotation, expected_first_row_sum):
    """Test get_piece_shape returns correct shapes based on type and rotation."""
    shape = get_piece_shape(piece_type, rotation)
    assert isinstance(shape, list)
    assert len(shape) > 0
    # A simple check based on expected sum of first row (or a known cell value)
    # Using sum here as a proxy for checking the overall shape structure
    assert sum(shape[0]) == expected_first_row_sum
    # Check color is embedded correctly (using expected color from TETROMINOES)
    expected_color = TETROMINOES[piece_type]["color"]
    has_correct_color = False
    for r in shape:
        for cell in r:
            if cell != 0:
                assert cell == expected_color
                has_correct_color = True
    assert has_correct_color  # Ensure the piece wasn't all zeros


def test_get_piece_shape_invalid_type():
    """Test get_piece_shape handles invalid piece types."""
    shape = get_piece_shape("InvalidType", 0)
    assert shape == [[0]]


# --- Fixtures ---
@pytest.fixture
def empty_board():
    """Fixture for an empty game board."""
    return create_board()


@pytest.fixture
def board_with_lines():
    """Fixture for a board with some filled lines."""
    board = create_board()
    # Fill the bottom two lines completely
    for x in range(BOARD_WIDTH):
        board[BOARD_HEIGHT - 1][x] = 1
        board[BOARD_HEIGHT - 2][x] = 2
    # Add a partial line
    board[BOARD_HEIGHT - 3][0] = 3
    board[BOARD_HEIGHT - 3][1] = 3
    return board


@pytest.fixture
def sample_piece():
    """Fixture for a sample piece (T)."""
    piece = Piece("T")
    piece.x = BOARD_WIDTH // 2 - 1  # Center it roughly
    piece.y = 0
    return piece


# --- Tests for Game Logic Functions ---


def test_create_board(empty_board):
    """Test if create_board generates a board with correct dimensions and content."""
    assert len(empty_board) == BOARD_HEIGHT
    assert len(empty_board[0]) == BOARD_WIDTH
    for row in empty_board:
        assert all(cell == EMPTY_CELL for cell in row)


def test_check_collision_boundaries(empty_board, sample_piece):
    """Test collision detection with board boundaries."""
    # Test collision with left wall
    sample_piece.x = -1
    assert check_collision(empty_board, sample_piece) is True

    # Test collision with right wall
    sample_piece.x = (
        BOARD_WIDTH - 1
    )  # T shape is 3 wide, 0-indexed -> last block at x+2
    assert check_collision(empty_board, sample_piece) is True

    # Test collision with floor
    sample_piece.x = BOARD_WIDTH // 2 - 1  # Reset x
    sample_piece.y = (
        BOARD_HEIGHT - 2
    )  # T shape is 2 high, 0-indexed -> last block at y+1
    assert check_collision(empty_board, sample_piece, dy=1) is True

    # Test no collision within bounds
    sample_piece.y = 5
    assert check_collision(empty_board, sample_piece) is False
    assert check_collision(empty_board, sample_piece, dx=1) is False
    assert check_collision(empty_board, sample_piece, dy=1) is False


def test_check_collision_other_pieces(empty_board, sample_piece):
    """Test collision detection with other pieces already on the board."""
    # Place a block where the moving piece would land
    landing_y = sample_piece.y + 1  # T piece shape: [[0, 3, 0], [3, 3, 3]]
    landing_x = sample_piece.x + 1  # Middle bottom block of T
    empty_board[landing_y + 1][landing_x] = 1  # Block below middle bottom block of T

    assert check_collision(empty_board, sample_piece, dy=1) is True

    # First ensure the board is clean for the rotation test
    empty_board[landing_y + 1][landing_x] = EMPTY_CELL

    # Test collision with rotated shape
    # When rotated clockwise, T piece becomes: [[3, 0], [3, 3], [3, 0]]
    rotated_t = sample_piece.rotate()

    # Place a block where the rotated piece would collide
    # For the rotated T, let's place a block at one of its actual positions
    empty_board[sample_piece.y][
        sample_piece.x
    ] = 1  # Block at the top-left of rotated T

    assert check_collision(empty_board, sample_piece, rotated_shape=rotated_t) is True


def test_merge_piece(empty_board, sample_piece):
    """Test merging a piece onto the board."""
    sample_piece.y = 5
    sample_piece.x = 3
    merge_piece(empty_board, sample_piece)

    # Check if the T piece's blocks are on the board at the correct location and color
    # T-piece shape: [[0, 3, 0], [3, 3, 3]]
    assert empty_board[5][4] == 3  # y=5, x=3+1
    assert empty_board[6][3] == 3  # y=5+1, x=3+0
    assert empty_board[6][4] == 3  # y=5+1, x=3+1
    assert empty_board[6][5] == 3  # y=5+1, x=3+2
    # Check that other cells are still empty
    assert empty_board[5][3] == EMPTY_CELL
    assert empty_board[7][4] == EMPTY_CELL


def test_clear_lines_simple(board_with_lines):
    """Test clearing completed lines."""
    cleared_count = clear_lines(board_with_lines)
    assert cleared_count == 2

    # The partial line from BOARD_HEIGHT-3 (with 3's at positions 0 and 1)
    # should now be at the bottom row (BOARD_HEIGHT-1)
    assert board_with_lines[BOARD_HEIGHT - 1][0] == 3
    assert board_with_lines[BOARD_HEIGHT - 1][1] == 3

    # The rest of the bottom row should be empty
    for x in range(2, BOARD_WIDTH):
        assert board_with_lines[BOARD_HEIGHT - 1][x] == EMPTY_CELL

    # The row above the bottom should be completely empty
    assert all(cell == EMPTY_CELL for cell in board_with_lines[BOARD_HEIGHT - 2])


def test_clear_lines_no_clear(empty_board):
    """Test clearing lines when no lines are complete."""
    empty_board[BOARD_HEIGHT - 1][0] = 1
    cleared_count = clear_lines(empty_board)
    assert cleared_count == 0
    assert empty_board[BOARD_HEIGHT - 1][0] == 1  # Board should be unchanged


@pytest.mark.parametrize(
    "lines_cleared, level, expected_score",
    [
        (0, 1, 0),
        (1, 1, 40),
        (2, 1, 100),
        (3, 1, 300),
        (4, 1, 1200),
        (1, 5, 200),  # 40 * 5
        (4, 10, 12000),  # 1200 * 10
    ],
)
def test_calculate_score(lines_cleared, level, expected_score):
    """Test score calculation based on lines cleared and level."""
    assert calculate_score(lines_cleared, level) == expected_score


def test_add_garbage_lines(empty_board):
    """Test adding garbage lines to the board."""
    # Add a marker to the initial board at top row to test shifting
    empty_board[0][0] = 1  # Add a non-empty cell at the top-left corner

    initial_top_row = empty_board[0][:]
    count = 3
    random.seed(42)  # Make gap predictable for testing
    add_garbage_lines(empty_board, count)

    assert len(empty_board) == BOARD_HEIGHT  # Height should remain constant

    # Check bottom `count` lines are garbage
    for y in range(BOARD_HEIGHT - count, BOARD_HEIGHT):
        garbage_line_count = 0
        empty_cell_count = 0
        for cell in empty_board[y]:
            if cell == GARBAGE_COLOR:
                garbage_line_count += 1
            elif cell == EMPTY_CELL:
                empty_cell_count += 1
        assert garbage_line_count == BOARD_WIDTH - 1
        assert empty_cell_count == 1

    # Check if original top row moved up (or rather, was replaced by shifted rows)
    # This is hard to check precisely without knowing what was above the initial board.
    # Instead, check that the *new* top row is NOT the original top row if count > 0
    print(empty_board)
    print(initial_top_row)
    assert empty_board[0] != initial_top_row


def test_add_garbage_lines_zero_count(empty_board):
    """Test adding zero garbage lines."""
    original_board = [row[:] for row in empty_board]  # Deep copy
    add_garbage_lines(empty_board, 0)
    assert empty_board == original_board
