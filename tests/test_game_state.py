import pytest
from game.state import (
    GameState,
    Piece,
    BOARD_WIDTH,
    BOARD_HEIGHT,
    EMPTY_CELL,
    GARBAGE_COLOR,
)


# Fixture to create a default GameState instance
@pytest.fixture
def game_state():
    return GameState(seed=123, debug_mode=False)


def test_game_state_initialization(game_state):
    """Test that GameState initializes correctly."""
    # Check board dimensions and content
    assert len(game_state.board) == BOARD_HEIGHT
    assert all(len(row) == BOARD_WIDTH for row in game_state.board)
    assert all(cell == EMPTY_CELL for row in game_state.board for cell in row)

    # Check initial state variables
    assert game_state.score == 0
    assert game_state.level == 1
    assert game_state.lines_cleared_total == 0
    assert not game_state.game_over
    assert game_state.pending_garbage == 0
    assert game_state.current_piece is not None
    assert game_state.next_piece is not None
    assert game_state.held_piece is None
    assert game_state.can_hold is True
    assert game_state.debug_mode is False

    # Check that the piece generator function is set
    assert hasattr(game_state, "_get_next_piece_func")
    assert callable(game_state._get_next_piece_func)


def test_piece_initial_position(game_state):
    """Test the initial position of different pieces."""
    # Test 'I' piece specifically for its higher start position
    i_piece = Piece("I")
    assert i_piece.y == -1
    assert i_piece.x == BOARD_WIDTH // 2 - len(i_piece.shape[0]) // 2

    # Test a non-'I' piece
    t_piece = Piece("T")
    assert t_piece.y == 0
    assert t_piece.x == BOARD_WIDTH // 2 - len(t_piece.shape[0]) // 2


def test_check_collision_bounds(game_state):
    """Test collision detection with board boundaries."""
    piece = Piece("T")  # Use a T piece for testing
    piece.x = 0
    piece.y = 0
    game_state.current_piece = piece

    # Check collision left boundary
    assert game_state.check_collision(piece, dx=-1, dy=0)

    # Check collision right boundary
    piece.x = BOARD_WIDTH - len(piece.shape[0])  # Move piece to the right edge
    assert game_state.check_collision(piece, dx=1, dy=0)

    # Check collision bottom boundary
    piece.x = BOARD_WIDTH // 2 - len(piece.shape[0]) // 2  # Reset x
    piece.y = BOARD_HEIGHT - len(piece.shape)  # Move piece to the bottom edge
    assert game_state.check_collision(piece, dx=0, dy=1)

    # Check no collision within bounds
    piece.x = 1
    piece.y = 1
    assert not game_state.check_collision(piece, dx=0, dy=0)


def test_check_collision_with_blocks(game_state):
    """Test collision detection with existing blocks on the board."""
    piece = Piece("T")
    piece.x = 4
    piece.y = 5
    game_state.current_piece = piece

    # Place a block where the piece will move
    game_state.board[7][
        5
    ] = 1  # Block at y=7, x=5 (where T piece's bottom middle would land)

    # Check collision downwards
    assert game_state.check_collision(piece, dx=0, dy=1)

    # Place block to the left
    game_state.board[6][
        3
    ] = 1  # Block at y=6, x=3 (where T piece's middle left would land)
    assert game_state.check_collision(piece, dx=-1, dy=0)

    # Place block to the right
    game_state.board[6][
        7
    ] = 1  # Block at y=6, x=7 (where T piece's middle right would land)
    assert game_state.check_collision(piece, dx=1, dy=0)

    # Check no collision in empty space
    game_state.board[7][5] = EMPTY_CELL
    game_state.board[6][3] = EMPTY_CELL
    game_state.board[6][7] = EMPTY_CELL
    assert not game_state.check_collision(piece, dx=0, dy=1)
    assert not game_state.check_collision(piece, dx=-1, dy=0)
    assert not game_state.check_collision(piece, dx=1, dy=0)


