import hashlib
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
from tetris_game import create_piece_generator, run_game, init_colors


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


def run_lobby_ui_and_game(listen_port, peer_addrs, player_name):
    """Top-level function to initialize curses and run lobby/game."""
    # curses.wrapper handles initscr, cleanup, and terminal restoration
    print("[LOBBY] Starting curses wrapper...")
    curses.wrapper(_run_lobby_ui_wrapper, listen_port, peer_addrs, player_name)
    print("[LOBBY] Curses wrapper finished.")


def _run_lobby_ui_wrapper(stdscr, listen_port, peer_addrs, player_name):
    """Main function called by curses.wrapper. Handles UI and game flow."""
    print("[LOBBY UI] Inside curses wrapper.")

    # Initialize curses settings within the wrapper
    stdscr.nodelay(True)  # Non-blocking input
    curses.curs_set(0)  # Hide cursor
    stdscr.keypad(True)  # Enable special keys (like arrow keys)
    init_colors()  # Initialize color pairs (function assumed to be in tetris_game or ui module)

    listen_addr = f"[::]:{listen_port}"
    print(f"[LOBBY UI] Setting up P2P Network on {listen_addr} for {player_name}")
    net = P2PNetwork(listen_addr, peer_addrs)

    all_addrs = sorted(set(peer_addrs))
    expected_peers = len(all_addrs)
    print(f"[LOBBY UI] Expecting {expected_peers} total peers.")

    # --- Shared State (for communication between threads and UI) ---
    peer_boards = {}
    peer_boards_lock = threading.Lock()
    game_message_queue = queue.Queue()  # For GARBAGE, etc., from net to game
    lobby_status_queue = (
        queue.Queue()
    )  # For READY, LOSE, RESULTS etc from net to lobby UI

    game_started_event = threading.Event()
    results_received_event = threading.Event()

    # Store results data when LOSE messages come in
    scores = {}  # peer_id -> result_string
    scores_lock = threading.Lock()

    # Track ready state based on unique IPs/normalized addrs
    ready_peers_normalized = set()
    ready_lock = threading.Lock()

    # --- Network Processing Thread ---
    print("[LOBBY UI] Starting network processing thread...")
    network_thread = threading.Thread(
        target=process_network_messages,  # Renamed from process_game_states
        args=(
            net,
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
            listen_addr,  # Pass own listen address for comparison
            all_addrs,  # Pass the list of all addresses
        ),
        daemon=True,
    )
    network_thread.start()

    # --- Game Loop ---
    while True:  # Loop for multiple games
        # Reset per-game state
        game_started_event.clear()
        results_received_event.clear()
        with scores_lock:
            scores.clear()
        with ready_lock:
            ready_peers_normalized.clear()
        with peer_boards_lock:
            peer_boards.clear()  # Clear opponent boards for new game

        print("[LOBBY UI] Entering lobby menu...")
        # Run the lobby menu UI - returns seed if game starts, None if user quits
        start_info = run_lobby_menu(
            stdscr,
            net,
            player_name,
            expected_peers,
            lobby_status_queue,
            ready_peers_normalized,
            ready_lock,
            listen_addr,  # Pass own listen addr to mark self ready
            game_started_event,  # Pass event to check for externally triggered start
            all_addrs,  # Pass all_addrs
        )

        if start_info is None:
            print("[LOBBY UI] User quit from lobby menu.")
            break  # Exit the main loop if user quits

        seed = start_info["seed"]
        print(f"[LOBBY UI] Lobby menu returned seed: {seed}. Starting game...")

        # --- Run the Actual Game ---
        # We need a piece generator based on the agreed seed
        get_next_piece = create_piece_generator(seed)

        # Create adapters for the game to interact with the network via queues
        class NetQueueAdapter(queue.Queue):
            def get_nowait(self):
                # Game primarily consumes game messages (e.g., GARBAGE)
                return game_message_queue.get_nowait()

        class PeerSocketAdapter:
            def send(self, target_addr, data: bytes):
                # This might need adjustment if direct sends are needed,
                # currently game sends GARBAGE/LOSE via broadcast.
                print(
                    f"[PeerSocketAdapter] WARNING: send() called for {target_addr}, not implemented for direct P2P."
                )
                pass

            def sendall(self, data: bytes):
                s = data.decode().strip()
                print(
                    f"[PeerSocketAdapter] sendall received: {s[:50]}..."
                )  # Log truncated message
                if s.startswith("GARBAGE:"):
                    try:
                        n = int(s.split(":", 1)[1])
                        if n > 0:
                            print(
                                f"[PeerSocketAdapter] Broadcasting GARBAGE: {n} lines"
                            )
                            net.broadcast(
                                tetris_pb2.TetrisMessage(
                                    type=tetris_pb2.GARBAGE,
                                    garbage=n,
                                    sender=listen_addr,
                                    extra=(
                                        player_name.encode() if player_name else b""
                                    ),
                                )
                            )
                    except ValueError:
                        print(f"[PeerSocketAdapter] ERROR: Invalid GARBAGE format: {s}")
                elif s.startswith("LOSE:"):
                    try:
                        parts = s.split(":")
                        if len(parts) >= 4:
                            survival_time_float = float(parts[1])
                            attacks_sent_int = int(parts[2])
                            attacks_received_int = int(parts[3])
                            print(
                                f"[PeerSocketAdapter] Broadcasting LOSE: time={survival_time_float}, sent={attacks_sent_int}, rcvd={attacks_received_int}"
                            )
                            net.broadcast(
                                tetris_pb2.TetrisMessage(
                                    type=tetris_pb2.LOSE,
                                    score=int(survival_time_float),
                                    extra=f"{attacks_sent_int}:{attacks_received_int}".encode(),
                                )
                            )
                        else:
                            print(
                                f"[PeerSocketAdapter] ERROR: Invalid LOSE format '{s}': Not enough parts."
                            )
                    except (ValueError, IndexError) as e:
                        print(
                            f"[PeerSocketAdapter] ERROR: Invalid LOSE format '{s}': {e}"
                        )
                elif s.startswith("BOARD_STATE:"):
                    try:
                        parts = s.split(":", 3)
                        if len(parts) == 4:
                            score = int(parts[1])
                            board_cells = [int(cell) for cell in parts[2].split(",")]
                            piece_info = parts[3]

                            board_state = tetris_pb2.BoardState(
                                cells=board_cells,
                                width=10,
                                height=20,
                                score=score,
                                player_name=player_name,
                            )
                            if piece_info != "NONE":
                                piece_parts = piece_info.split(",")
                                if len(piece_parts) == 5:
                                    ptype, x, y, rot, color = piece_parts
                                    active_piece = tetris_pb2.ActivePiece(
                                        piece_type=ptype,
                                        x=int(x),
                                        y=int(y),
                                        rotation=int(rot),
                                        color=int(color),
                                    )
                                    board_state.active_piece.CopyFrom(active_piece)
                                    # print(f"[PeerSocketAdapter] Broadcasting GAME_STATE for {player_name}") # Too noisy
                                    net.broadcast(
                                        tetris_pb2.TetrisMessage(
                                            type=tetris_pb2.GAME_STATE,
                                            board_state=board_state,
                                        )
                                    )
                                else:
                                    print(
                                        f"[PeerSocketAdapter] ERROR: Invalid BOARD_STATE format '{s}': Not enough parts."
                                    )
                            else:
                                print(
                                    f"[PeerSocketAdapter] ERROR: Invalid BOARD_STATE format '{s}': Not enough parts."
                                )
                    except (ValueError, IndexError) as e:
                        print(
                            f"[PeerSocketAdapter] ERROR: Invalid BOARD_STATE format '{s}': {e}"
                        )
                else:
                    print(
                        f"[PeerSocketAdapter] WARNING: Unsupported message type in sendall: {s[:20]}..."
                    )

        print(f"[LOBBY UI] Calling run_game for {player_name}")
        # Pass stdscr to run_game now
        final_score = run_game(
            stdscr,  # Pass the screen object
            get_next_piece,
            PeerSocketAdapter(),
            NetQueueAdapter(),
            listen_port,
            peer_boards,
            peer_boards_lock,
            player_name,
        )
        print(f"[LOBBY UI] Game finished for {player_name}. Final score: {final_score}")

        # --- Post-Game Results Handling (Simplified Placeholder) ---
        # Broadcast our LOSE message one last time in case it was missed
        net.broadcast(
            tetris_pb2.TetrisMessage(
                type=tetris_pb2.LOSE,
                score=int(final_score["survival_time"]),
                extra=f"{final_score['attacks_sent']}:{final_score['attacks_received']}".encode(),
            )
        )

        # Display results screen (basic version)
        draw_results_screen(
            stdscr,
            scores,
            scores_lock,
            player_name,
            expected_peers,
            results_received_event,
        )

        # Wait a bit before returning to lobby
        time.sleep(5)


