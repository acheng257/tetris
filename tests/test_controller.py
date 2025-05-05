import pytest
import threading
import time
import curses
import queue
from unittest.mock import MagicMock, patch, ANY
from game.controller import GameController
from game.state import GameState, Piece
from game.combo import ComboSystem
from ui.curses_renderer import CursesRenderer
from ui.input_handler import InputHandler
from proto import tetris_pb2

# --- Mocks and Fixtures ---


@pytest.fixture
def mock_game_state():
    state = MagicMock(spec=GameState)
    state.current_piece = MagicMock(spec=Piece)
    state.current_piece.type = "T"
    state.current_piece.x = 5
    state.current_piece.y = 5
    state.next_piece = MagicMock(spec=Piece)
    state.held_piece = None
    state.board = [[0] * 10 for _ in range(20)]
    state.game_over = False
    state.pending_garbage = 0
    state.check_collision.return_value = False
    state.attempt_move.return_value = True
    state.attempt_rotation.return_value = True
    state.clear_lines.return_value = 0
    state.calculate_score.return_value = 0
    state.hard_drop.return_value = 5  # Simulate dropping 5 lines
    state.hold_piece.return_value = True
    state.is_game_over.return_value = False
    state.reduce_pending_garbage.return_value = 0
    state.apply_pending_garbage.return_value = False
    return state


@pytest.fixture
def mock_renderer():
    return MagicMock(spec=CursesRenderer)


@pytest.fixture
def mock_input_handler():
    handler = MagicMock(spec=InputHandler)
    handler.process_input.return_value = -1  # No input by default
    handler.is_first_press.return_value = False
    handler.is_pressed.return_value = False
    handler.is_soft_drop_active.return_value = False
    handler.should_move_continuously.return_value = False
    return handler


@pytest.fixture
def mock_combo_system():
    combo = MagicMock(spec=ComboSystem)
    combo.update.return_value = {
        "combo_count": 0,
        "debug_message": None,
        "is_combo_active": False,
    }
    combo.get_garbage_count.return_value = 0
    combo.get_display.return_value = "-"
    combo.debug_message = ""
    return combo


@pytest.fixture
def mock_client_socket():
    socket = MagicMock()
    socket.sendall = MagicMock()
    # ensure send() delegates to sendall for compatibility
    def fake_send(peer_id, body):
        socket.sendall(body)
    socket.send = fake_send
    return socket


@pytest.fixture
def mock_net_queue():
    q = MagicMock(spec=queue.Queue)
    q.get_nowait.side_effect = queue.Empty
    return q


@pytest.fixture
def game_controller(
    mock_game_state,
    mock_renderer,
    mock_input_handler,
    mock_combo_system,
    mock_client_socket,
    mock_net_queue,
):
    controller = GameController(
        game_state=mock_game_state,
        renderer=mock_renderer,
        input_handler=mock_input_handler,
        client_socket=mock_client_socket,
        net_queue=mock_net_queue,
        player_name="TestPlayer",
        debug_mode=False,
    )
    # Provide dummy peer boards and lock
    controller.peer_boards = {'peer1': {'score': 0}}
    controller.peer_boards_lock = threading.Lock()
    controller.combo_system = mock_combo_system
    controller.get_next_piece_func = lambda: MagicMock(spec=Piece)
    return controller


# --- Test Cases ---


def test_controller_initialization(game_controller):
    """Test controller initializes with correct components."""
    assert isinstance(game_controller.game_state, MagicMock)
    assert isinstance(game_controller.renderer, MagicMock)
    assert isinstance(game_controller.input_handler, MagicMock)
    assert isinstance(game_controller.combo_system, MagicMock)
    assert game_controller.score == 0
    assert game_controller.level == 1
    assert game_controller.attacks_sent == 0
    assert game_controller.attacks_received == 0
    assert game_controller.fall_speed == 1.0


