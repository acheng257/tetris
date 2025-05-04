import time
import curses
import queue
from proto import tetris_pb2
from typing import Dict, Any, Optional, Tuple

from game.state import Piece
from game.combo import ComboSystem


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

    def process_network_messages(self):
        """Process incoming network messages"""
        if self.net_queue is None:
            return

        try:
            while True:
                net_msg = self.net_queue.get_nowait()
                if (
                    hasattr(net_msg, "type")
                    and net_msg.type == tetris_pb2.GARBAGE
                    and hasattr(net_msg, "garbage")
                    and net_msg.garbage > 0
                ):
                    # Process garbage from protocol buffer
                    try:
                        garbage_amount = net_msg.garbage
                        sender_info = getattr(net_msg, "sender", "")
                        print(
                            f"[NET GARBAGE] Received protobuf GARBAGE message: {garbage_amount} lines from {sender_info}"
                        )
                        # Queue garbage in game state
                        self.game_state.queue_garbage(garbage_amount)
                        self.attacks_received += garbage_amount
                    except Exception as e:
                        print(f"[NET GARBAGE] Error processing protobuf GARBAGE: {e}")
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
        """Lock the current piece, handle line clearing, garbage reduction/application, scoring, etc."""
        self.game_state.merge_piece(self.game_state.current_piece)
        lines_cleared = self.game_state.clear_lines()

        # Calculate attack/garbage sent based *only* on the line clear type
        base_attack = self._get_attack_value(lines_cleared)
        print(
            f"[ATTACK CALC] Lines Cleared: {lines_cleared}, Base Attack: {base_attack}"
        )

        # Calculate combo bonus garbage separately (Jstris combo table)
        combo_bonus_garbage = 0
        combo_result = self.combo_system.update(lines_cleared, current_time)
        combo_num = combo_result["combo_count"]
        attack_sent = self.combo_system.get_garbage_count(
            lines_cleared, combo_num, base_attack
        )

        # Set combo debug message
        if combo_result["debug_message"]:
            player_display_name = self.player_name if self.player_name else "You"
            self.combo_system.debug_message = (
                f"{player_display_name} {combo_result['debug_message']}"
            )

        # --- Garbage Handling ---
        if lines_cleared > 0:
            # Lines cleared: Reduce incoming garbage first
            cancelled_garbage = self.game_state.reduce_pending_garbage(attack_sent)
            # Send the remaining attack (if any) after cancelling
            net_attack_sent = attack_sent - cancelled_garbage
            if net_attack_sent > 0:
                print(
                    f"[ATTACK SEND] Calculated Net Attack: {net_attack_sent} (Attack: {attack_sent}, Cancelled: {cancelled_garbage})"
                )
                self._send_garbage_to_opponents(net_attack_sent)
            print(
                f"[ATTACK] Cleared {lines_cleared}. Attack: {attack_sent}, Cancelled: {cancelled_garbage}, Sent: {net_attack_sent}"
            )
        else:
            # No lines cleared: Apply pending garbage from queue
            print(
                f"[GARBAGE APPLY CHECK] Locking piece, lines_cleared=0. Pending garbage: {self.game_state.pending_garbage}"
            )
            applied_garbage = self.game_state.apply_pending_garbage()

        # Calculate score
        score_gained = self.game_state.calculate_score(lines_cleared, self.level)
        self.score += score_gained

        # Spawn next piece (unless game over happened during garbage apply)
        self._spawn_next_piece()

    def _send_garbage_to_opponents(self, garbage_amount):
        """Send a specific amount of garbage lines to opponents."""
        if self.client_socket and garbage_amount > 0:
            print(f"[SEND GARBAGE] Attempting to send {garbage_amount} lines.")
            # BROADCAST garbage for now instead of targeting lowest score
            # This makes testing easier and is common in many Tetris versions
            try:
                self.client_socket.sendall(  # Use sendall for broadcasting via lobby adapter
                    f"GARBAGE:{garbage_amount}\n".encode(),
                )
                self.attacks_sent += garbage_amount
                print(
                    f"[SEND GARBAGE] Successfully broadcast {garbage_amount} lines. Total sent: {self.attacks_sent}"
                )
            except Exception as e:
                print(f"[ERROR] Failed to broadcast garbage: {e}")
        elif garbage_amount <= 0:
            print(f"[SEND GARBAGE] No garbage to send ({garbage_amount}).")

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
        """Send board state updates over the network"""
        current_time = time.time()

        if (
            self.client_socket is not None
            and current_time - self.last_board_update_time > self.board_update_interval
        ):

            # Flatten the board to a string for sending
            flattened_board = ",".join(
                str(cell) for row in self.game_state.board for cell in row
            )

            # Add active piece information
            if self.game_state.current_piece:
                # Determine rotation state (simplified - using 0)
                rotation_state = 0

                piece_type = self.game_state.current_piece.type
                piece_info = (
                    f"{piece_type},"
                    f"{self.game_state.current_piece.x},"
                    f"{self.game_state.current_piece.y},"
                    f"{rotation_state},"
                    f"{self.game_state.current_piece.color}"
                )
            else:
                piece_info = "NONE"

            # Send the board state message
            board_state_msg = (
                f"BOARD_STATE:{self.score}:{flattened_board}:{piece_info}".encode()
            )
            self.client_socket.sendall(board_state_msg)
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