def test_merge_piece(game_state):
    """Test merging a piece onto the board."""
    piece = Piece("O")  # 2x2 O piece
    piece.x = 4
    piece.y = 18
    game_state.merge_piece(piece)

    assert game_state.board[18][4] == piece.color
    assert game_state.board[18][5] == piece.color
    assert game_state.board[19][4] == piece.color
    assert game_state.board[19][5] == piece.color
    # Check an empty cell nearby
    assert game_state.board[17][4] == EMPTY_CELL
    assert game_state.board[18][3] == EMPTY_CELL


def test_clear_lines_single(game_state):
    """Test clearing a single line."""
    # Fill the bottom row completely
    game_state.board[BOARD_HEIGHT - 1] = [1] * BOARD_WIDTH
    # Add some blocks above
    original_block = 2
    game_state.board[BOARD_HEIGHT - 2][5] = original_block

    lines = game_state.clear_lines()
    assert lines == 1
    assert game_state.lines_cleared_total == 1
    # Check bottom row now contains the fallen block
    expected_bottom_row = [EMPTY_CELL] * BOARD_WIDTH
    expected_bottom_row[5] = original_block
    assert game_state.board[BOARD_HEIGHT - 1] == expected_bottom_row
    # Check row above is now empty
    assert all(cell == EMPTY_CELL for cell in game_state.board[BOARD_HEIGHT - 2])


def test_clear_lines_multiple(game_state):
    """Test clearing multiple lines (Tetris)."""
    # Fill bottom 4 rows
    for y in range(BOARD_HEIGHT - 4, BOARD_HEIGHT):
        game_state.board[y] = [i + 1 for i in range(BOARD_WIDTH)]  # Use varied colors
    # Add a block above
    original_block = 5
    original_block_x = 3
    game_state.board[BOARD_HEIGHT - 5][original_block_x] = original_block

    lines = game_state.clear_lines()
    assert lines == 4
    assert game_state.lines_cleared_total == 4
    # Check rows BOARD_HEIGHT-4 to BOARD_HEIGHT-2 are now empty
    for y in range(BOARD_HEIGHT - 4, BOARD_HEIGHT - 1):
        assert all(cell == EMPTY_CELL for cell in game_state.board[y])
    # Check bottom row (BOARD_HEIGHT-1) contains the fallen block
    expected_bottom_row = [EMPTY_CELL] * BOARD_WIDTH
    expected_bottom_row[original_block_x] = original_block
    assert game_state.board[BOARD_HEIGHT - 1] == expected_bottom_row
    # Check original block position is now empty
    assert game_state.board[BOARD_HEIGHT - 5][original_block_x] == EMPTY_CELL


def test_clear_lines_no_clear(game_state):
    """Test when no lines should be cleared."""
    game_state.board[BOARD_HEIGHT - 1][0] = 1
    game_state.board[BOARD_HEIGHT - 1][-1] = 1
    lines = game_state.clear_lines()
    assert lines == 0
    assert game_state.lines_cleared_total == 0
    assert game_state.board[BOARD_HEIGHT - 1][0] == 1
    assert game_state.board[BOARD_HEIGHT - 1][-1] == 1


def test_calculate_score(game_state):
    """Test score calculation based on lines cleared and level."""
    game_state.level = 1
    assert game_state.calculate_score(0, game_state.level) == 0
    assert game_state.calculate_score(1, game_state.level) == 40
    assert game_state.calculate_score(2, game_state.level) == 100
    assert game_state.calculate_score(3, game_state.level) == 300
    assert game_state.calculate_score(4, game_state.level) == 1200

    game_state.level = 5
    assert game_state.calculate_score(1, game_state.level) == 40 * 5
    assert game_state.calculate_score(4, game_state.level) == 1200 * 5


