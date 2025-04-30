import argparse
from peer.lobby import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2P Tetris Peer")
    parser.add_argument("--port", required=True, help="Port to listen on (e.g. 50051)")
    parser.add_argument(
        "--peers",
        nargs="+",
        required=True,
        help="List of peer addresses (host:port) including yourself. Can be space or comma separated.",
    )
    args = parser.parse_args()

    # Process peer list to handle both space and comma separation
    peer_list = []
    for peer in args.peers:
        # Split by comma and strip whitespace
        for p in peer.split(","):
            p = p.strip()
            if p:  # Only add non-empty strings
                peer_list.append(p)

    print(f"[DEBUG] Processed peer list: {peer_list}")
    main(args.port, peer_list)
