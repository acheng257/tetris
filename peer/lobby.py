import sys
import select
import random
import queue
import time
import threading
import socket
from proto import tetris_pb2
from peer.grpc_peer import P2PNetwork
from tetris_game import create_piece_generator, run_game


def generate_random_name():
    """Generate a random player name"""
    adjectives = [
        "Cool",
        "Swift",
        "Mighty",
        "Quick",
        "Brave",
        "Agile",
        "Epic",
        "Fast",
        "Grand",
        "Noble",
        "Rapid",
        "Super",
        "Power",
        "Prime",
        "Elite",
        "Neon",
        "Pixel",
        "Cyber",
        "Retro",
        "Hyper",
        "Ultra",
        "Mega",
        "Alpha",
        "Beta",
    ]

    nouns = [
        "Player",
        "Master",
        "Knight",
        "Falcon",
        "Tiger",
        "Dragon",
        "Eagle",
        "Wolf",
        "Wizard",
        "Hunter",
        "Ninja",
        "Gamer",
        "Hero",
        "Legend",
        "Warrior",
        "Commander",
        "Captain",
        "Pilot",
        "Ranger",
        "Titan",
        "Phoenix",
        "Cobra",
        "Viper",
        "Monarch",
    ]

    return f"{random.choice(adjectives)}{random.choice(nouns)}"


def flatten_board(board):
    """Convert 2D board array to flattened array for protobuf message"""
    return [cell for row in board for cell in row]


def unflatten_board(cells, width, height):
    """Convert flattened array back to 2D board array"""
    board = []
    for y in range(height):
        row = cells[y * width : (y + 1) * width]
        board.append(row)
    return board


def normalize_peer_address(peer_addr):
    """
    Normalize a peer address to a consistent format for comparison.
    Handles various formats like 'ipv4:1.2.3.4:5000', 'localhost:5000', '1.2.3.4:5000', '[::]:5000'.

    Returns a normalized string that can be used for deduplication.
    """
    # If it has a protocol prefix like 'ipv4:' or 'ipv6:', remove it
    if ":" in peer_addr and peer_addr.split(":", 1)[0] in ("ipv4", "ipv6"):
        peer_addr = peer_addr.split(":", 1)[1]

    # Handle localhost by extracting just the port
    if peer_addr.startswith("localhost:"):
        return f"port:{peer_addr.split(':')[1]}"

    # Handle the [::] IPv6 listener address - this is the local machine
    if peer_addr.startswith("[::]:"):
        port = peer_addr.split(":")[-1]
        # Return a special format for the listener
        return f"listener:{port}"

    # For IP addresses, extract just the IP and port
    parts = peer_addr.split(":")
    if len(parts) >= 2:
        # Get the last part as the port
        port = parts[-1]
        # Get the rest as the address
        address = ":".join(parts[:-1])
        return f"{address.lower()}:{port}"

    return peer_addr.lower()