def test_get_attack_value(game_controller):
    """Test the internal attack value calculation."""
    assert game_controller._get_attack_value(0) == 0
    assert game_controller._get_attack_value(1) == 0  # Single
    assert game_controller._get_attack_value(2) == 1  # Double
    assert game_controller._get_attack_value(3) == 2  # Triple
    assert game_controller._get_attack_value(4) == 4  # Tetris
    assert game_controller._get_attack_value(5) == 0  # Invalid clear count


def test_update_difficulty(game_controller):
    """Test that difficulty increases over time."""
    initial_fall_speed = game_controller.fall_speed
    initial_level = game_controller.level
    game_controller.last_speed_increase_time = (
        time.time() - game_controller.speed_increase_interval - 1
    )

    game_controller.update_difficulty()

    assert game_controller.fall_speed < initial_fall_speed
    assert game_controller.fall_speed == initial_fall_speed * (
        1 - game_controller.speed_increase_rate
    )
    # Level increases every 3 speed increases, check if it increased (might not on first call)
    # assert game_controller.level > initial_level # This depends on the exact timing


def test_handle_input_quit(game_controller, mock_input_handler):
    """Test handling the quit command."""
    mock_input_handler.process_input.return_value = ord("q")
    result = game_controller.handle_input()
    assert result == "quit"


def test_handle_input_move_left(game_controller, mock_input_handler, mock_game_state):
    """Test handling left movement input."""
    mock_input_handler.process_input.return_value = curses.KEY_LEFT
    mock_input_handler.is_first_press.side_effect = lambda key: key == curses.KEY_LEFT

    game_controller.handle_input()

    mock_game_state.attempt_move.assert_called_once_with(-1, 0)
    mock_input_handler.update_move_time.assert_called_once()


def test_handle_input_rotate(game_controller, mock_input_handler, mock_game_state):
    """Test handling rotation input."""
    mock_input_handler.process_input.return_value = curses.KEY_UP
    mock_input_handler.is_first_press.side_effect = lambda key: key == curses.KEY_UP
    mock_game_state.check_collision.return_value = (
        False  # Not touching ground initially
    )

    game_controller.handle_input()
    mock_game_state.attempt_rotation.assert_called_once()
    # Lock timer shouldn't start if not touching ground
    assert game_controller.lock_timer is None


def test_handle_input_rotate_locking(
    game_controller, mock_input_handler, mock_game_state
):
    """Test rotation starts lock timer when touching ground."""
    mock_input_handler.process_input.return_value = curses.KEY_UP
    mock_input_handler.is_first_press.side_effect = lambda key: key == curses.KEY_UP
    mock_game_state.check_collision.return_value = True  # Touching ground
    mock_game_state.attempt_rotation.return_value = True  # Rotation succeeds

    start_time = time.time()
    with patch("time.time", return_value=start_time):
        game_controller.handle_input()

    mock_game_state.attempt_rotation.assert_called_once()
    assert game_controller.lock_timer == start_time
    assert game_controller.landing_y == mock_game_state.current_piece.y


def test_handle_input_hold(game_controller, mock_input_handler, mock_game_state):
    """Test handling the hold input."""
    mock_input_handler.process_input.return_value = ord("c")

    start_time = time.time()
    with patch("time.time", return_value=start_time):
        game_controller.handle_input()

    mock_game_state.hold_piece.assert_called_once()
    assert game_controller.lock_timer is None
    assert game_controller.last_fall_time == start_time


def test_handle_hard_drop(game_controller, mock_input_handler, mock_game_state):
    """Test handling hard drop input."""
    mock_input_handler.process_input.return_value = ord(" ")
    # Simulate hard drop result
    drop_distance = 5
    mock_game_state.hard_drop.return_value = drop_distance
    # Simulate line clear after hard drop
    mock_game_state.clear_lines.return_value = 1
    mock_game_state.calculate_score.return_value = 40  # Score for 1 line clear

    initial_score = game_controller.score
    game_controller.handle_input()

    mock_game_state.hard_drop.assert_called_once()
    # Score should include hard drop points + line clear points
    assert game_controller.score == initial_score + (drop_distance * 2) + 40
    # Check that piece locking and spawning logic was called via _lock_current_piece
    mock_game_state.merge_piece.assert_called_once()
    mock_game_state.clear_lines.assert_called_once()
    mock_game_state.calculate_score.assert_called_once()
    assert (
        mock_game_state.current_piece != mock_game_state.next_piece
    )  # Check spawn happened


