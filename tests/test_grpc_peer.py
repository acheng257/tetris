import pytest
import threading
import queue
import grpc
import socket
from unittest.mock import MagicMock, patch, ANY

from proto import tetris_pb2
from peer.grpc_peer import P2PNetwork


class MockResponseIterator:
    """Mock iterator for gRPC response streams"""

    def __init__(self, messages=None):
        self.messages = messages or []
        self.index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.index < len(self.messages):
            msg = self.messages[self.index]
            self.index += 1
            return msg
        raise StopIteration


@pytest.fixture
def mock_grpc_context():
    context = MagicMock()
    context.peer.return_value = "ipv4:127.0.0.1:12345"
    return context


@pytest.fixture
def mock_stub():
    stub = MagicMock()
    # Mock response iterator that can be customized by tests
    stub.Play.return_value = MockResponseIterator()
    return stub


@pytest.fixture
def patch_grpc_server():
    """Patch gRPC server creation and channel setup"""
    with patch("grpc.server") as mock_server, patch(
        "grpc.insecure_channel"
    ) as mock_channel, patch(
        "peer.grpc_peer.tetris_pb2_grpc.add_TetrisServiceServicer_to_server"
    ) as mock_add, patch(
        "peer.grpc_peer.tetris_pb2_grpc.TetrisServiceStub"
    ) as mock_stub_class:

        # Setup mock server
        server_instance = MagicMock()
        server_instance.start.return_value = None
        mock_server.return_value = server_instance

        # Setup mock channel
        mock_channel.return_value = MagicMock()

        # Setup mock stub
        stub_instance = MagicMock()
        # Default to empty response iterator
        stub_instance.Play.return_value = MockResponseIterator()
        mock_stub_class.return_value = stub_instance

        yield {
            "server": mock_server,
            "server_instance": server_instance,
            "channel": mock_channel,
            "add_servicer": mock_add,
            "stub_class": mock_stub_class,
            "stub_instance": stub_instance,
        }


@pytest.fixture
def mock_thread_start():
    """Patch threading.Thread.start to avoid spawning real threads during tests"""
    with patch("threading.Thread.start") as mock_start:
        yield mock_start


@pytest.fixture
def mock_socket_functions():
    """Mock socket functions used in _get_my_ip_addresses"""
    with patch("socket.gethostname") as mock_hostname, patch(
        "socket.gethostbyname_ex"
    ) as mock_hostbyname, patch("socket.socket") as mock_socket:

        # Configure mock returns
        mock_hostname.return_value = "testhost"
        mock_hostbyname.return_value = ("testhost", [], ["192.168.1.1", "10.0.0.1"])

        # Socket for external IP check
        socket_instance = MagicMock()
        socket_instance.getsockname.return_value = ("8.8.8.8", 12345)
        mock_socket.return_value = socket_instance

        yield {
            "hostname": mock_hostname,
            "hostbyname": mock_hostbyname,
            "socket": mock_socket,
        }