def main(listen_port, peer_addrs):
    listen_addr = f"[::]:{listen_port}"
    net = P2PNetwork(listen_addr, peer_addrs)

    # Generate a random player name
    player_name = generate_random_name()
    print(f"You are playing as: {player_name}")

    # Store hostname to avoid having to repeat this
    hostname = socket.gethostname()

    # Full list of peer addresses (including this one)
    all_addrs = sorted(set(peer_addrs))  # Use a set to deduplicate addresses

    # The total number of expected peers (including self)
    expected_peers = len(all_addrs)
    print(f"[LOBBY] Expecting {expected_peers} total peers")

    # Dictionary to store the current board state of all peers
    peer_boards = {}
    peer_boards_lock = threading.Lock()

    # Queue for forwarding GARBAGE messages to the game
    game_message_queue = queue.Queue()

    # Track unique peers that are ready
    ready_peers = set()
    ready_lock = threading.Lock()
    # Dictionary to map normalized peer addresses to their original form
    peer_address_map = {}
    # Set to track unique IP addresses (without port) that are ready
    unique_ips = set()

    # Helper function to extract IP from peer_id
    def extract_ip(peer_id):
        """
        Extract the IP part from a peer_id for uniqueness checking.
        Special handling for localhost to allow multiple local instances.
        """
        # Remove protocol prefix if present
        if ":" in peer_id and peer_id.split(":", 1)[0] in ("ipv4", "ipv6"):
            peer_id = peer_id.split(":", 1)[1]

        # Handle special cases - for localhost, include the port for uniqueness
        if peer_id.startswith("[::]:"):
            return f"localhost:{peer_id.split(':')[-1]}"
        if peer_id.startswith("localhost:"):
            return peer_id  # Keep as is to differentiate local instances

        # Extract IP without port for non-localhost addresses
        parts = peer_id.split(":")
        if len(parts) >= 2:
            # The IP is everything except the last part (port)
            return ":".join(parts[:-1]).lower()

        return peer_id.lower()

    # Thread to process incoming game state messages
    def process_game_states():
        nonlocal seed
        while True:
            try:
                peer_id, msg = net.incoming.get(timeout=0.1)
                if msg.type == tetris_pb2.GAME_STATE:
                    with peer_boards_lock:
                        board_state = {
                            "board": unflatten_board(
                                msg.board_state.cells,
                                msg.board_state.width,
                                msg.board_state.height,
                            ),
                            "score": msg.board_state.score,
                            "player_name": msg.board_state.player_name,
                            "timestamp": time.time(),
                        }

                        # Add active piece information if present
                        if msg.board_state.HasField("active_piece"):
                            board_state["active_piece"] = {
                                "type": msg.board_state.active_piece.piece_type,
                                "x": msg.board_state.active_piece.x,
                                "y": msg.board_state.active_piece.y,
                                "rotation": msg.board_state.active_piece.rotation,
                                "color": msg.board_state.active_piece.color,
                            }

                        peer_boards[peer_id] = board_state
                elif msg.type == tetris_pb2.READY:
                    with ready_lock:
                        # Normalize the peer address for comparison
                        normalized_peer_id = normalize_peer_address(peer_id)

                        # Extract just the IP part for uniqueness check
                        ip = extract_ip(peer_id)

                        # Check if this IP is already in our tracked set
                        if ip in unique_ips:
                            print(
                                f"[LOBBY DEBUG] Ignoring duplicate READY from {peer_id} (IP {ip} already registered)"
                            )
                        else:
                            # This is a new unique peer
                            unique_ips.add(ip)
                            peer_address_map[normalized_peer_id] = peer_id
                            ready_peers.add(peer_id)
                            print(
                                f"[LOBBY] {peer_id} READY ({len(unique_ips)}/{expected_peers})"
                            )
                elif msg.type == tetris_pb2.START:
                    seed = msg.seed
                    print(f"[LOBBY] Received START, seed = {seed}")
                    game_started_event.set()
                elif msg.type == tetris_pb2.LOSE:
                    if peer_id not in scores:
                        # Handle LOSE message with survival time and attacks data
                        survival_time = msg.score
                        attacks_data = ""

                        # Check for additional attack data in the extra field
                        if hasattr(msg, "extra") and msg.extra:
                            try:
                                attacks_data = msg.extra.decode()
                            except Exception:
                                pass

                        # Store the result data: survival_time:attacks_sent:attacks_received
                        result_data = f"{survival_time:.2f}"
                        if attacks_data:
                            result_data += f":{attacks_data}"

                        scores[peer_id] = result_data

                        # Get player name if available
                        player = peer_boards.get(peer_id, {}).get(
                            "player_name", peer_id
                        )

                        # Parse and display the data
                        parts = result_data.split(":")
                        survival_time = float(parts[0])
                        attacks_sent = int(parts[1]) if len(parts) > 1 else 0
                        attacks_received = int(parts[2]) if len(parts) > 2 else 0

                        print(
                            f"[RESULTS] {player} survived for {survival_time:.1f}s (Attacks: {attacks_sent}→, {attacks_received}←)"
                        )
                elif msg.type == tetris_pb2.GAME_RESULTS:
                    print("=== FINAL RESULTS ===")
                    print(msg.results)
                    print("=====================")
                    results_received = True
                    results_received_event.set()
                elif msg.type == tetris_pb2.GARBAGE:
                    if peer_id != listen_addr:  # Don't apply our own garbage
                        print(
                            f"[LOBBY DEBUG] Received GARBAGE message from {peer_id}: {msg.garbage} lines"
                        )
                        try:
                            # Put GARBAGE message in queue for game to consume
                            game_message_queue.put(f"GARBAGE:{msg.garbage}")
                            print(
                                f"[LOBBY DEBUG] Queued garbage for game: {msg.garbage} lines"
                            )
                        except Exception as e:
                            print(f"[LOBBY DEBUG] Error queueing garbage: {e}")
                    else:
                        print(
                            f"[LOBBY DEBUG] Ignored own GARBAGE message: {msg.garbage} lines"
                        )
            except queue.Empty:
                pass
            except Exception as e:
                print(f"[LOBBY ERROR] Error processing message from {peer_id}: {e}")
                import traceback

                print(f"[LOBBY ERROR] Traceback: {traceback.format_exc()}")

    # Start game state processing thread
    game_state_thread = threading.Thread(target=process_game_states, daemon=True)
    game_state_thread.start()

    while True:
        # Reset state each round
        with ready_lock:
            ready_peers.clear()
            peer_address_map.clear()
            unique_ips.clear()
        game_started = False
        game_started_event = threading.Event()
        seed = None
        results_received = False
        results_received_event = threading.Event()

        # Clear peer boards between games
        with peer_boards_lock:
            peer_boards.clear()

        print(
            "Type 'ready' to join lobby. Game will start automatically when all peers are ready."
        )

        while not game_started:
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                cmd = sys.stdin.readline().strip().lower()
                if cmd == "ready":
                    net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.READY))
                    with ready_lock:
                        # Normalize our own address
                        normalized_addr = normalize_peer_address(listen_addr)
                        # Extract just the IP part
                        ip = extract_ip(listen_addr)

                        if ip not in unique_ips:
                            unique_ips.add(ip)
                            peer_address_map[normalized_addr] = listen_addr
                            ready_peers.add(listen_addr)
                            print(
                                f"[LOBBY] You are READY ({len(unique_ips)}/{expected_peers})"
                            )
                        else:
                            print(f"[LOBBY DEBUG] You are already marked as READY")
                elif cmd == "peers":
                    # Print all peers that are ready and their normalized addresses
                    with ready_lock:
                        print("\n=== PEER ADDRESSES ===")
                        print(f"Expected peers: {expected_peers}")
                        print(f"Ready peers count: {len(ready_peers)}")
                        print(f"Unique IPs count: {len(unique_ips)}")

                        print("\nReady peers (Original addresses):")
                        for idx, peer in enumerate(sorted(ready_peers), 1):
                            print(f"{idx}. {peer} (IP: {extract_ip(peer)})")

                        print("\nNormalized address mapping:")
                        for idx, (norm_addr, orig_addr) in enumerate(
                            sorted(peer_address_map.items()), 1
                        ):
                            print(f"{idx}. {norm_addr} -> {orig_addr}")

                        print("\nUnique IPs:")
                        for idx, ip in enumerate(sorted(unique_ips), 1):
                            print(f"{idx}. {ip}")
                        print("=====================\n")
                elif cmd == "quit":
                    print("[LOBBY] Exiting...")
                    sys.exit(0)
                else:
                    print("[LOBBY] Unknown command. Use 'ready', 'peers', or 'quit'.")

            # Check if all expected peers are ready
            with ready_lock:
                if not game_started and len(unique_ips) >= expected_peers:
                    # Generate a deterministic seed based on the sorted list of peer IPs
                    # This ensures all peers generate the same seed without a leader
                    seed_source = ",".join(sorted(unique_ips))
                    seed = hash(seed_source) % 1000000

                    # Broadcast START to all peers
                    net.broadcast(
                        tetris_pb2.TetrisMessage(type=tetris_pb2.START, seed=seed)
                    )
                    game_started = True
                    game_started_event.set()
                    print(
                        f"[LOBBY] All players ready! Game starting automatically with seed = {seed}"
                    )

            # Wait for game start or check again in a short time
            game_started = game_started_event.wait(0.1)

        print("=== GAME STARTED ===")
        get_next_piece = create_piece_generator(seed)

        class NetQueueAdapter(queue.Queue):
            def get_nowait(self):
                try:
                    # First check for game messages (GARBAGE, etc)
                    return game_message_queue.get_nowait()
                except queue.Empty:
                    # If no game messages, get from network
                    _, msg = net.incoming.get_nowait()
                    return msg

        class PeerSocket:
            def sendall(self, data: bytes):
                s = data.decode().strip()
                if s.startswith("GARBAGE:"):
                    n = int(s.split(":", 1)[1])
                    print(f"[PEER SOCKET DEBUG] Game sent GARBAGE message: {n} lines")
                    if n > 0:
                        net.broadcast(
                            tetris_pb2.TetrisMessage(
                                type=tetris_pb2.GARBAGE,
                                garbage=n,
                                sender=listen_addr,  # Include sender for self-identification
                                extra=(
                                    player_name.encode() if player_name else b""
                                ),  # Include player name for better debug messages
                            )
                        )
                        print(
                            f"[PEER SOCKET DEBUG] Broadcast GARBAGE message to network: {n} lines"
                        )
                elif s.startswith("LOSE:"):
                    sc = int(s.split(":", 1)[1])
                    net.broadcast(
                        tetris_pb2.TetrisMessage(type=tetris_pb2.LOSE, score=sc)
                    )
                elif s.startswith("BOARD_STATE:"):
                    # Expected format: "BOARD_STATE:score:flattened_board:piece_info"
                    # Where piece_info is "piece_type,x,y,rotation,color" or "NONE" if no active piece
                    parts = s.split(":", 3)
                    if len(parts) == 4:
                        score = int(parts[1])
                        board_cells = [int(cell) for cell in parts[2].split(",")]
                        piece_info = parts[3]

                        # Create BoardState message
                        board_state = tetris_pb2.BoardState(
                            cells=board_cells,
                            width=10,  # BOARD_WIDTH
                            height=20,  # BOARD_HEIGHT
                            score=score,
                            player_name=player_name,
                        )

                        # Add active piece if there is one
                        if piece_info != "NONE":
                            piece_parts = piece_info.split(",")
                            if len(piece_parts) == 5:
                                piece_type, x, y, rotation, color = piece_parts
                                active_piece = tetris_pb2.ActivePiece(
                                    piece_type=piece_type,
                                    x=int(x),
                                    y=int(y),
                                    rotation=int(rotation),
                                    color=int(color),
                                )
                                board_state.active_piece.CopyFrom(active_piece)

                        # Broadcast the message
                        net.broadcast(
                            tetris_pb2.TetrisMessage(
                                type=tetris_pb2.GAME_STATE, board_state=board_state
                            )
                        )

        # Pass peer_boards and player name to the game to display other players' boards
        final_score = run_game(
            get_next_piece,
            PeerSocket(),
            NetQueueAdapter(),
            listen_port,
            peer_boards,
            peer_boards_lock,
            player_name,
        )
        print(
            f"[RESULTS] Your stats: Survival Time = {final_score['survival_time']:.1f}s, Attacks: {final_score['attacks_sent']}→, {final_score['attacks_received']}←"
        )

        net.broadcast(
            tetris_pb2.TetrisMessage(
                type=tetris_pb2.LOSE,
                score=int(final_score["survival_time"]),
                extra=f"{final_score['attacks_sent']}:{final_score['attacks_received']}".encode(),
            )
        )

        scores = {
            listen_addr: f"{final_score['survival_time']:.2f}:{final_score['attacks_sent']}:{final_score['attacks_received']}"
        }
        results_timeout = time.time() + 10  # 10 second timeout

        while len(scores) < len(all_addrs) and time.time() < results_timeout:
            try:
                peer_id, msg = net.incoming.get(timeout=0.5)
                if msg.type == tetris_pb2.LOSE and peer_id not in scores:
                    scores[peer_id] = msg.score
                    player = peer_boards.get(peer_id, {}).get("player_name", peer_id)
                    print(f"[RESULTS] {player} scored = {msg.score}")
                elif msg.type == tetris_pb2.GAME_RESULTS:
                    print("=== FINAL RESULTS ===")
                    print(msg.results)
                    print("=====================")
                    results_received = True
                    results_received_event.set()
                    break
            except queue.Empty:
                continue

        # Wait for results or timeout
        results_received = results_received_event.wait(5)

        # Everyone broadcasts their own results
        if not results_received:
            # First, broadcast our own score for any peers that might have missed it
            net.broadcast(
                tetris_pb2.TetrisMessage(
                    type=tetris_pb2.LOSE,
                    score=int(final_score["survival_time"]),
                    extra=f"{final_score['attacks_sent']}:{final_score['attacks_received']}".encode(),
                )
            )

            # Create a mapping from peer_id to player name
            player_names = {}
            with peer_boards_lock:
                for pid, data in peer_boards.items():
                    if "player_name" in data:
                        player_names[pid] = data["player_name"]

            # Include current player
            player_names[listen_addr] = player_name

            # Format results with player names and survival time
            results_list = []
            for pid, result_data in sorted(
                scores.items(), key=lambda x: -float(x[1].split(":")[0])
            ):
                player = player_names.get(pid, pid)

                # Parse the result data (survival time and attacks)
                result_parts = result_data.split(":")
                survival_time = float(result_parts[0])

                # Get attacks data if available
                attacks_sent = int(result_parts[1]) if len(result_parts) > 1 else 0
                attacks_received = int(result_parts[2]) if len(result_parts) > 2 else 0

                # Format as: "PlayerName: 120.5s (Attacks: 15→, 8←)"
                results_list.append(
                    f"{player}: {survival_time:.1f}s (Attacks: {attacks_sent}→, {attacks_received}←)"
                )

            results_str = " | ".join(results_list)

            # Everyone broadcasts results to ensure all peers have them
            net.broadcast(
                tetris_pb2.TetrisMessage(
                    type=tetris_pb2.GAME_RESULTS, results=results_str
                )
            )

            print("=== FINAL RESULTS ===")
            print(results_str)
            print("=====================")

        while not net.incoming.empty():
            try:
                net.incoming.get_nowait()
            except queue.Empty:
                break

        print("Returning to lobby for a new game...")