# --- Lobby Menu Implementation ---
def run_lobby_menu(
    stdscr,
    net,
    player_name,
    expected_peers,
    lobby_status_queue,
    ready_peers_normalized,
    ready_lock,
    listen_addr,
    game_started_event,
    all_addrs,
):
    """Displays the lobby menu, handles input, and waits for game start."""
    print("[LOBBY MENU] Entered.")

    menu_options = ["Ready", "View Peers", "View Network", "Quit"]
    current_selection = 0
    last_status_update = ""
    received_seed = None

    # Determine the leader based on the sorted canonical address list
    # Normalize addresses first for consistent comparison
    normalized_addrs = sorted([net._get_peer_identity(addr) for addr in all_addrs])
    leader_identity = normalized_addrs[0] if normalized_addrs else None
    my_identity = net._get_peer_identity(listen_addr)
    is_leader = my_identity == leader_identity

    print(f"[LOBBY MENU] All Normalized Addrs: {normalized_addrs}")
    print(f"[LOBBY MENU] Leader Identity: {leader_identity}")
    print(f"[LOBBY MENU] My Identity: {my_identity}")
    print(f"[LOBBY MENU] Is Leader: {is_leader}")

    # Mark self as ready immediately if only one expected peer (solo play/debug)
    if expected_peers == 1:
        with ready_lock:
            if my_identity not in ready_peers_normalized:
                ready_peers_normalized.add(my_identity)
                print(f"[LOBBY MENU] Auto-ready (1 player): {my_identity}")
                net.broadcast(
                    tetris_pb2.TetrisMessage(type=tetris_pb2.READY, sender=listen_addr)
                )

    while True:
        # --- Process Network Updates for UI ---
        try:
            status_update = lobby_status_queue.get_nowait()
            # status_update could be ('READY', peer_addr), ('START', seed), ('PEER_COUNT', count), etc.
            # For now, just store the latest message type
            status_message = str(status_update[0])
            if len(status_update) > 1:
                status_message += f": {status_update[1]}"
            last_status_update = f"Net: {status_message}"

            if status_update[0] == "START":
                received_seed = status_update[1]
                game_started_event.set()  # Ensure event is set if START received
                print(f"[LOBBY MENU] Received START via queue, seed={received_seed}")

        except queue.Empty:
            pass

        # --- Check Game Start Conditions ---
        # 1. Explicit START message received
        if received_seed is not None:
            print("[LOBBY MENU] Game starting due to received START message.")
            return {"seed": received_seed}

        # 2. All peers are ready AND I am the leader (implicit start for leader)
        with ready_lock:
            ready_count = len(ready_peers_normalized)
            if ready_count >= expected_peers and is_leader:
                # Leader calculates seed using the canonical sorted list of *all* expected peers
                # Ensure we use the *original* addresses, not the normalized ones, for the seed source if needed,
                # but normalized is likely better for consistency.
                # Using normalized addresses ensures everyone calculates the same hash.
                seed_source = ",".join(normalized_addrs)
                print(f"[LOBBY MENU LEADER] Calculating seed from peers: {seed_source}")
                calculated_seed = hash(seed_source) % 1000000
                print(
                    f"[LOBBY MENU LEADER] All peers ready ({ready_count}/{expected_peers}). Broadcasting START, seed={calculated_seed}"
                )
                net.broadcast(
                    tetris_pb2.TetrisMessage(
                        type=tetris_pb2.START, seed=calculated_seed
                    )
                )
                game_started_event.set()  # Signal game start
                return {"seed": calculated_seed}

        # --- Draw Menu ---
        stdscr.clear()
        h, w = stdscr.getmaxyx()

        title = f"P2P Tetris Lobby - Player: {player_name}"
        stdscr.addstr(1, (w - len(title)) // 2, title, curses.A_BOLD)

        # Display ready status
        with ready_lock:
            ready_count = len(ready_peers_normalized)
        status_line = (
            f"Status: Waiting for players ({ready_count}/{expected_peers} ready)"
        )
        stdscr.addstr(3, 2, status_line)
        stdscr.addstr(4, 2, last_status_update)  # Display last network event info

        # Draw menu options
        for i, option in enumerate(menu_options):
            y = 6 + i
            x = 5
            if i == current_selection:
                stdscr.addstr(y, x, f"> {option}", curses.A_REVERSE)
            else:
                stdscr.addstr(y, x, f"  {option}")

        stdscr.refresh()

        # --- Handle Input ---
        try:
            key = stdscr.getch()  # Non-blocking due to stdscr.nodelay(True)
        except curses.error:
            key = -1  # Handle potential error during resize etc.
            time.sleep(0.05)  # Prevent busy-waiting on error

        if key == curses.KEY_UP:
            current_selection = (current_selection - 1) % len(menu_options)
        elif key == curses.KEY_DOWN:
            current_selection = (current_selection + 1) % len(menu_options)
        elif key == ord("q"):  # Allow quitting with 'q'
            selected_option = "Quit"
            key = curses.KEY_ENTER  # Treat 'q' as selecting Quit
        elif key == curses.KEY_ENTER or key == 10 or key == 13:
            selected_option = menu_options[current_selection]
            print(f"[LOBBY MENU] User selected: {selected_option}")

            if selected_option == "Ready":
                with ready_lock:
                    # Use my_identity which is already calculated
                    if my_identity not in ready_peers_normalized:
                        ready_peers_normalized.add(my_identity)
                        print(f"[LOBBY MENU] Sending READY message for {my_identity}")
                        net.broadcast(
                            tetris_pb2.TetrisMessage(
                                type=tetris_pb2.READY, sender=listen_addr
                            )
                        )
                    else:
                        print(f"[LOBBY MENU] Already marked as ready.")
                last_status_update = "You are Ready!"  # Update local status display

            elif selected_option == "View Peers":
                # Call the specific function to draw peer info
                draw_peers_info(
                    stdscr, net, ready_peers_normalized, ready_lock, expected_peers
                )
                pass
            elif selected_option == "View Network":
                # Call the specific function to draw network info
                draw_network_info(stdscr, net, all_addrs)  # Need all_addrs here
                pass
            elif selected_option == "Quit":
                return None  # Signal to exit

        # Small delay to prevent high CPU usage
        time.sleep(0.05)


def draw_info_screen(stdscr, title, lines):
    """Helper to draw a simple info screen and wait for a key press."""
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    stdscr.addstr(1, (w - len(title)) // 2, title, curses.A_BOLD)
    for i, line in enumerate(lines):
        stdscr.addstr(3 + i, 2, line)
    stdscr.addstr(h - 2, 2, "Press any key to return...")
    stdscr.refresh()
    stdscr.nodelay(False)  # Switch to blocking mode to wait for key
    stdscr.getch()
    stdscr.nodelay(True)  # Switch back to non-blocking


def draw_results_screen(
    stdscr, scores, scores_lock, player_name, expected_peers, results_received_event
):
    """Displays the final game results."""
    print("[RESULTS] Drawing results screen.")
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    title = "=== FINAL RESULTS ==="
    stdscr.addstr(2, (w - len(title)) // 2, title, curses.A_BOLD)

    # Wait briefly for results to potentially arrive
    results_received_event.wait(timeout=2.0)

    with scores_lock:
        # Format results: "PlayerName: 120.5s (Attacks: 15->, 8<-)"
        results_list = []
        # Need player names - fetch from peer_boards (might be cleared, need adjustment)
        # For now, just use peer_id if name isn't available
        # Sorting: Higher survival time first
        sorted_scores = sorted(
            scores.items(), key=lambda item: float(item[1].split(":")[0]), reverse=True
        )

        for i, (peer_id, result_data) in enumerate(sorted_scores):
            try:
                parts = result_data.split(":")
                survival_time = float(parts[0])
                attacks_sent = int(parts[1]) if len(parts) > 1 else 0
                attacks_received = int(parts[2]) if len(parts) > 2 else 0
                # Ideally, resolve peer_id to player_name here
                display_name = f"Peer_{i+1}"  # Placeholder name
                line = f"{i+1}. {display_name}: {survival_time:.1f}s (Atk: {attacks_sent} S / {attacks_received} R)"
                results_list.append(line)
            except (ValueError, IndexError):
                results_list.append(
                    f"{i+1}. Peer_{i+1}: Invalid score data '{result_data}'"
                )

        for i, line in enumerate(results_list):
            stdscr.addstr(5 + i, 4, line)

    if len(scores) < expected_peers:
        stdscr.addstr(
            h - 4,
            4,
            f"Waiting for results from other players ({len(scores)}/{expected_peers})...",
        )

    stdscr.addstr(h - 2, 4, "Returning to lobby shortly...")
    stdscr.refresh()
    # No getch here, let the main loop handle the delay


# --- Network Message Processing Thread ---
def process_network_messages(
    net,
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
    listen_addr,  # Own address
    all_addrs,  # Pass the list of all addresses
):
    """Thread function to continuously process incoming network messages."""
    print("[NET THREAD] Started.")
    seed_value = None  # Track locally if START received

    while True:
        try:
            peer_id, msg = net.incoming.get(
                timeout=1.0
            )  # Use timeout to allow periodic checks
            # print(f"[NET THREAD] Received {tetris_pb2.MessageType.Name(msg.type)} from {peer_id}") # Debug: Log message type

            if msg.type == tetris_pb2.GAME_STATE:
                # Update peer board state (used by renderer)
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
                    if msg.board_state.HasField("active_piece"):
                        board_state["active_piece"] = {
                            "type": msg.board_state.active_piece.piece_type,
                            "x": msg.board_state.active_piece.x,
                            "y": msg.board_state.active_piece.y,
                            "rotation": msg.board_state.active_piece.rotation,
                            "color": msg.board_state.active_piece.color,
                        }
                    peer_boards[peer_id] = board_state
                    # print(f"[NET THREAD] Updated board for {msg.board_state.player_name}") # Debug

            elif msg.type == tetris_pb2.READY:
                # Update ready state (used by lobby menu)
                sender_addr = msg.sender
                normalized_peer = net._normalize_peer_addr(sender_addr)
                with ready_lock:
                    if normalized_peer not in ready_peers_normalized:
                        ready_peers_normalized.add(normalized_peer)
                        print(
                            f"[NET THREAD] Peer READY: {normalized_peer} ({len(ready_peers_normalized)} total)"
                        )
                        # Send status update to lobby UI
                        lobby_status_queue.put(("READY", normalized_peer))

            elif msg.type == tetris_pb2.START:
                # Signal game start (used by lobby menu)
                if not game_started_event.is_set():
                    seed_value = msg.seed
                    print(f"[NET THREAD] Received START, seed = {seed_value}")
                    game_started_event.set()
                    lobby_status_queue.put(("START", seed_value))

            elif msg.type == tetris_pb2.LOSE:
                # Store score, signal results processing
                with scores_lock:
                    if peer_id not in scores:
                        survival_time = msg.score  # Integer part
                        attacks_data = ""
                        if hasattr(msg, "extra") and msg.extra:
                            try:
                                attacks_data = msg.extra.decode()  # sent:received
                            except Exception:
                                pass

                        result_data = f"{survival_time:.2f}"  # Store float for sorting
                        if attacks_data:
                            result_data += f":{attacks_data}"

                        scores[peer_id] = result_data
                        print(
                            f"[NET THREAD] Received LOSE from {peer_id}. Score data: {result_data}"
                        )
                        lobby_status_queue.put(("LOSE", peer_id))

            elif msg.type == tetris_pb2.GAME_RESULTS:
                # Signal results fully received (used by results screen)
                print(f"[NET THREAD] Received GAME_RESULTS: {msg.results}")
                results_received_event.set()
                lobby_status_queue.put(("RESULTS", msg.results))

            elif msg.type == tetris_pb2.GARBAGE:
                # Forward GARBAGE to game logic if it's not from ourselves
                if msg.sender != listen_addr:
                    print(
                        f"[NET THREAD] Received GARBAGE from {msg.sender}: {msg.garbage} lines. Queuing for game."
                    )
                    try:
                        game_message_queue.put(msg)  # Pass the whole message
                    except Exception as e:
                        print(f"[NET THREAD] Error queueing garbage: {e}")
                else:
                    print(
                        f"[NET THREAD] Ignored own GARBAGE message: {msg.garbage} lines"
                    )

        except queue.Empty:
            # Timeout occurred, loop continues
            pass
        except Exception as e:
            print(
                f"[NET THREAD] Error processing message from {peer_id if 'peer_id' in locals() else 'UNKNOWN'}: {e}"
            )
            import traceback

            print(f"[NET THREAD] Traceback: {traceback.format_exc()}")


def draw_peers_info(stdscr, net, ready_peers_normalized, ready_lock, expected_peers):
    """Displays information about connected and ready peers."""
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    title = "=== Peer Status ==="
    stdscr.addstr(1, (w - len(title)) // 2, title, curses.A_BOLD)

    lines = []
    with ready_lock:
        ready_count = len(ready_peers_normalized)
        lines.append(f"Ready Peers: {ready_count} / {expected_peers}")
        lines.append("Ready Peer Identities:")
        if ready_peers_normalized:
            for i, peer_identity in enumerate(sorted(list(ready_peers_normalized))):
                lines.append(f"  {i+1}. {peer_identity}")
        else:
            lines.append("  (None)")

    # Add separator
    lines.append("-" * (w - 4))

    # Also show currently connected peers from network layer
    with net.lock:
        lines.append("Active Connections (Unique Inbound/Established):")
        unique_list = sorted(list(net.unique_peers))
        if unique_list:
            for i, peer_addr in enumerate(unique_list):
                # Attempt to normalize for display consistency
                identity = net._get_peer_identity(peer_addr)
                lines.append(f"  {i+1}. {peer_addr} (ID: {identity})")
        else:
            lines.append("  (None)")

    # Draw the collected lines
    for i, line in enumerate(lines):
        if i < h - 4:  # Prevent writing outside screen bounds
            stdscr.addstr(3 + i, 2, line[: w - 3])  # Truncate long lines

    stdscr.addstr(h - 2, 2, "Press any key to return...")
    stdscr.refresh()
    stdscr.nodelay(False)  # Wait for key
    stdscr.getch()
    stdscr.nodelay(True)  # Restore non-blocking


def draw_network_info(stdscr, net, all_addrs):
    """Displays detailed network connection information."""
    stdscr.clear()
    h, w = stdscr.getmaxyx()
    title = "=== Network Status ==="
    stdscr.addstr(1, (w - len(title)) // 2, title, curses.A_BOLD)

    lines = []
    lines.append(f"My Listen Address: {net.listen_addr}")
    lines.append(f"Expected Peers (from cmd args): {len(all_addrs)}")
    for i, addr in enumerate(all_addrs):
        lines.append(f"  {i+1}. {addr}")

    lines.append("-" * (w - 4))

    with net.lock:
        lines.append(f"Outgoing Connections Attempted/Active ({len(net.out_queues)}):")
        out_list = sorted(list(net.out_queues.keys()))
        if out_list:
            for i, addr in enumerate(out_list):
                lines.append(f"  {i+1}. {addr}")
        else:
            lines.append("  (None)")

        lines.append("-" * (w - 4))

        lines.append(
            f"Unique Inbound/Established Connections ({len(net.unique_peers)}):"
        )
        unique_list = sorted(list(net.unique_peers))
        if unique_list:
            for i, addr in enumerate(unique_list):
                lines.append(f"  {i+1}. {addr}")
        else:
            lines.append("  (None)")

    # Draw the collected lines
    for i, line in enumerate(lines):
        if i < h - 4:
            stdscr.addstr(3 + i, 2, line[: w - 3])

    stdscr.addstr(h - 2, 2, "Press any key to return...")
    stdscr.refresh()
    stdscr.nodelay(False)  # Wait for key
    stdscr.getch()
    stdscr.nodelay(True)  # Restore non-blocking