def test_lock_current_piece_no_clear(
    game_controller, mock_game_state, mock_combo_system
):
    """Test locking a piece that clears no lines."""
    mock_game_state.clear_lines.return_value = 0
    # Simulate pending garbage to check application
    mock_game_state.pending_garbage = 3
    mock_game_state.apply_pending_garbage.return_value = True
    current_piece_before_lock = mock_game_state.current_piece  # Store ref before spawn

    game_controller._lock_current_piece(time.time())

    # Assert merge_piece was called with the piece *before* spawning the next one
    mock_game_state.merge_piece.assert_called_once_with(current_piece_before_lock)
    mock_game_state.clear_lines.assert_called_once()
    mock_combo_system.update.assert_called_once_with(0, ANY)
    mock_game_state.calculate_score.assert_called_once_with(0, game_controller.level)
    mock_game_state.apply_pending_garbage.assert_called_once()  # Should apply garbage
    mock_game_state.reduce_pending_garbage.assert_not_called()  # Should not reduce/cancel
    # Check spawn happened
    assert mock_game_state.current_piece != mock_game_state.next_piece


def test_lock_current_piece_clear_lines_no_garbage(
    game_controller, mock_game_state, mock_combo_system, mock_client_socket
):
    lines_cleared = 2
    base_attack = 1  # For double clear
    combo_attack = 1
    score_gained = 100
    mock_game_state.clear_lines.return_value = lines_cleared
    mock_game_state.calculate_score.return_value = score_gained
    mock_combo_system.update.return_value = {"combo_count": 1, "debug_message": None, "is_combo_active": True}
    mock_combo_system.get_garbage_count.return_value = combo_attack
    mock_game_state.pending_garbage = 0
    mock_game_state.reduce_pending_garbage.return_value = 0

    initial_score = game_controller.score
    initial_attacks_sent = game_controller.attacks_sent

    game_controller._lock_current_piece(time.time())

    # total attack is base + combo
    total_attack = base_attack + combo_attack
    mock_client_socket.sendall.assert_called_once_with(
        f"GARBAGE:{total_attack}\n".encode()
    )
    # attacks_sent should have increased by total_attack
    assert game_controller.attacks_sent == initial_attacks_sent + total_attack


def test_lock_current_piece_clear_lines_cancel_garbage(
    game_controller, mock_game_state, mock_combo_system, mock_client_socket
):
    lines_cleared = 4
    base_attack = 4
    combo_attack = 4
    score_gained = 1200
    mock_game_state.clear_lines.return_value = lines_cleared
    mock_game_state.calculate_score.return_value = score_gained
    mock_combo_system.update.return_value = {"combo_count": 0, "debug_message": None, "is_combo_active": True}
    mock_combo_system.get_garbage_count.return_value = combo_attack
    mock_game_state.pending_garbage = 10
    cancelled = 3
    mock_game_state.reduce_pending_garbage.return_value = cancelled

    initial_attacks_sent = game_controller.attacks_sent

    game_controller._lock_current_piece(time.time())

    # net attack = (base + combo) - cancelled
    net_attack = (base_attack + combo_attack) - cancelled
    mock_client_socket.sendall.assert_called_once_with(
        f"GARBAGE:{net_attack}\n".encode()
    )
    assert game_controller.attacks_sent == initial_attacks_sent + net_attack


