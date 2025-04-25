import argparse
from peer.lobby import main

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P2P Tetris Peer')
    parser.add_argument(
        '--port', required=True,
        help='Port to listen on (e.g. 50051)'
    )
    parser.add_argument(
        '--peers', nargs='+', required=True,
        help='List of peer addresses (host:port) including yourself'
    )
    args = parser.parse_args()

    main(args.port, args.peers)