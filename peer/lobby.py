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


def main(listen_port, peer_addrs):
    listen_addr = f"[::]:{listen_port}"
    net = P2PNetwork(listen_addr, peer_addrs)

    # Generate a random player name
    player_name = generate_random_name()
    print(f"You are playing as: {player_name}")

    # Store hostname to avoid having to repeat this
    hostname = socket.gethostname()

    # Full list of peer addresses (including this one)
    all_addrs = sorted(peer_addrs)

    # Dictionary to store the current board state of all peers
    peer_boards = {}
    peer_boards_lock = threading.Lock()

    # Thread to process incoming game state messages
    def process_game_states():
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
                    ready.add(peer_id)
                    print(f"[LOBBY] {peer_id} READY ({len(ready)}/{len(all_addrs)})")
                elif msg.type == tetris_pb2.START:
                    seed = msg.seed
                    game_started = True
                    print(f"[LOBBY] Received START, seed = {seed}")
                    game_started_event.set()
                elif msg.type == tetris_pb2.LOSE:
                    if peer_id not in scores:
                        scores[peer_id] = msg.score
                        player = peer_boards.get(peer_id, {}).get(
                            "player_name", peer_id
                        )
                        print(f"[RESULTS] {player} scored = {msg.score}")
                elif msg.type == tetris_pb2.GAME_RESULTS:
                    print("=== FINAL RESULTS ===")
                    print(msg.results)
                    print("=====================")
                    results_received = True
                    results_received_event.set()
            except queue.Empty:
                pass
            except Exception as e:
                print(f"Error processing messages: {e}")

    # Start game state processing thread
    game_state_thread = threading.Thread(target=process_game_states, daemon=True)
    game_state_thread.start()

    while True:
        # Reset state each round
        ready = set()
        game_started = False
        game_started_event = threading.Event()
        seed = None
        results_received = False
        results_received_event = threading.Event()

        # Clear peer boards between games
        with peer_boards_lock:
            peer_boards.clear()

        print("Type 'ready' to join lobby. Once everyone is ready, leader auto-starts.")

        while not game_started:
            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                cmd = sys.stdin.readline().strip().lower()
                if cmd == "ready":
                    net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.READY))
                    ready.add(listen_addr)
                    print(f"[LOBBY] You are READY ({len(ready)}/{len(all_addrs)})")
                elif cmd == "start":
                    leader = min(all_addrs)
                    if listen_addr == leader or f"localhost:{listen_port}" == leader:
                        if len(ready) == len(all_addrs):
                            seed = random.randint(0, 1_000_000)
                            net.broadcast(
                                tetris_pb2.TetrisMessage(
                                    type=tetris_pb2.START, seed=seed
                                )
                            )
                            game_started = True
                            game_started_event.set()
                            print(f"[LOBBY] You (leader) START, seed = {seed}")
                        else:
                            print(
                                f"[LOBBY] Cannot start: waiting for {len(all_addrs) - len(ready)} more players to be ready"
                            )
                    else:
                        print(f"[LOBBY] Only leader ({leader}) can START")
                elif cmd == "quit":
                    print("[LOBBY] Exiting...")
                    sys.exit(0)
                else:
                    print("[LOBBY] Unknown command. Use 'ready', 'start', or 'quit'.")

            if not game_started and len(ready) == len(all_addrs):
                leader = min(all_addrs)
                if listen_addr == leader or f"localhost:{listen_port}" == leader:
                    seed = random.randint(0, 1_000_000)
                    net.broadcast(
                        tetris_pb2.TetrisMessage(type=tetris_pb2.START, seed=seed)
                    )
                    game_started = True
                    game_started_event.set()
                    print(f"[LOBBY] All ready. Leader auto START, seed = {seed}")

            # Wait for game start or check again in a short time
            game_started = game_started_event.wait(0.1)

        print("=== GAME STARTED ===")
        get_next_piece = create_piece_generator(seed)

        class NetQueueAdapter(queue.Queue):
            def get_nowait(self):
                _, msg = net.incoming.get_nowait()
                return msg

        class PeerSocket:
            def sendall(self, data: bytes):
                s = data.decode().strip()
                if s.startswith("GARBAGE:"):
                    n = int(s.split(":", 1)[1])
                    if n > 0:
                        net.broadcast(
                            tetris_pb2.TetrisMessage(
                                type=tetris_pb2.GARBAGE,
                                garbage=n,
                                sender=listen_addr,  # Include sender for self-identification
                            )
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
        print(f"[RESULTS] Your score = {final_score}")

        net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.LOSE, score=final_score))

        scores = {listen_addr: final_score}
        results_timeout = time.time() + 10  # 10 second timeout

        leader = min(all_addrs)
        is_leader = listen_addr == leader or f"localhost:{listen_port}" == leader

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

        # Leader broadcasts results - modified to use player names when available
        if is_leader and not results_received:
            # Create a mapping from peer_id to player name
            player_names = {}
            with peer_boards_lock:
                for pid, data in peer_boards.items():
                    if "player_name" in data:
                        player_names[pid] = data["player_name"]

            # Include current player
            player_names[listen_addr] = player_name

            # Format results with player names when available
            results_list = []
            for pid, sc in sorted(scores.items(), key=lambda x: -x[1]):
                player = player_names.get(pid, pid)
                results_list.append(f"{player}: {sc}")

            results_str = " | ".join(results_list)

            net.broadcast(
                tetris_pb2.TetrisMessage(
                    type=tetris_pb2.GAME_RESULTS, results=results_str
                )
            )
            print(f"[RESULTS] Leader broadcasting = {results_str}")

        # Wait for results or timeout
        results_received = results_received_event.wait(5)

        if not results_received:
            print("=== PARTIAL RESULTS (timeout) ===")
            # Create a mapping from peer_id to player name
            player_names = {}
            with peer_boards_lock:
                for pid, data in peer_boards.items():
                    if "player_name" in data:
                        player_names[pid] = data["player_name"]

            # Include current player
            player_names[listen_addr] = player_name

            sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
            for peer_id, score in sorted_scores:
                player = player_names.get(peer_id, peer_id)
                print(f"{player}: {score}")
            print("================================")

        while not net.incoming.empty():
            try:
                net.incoming.get_nowait()
            except queue.Empty:
                break

        print("Returning to lobby for a new game...")