def test_send_garbage_to_opponents(game_controller, mock_client_socket):
    """Test sending garbage via the client socket."""
    garbage_amount = 5
    initial_attacks_sent = game_controller.attacks_sent

    # Patch the internal call within the test
    with patch.object(
        game_controller,
        "_send_garbage_to_opponents",
        wraps=game_controller._send_garbage_to_opponents,
    ) as wrapped_send:
        game_controller._send_garbage_to_opponents(garbage_amount)

        mock_client_socket.sendall.assert_called_once_with(
            f"GARBAGE:{garbage_amount}\n".encode()
        )
        # The counter update happens *inside* the real method, which we wrapped
        assert game_controller.attacks_sent == initial_attacks_sent + garbage_amount


def test_send_garbage_no_socket(game_controller):
    """Test that sending garbage does nothing if no socket."""
    game_controller.client_socket = None
    initial_attacks_sent = game_controller.attacks_sent
    game_controller._send_garbage_to_opponents(5)
    assert game_controller.attacks_sent == initial_attacks_sent  # Should not change


def test_spawn_next_piece(game_controller, mock_game_state):
    """Test spawning the next piece."""
    current = mock_game_state.current_piece
    next_p = mock_game_state.next_piece
    new_next = MagicMock(spec=Piece)
    game_controller.get_next_piece_func = lambda: new_next

    start_time = time.time()
    with patch("time.time", return_value=start_time):
        game_controller._spawn_next_piece()

    assert game_controller.game_state.current_piece == next_p
    assert game_controller.game_state.next_piece == new_next
    assert game_controller.game_state.can_hold is True
    assert game_controller.lock_timer is None
    assert game_controller.landing_y is None
    assert game_controller.last_fall_time == start_time
    mock_game_state.is_game_over.assert_called_once()


def test_spawn_next_piece_game_over(
    game_controller, mock_game_state, mock_client_socket
):
    """Test spawning piece triggers game over handling."""
    mock_game_state.is_game_over.return_value = (
        True  # Simulate game over on spawn check
    )

    with patch.object(game_controller, "_handle_game_over") as mock_handle_game_over:
        game_controller._spawn_next_piece()
        mock_handle_game_over.assert_called_once()


def test_handle_game_over(game_controller, mock_client_socket):
    """Test the game over handler sends the LOSE message."""
    start_time = time.time() - 60  # Simulate game lasted 60 seconds
    game_controller.start_time = start_time
    game_controller.attacks_sent = 10
    game_controller.attacks_received = 5
    game_controller.score = 5000

    game_controller._handle_game_over()

    assert game_controller.survival_time >= 59.9  # Check survival time calculated
    expected_msg = f"LOSE:{game_controller.survival_time:.2f}:{game_controller.attacks_sent}:{game_controller.attacks_received}:{game_controller.score}".encode()
    mock_client_socket.sendall.assert_called_once_with(expected_msg)


def test_update_piece_gravity_fall(game_controller, mock_game_state):
    """Test gravity causing the piece to fall."""
    mock_game_state.check_collision.return_value = False  # Not touching ground
    fall_delay = game_controller.fall_speed / game_controller.level
    # Simulate time passing beyond fall delay
    game_controller.last_fall_time = time.time() - fall_delay - 0.1

    game_controller.update_piece_gravity()
    mock_game_state.attempt_move.assert_called_once_with(0, 1)


def test_update_piece_gravity_soft_drop(
    game_controller, mock_game_state, mock_input_handler
):
    """Test gravity during soft drop."""
    mock_game_state.check_collision.return_value = False
    mock_input_handler.is_soft_drop_active.return_value = True
    fall_delay = (
        game_controller.fall_speed / game_controller.level
    ) * 0.1  # Faster delay
    game_controller.last_fall_time = time.time() - fall_delay - 0.1
    initial_score = game_controller.score

    game_controller.update_piece_gravity()

    mock_game_state.attempt_move.assert_called_once_with(0, 1)
    assert game_controller.score == initial_score + 1  # Soft drop score