def test_init_starts_server(
    patch_grpc_server, mock_thread_start, mock_socket_functions
):
    """Test that P2PNetwork initialization starts the server"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = ["localhost:50052", "localhost:50053"]

    # Act
    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=True)

    # Assert
    patch_grpc_server["server"].assert_called_once()
    patch_grpc_server["add_servicer"].assert_called_once()
    patch_grpc_server["server_instance"].add_insecure_port.assert_called_once_with(
        listen_addr
    )
    patch_grpc_server["server_instance"].start.assert_called_once()

    # Should attempt to connect to both peers
    assert patch_grpc_server["channel"].call_count == 2
    assert patch_grpc_server["stub_class"].call_count == 2


def test_get_my_ip_addresses(mock_socket_functions):
    """Test that _get_my_ip_addresses collects IP addresses correctly"""
    # Arrange
    with patch.object(P2PNetwork, "__init__", lambda self, *args, **kwargs: None):
        network = P2PNetwork(None, None)
        network.debug_mode = False

    # Act
    ips = network._get_my_ip_addresses()

    # Assert
    assert "localhost" in ips
    assert "127.0.0.1" in ips
    assert "testhost" in ips
    assert "192.168.1.1" in ips
    assert "10.0.0.1" in ips
    assert "8.8.8.8" in ips


def test_is_self_addr():
    """Test the self address detection logic"""
    # Arrange
    with patch.object(P2PNetwork, "__init__", lambda self, *args, **kwargs: None):
        network = P2PNetwork(None, None)
        network.listen_addr = "[::]:50051"
        network.listen_port = 50051
        network.my_ips = {"localhost", "127.0.0.1", "::1", "::", "testhost"}
        network.debug_mode = False

    # Act & Assert
    # Should detect self addresses
    assert network._is_self_addr("[::]:50051", "[::]", 50051)
    assert network._is_self_addr("localhost:50051", "localhost", 50051)
    assert network._is_self_addr("127.0.0.1:50051", "127.0.0.1", 50051)
    assert network._is_self_addr("[::1]:50051", "[::1]", 50051)

    # Should not detect different ports or hosts
    assert not network._is_self_addr("localhost:50052", "localhost", 50052)
    assert not network._is_self_addr("192.168.1.1:50051", "192.168.1.1", 50051)


def test_normalize_peer_addr():
    """Test that peer addresses are normalized correctly"""
    # Arrange
    with patch.object(P2PNetwork, "__init__", lambda self, *args, **kwargs: None):
        network = P2PNetwork(None, None)
        network.debug_mode = False

    # Act & Assert
    assert network._normalize_peer_addr("localhost:50051") == "localhost:50051"
    assert network._normalize_peer_addr("LOCALHOST:50051") == "localhost:50051"
    assert network._normalize_peer_addr("ipv4:192.168.1.1:50051") == "192.168.1.1:50051"
    assert network._normalize_peer_addr("[::1]:50051") == "::1:50051"
    assert network._normalize_peer_addr("ipv6:[::1]:50051") == "::1:50051"


def test_get_peer_identity():
    """Test that peer identities are extracted correctly"""
    # Arrange
    with patch.object(P2PNetwork, "__init__", lambda self, *args, **kwargs: None):
        network = P2PNetwork(None, None)
        network.listen_port = 50051
        network.debug_mode = False

    # Act & Assert
    assert network._get_peer_identity("localhost:50051") == "localhost:50051"
    assert network._get_peer_identity("127.0.0.1:50051") == "localhost:50051"
    assert network._get_peer_identity("ipv4:127.0.0.1:50051") == "localhost:50051"
    assert network._get_peer_identity("ipv6:[::1]:50051") == "localhost:50051"
    assert network._get_peer_identity("192.168.1.1:50051") == "192.168.1.1:50051"


def test_is_duplicate_connection():
    """Test the duplicate connection detection logic"""
    # Arrange
    with patch.object(P2PNetwork, "__init__", lambda self, *args, **kwargs: None):
        network = P2PNetwork(None, None)
        network.unique_peers = {"ipv4:127.0.0.1:50051", "ipv4:192.168.1.1:50052"}
        network.lock = threading.RLock()
        network.debug_mode = False

    # Act & Assert
    # Same connection (different representation)
    assert network._is_duplicate_connection("localhost:50051")

    # Different connection
    assert not network._is_duplicate_connection("192.168.1.1:50053")


def test_broadcast(mock_thread_start, patch_grpc_server):
    """Test that broadcast sends messages to all peers"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = ["localhost:50052", "localhost:50053"]

    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=False)

    # Replace the actual queues with mocks
    mock_queue1 = MagicMock()
    mock_queue2 = MagicMock()
    network.out_queues = {
        "localhost:50052": mock_queue1,
        "localhost:50053": mock_queue2,
    }

    # Create a test message
    test_msg = tetris_pb2.TetrisMessage(
        type=tetris_pb2.GARBAGE, garbage=3, sender="TestPlayer"
    )

    # Act
    network.broadcast(test_msg)

    # Assert
    mock_queue1.put.assert_called_once_with(test_msg)
    mock_queue2.put.assert_called_once_with(test_msg)


