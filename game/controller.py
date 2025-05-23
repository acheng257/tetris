import base64
import time
import curses
import queue
from proto import tetris_pb2
from typing import Dict, Any, Optional, Tuple

from game.state import Piece
from game.combo import ComboSystem

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

BOARD_WIDTH = 10
BOARD_HEIGHT = 20

class GameController:
    """
    Coordinates game logic, input handling, and rendering.
    Acts as the central controller for the Tetris game.
    """

    def __init__(
        self,
        game_state,
        renderer,
        input_handler,
        client_socket=None,
        net_queue=None,
        listen_port=None,
        peer_boards=None,
        peer_boards_lock=None,
        player_name=None,
        debug_mode=False,
        privkey: Ed25519PrivateKey = None,
        peer_pubkeys: Dict[str, Ed25519PublicKey] = None,
    ):
        self.game_state = game_state
        self.renderer = renderer
        self.input_handler = input_handler

        # Network-related members
        self.client_socket = client_socket
        self.net_queue = net_queue
        self.listen_port = listen_port
        self.peer_boards = peer_boards
        self.peer_boards_lock = peer_boards_lock
        self.player_name = player_name

        # Game tracking stats
        self.score = 0
        self.level = 1
        self.attacks_sent = 0
        self.attacks_received = 0
        self.start_time = time.time()
        self.survival_time = 0

        # Game timing variables
        self.combo_system = ComboSystem()
        self.last_fall_time = time.time()
        self.game_start_time = time.time()
        self.fall_speed = 1.0
        self.initial_fall_speed = self.fall_speed

        # Difficulty progression
        self.speed_increase_interval = 30.0  # Increase speed every 30 seconds
        self.speed_increase_rate = 0.05  # Reduce fall_speed by 5% every interval
        self.last_speed_increase_time = self.game_start_time

        # Piece locking
        self.lock_delay = 0.5
        self.lock_timer = None
        self.landing_y = None

        # Board state updates
        self.last_board_update_time = time.time()
        self.board_update_interval = 0.5

        # Store debug mode
        self.debug_mode = debug_mode

        # Your own Ed25519 private key for signing
        self.privkey = privkey
        # Mapping from peer player_name → their Ed25519PublicKey
        self.peer_pubkeys: Dict[str, Ed25519PublicKey] = peer_pubkeys or {}

    def _handle_board_state(self, text: str):
        """
        Parse "BOARD_STATE:<score>:<flattened_board>:<piece_info>"
        and apply it to self.peer_boards or however you track peers.
        """
        try:
            _, score_s, flat, piece = text.split(":", 3)
            score = int(score_s)
            cells = list(map(int, flat.split(",")))
            # reconstruct board
            board = [
                cells[i * BOARD_WIDTH : (i + 1) * BOARD_WIDTH]
                for i in range(BOARD_HEIGHT)
            ]
            # TODO: parse piece if you need it
            # Now store in peer_boards under sender’s name
            sender = getattr(text, "sender", None)
            if sender and self.peer_boards is not None:
                with self.peer_boards_lock:
                    self.peer_boards[sender] = {
                        "board": board,
                        "score": score,
                        # you can store piece if desired
                    }
        except Exception as e:
            if self.debug_mode:
                print(f"[HANDLE BOARD] Failed to parse: {e}")

    def process_network_messages(self):
        """Process incoming network messages, verifying Ed25519 signatures on BOARD_STATE."""
        if self.net_queue is None:
            return

        try:
            while True:
                raw = self.net_queue.get_nowait()

                # ——— Check for signed BOARD_STATE ———
                if isinstance(raw, bytes) and raw.startswith(b"BOARD_STATE:"):
                    try:
                        body, sigpart = raw.split(b"|SIG:", 1)
                        signature = base64.b64decode(sigpart)
                        # You must have stored sender name on the raw message
                        sender = getattr(raw, "sender", None)
                        pubkey = self.peer_pubkeys.get(sender)
                        if not pubkey:
                            # no public key for this sender → ignore
                            continue
                        pubkey.verify(signature, body)
                        # signature valid: apply the board update
                        self._handle_board_state(body.decode("utf-8"))
                    except Exception:
                        # malformed or bad signature → drop
                        pass
                    continue

                # ——— Fallback to existing protobuf GARBAGE handler ———
                net_msg = raw
                if (
                    hasattr(net_msg, "type")
                    and net_msg.type == tetris_pb2.GARBAGE
                    and hasattr(net_msg, "garbage")
                    and net_msg.garbage > 0
                ):
                    try:
                        amt = net_msg.garbage
                        sender_info = getattr(net_msg, "sender", "")
                        if self.debug_mode:
                            print(f"[NET GARBAGE] {amt} lines from {sender_info}")
                        self.game_state.queue_garbage(amt)
                        self.attacks_received += amt
                    except Exception as e:
                        print(f"[NET GARBAGE] Error: {e}")
        except queue.Empty:
            pass


    def update_difficulty(self):
        """Update game difficulty based on time"""
        current_time = time.time()

        # Check if it's time to increase the game speed
        if current_time - self.last_speed_increase_time >= self.speed_increase_interval:
            # Increase speed by reducing fall_speed (faster pieces)
            self.fall_speed = max(
                self.fall_speed * (1 - self.speed_increase_rate), 0.1
            )  # Don't allow it to get too fast

            # Increase level every few speed increases
            if (
                current_time - self.game_start_time
            ) / self.speed_increase_interval % 3 == 0:
                self.level = min(self.level + 1, 10)  # Cap at level 10

            self.last_speed_increase_time = current_time

    def handle_input(self):
        """Process player input and update game state"""
        current_time = time.time()
        key = self.input_handler.process_input()
        touching_ground = self.game_state.check_collision(
            self.game_state.current_piece, 0, 1
        )

        # Handle rotation (up key)
        if self.input_handler.is_first_press(curses.KEY_UP):
            rotation_successful = self.game_state.attempt_rotation()
            if rotation_successful and touching_ground:
                self.lock_timer = current_time
                self.landing_y = self.game_state.current_piece.y

        # Handle left movement
        if self.input_handler.is_first_press(curses.KEY_LEFT):
            if self.game_state.attempt_move(-1, 0):
                if touching_ground:
                    self.lock_timer = current_time
                    self.landing_y = self.game_state.current_piece.y
            self.input_handler.update_move_time()

        # Handle right movement
        if self.input_handler.is_first_press(curses.KEY_RIGHT):
            if self.game_state.attempt_move(1, 0):
                if touching_ground:
                    self.lock_timer = current_time
                    self.landing_y = self.game_state.current_piece.y
            self.input_handler.update_move_time()

        # Handle continuous movement while key is held
        if self.input_handler.should_move_continuously():
            if self.input_handler.is_pressed(curses.KEY_LEFT):
                if self.game_state.attempt_move(-1, 0):
                    if touching_ground:
                        self.lock_timer = current_time
                        self.landing_y = self.game_state.current_piece.y
                    self.input_handler.update_move_time()
            elif self.input_handler.is_pressed(curses.KEY_RIGHT):
                if self.game_state.attempt_move(1, 0):
                    if touching_ground:
                        self.lock_timer = current_time
                        self.landing_y = self.game_state.current_piece.y
                    self.input_handler.update_move_time()

        # Handle non-movement keys
        if key == ord("q"):
            return "quit"
        elif key == ord(" "):
            self._handle_hard_drop()
            if self.game_state.game_over:
                return "game_over"
        elif key == ord("c"):
            if self.game_state.hold_piece():
                self.lock_timer = None
                self.landing_y = None
                self.last_fall_time = current_time

        return None

    def _handle_hard_drop(self):
        """Handle hard drop action (space key)"""
        current_time = time.time()

        # Hard drop
        drop_distance = self.game_state.hard_drop()
        self.score += drop_distance * 2  # Score for hard drop

        # Lock the piece and handle consequences
        self._lock_current_piece(current_time)

    def _get_attack_value(self, lines_cleared):
        """Calculate garbage lines sent based on lines cleared (Jstris basic table)."""
        # Basic Jstris attack table (ignoring T-Spins, Perfect Clear, B2B for now)
        attack_values = {
            0: 0,
            1: 0,  # Single
            2: 1,  # Double
            3: 2,  # Triple
            4: 4,  # Tetris
        }
        return attack_values.get(lines_cleared, 0)

    def _lock_current_piece(self, current_time):
        """Lock the current piece in place, check for line clears, and spawn the next piece."""
        # Merge the piece into the board
        self.game_state.merge_piece(self.game_state.current_piece)
        lines_cleared = self.game_state.clear_lines()

        # 2) Compute base attack
        base_attack = self._get_attack_value(lines_cleared)
        if self.debug_mode:
            print(f"[ATTACK CALC] Lines Cleared: {lines_cleared}, Base Attack: {base_attack}")

        # 3) Update combo system and get combo bonus
        combo_result = self.combo_system.update(lines_cleared, current_time)
        combo_num = combo_result["combo_count"]
        combo_bonus = self.combo_system.get_garbage_count(
            lines_cleared, combo_num, base_attack
        )
        if self.debug_mode and combo_bonus > 0:
            print(f"[COMBO BONUS] Combo Count: {combo_num}, Combo Bonus: {combo_bonus}")

        # 4) Total garbage to send: base + combo
        attack_sent = base_attack + combo_bonus
        if self.debug_mode:
            print(f"[TOTAL ATTACK] Sending {attack_sent} lines (Base {base_attack} + Combo {combo_bonus})")

        # 5) Cancel incoming garbage first
        if attack_sent > 0:
            cancelled = self.game_state.reduce_pending_garbage(attack_sent)
            net_to_send = attack_sent - cancelled
            if self.debug_mode:
                print(f"[GARBAGE REDUCTION] Cancelled: {cancelled}, Net to send: {net_to_send}")

            if net_to_send > 0:
                self._send_garbage_to_opponents(net_to_send)
                if self.debug_mode:
                    print(f"[ATTACK SENT] Unicasted {net_to_send} lines")
        else:
            if self.debug_mode:
                print("[GARBAGE] No new garbage to send")

        # 6) Always apply any pending incoming garbage after sending
        if self.game_state.pending_garbage > 0:
            applied = self.game_state.apply_pending_garbage()
            self.attacks_received += applied
            if self.debug_mode:
                print(f"[GARBAGE APPLIED] Applied {applied} pending lines")

        # 7) Award points
        gained = self.game_state.calculate_score(lines_cleared, self.level)
        self.score += gained
        if self.debug_mode and gained > 0:
            print(f"[SCORE] +{gained} points (Level {self.level})")

        # 8) Spawn next piece & check game over
        self._spawn_next_piece()

    def _send_garbage_to_opponents(self, garbage_amount):
        """Send the full garbage amount to each player with the lowest score"""
        if not self.client_socket or garbage_amount <= 0:
            return

        with self.peer_boards_lock:
            if not self.peer_boards:
                return
            
            # Find all players with the minimum score
            min_score = float("inf")
            lowest_score_peers = []
            
            # First pass: find the minimum score
            for peer_id, board_data in self.peer_boards.items():
                peer_score = board_data.get("score", float("inf"))
                if peer_score < min_score:
                    min_score = peer_score
            
            # Second pass: collect all players with that minimum score
            for peer_id, board_data in self.peer_boards.items():
                if board_data.get("score", float("inf")) == min_score:
                    lowest_score_peers.append(peer_id)
            
            if not lowest_score_peers:
                return
                
            # Send the full garbage amount to each lowest-score player
            if self.debug_mode:
                print(f"[SEND GARBAGE] Sending {garbage_amount} lines to {len(lowest_score_peers)} players with lowest score")
            
            for peer_id in lowest_score_peers:
                body = f"GARBAGE:{garbage_amount}\n".encode("utf-8")
                self.client_socket.send(peer_id, body)
                
                if self.debug_mode:
                    print(f"[SEND GARBAGE] Sent {garbage_amount} lines to {peer_id}")
            
            # Track total garbage sent (multiply by number of recipients)
            self.attacks_sent += garbage_amount * len(lowest_score_peers)


    def _spawn_next_piece(self):
        """Spawn the next piece and handle game over if needed"""
        self.game_state.current_piece = self.game_state.next_piece
        self.game_state.next_piece = self.get_next_piece_func()
        self.game_state.can_hold = True

        # Reset piece lock variables
        self.lock_timer = None
        self.landing_y = None
        self.last_fall_time = time.time()

        # Check for game over
        if self.game_state.is_game_over():
            if self.debug_mode:
                print("[SPAWN DEBUG] Game over detected, calling _handle_game_over")
            self._handle_game_over()

    def _handle_game_over(self):
        """Handle game over: calculate final stats, send LOSE message, return stats."""
        # Calculate final survival time
        self.survival_time = time.time() - self.start_time

        # Send LOSE message via adapter (includes final stats)
        if self.client_socket:
            try:
                msg = f"LOSE:{self.survival_time:.2f}:{self.attacks_sent}:{self.attacks_received}:{self.score}"
                if self.debug_mode:
                    print(f"[CONTROLLER] Sending final LOSE message: {msg}")
                self.client_socket.sendall(msg.encode())
            except Exception as e:
                print(f"Error sending LOSE message: {e}")

    def update_piece_gravity(self):
        """Apply gravity to the current piece"""
        current_time = time.time()
        touching_ground = self.game_state.check_collision(
            self.game_state.current_piece, 0, 1
        )

        # Handle piece locking when touching ground
        if touching_ground:
            self._handle_piece_touching_ground(current_time)
        else:
            # Reset lock timer when piece is not touching ground
            self.lock_timer = None
            self.landing_y = None

            # Apply gravity based on fall speed and level
            soft_drop = self.input_handler.is_soft_drop_active()
            fall_delay = self.fall_speed / self.level

            if soft_drop:
                fall_delay *= 0.1

            if current_time - self.last_fall_time > fall_delay:
                if self.game_state.attempt_move(0, 1):
                    if soft_drop:
                        self.score += 1
                self.last_fall_time = current_time

    def _handle_piece_touching_ground(self, current_time):
        """Handle the case when a piece is touching the ground"""
        # Start lock timer if it hasn't started yet
        if self.lock_timer is None:
            self.lock_timer = current_time
            self.landing_y = self.game_state.current_piece.y
        # Reset lock timer if piece has moved horizontally or rotated
        elif self.game_state.current_piece.y != self.landing_y:
            self.lock_timer = current_time
            self.landing_y = self.game_state.current_piece.y

        # Check if lock delay has elapsed
        if (
            self.lock_timer is not None
            and current_time - self.lock_timer >= self.lock_delay
        ):
            self._lock_current_piece(current_time)

    def send_board_state_update(self):
        """Send board state updates over the network, with optional Ed25519 signature."""
        current_time = time.time()

        if (
            self.client_socket is not None
            and current_time - self.last_board_update_time > self.board_update_interval
        ):

            # 1) Flatten board
            flattened = ",".join(
                str(cell) for row in self.game_state.board for cell in row
            )

            # 2) Active piece info
            if self.game_state.current_piece:
                rotation = 0
                p = self.game_state.current_piece
                piece_info = f"{p.type},{p.x},{p.y},{rotation},{p.color}"
            else:
                piece_info = "NONE"

            # 3) Build payload body
            body = f"BOARD_STATE:{self.score}:{flattened}:{piece_info}".encode("utf-8")

            # 4) Sign it if we have a private key
            if self.privkey:
                sig = self.privkey.sign(body)
                sig_b64 = base64.b64encode(sig).decode("ascii")
                payload = body + b"|SIG:" + sig_b64.encode("ascii")
            else:
                payload = body

            # 5) Broadcast
            self.client_socket.sendall(payload)
            self.last_board_update_time = current_time

    def update(self):
        """Main update method to be called each game loop iteration"""
        # Process any pending network messages
        self.process_network_messages()

        # Update game difficulty based on time
        self.update_difficulty()

        # Handle user input - returns command if needed (quit, etc.)
        command = self.handle_input()
        if command == "quit":
            return command
        elif command == "game_over":
            return command

        # Apply gravity to the current piece
        self.update_piece_gravity()

        # Send network updates
        self.send_board_state_update()

        # Check if game over
        if self.game_state.game_over:
            return "game_over"

        return None

    def render(self):
        """Render the current game state (board, pieces, info, peers)"""
        current_time = time.time()

        # Render the board
        if not self.renderer.draw_board(
            self.game_state.board,
            self.score,
            self.level,
            self.combo_system.get_display(),
            self.player_name,
        ):
            # If rendering failed (e.g., terminal too small), wait and continue
            time.sleep(1)
            return

        # Render other elements
        self.renderer.draw_piece(
            self.game_state.current_piece, self.game_state.board, ghost=True
        )
        self.renderer.draw_next_and_held(
            self.game_state.next_piece, self.game_state.held_piece
        )

        # Draw pending garbage indicator
        self.renderer.draw_pending_garbage_indicator(self.game_state.pending_garbage)

        # Draw other players' boards if available
        if self.peer_boards is not None and self.peer_boards_lock is not None:
            self.renderer.draw_other_players_boards(
                self.peer_boards, self.peer_boards_lock
            )

        # Draw combo message
        self.renderer.draw_combo_message(self.combo_system, current_time)

    def get_stats(self):
        """Return game statistics"""
        # Calculate final survival time if game is over and wasn't calculated yet
        if self.game_state.game_over and self.survival_time == 0:
            self.survival_time = time.time() - self.start_time
        elif not self.game_state.game_over:
            # If the game is still running, calculate current survival time
            self.survival_time = time.time() - self.start_time

        return {
            "survival_time": self.survival_time,
            "attacks_sent": self.attacks_sent,
            "attacks_received": self.attacks_received,
            "score": self.score,
            "level": self.level,
        }
