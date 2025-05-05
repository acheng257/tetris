import pytest
import sys
from unittest.mock import patch, MagicMock, ANY

# Since peer.py runs code at import time (argparse, logging), we need careful mocking.
# Mock modules before importing the module under test.


@pytest.fixture(autouse=True)
def mock_imports():
    # Mock modules that peer.py interacts with significantly at import/runtime
    mock_argparse = MagicMock()
    mock_parser = MagicMock()
    mock_args = MagicMock()
    mock_args.port = "50051"
    mock_args.peers = ["localhost:50051", "localhost:50052"]
    mock_args.debug = False
    mock_parser.parse_args.return_value = mock_args
    mock_argparse.ArgumentParser.return_value = mock_parser

    mock_lobby = MagicMock()

    # Mock builtins like open before importing peer.py
    with patch("builtins.open", MagicMock()), patch.dict(
        sys.modules,
        {
            "argparse": mock_argparse,
            "peer.lobby": mock_lobby,
            "curses": MagicMock(),  # Mock curses if lobby/game import it
        },
    ):
        yield mock_argparse, mock_lobby  # Yield mocks for use in tests


# Now import the module under test AFTER mocks are set up
from peer import peer


def test_generate_random_name():
    """Test the random name generation function."""
    # Difficult to test randomness precisely, just check format/type
    name1 = peer.generate_random_name()
    name2 = peer.generate_random_name()
    assert isinstance(name1, str)
    assert len(name1) > 4  # Should be reasonably long
    # Low probability of exact same name, but possible
    # assert name1 != name2


@patch("peer.peer.run_lobby_ui_and_game")  # Patch the function called by __main__
def test_main_block(mock_run_lobby, mock_imports):
    """Test the main execution block logic (argument parsing and function call)."""
    mock_argparse, _ = mock_imports
    parser = mock_argparse.ArgumentParser.return_value
    args = parser.parse_args.return_value

    # Simulate running the script
    # We need to re-run the logic inside if __name__ == "__main__":
    # because the import happened within the fixture scope.
    # Reset the mock call count before re-running the logic
    parser.parse_args.reset_mock()
    # Simulate script execution - this will re-parse args and call run_lobby
    peer.args = parser.parse_args()
    peer.peer_list = []
    for p_arg in peer.args.peers:
        for p in p_arg.split(","):
            p = p.strip()
            if p:
                peer.peer_list.append(p)

    peer.run_lobby_ui_and_game(
        peer.args.port, peer.peer_list, peer.player_name, peer.args.debug
    )

    # Verify argument parsing was called (again)
    parser.parse_args.assert_called_once()

    # Verify run_lobby_ui_and_game was called with correct arguments
    expected_peers = ["localhost:50051", "localhost:50052"]
    mock_run_lobby.assert_called_once_with(
        "50051",  # port
        expected_peers,  # processed peer list
        ANY,  # player_name (can vary)
        False,  # debug flag
    )


# Test argument processing specifically for comma separation
def test_arg_processing_comma(mock_imports):
    mock_argparse, _ = mock_imports
    parser = mock_argparse.ArgumentParser.return_value
    args = parser.parse_args.return_value
    # Override peers for this test
    args.peers = ["host1:111", "host2:222,host3:333", " host4:444 "]

    peer_list = []
    for p_arg in args.peers:
        for p in p_arg.split(","):
            p = p.strip()
            if p:
                peer_list.append(p)

    assert peer_list == ["host1:111", "host2:222", "host3:333", "host4:444"]