def test_send(mock_thread_start, patch_grpc_server):
    """Test that send delivers message to a specific peer"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = ["localhost:50052", "localhost:50053"]

    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=False)

    # Replace the actual queues with mocks
    mock_queue1 = MagicMock()
    mock_queue2 = MagicMock()
    network.out_queues = {
        "localhost:50052": mock_queue1,
        "localhost:50053": mock_queue2,
    }

    # Create a test message
    test_msg = tetris_pb2.TetrisMessage(
        type=tetris_pb2.GARBAGE, garbage=3, sender="TestPlayer"
    )

    # Act
    network.send("localhost:50052", test_msg)

    # Assert
    mock_queue1.put.assert_called_once_with(test_msg)
    mock_queue2.put.assert_not_called()


def test_connect_to_peer_duplicate(mock_thread_start, patch_grpc_server):
    """Test that _connect_to_peer skips duplicate connections"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = []

    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=False)

    # Mock the _is_duplicate_connection method to always return True
    with patch.object(network, "_is_duplicate_connection", return_value=True):
        # Act
        network._connect_to_peer("localhost:50052")

        # Assert
        # Should not have created a channel or stub
        assert "localhost:50052" not in network.out_queues
        patch_grpc_server["channel"].assert_not_called()


def test_connect_to_peer_exception(mock_thread_start, patch_grpc_server):
    """Test that _connect_to_peer handles connection exceptions"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = []

    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=False)
    network.persistent_peers.add("localhost:50052")

    # Make channel creation raise an exception
    patch_grpc_server["channel"].side_effect = Exception("Connection failed")

    # Act
    with patch.object(network, "_schedule_reconnect") as mock_reconnect:
        network._connect_to_peer("localhost:50052")

        # Assert
        # Should have tried to create a channel
        patch_grpc_server["channel"].assert_called_once()
        # Should have scheduled a reconnection attempt
        mock_reconnect.assert_called_once_with("localhost:50052")


def test_recv_thread_success(mock_thread_start, patch_grpc_server):
    """Test the _recv_thread function with successful messages"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = []

    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=False)

    # Create test messages
    test_msg1 = tetris_pb2.TetrisMessage(type=tetris_pb2.READY, sender="TestPeer")
    test_msg2 = tetris_pb2.TetrisMessage(type=tetris_pb2.GARBAGE, garbage=3)
    mock_iter = MockResponseIterator([test_msg1, test_msg2])

    # Act
    network._recv_thread("localhost:50052", mock_iter)

    # Assert
    # Should have put both messages in the incoming queue
    assert network.incoming.qsize() == 2
    addr1, msg1 = network.incoming.get()
    addr2, msg2 = network.incoming.get()

    assert addr1 == "localhost:50052"
    assert addr2 == "localhost:50052"
    assert msg1 == test_msg1
    assert msg2 == test_msg2


def test_recv_thread_exception(mock_thread_start, patch_grpc_server):
    """Test the _recv_thread function with exceptions"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = []

    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=False)
    network.persistent_peers.add("localhost:50052")
    network.out_queues["localhost:50052"] = queue.Queue()
    network.unique_peers.add("localhost:50052")

    # Create a failing iterator
    class FailingIterator:
        def __iter__(self):
            return self

        def __next__(self):
            raise Exception("Iterator failed")

    # Act
    with patch.object(network, "_schedule_reconnect") as mock_reconnect:
        network._recv_thread("localhost:50052", FailingIterator())

        # Assert
        # Should have removed from out_queues
        assert "localhost:50052" not in network.out_queues
        # Should have removed from unique_peers
        assert "localhost:50052" not in network.unique_peers
        # Should have scheduled a reconnection
        mock_reconnect.assert_called_once_with("localhost:50052")


def test_schedule_reconnect(mock_thread_start, patch_grpc_server):
    """Test the reconnection scheduling logic"""
    # Arrange
    listen_addr = "[::]:50051"
    peer_addrs = []

    network = P2PNetwork(listen_addr, peer_addrs, debug_mode=False)

    # Act
    with patch("threading.Timer") as mock_timer:
        timer_instance = MagicMock()
        mock_timer.return_value = timer_instance

        network._schedule_reconnect("localhost:50052", delay=5)

        # Assert
        mock_timer.assert_called_once()
        assert mock_timer.call_args[0][0] == 5  # Delay
        timer_instance.daemon = True
        timer_instance.start.assert_called_once()
        assert "localhost:50052" in network.reconnect_timers