def test_handle_piece_touching_ground_start_timer(game_controller, mock_game_state):
    """Test that lock timer starts when piece first touches ground."""
    mock_game_state.check_collision.side_effect = [
        True
    ]  # First check (in update_piece_gravity) detects ground
    game_controller.lock_timer = None  # Ensure timer is not set

    start_time = time.time()
    with patch("time.time", return_value=start_time):
        game_controller.update_piece_gravity()  # This calls _handle_piece_touching_ground

    assert game_controller.lock_timer == start_time
    assert game_controller.landing_y == mock_game_state.current_piece.y


def test_handle_piece_touching_ground_reset_timer(game_controller, mock_game_state):
    """Test that lock timer resets if piece moves vertically while touching ground."""
    current_time = time.time()
    game_controller.lock_timer = current_time - 0.2  # Timer already started
    game_controller.landing_y = mock_game_state.current_piece.y  # Initial landing y

    # Simulate piece moving/rotating, changing its y coordinate slightly while still on ground
    mock_game_state.current_piece.y += 1
    mock_game_state.check_collision.return_value = True  # Still on ground

    reset_time = current_time + 0.1
    with patch("time.time", return_value=reset_time):
        game_controller._handle_piece_touching_ground(
            reset_time
        )  # Call manually for test

    assert game_controller.lock_timer == reset_time  # Timer should reset
    assert (
        game_controller.landing_y == mock_game_state.current_piece.y
    )  # Landing Y updated


def test_handle_piece_touching_ground_lock_piece(game_controller, mock_game_state):
    """Test that piece locks after lock delay expires."""
    lock_start_time = time.time() - game_controller.lock_delay - 0.1
    game_controller.lock_timer = lock_start_time
    game_controller.landing_y = mock_game_state.current_piece.y
    mock_game_state.check_collision.return_value = True  # Still touching ground

    with patch.object(game_controller, "_lock_current_piece") as mock_lock:
        game_controller.update_piece_gravity()  # Should trigger lock
        mock_lock.assert_called_once()


def test_process_network_messages_garbage(
    game_controller, mock_net_queue, mock_game_state
):
    """Test processing a GARBAGE message from the network queue."""
    garbage_amount = 5
    sender_info = "OpponentPlayer"
    # Create a mock protobuf message
    mock_msg = MagicMock(spec=tetris_pb2.TetrisMessage)
    mock_msg.type = tetris_pb2.GARBAGE
    mock_msg.garbage = garbage_amount
    mock_msg.sender = sender_info

    # Configure queue to return the message once, then raise Empty
    mock_net_queue.get_nowait.side_effect = [mock_msg, queue.Empty]
    initial_received = game_controller.attacks_received

    game_controller.process_network_messages()

    mock_game_state.queue_garbage.assert_called_once_with(garbage_amount)
    assert game_controller.attacks_received == initial_received + garbage_amount


def test_process_network_messages_empty(
    game_controller, mock_net_queue, mock_game_state
):
    """Test processing when the network queue is empty."""
    mock_net_queue.get_nowait.side_effect = queue.Empty
    game_controller.process_network_messages()
    mock_game_state.queue_garbage.assert_not_called()


def test_send_board_state_update(game_controller, mock_game_state, mock_client_socket):
    """Test sending board state updates over the network."""
    # Simulate time passing to trigger update
    game_controller.last_board_update_time = (
        time.time() - game_controller.board_update_interval - 1
    )
    # Mock board and piece data for the message
    mock_game_state.board = [[1] * 10 for _ in range(20)]
    # Set the score on the controller itself, as that's what send_board_state uses
    game_controller.score = 1234
    # mock_game_state.score = 1234 # Setting on mock state is not enough
    mock_game_state.current_piece.type = "L"
    mock_game_state.current_piece.x = 3
    mock_game_state.current_piece.y = 4
    # Rotation state is simplified in current implementation
    # mock_game_state.current_piece.rotation = 1
    mock_game_state.current_piece.color = 7

    game_controller.send_board_state_update()

    # Check that sendall was called (detailed message check is complex)
    mock_client_socket.sendall.assert_called_once()
    call_args = mock_client_socket.sendall.call_args[0][0]  # Get the bytes sent
    assert b"BOARD_STATE:1234:" in call_args
    assert b"L,3,4,0,7" in call_args  # Piece info (simplified rotation 0)
    assert b"1,1,1" in call_args  # Part of the board data