def test_attempt_move_valid(game_state):
    """Test valid piece movements."""
    piece = Piece("T")
    initial_x = piece.x
    initial_y = piece.y
    game_state.current_piece = piece

    # Move right
    assert game_state.attempt_move(1, 0)
    assert piece.x == initial_x + 1
    assert piece.y == initial_y

    # Move left
    assert game_state.attempt_move(-1, 0)
    assert piece.x == initial_x
    assert piece.y == initial_y

    # Move down
    assert game_state.attempt_move(0, 1)
    assert piece.x == initial_x
    assert piece.y == initial_y + 1


def test_attempt_move_invalid(game_state):
    """Test invalid piece movements due to boundaries or blocks."""
    piece = Piece("T")
    piece.x = 0
    piece.y = 0
    initial_x = piece.x
    initial_y = piece.y
    game_state.current_piece = piece

    # Move left (invalid - boundary)
    assert not game_state.attempt_move(-1, 0)
    assert piece.x == initial_x
    assert piece.y == initial_y

    # Place a block below
    game_state.board[2][piece.x + 1] = 1  # Below middle part of T
    assert not game_state.attempt_move(0, 1)
    assert piece.x == initial_x
    assert piece.y == initial_y


def test_attempt_rotation_simple(game_state):
    """Test simple rotation in open space."""
    piece = Piece("L")
    game_state.current_piece = piece
    initial_shape = [row[:] for row in piece.shape]  # Deep copy

    assert game_state.attempt_rotation()
    # Check that shape has changed (not just reference)
    assert piece.shape != initial_shape
    # Basic check if it looks rotated (hard to be exact without knowing the exact rotated form)
    assert len(piece.shape) != len(initial_shape) or len(piece.shape[0]) != len(
        initial_shape[0]
    )


def test_attempt_rotation_blocked(game_state):
    """Test rotation blocked by walls or other pieces."""
    piece = Piece("I")  # Long piece
    piece.x = BOARD_WIDTH - 2  # Near right wall
    piece.y = 5
    game_state.current_piece = piece
    initial_shape = [row[:] for row in piece.shape]

    # Block rotation with wall
    # I piece vertical: [[1],[1],[1],[1]] needs space to become horizontal
    game_state.attempt_rotation()  # Rotate to vertical
    piece.x = BOARD_WIDTH - 1  # Move against wall
    initial_shape = [row[:] for row in piece.shape]  # Shape is now vertical

    assert not game_state.attempt_rotation()  # Should fail to rotate back to horizontal
    assert piece.shape == initial_shape  # Shape should not have changed

    # Block rotation with another piece
    piece.x = 5
    piece.y = 10
    # Rotate I piece to horizontal: [[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]]
    # Anchor (5,10) -> blocks at (5,11), (6,11), (7,11), (8,11)
    assert game_state.attempt_rotation()  # Should rotate to horizontal
    initial_shape = [row[:] for row in piece.shape]
    # Place block where it would NOT rotate into for vertical
    # Vertical blocks (anchor 5,10) -> (5,10), (5,11), (5,12), (5,13)
    game_state.board[11][4] = 1  # Block at (4, 11) - should NOT block rotation

    # assert not game_state.attempt_rotation() # Should fail to rotate to vertical
    assert (
        game_state.attempt_rotation()
    )  # Rotation should SUCCEED as block is not in the way
    assert piece.shape != initial_shape  # Shape should have changed back to vertical


def test_attempt_rotation_wall_kick(game_state):
    """Test rotation with a simple wall kick."""
    # Test T-piece kick near left wall
    piece = Piece("T")
    piece.x = 0  # T-piece initial: [[0,3,0],[3,3,3]]
    piece.y = 5
    game_state.current_piece = piece

    # Place a block that would normally block rotation without kick
    # Original T blocks: (1,5), (0,6), (1,6), (2,6)
    # Rotated T blocks (no kick): (0,5), (0,6), (1,6), (0,7)
    # game_state.board[5][2] = 1 # Block top-right of T -> (2,5) - doesn't block rotation
    game_state.board[7][1] = 1  # Block bottom-left of where rotated T would go (0,7)

    assert game_state.attempt_rotation()  # Should succeed with a kick
    # Verify shape has rotated
    # Original T: [[0,3,0],[3,3,3]] Rotated: [[3,0],[3,3],[3,0]]
    assert len(piece.shape) == 3 and len(piece.shape[0]) == 2


