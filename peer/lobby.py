import sys
import select
import random
import queue
import time
import threading
import socket
import curses
from proto import tetris_pb2
from peer.grpc_peer import P2PNetwork
from tetris_game import create_piece_generator, run_game

# Global debug flag
DEBUG_MODE = False


def show_curses_menu(
    stdscr, listen_addr, net, ready_lock, ready_peers, unique_ips, expected_peers
):
    """Show a curses-based menu for the lobby"""
    global DEBUG_MODE
    curses.curs_set(0)  # Hide cursor
    stdscr.clear()
    stdscr.refresh()

    # Set up colors
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Ready
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Peers
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Net
    curses.init_pair(4, curses.COLOR_MAGENTA, curses.COLOR_BLACK)  # Debug
    curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)  # Quit
    curses.init_pair(6, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Selected item

    # Menu options
    menu_items = ["Ready", "Peers", "Net", "Toggle Debug", "Quit"]
    selected_row = 0

    # Function to display menu
    def draw_menu():
        h, w = stdscr.getmaxyx()
        stdscr.clear()

        # Title
        title = "P2P Tetris Lobby"
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(1, (w - len(title)) // 2, title)
        stdscr.attroff(curses.A_BOLD)

        # Status
        with ready_lock:
            status = f"Status: {len(unique_ips)}/{expected_peers} players ready"
        stdscr.addstr(3, (w - len(status)) // 2, status)

        # Debug status
        debug_status = f"Debug Mode: {'ON' if DEBUG_MODE else 'OFF'}"
        stdscr.addstr(4, (w - len(debug_status)) // 2, debug_status)

        # Menu items
        menu_y = 6
        for idx, item in enumerate(menu_items):
            color = idx + 1  # Match color pairs defined above
            x = w // 2 - len(item) // 2
            if idx == selected_row:
                stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
                stdscr.addstr(menu_y + idx, x, item)
                stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)
            else:
                stdscr.attron(curses.color_pair(color))
                stdscr.addstr(menu_y + idx, x, item)
                stdscr.attroff(curses.color_pair(color))

        # Instructions
        instr = "Use arrow keys to navigate, Enter to select"
        stdscr.addstr(menu_y + len(menu_items) + 2, (w - len(instr)) // 2, instr)

        stdscr.refresh()

    # Function to handle peers display
    def show_peers():
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # Title
        title = "Peer Addresses"
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(1, (w - len(title)) // 2, title)
        stdscr.attroff(curses.A_BOLD)

        # Content
        with ready_lock:
            lines = []
            lines.append(f"Expected peers: {expected_peers}")
            lines.append(f"Ready peers count: {len(ready_peers)}")
            lines.append(f"Unique IPs count: {len(unique_ips)}")
            lines.append("")
            lines.append("Ready peers:")

            for idx, peer in enumerate(sorted(ready_peers), 1):
                identity = net._get_peer_identity(peer)
                lines.append(f"{idx}. {peer} (Identity: {identity})")

            lines.append("")
            lines.append("Unique IPs:")
            for idx, ip in enumerate(sorted(unique_ips), 1):
                lines.append(f"{idx}. {ip}")

        # Display content with scrolling if needed
        start_y = 3
        max_lines = h - 5  # Reserve space for title and footer
        scroll_offset = 0

        # Handle scrolling
        while True:
            stdscr.clear()
            stdscr.attron(curses.A_BOLD)
            stdscr.addstr(1, (w - len(title)) // 2, title)
            stdscr.attroff(curses.A_BOLD)

            # Show content
            for i in range(min(max_lines, len(lines) - scroll_offset)):
                if scroll_offset + i < len(lines):
                    try:
                        stdscr.addstr(start_y + i, 2, lines[scroll_offset + i])
                    except curses.error:
                        pass  # Ignore errors if line doesn't fit

            # Footer
            footer = "↑↓: Scroll | q: Back to menu"
            try:
                stdscr.addstr(h - 2, (w - len(footer)) // 2, footer)
            except curses.error:
                pass

            stdscr.refresh()

            # Get user input
            key = stdscr.getch()
            if key == ord("q"):
                break
            elif key == curses.KEY_UP and scroll_offset > 0:
                scroll_offset -= 1
            elif key == curses.KEY_DOWN and scroll_offset < len(lines) - max_lines:
                scroll_offset += 1

    # Function to show network details
    def show_network():
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        # Title
        title = "Network Connections"
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(1, (w - len(title)) // 2, title)
        stdscr.attroff(curses.A_BOLD)

        # Content
        lines = []
        lines.append(f"My listen address: {listen_addr}")
        lines.append(f"Total expected peers: {expected_peers}")
        lines.append("")

        with net.lock:
            lines.append(f"Outgoing connections ({len(net.out_queues)}):")
            for idx, addr in enumerate(sorted(net.out_queues.keys()), 1):
                lines.append(f"{idx}. {addr}")

            lines.append("")
            lines.append(f"Unique peer connections ({len(net.unique_peers)}):")
            for idx, peer in enumerate(sorted(net.unique_peers), 1):
                lines.append(f"{idx}. {peer}")

        # Display content with scrolling if needed
        start_y = 3
        max_lines = h - 5  # Reserve space for title and footer
        scroll_offset = 0

        # Handle scrolling
        while True:
            stdscr.clear()
            stdscr.attron(curses.A_BOLD)
            stdscr.addstr(1, (w - len(title)) // 2, title)
            stdscr.attroff(curses.A_BOLD)

            # Show content
            for i in range(min(max_lines, len(lines) - scroll_offset)):
                if scroll_offset + i < len(lines):
                    try:
                        stdscr.addstr(start_y + i, 2, lines[scroll_offset + i])
                    except curses.error:
                        pass

            # Footer
            footer = "↑↓: Scroll | q: Back to menu"
            try:
                stdscr.addstr(h - 2, (w - len(footer)) // 2, footer)
            except curses.error:
                pass

            stdscr.refresh()

            # Get user input
            key = stdscr.getch()
            if key == ord("q"):
                break
            elif key == curses.KEY_UP and scroll_offset > 0:
                scroll_offset -= 1
            elif key == curses.KEY_DOWN and scroll_offset < len(lines) - max_lines:
                scroll_offset += 1

    # Main menu loop
    action = None
    while action != "quit":
        draw_menu()
        key = stdscr.getch()

        if key == curses.KEY_UP and selected_row > 0:
            selected_row -= 1
        elif key == curses.KEY_DOWN and selected_row < len(menu_items) - 1:
            selected_row += 1
        elif key == curses.KEY_ENTER or key in [10, 13]:  # Enter key
            if selected_row == 0:  # Ready
                action = "ready"
                break
            elif selected_row == 1:  # Peers
                show_peers()
            elif selected_row == 2:  # Net
                show_network()
            elif selected_row == 3:  # Toggle Debug
                DEBUG_MODE = not DEBUG_MODE
            elif selected_row == 4:  # Quit
                action = "quit"
                break

    # Clean up
    curses.endwin()
    return action


def generate_random_name():
    """Generate a random player name limited to 12 characters"""
    short_adjectives = [
        "Cool",
        "Swift",
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
        "Ultra",
        "Mega",
        "Alpha",
        "Beta",
        "Pro",
        "Ace",
        "Top",
    ]

    short_nouns = [
        "Player",
        "Master",
        "Knight",
        "Tiger",
        "Wolf",
        "Ninja",
        "Gamer",
        "Hero",
        "Titan",
        "Cobra",
        "Viper",
        "Ace",
        "Hawk",
        "Fox",
        "Pilot",
        "Owl",
        "Bear",
        "Lynx",
        "Bot",
        "Star",
        "Chief",
        "Lion",
        "Shark",
        "Rex",
    ]

    adjective = random.choice(short_adjectives)
    noun = random.choice(short_nouns)

    # Make sure the combination doesn't exceed 12 characters
    while len(adjective + noun) > 12:
        # Try again with potentially shorter words
        adjective = random.choice(short_adjectives)
        noun = random.choice(short_nouns)

    return f"{adjective}{noun}"


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


def extract_ip(peer_id):
    """
    Extract the IP part from a peer_id for uniqueness checking.
    Special handling for localhost to allow multiple local instances.

    Handle various formats from gRPC:
    - ipv4:10.0.0.1:12345
    - ipv6:[::1]:12345
    - localhost:12345
    - [::]:12345 (server listener)
    """
    try:
        # Remove protocol prefix if present
        if ":" in peer_id and peer_id.split(":", 1)[0] in ("ipv4", "ipv6"):
            peer_id = peer_id.split(":", 1)[1]

        # Handle special cases - for localhost, include the port for uniqueness
        if peer_id.startswith("[::]:"):
            result = f"localhost:{peer_id.split(':')[-1]}"
            return result

        if peer_id.startswith("localhost:"):
            return peer_id  # Keep as is to differentiate local instances

        # IPv6 addresses have multiple colons and may be wrapped in brackets
        if "[" in peer_id and "]" in peer_id:
            # Extract the IPv6 address inside brackets
            ipv6_part = peer_id[peer_id.find("[") + 1 : peer_id.find("]")]
            # For local IPv6 addresses, treat them as localhost
            if ipv6_part in ("::1", "::"):
                port = peer_id.split("]:", 1)[1] if "]:" in peer_id else "0"
                return f"localhost:{port}"
            # Otherwise normalize the IPv6 address
            return ipv6_part

        # Extract IP without port for non-localhost addresses
        parts = peer_id.split(":")
        if len(parts) >= 2:
            # The IP is everything except the last part (port)
            ip = ":".join(parts[:-1]).lower()
            return ip
    except Exception as e:
        print(f"[LOBBY ERROR] Error extracting IP from {peer_id}: {e}")

    return peer_id.lower()


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

    # Print all peer addresses for debugging
    print(f"[DEBUG] Original peer addresses: {peer_addrs}")
    print(f"[DEBUG] Deduplicated peer addresses: {all_addrs}")

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
    # Set to track unique IP addresses (without port) that are ready
    unique_ips = set()

    # Thread to process incoming game state messages
    def process_game_states():
        nonlocal seed
        nonlocal scores
        scores = {}
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
                        # Use sender's self-reported listen address
                        sender_addr = msg.sender  # Added to protobuf
                        normalized_peer = net._normalize_peer_addr(sender_addr)

                        if normalized_peer not in unique_ips:
                            unique_ips.add(normalized_peer)
                            print(
                                f"[LOBBY] {normalized_peer} READY ({len(unique_ips)}/{expected_peers})"
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
            unique_ips.clear()

        game_started = False
        scores = {}
        game_started_event = threading.Event()
        seed = None
        results_received = False
        results_received_event = threading.Event()

        # Clear peer boards between games
        with peer_boards_lock:
            peer_boards.clear()

        print("Starting lobby menu. Use arrow keys to navigate.")

        # Show menu and get action
        action = curses.wrapper(
            show_curses_menu,
            listen_addr,
            net,
            ready_lock,
            ready_peers,
            unique_ips,
            expected_peers,
        )

        # Process menu action
        if action == "quit":
            print("[LOBBY] Exiting...")
            sys.exit(0)
        elif action == "ready":
            # Send ready message
            net.broadcast(
                tetris_pb2.TetrisMessage(type=tetris_pb2.READY, sender=listen_addr)
            )

            with ready_lock:
                # Get our own identity
                self_identity = net._get_peer_identity(listen_addr)

                # Check if we're already registered
                is_duplicate = False
                for existing_peer in ready_peers:
                    if net._get_peer_identity(existing_peer) == self_identity:
                        is_duplicate = True
                        print(f"[LOBBY DEBUG] You are already marked as READY")
                        break

                if not is_duplicate:
                    ready_peers.add(listen_addr)
                    unique_ips.add(self_identity)
                    print(f"[LOBBY] You are READY ({len(unique_ips)}/{expected_peers})")

        # Loop and wait for game to start
        print("Waiting for all players to be ready...")
        while not game_started:
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
            def send(self, target_addr, data: bytes):
                s = data.decode().strip()
                if s.startswith("GARBAGE:"):
                    n = int(s.split(":", 1)[1])
                    print(
                        f"[PEER SOCKET DEBUG] Targeting {target_addr} with {n} garbage lines"
                    )
                    net.send(
                        target_addr,
                        tetris_pb2.TetrisMessage(
                            type=tetris_pb2.GARBAGE,
                            garbage=n,
                            sender=listen_addr,
                            extra=(player_name.encode() if player_name else b""),
                        ),
                    )

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
            DEBUG_MODE,  # Pass debug mode flag to the game
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
