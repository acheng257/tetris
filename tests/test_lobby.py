import pytest
import sys
from unittest.mock import patch, MagicMock, ANY, call
import queue
import threading
import time
from proto import tetris_pb2

# Import utility functions directly for testing
sys.path.insert(0, ".")
from peer.lobby import (
    extract_ip,
    flatten_board,
    unflatten_board,
    process_network_messages,
)


class TestLobbyUtils:
    """Test utility functions from the lobby module."""

    def test_flatten_board(self):
        """Test flattening a 2D board into a 1D array."""
        # Create a small test board
        board = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

        flattened = flatten_board(board)

        # Check that the board was flattened correctly
        assert flattened == [1, 2, 3, 4, 5, 6, 7, 8, 9]

    def test_unflatten_board(self):
        """Test unflattening a 1D array back into a 2D board."""
        cells = [1, 2, 3, 4, 5, 6, 7, 8, 9]
        width = 3
        height = 3

        board = unflatten_board(cells, width, height)

        # Check that the board was unflattened correctly
        assert board == [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

    def test_extract_ip_ipv4(self):
        """Test extracting IP address from a standard IPv4 peer_id."""
        peer_id = "ipv4:192.168.1.1:12345"
        result = extract_ip(peer_id)
        assert result == "192.168.1.1"

    def test_extract_ip_ipv6(self):
        """Test extracting IP address from an IPv6 peer_id."""
        peer_id = "[2001:db8::1]:12345"
        result = extract_ip(peer_id)
        assert result == "2001:db8::1"

    def test_extract_ip_localhost(self):
        """Test extracting IP address from a localhost peer_id, which should include port."""
        peer_id = "localhost:8080"
        result = extract_ip(peer_id)
        assert result == "localhost:8080"

    def test_extract_ip_localhost_ipv6(self):
        """Test extracting IP address from an IPv6 localhost peer_id."""
        peer_id = "[::1]:12345"
        result = extract_ip(peer_id)
        assert result == "localhost:12345"

    def test_extract_ip_server_listener(self):
        """Test extracting IP address from a server listener address."""
        peer_id = "[::]:"
        result = extract_ip(peer_id)
        assert result.startswith("localhost:")


@pytest.fixture
def mock_network():
    """Create a mock P2PNetwork instance."""
    mock_net = MagicMock()
    mock_net.incoming = queue.Queue()
    mock_net._normalize_peer_addr.side_effect = lambda addr: f"normalized_{addr}"
    mock_net._get_peer_identity.side_effect = lambda addr: f"identity_{addr}"
    return mock_net


class TestNetworkProcessing:
    """Test the network message processing thread."""

    def test_process_game_state_message(self, mock_network):
        """Test processing a GAME_STATE message updates peer_boards correctly."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock game state message
        board_state = tetris_pb2.BoardState(
            width=10,
            height=20,
            cells=[0] * 200,  # 10x20 empty board
            score=1000,
            player_name="TestPlayer",
        )

        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.GAME_STATE, board_state=board_state
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread (with timeout to avoid infinite loop)
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that peer_boards was updated
        with peer_boards_lock:
            assert "peer1" in peer_boards
            assert peer_boards["peer1"]["player_name"] == "TestPlayer"
            assert peer_boards["peer1"]["score"] == 1000
            assert len(peer_boards["peer1"]["board"]) == 20  # Height
            assert len(peer_boards["peer1"]["board"][0]) == 10  # Width

    def test_process_game_state_message_with_active_piece(self, mock_network):
        """Test processing a GAME_STATE message with active piece."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock game state message with active piece
        active_piece = tetris_pb2.ActivePiece(
            piece_type="I", x=4, y=0, rotation=0, color=1
        )

        board_state = tetris_pb2.BoardState(
            width=10,
            height=20,
            cells=[0] * 200,  # 10x20 empty board
            score=1000,
            player_name="TestPlayer",
            active_piece=active_piece,
        )

        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.GAME_STATE, board_state=board_state
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that peer_boards was updated with active piece
        with peer_boards_lock:
            assert "peer1" in peer_boards
            assert "active_piece" in peer_boards["peer1"]
            assert peer_boards["peer1"]["active_piece"]["type"] == "I"
            assert peer_boards["peer1"]["active_piece"]["x"] == 4
            assert peer_boards["peer1"]["active_piece"]["y"] == 0

    def test_process_ready_message(self, mock_network):
        """Test processing a READY message updates ready_peers_normalized correctly."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock ready message
        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.READY, sender="test_peer_addr"
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that ready_peers_normalized was updated
        with ready_lock:
            assert "normalized_test_peer_addr" in ready_peers_normalized

        # Check that a status update was queued
        assert not lobby_status_queue.empty()
        status_update = lobby_status_queue.get()
        assert status_update[0] == "READY"

    def test_process_start_message(self, mock_network):
        """Test processing a START message signals game_started_event correctly."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock start message with seed
        test_seed = 12345
        test_message = tetris_pb2.TetrisMessage(type=tetris_pb2.START, seed=test_seed)

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that game_started_event was set
        assert game_started_event.is_set()

        # Check that a status update was queued with the seed
        assert not lobby_status_queue.empty()
        status_update = lobby_status_queue.get()
        assert status_update[0] == "START"
        assert status_update[1] == test_seed

    def test_process_start_message_already_started(self, mock_network):
        """Test processing a START message when game already started."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        game_started_event.set()  # Game already started
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock start message with seed
        test_seed = 12345
        test_message = tetris_pb2.TetrisMessage(type=tetris_pb2.START, seed=test_seed)

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # No status update should be queued when already started
        try:
            status_update = lobby_status_queue.get(block=False)
            assert status_update[0] != "START"  # Should not receive START
        except queue.Empty:
            pass  # Expected: no message

    def test_process_lose_message(self, mock_network):
        """Test processing a LOSE message updates scores correctly."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock lose message
        test_player = "TestPlayer"
        survival_time = 60
        attacks_sent = 5
        attacks_received = 3
        final_score = 1500
        extra_data = f"{attacks_sent}:{attacks_received}:{final_score}"

        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.LOSE,
            sender=test_player,
            score=survival_time,
            extra=extra_data.encode(),
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that scores was updated
        with scores_lock:
            assert test_player in scores
            expected_score_data = f"{float(survival_time):.2f}:{attacks_sent}:{attacks_received}:{final_score}"
            assert scores[test_player] == expected_score_data

    def test_process_lose_message_invalid_format(self, mock_network):
        """Test processing a LOSE message with invalid extra data format."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock lose message with invalid extra data
        test_player = "TestPlayer"
        survival_time = 60
        invalid_extra = "not_valid_data"

        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.LOSE,
            sender=test_player,
            score=survival_time,
            extra=invalid_extra.encode(),
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Should still record score with default values for missing data
        with scores_lock:
            assert test_player in scores

    def test_process_lose_message_no_sender(self, mock_network):
        """Test processing a LOSE message with no sender field should be skipped."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock lose message with no sender
        test_message = tetris_pb2.TetrisMessage(type=tetris_pb2.LOSE, score=60)

        # Put message in network queue
        mock_network.incoming.put(("", test_message))  # Empty peer_id

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # No score should be recorded
        with scores_lock:
            assert len(scores) == 0

    def test_process_garbage_message(self, mock_network):
        """Test processing a GARBAGE message queues it for the game logic."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "not_matching_addr"  # Important! Different from sender
        all_addrs = []

        # Create a mock garbage message
        test_sender = "TestPlayer"
        garbage_lines = 3

        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.GARBAGE,
            sender="other_addr",  # Different from listen_addr
            garbage=garbage_lines,
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that message was queued for game logic
        assert not game_message_queue.empty()
        queued_message = game_message_queue.get()
        assert queued_message.type == tetris_pb2.GARBAGE
        assert queued_message.garbage == garbage_lines

    def test_process_garbage_message_own_message(self, mock_network):
        """Test processing own GARBAGE message, should be ignored."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "my_addr"  # Must match sender to test self-message
        all_addrs = []

        # Create a mock garbage message with sender matching listen_addr
        garbage_lines = 3
        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.GARBAGE,
            sender="my_addr",  # Same as listen_addr
            garbage=garbage_lines,
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Own GARBAGE messages should be ignored, nothing queued
        assert game_message_queue.empty()

    def test_process_game_results_message(self, mock_network):
        """Test processing a GAME_RESULTS message sets the results_received_event."""
        # Setup test dependencies
        game_message_queue = queue.Queue()
        lobby_status_queue = queue.Queue()
        peer_boards = {}
        peer_boards_lock = threading.Lock()
        scores = {}
        scores_lock = threading.Lock()
        ready_peers_normalized = set()
        ready_lock = threading.Lock()
        game_started_event = threading.Event()
        results_received_event = threading.Event()
        listen_addr = "[::]:"
        all_addrs = []

        # Create a mock game results message
        test_message = tetris_pb2.TetrisMessage(
            type=tetris_pb2.GAME_RESULTS, results="player1:100,player2:200"
        )

        # Put message in network queue
        mock_network.incoming.put(("peer1", test_message))

        # Start processing in a thread
        thread = threading.Thread(
            target=process_network_messages,
            args=(
                mock_network,
                game_message_queue,
                lobby_status_queue,
                peer_boards,
                peer_boards_lock,
                scores,
                scores_lock,
                ready_peers_normalized,
                ready_lock,
                game_started_event,
                results_received_event,
                listen_addr,
                all_addrs,
                True,
            ),
            daemon=True,
        )
        thread.start()

        # Wait a bit for processing
        time.sleep(0.1)

        # Check that results event was set
        assert results_received_event.is_set()

        # Check that a status update was queued
        assert not lobby_status_queue.empty()
        status_update = lobby_status_queue.get()
        assert status_update[0] == "RESULTS"


@patch("curses.wrapper")
@patch("peer.grpc_peer.P2PNetwork")
@patch("game.tetris_game.init_colors")
@patch("threading.Thread")
def test_run_lobby_ui_and_game(mock_thread, mock_init_colors, mock_p2p, mock_wrapper):
    """Test the main entry point run_lobby_ui_and_game function."""
    from peer.lobby import run_lobby_ui_and_game

    # Call the function
    run_lobby_ui_and_game(12345, ["peer1:12345"], "TestPlayer", True)

    # Check that curses.wrapper was called with the correct wrapper function
    mock_wrapper.assert_called_once()
    assert mock_wrapper.call_args[0][1] == 12345  # Port
    assert mock_wrapper.call_args[0][2] == ["peer1:12345"]  # Peers
    assert mock_wrapper.call_args[0][3] == "TestPlayer"  # Player name
    assert mock_wrapper.call_args[0][4] is True  # Debug mode