def test_hard_drop(game_state):
    """Test the hard drop functionality."""
    piece = Piece("O")  # O piece: [[2,2],[2,2]]
    piece.x = 4
    piece.y = 0
    game_state.current_piece = piece
    initial_score = game_state.score

    # Add an obstruction partway down
    game_state.board[10][4] = 1
    game_state.board[10][5] = 1

    distance = game_state.hard_drop()
    assert distance == 8  # Should drop 8 rows (y=0 to y=8, collision at y=10)
    assert piece.y == 8  # Final y position
    assert game_state.score == initial_score + (distance * 2)  # Check score update


def test_hold_piece_empty_hold(game_state):
    """Test holding a piece when the hold slot is empty."""
    current_p = game_state.current_piece
    next_p = game_state.next_piece
    current_type = current_p.type

    assert game_state.hold_piece()
    assert game_state.held_piece is not None
    assert game_state.held_piece.type == current_type
    assert (
        game_state.current_piece == next_p
    )  # Current piece should be the former next piece
    assert game_state.next_piece is not None  # A new next piece should be generated
    assert game_state.next_piece != next_p  # Ensure it's a *new* piece
    assert not game_state.can_hold  # Can't hold again immediately


def test_hold_piece_swap_hold(game_state):
    """Test swapping the current piece with the held piece."""
    # First, hold a piece
    initial_held_piece = Piece("S")
    game_state.held_piece = initial_held_piece
    game_state.can_hold = True  # Manually allow hold

    current_p = game_state.current_piece
    current_type = current_p.type
    next_p = game_state.next_piece

    assert game_state.hold_piece()
    assert game_state.held_piece is not None
    assert (
        game_state.held_piece.type == current_type
    )  # Held piece is now the former current
    assert (
        game_state.current_piece.type == initial_held_piece.type
    )  # Current is the previously held 'S'
    # Check position reset for the swapped-in piece
    assert (
        game_state.current_piece.x
        == BOARD_WIDTH // 2 - len(game_state.current_piece.shape[0]) // 2
    )
    assert game_state.current_piece.y == 0

    assert game_state.next_piece == next_p  # Next piece should not change during swap
    assert not game_state.can_hold


def test_hold_piece_cannot_hold(game_state):
    """Test that holding is blocked immediately after a hold."""
    game_state.hold_piece()  # Perform initial hold
    assert not game_state.can_hold
    # Try holding again immediately
    current_p = game_state.current_piece
    held_p = game_state.held_piece
    assert not game_state.hold_piece()
    # Ensure pieces didn't change
    assert game_state.current_piece == current_p
    assert game_state.held_piece == held_p


def test_queue_garbage(game_state):
    """Test adding garbage to the pending queue."""
    assert game_state.pending_garbage == 0
    game_state.queue_garbage(5)
    assert game_state.pending_garbage == 5
    game_state.queue_garbage(3)
    assert game_state.pending_garbage == 8
    game_state.queue_garbage(0)  # Adding 0 should do nothing
    assert game_state.pending_garbage == 8


def test_reduce_pending_garbage(game_state):
    """Test reducing the pending garbage amount."""
    game_state.pending_garbage = 10

    reduced = game_state.reduce_pending_garbage(4)
    assert reduced == 4
    assert game_state.pending_garbage == 6

    # Try reducing more than available
    reduced = game_state.reduce_pending_garbage(10)
    assert reduced == 6  # Only reduces by the remaining amount
    assert game_state.pending_garbage == 0

    # Try reducing when already zero
    reduced = game_state.reduce_pending_garbage(5)
    assert reduced == 0
    assert game_state.pending_garbage == 0

    # Try reducing by zero or negative
    game_state.pending_garbage = 5
    reduced = game_state.reduce_pending_garbage(0)
    assert reduced == 0
    assert game_state.pending_garbage == 5
    reduced = game_state.reduce_pending_garbage(-2)
    assert reduced == 0
    assert game_state.pending_garbage == 5