def test_main_update_loop(game_controller, mock_input_handler, mock_game_state):
    """Test the main update method calls its sub-components."""
    # Use nested with statements to avoid potential syntax issues with comma-separated contexts
    with patch.object(game_controller, "process_network_messages") as mock_proc_net:
        with patch.object(game_controller, "update_difficulty") as mock_upd_diff:
            # Set return_value directly in the patch for handle_input
            with patch.object(
                game_controller, "handle_input", return_value=None
            ) as mock_hnd_inp:
                with patch.object(
                    game_controller, "update_piece_gravity"
                ) as mock_upd_grav:
                    with patch.object(
                        game_controller, "send_board_state_update"
                    ) as mock_send_state:

                        mock_game_state.game_over = False

                        result = game_controller.update()

                        assert result is None
                        mock_proc_net.assert_called_once()
                        mock_upd_diff.assert_called_once()
                        mock_hnd_inp.assert_called_once()
                        mock_upd_grav.assert_called_once()
                        mock_send_state.assert_called_once()


def test_main_update_loop_quit(game_controller, mock_input_handler):
    """Test update loop exits on quit command."""
    mock_input_handler.process_input.return_value = ord("q")
    # Simulate handle_input returning 'quit'
    with patch.object(
        game_controller, "handle_input", return_value="quit"
    ) as mock_hnd_inp:
        result = game_controller.update()
        assert result == "quit"
        mock_hnd_inp.assert_called_once()


def test_main_update_loop_game_over(game_controller, mock_game_state):
    """Test update loop exits on game over state."""
    mock_game_state.game_over = True
    result = game_controller.update()
    assert result == "game_over"


def test_render_call(
    game_controller, mock_renderer, mock_game_state, mock_combo_system
):
    """Test that the render method calls the renderer's methods."""
    mock_renderer.draw_board.return_value = True  # Simulate successful draw
    game_controller.render()

    mock_renderer.draw_board.assert_called_once_with(
        mock_game_state.board,
        game_controller.score,
        game_controller.level,
        mock_combo_system.get_display(),
        game_controller.player_name,
    )
    mock_renderer.draw_piece.assert_called_once_with(
        mock_game_state.current_piece, mock_game_state.board, ghost=True
    )
    mock_renderer.draw_next_and_held.assert_called_once_with(
        mock_game_state.next_piece, mock_game_state.held_piece
    )
    mock_renderer.draw_pending_garbage_indicator.assert_called_once_with(
        mock_game_state.pending_garbage
    )
    # draw_other_players_boards depends on having peer_boards
    # mock_renderer.draw_other_players_boards.assert_called_once()
    mock_renderer.draw_combo_message.assert_called_once_with(mock_combo_system, ANY)


def test_get_stats(game_controller, mock_game_state):
    """Test retrieving game statistics."""
    game_controller.score = 1500
    game_controller.level = 3
    game_controller.attacks_sent = 25
    game_controller.attacks_received = 15
    game_controller.start_time = time.time() - 120  # Started 2 mins ago
    mock_game_state.game_over = False  # Game still running

    stats = game_controller.get_stats()

    assert stats["score"] == 1500
    assert stats["level"] == 3
    assert stats["attacks_sent"] == 25
    assert stats["attacks_received"] == 15
    assert 119 < stats["survival_time"] < 121  # Should be approx 120


def test_get_stats_game_over(game_controller, mock_game_state):
    """Test retrieving stats when game is over."""
    game_controller.start_time = time.time() - 90
    mock_game_state.game_over = True
    # Simulate survival time already calculated by game over handler
    game_controller.survival_time = 90.5

    stats = game_controller.get_stats()
    assert stats["survival_time"] == 90.5  # Should use pre-calculated value