def test_apply_pending_garbage(game_state):
    """Test applying pending garbage lines to the board."""
    game_state.pending_garbage = 3
    # Add some existing blocks
    game_state.board[5][5] = 1

    applied = game_state.apply_pending_garbage()
    assert applied is True
    assert game_state.pending_garbage == 0

    # Check that 3 lines were added at the bottom
    for y in range(BOARD_HEIGHT - 3, BOARD_HEIGHT):
        assert any(
            cell == GARBAGE_COLOR for cell in game_state.board[y]
        )  # Check for garbage color
        assert (
            sum(1 for cell in game_state.board[y] if cell == EMPTY_CELL) == 1
        )  # Check for single gap

    # Check that original block moved up
    assert game_state.board[5 - 3][5] == 1
    assert (
        game_state.board[5][5] == EMPTY_CELL
    )  # Original position should be empty or garbage

    # Check applying zero garbage
    assert game_state.apply_pending_garbage() is False


def test_game_over_on_spawn_block_out(game_state):
    """Test game over when a new piece spawns and immediately collides (block out)."""
    # Fill the top rows almost completely
    for y in range(4):
        for x in range(BOARD_WIDTH):
            if y < 2 or x < 4 or x > 5:  # Leave 4x2 spawn area clear initially
                game_state.board[y][x] = 1

    # Force next piece to be 'O', which spawns with blocks at (4,0),(5,0),(4,1),(5,1)
    game_state.current_piece = Piece("O")

    # Block the spawn area and below to cause check_collision(0,0) AND check_collision(0,1) to be true
    game_state.board[1][4] = 1  # Block collision for (0,0)
    game_state.board[2][4] = 1  # Block collision for (0,1)
    game_state.board[2][5] = 1  # Block collision for (0,1)

    assert game_state.is_game_over()
    assert game_state.game_over is True


def test_game_over_on_spawn_top_out(game_state):
    """Test game NOT over when a new piece spawns colliding, but can move down (top out)."""
    # Force next piece to be 'O' - which is a 2x2 piece with shape [[2,2],[2,2]]
    game_state.current_piece = Piece("O")

    # The O piece spans positions: (4,0), (5,0), (4,1), (5,1)

    # Let's verify where the piece actually is
    assert (
        game_state.current_piece.x == 4
    )  # Center position for a 2x2 piece in a 10-wide board
    assert game_state.current_piece.y == 0

    # Block a cell where the piece is now, but NOT where it would move to
    # This is tricky - we need to create a situation where:
    # 1. There IS a collision at (0,0) - current position
    # 2. There is NO collision at (0,1) - when moved down

    # Place a block at the upper-left of the O piece (4,0)
    game_state.board[0][4] = 1

    # Make sure cells below are empty so it can move down
    game_state.board[1][4] = EMPTY_CELL
    game_state.board[1][5] = EMPTY_CELL
    game_state.board[2][4] = EMPTY_CELL
    game_state.board[2][5] = EMPTY_CELL

    # Verify a collision exists at the current position
    assert game_state.check_collision(game_state.current_piece, 0, 0) is True

    # Verify NO collision one cell down
    assert game_state.check_collision(game_state.current_piece, 0, 1) is False

    # This test says game should NOT be over (piece can still move down)
    assert not game_state.is_game_over()
    assert game_state.game_over is False


def test_game_over_no_collision(game_state):
    """Test game not over when spawn is clear."""
    # Ensure spawn area is clear
    game_state.current_piece = Piece("T")
    assert not game_state.is_game_over()
    assert game_state.game_over is False
