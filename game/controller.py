## controller.py
import base64
import time
import curses
import queue
from proto import tetris_pb2
from typing import Dict, Optional

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
        self.combo_system = ComboSystem(debug_mode)
        self.last_fall_time = time.time()
        self.game_start_time = time.time()
        self.fall_speed = 1.0
        self.initial_fall_speed = self.fall_speed

        # Difficulty progression
        self.speed_increase_interval = 30.0
        self.speed_increase_rate = 0.05
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

        # Ed25519 keys
        self.privkey = privkey
        self.peer_pubkeys: Dict[str, Ed25519PublicKey] = peer_pubkeys or {}

    def _handle_board_state(self, text: str):
        """
        Parse "BOARD_STATE:<score>:<flattened_board>:<piece_info>" and update peer_boards
        """
        try:
            _, score_s, flat, piece = text.split(':', 3)
            score = int(score_s)
            cells = list(map(int, flat.split(',')))
            board = [
                cells[i * BOARD_WIDTH : (i + 1) * BOARD_WIDTH]
                for i in range(BOARD_HEIGHT)
            ]
            sender = getattr(text, 'sender', None)
            if sender and self.peer_boards is not None:
                with self.peer_boards_lock:
                    self.peer_boards[sender] = {'board': board, 'score': score}
        except Exception as e:
            if self.debug_mode:
                print(f"[HANDLE BOARD] Failed to parse: {e}")

    def process_network_messages(self):
        """Process incoming messages, verify signatures and GARBAGE protobufs"""
        if self.net_queue is None:
            return
        try:
            while True:
                raw = self.net_queue.get_nowait()
                if isinstance(raw, bytes) and raw.startswith(b'BOARD_STATE:'):
                    try:
                        body, sigpart = raw.split(b'|SIG:', 1)
                        signature = base64.b64decode(sigpart)
                        sender = getattr(raw, 'sender', None)
                        pubkey = self.peer_pubkeys.get(sender)
                        if not pubkey:
                            continue
                        pubkey.verify(signature, body)
                        self._handle_board_state(body.decode('utf-8'))
                    except Exception:
                        pass
                    continue
                net_msg = raw
                if (hasattr(net_msg, 'type') and net_msg.type == tetris_pb2.GARBAGE
                        and hasattr(net_msg, 'garbage') and net_msg.garbage > 0):
                    try:
                        amt = net_msg.garbage
                        if self.debug_mode:
                            print(f"[NET GARBAGE] {amt} lines from {getattr(net_msg, 'sender', '')}")
                        self.game_state.queue_garbage(amt)
                        self.attacks_received += amt
                    except Exception as e:
                        print(f"[NET GARBAGE] Error: {e}")
        except queue.Empty:
            pass

    def update_difficulty(self):
        current_time = time.time()
        if current_time - self.last_speed_increase_time >= self.speed_increase_interval:
            self.fall_speed = max(self.fall_speed * (1 - self.speed_increase_rate), 0.1)
            if ((current_time - self.game_start_time) / self.speed_increase_interval) % 3 == 0:
                self.level = min(self.level + 1, 10)
            self.last_speed_increase_time = current_time

    def handle_input(self):
        current_time = time.time()
        key = self.input_handler.process_input()
        touching_ground = self.game_state.check_collision(self.game_state.current_piece, 0, 1)
        if self.input_handler.is_first_press(curses.KEY_UP):
            if self.game_state.attempt_rotation() and touching_ground:
                self.lock_timer = current_time; self.landing_y = self.game_state.current_piece.y
        if self.input_handler.is_first_press(curses.KEY_LEFT):
            if self.game_state.attempt_move(-1, 0) and touching_ground:
                self.lock_timer = current_time; self.landing_y = self.game_state.current_piece.y
            self.input_handler.update_move_time()
        if self.input_handler.is_first_press(curses.KEY_RIGHT):
            if self.game_state.attempt_move(1, 0) and touching_ground:
                self.lock_timer = current_time; self.landing_y = self.game_state.current_piece.y
            self.input_handler.update_move_time()
        if self.input_handler.should_move_continuously():
            if self.input_handler.is_pressed(curses.KEY_LEFT) and self.game_state.attempt_move(-1, 0):
                if touching_ground:
                    self.lock_timer = current_time; self.landing_y = self.game_state.current_piece.y
                self.input_handler.update_move_time()
            elif self.input_handler.is_pressed(curses.KEY_RIGHT) and self.game_state.attempt_move(1, 0):
                if touching_ground:
                    self.lock_timer = current_time; self.landing_y = self.game_state.current_piece.y
                self.input_handler.update_move_time()
        if key == ord('q'):
            return 'quit'
        elif key == ord(' '):
            self._handle_hard_drop()
            if self.game_state.game_over:
                return 'game_over'
        elif key == ord('c'):
            if self.game_state.hold_piece():
                self.lock_timer = None; self.landing_y = None; self.last_fall_time = current_time
        return None

    def _handle_hard_drop(self):
        current_time = time.time()
        drop_distance = self.game_state.hard_drop()
        self.score += drop_distance * 2
        self._lock_current_piece(current_time)

    def _get_attack_value(self, lines_cleared: int) -> int:
        return {0:0,1:0,2:1,3:2,4:4}.get(lines_cleared, 0)

    def _lock_current_piece(self, current_time: float):
        self.game_state.merge_piece(self.game_state.current_piece)
        lines_cleared = self.game_state.clear_lines()
        base_attack = self._get_attack_value(lines_cleared)
        if self.debug_mode:
            print(f"[ATTACK CALC] Lines: {lines_cleared}, Base: {base_attack}")
        combo = self.combo_system.update(lines_cleared, current_time)
        bonus = self.combo_system.get_garbage_count(lines_cleared, combo['combo_count'], base_attack)
        if self.debug_mode:
            print(f"[COMBO BONUS] Count {combo['combo_count']}, Bonus {bonus}")
        total = base_attack + bonus
        if self.debug_mode:
            print(f"[TOTAL ATTACK] Sending {total} lines")
        if total > 0:
            canceled = self.game_state.reduce_pending_garbage(total)
            net = total - canceled
            if self.debug_mode:
                print(f"[GARBAGE REDUCTION] Canceled {canceled}, Net {net}")
            if net > 0:
                self._send_garbage_to_opponents(net)
        if self.game_state.pending_garbage > 0:
            applied = self.game_state.apply_pending_garbage()
            self.attacks_received += applied
            if self.debug_mode:
                print(f"[GARBAGE APPLIED] {applied} lines")
        gained = self.game_state.calculate_score(lines_cleared, self.level)
        self.score += gained
        if self.debug_mode and gained > 0:
            print(f"[SCORE] +{gained} pts (Level {self.level})")
        self._spawn_next_piece()

    def _normalize_peer_identity(self, peer_id):
        """Normalize peer addresses to identify unique clients"""
        # Handle URL-encoded characters from gRPC
        if "%5B" in peer_id:
            peer_id = peer_id.replace("%5B", "[").replace("%5D", "]")
        
        # Handle protocol prefixes
        if peer_id.startswith("ipv4:") or peer_id.startswith("ipv6:"):
            peer_id = peer_id.split(":", 1)[1]
        
        # Extract host and port
        host = None
        port = None
        
        if peer_id.startswith("[") and "]:" in peer_id:
            # IPv6 with port: [::1]:50053
            host = peer_id[1:peer_id.find("]")]
            port = peer_id.split("]:", 1)[1]
        elif ":" in peer_id:
            # Regular host:port format
            parts = peer_id.split(":", 1)
            host = parts[0]
            port = parts[1] if len(parts) > 1 else None
        
        # For localhost variants, use a consistent identity based on port range
        if host in ("127.0.0.1", "::1", "::", "0.0.0.0", "localhost"):
            # Check if this is a standard port (below 1024) or an ephemeral port
            if port and port.isdigit():
                port_num = int(port)
                if port_num < 1024:
                    # For standard ports, keep the full port number
                    return f"localhost:{port}"
                else:
                    # For ephemeral ports, normalize to the base port they're connecting to
                    # This assumes ephemeral ports connect to standard ports
                    for base_port in ["50051", "50052", "50053"]:
                        if base_port in self.persistent_peers:
                            return f"localhost:{base_port}"
                    # If no match, use a consistent identifier
                    return "localhost:ephemeral"
            return "localhost"
        
        return peer_id



    # def _send_garbage_to_opponents(self, garbage_amount):
    #     if not self.client_socket or garbage_amount <= 0:
    #         return

    #     with self.peer_boards_lock:
    #         if not self.peer_boards:
    #             return
            
    #         # Track unique peer identities
    #         unique_peers = {}
    #         min_score = float("inf")
            
    #         # First pass: find minimum score
    #         for peer_id, board_data in self.peer_boards.items():
    #             score = board_data.get("score", float("inf"))
    #             if score < min_score:
    #                 min_score = score
            
    #         # Second pass: collect unique peers with minimum score
    #         for peer_id, board_data in self.peer_boards.items():
    #             if board_data.get("score", float("inf")) == min_score:
    #                 # Use normalized identity to deduplicate
    #                 peer_identity = self._normalize_peer_identity(peer_id)
    #                 unique_peers[peer_id] = peer_identity
            
    #         # Deduplicate by normalized identity
    #         seen_identities = set()
    #         final_peers = []
            
    #         for peer_id, identity in unique_peers.items():
    #             if identity not in seen_identities:
    #                 seen_identities.add(identity)
    #                 final_peers.append(peer_id)
            
    #         if self.debug_mode:
    #             print(f"[SEND GARBAGE] Sending {garbage_amount} lines to {len(final_peers)} unique peers")
            
    #         # Send to each unique peer
    #         for peer_id in final_peers:
    #             body = f"GARBAGE:{garbage_amount}\n".encode("utf-8")
    #             self.client_socket.send(peer_id, body)
                
    #         # Track total garbage sent
    #         self.attacks_sent += garbage_amount * len(final_peers)
    def _send_garbage_to_opponents(self, garbage_amount):
        if not self.client_socket or garbage_amount <= 0:
            return

        with self.peer_boards_lock:
            if not self.peer_boards:
                return
            
            # Track unique peer identities by normalized address
            unique_identities = {}
            min_score = float("inf")
            
            # First pass: find minimum score among active players
            for peer_id, board_data in self.peer_boards.items():
                # Skip players who have lost
                if board_data.get("lost", False):
                    continue
                    
                score = board_data.get("score", float("inf"))
                if score < min_score:
                    min_score = score
            
            # Second pass: collect all unique peers with minimum score
            for peer_id, board_data in self.peer_boards.items():
                if board_data.get("lost", False):
                    continue
                    
                if board_data.get("score", float("inf")) == min_score:
                    # Group peers by identity
                    identity = self._normalize_peer_identity(peer_id)
                    print(f"[SEND GARBAGE] Peer is {identity}")
                    if identity not in unique_identities:
                        unique_identities[identity] = []
                    unique_identities[identity].append(peer_id)
            
            # Send to one representative per unique identity
            recipients = [peers[0] for peers in unique_identities.values()]
            
            print(f"[SEND GARBAGE] Sending {garbage_amount} lines to {len(recipients)} players with lowest score: {recipients}")
            
            # Send to each unique peer
            for peer_id in recipients:
                body = f"GARBAGE:{garbage_amount}\n".encode("utf-8")
                self.client_socket.send(peer_id, body)
                
            # Track total garbage sent
            self.attacks_sent += garbage_amount * len(recipients)



    def _spawn_next_piece(self):
        self.game_state.current_piece = self.game_state.next_piece
        self.game_state.next_piece = self.get_next_piece_func()
        self.game_state.can_hold = True
        self.lock_timer = None; self.landing_y = None; self.last_fall_time = time.time()
        if self.game_state.is_game_over():
            if self.debug_mode:
                print("[SPAWN] Game over, handling")
            self._handle_game_over()

    def _handle_game_over(self):
        self.survival_time = time.time() - self.start_time
        if self.client_socket:
            msg = f"LOSE:{self.survival_time:.2f}:{self.attacks_sent}:{self.attacks_received}:{self.score}"
            if self.debug_mode:
                print(f"[CONTROLLER] {msg}")
            try:
                self.client_socket.sendall(msg.encode())
            except Exception as e:
                print(f"Error sending LOSE: {e}")

    def update_piece_gravity(self):
        current_time = time.time()
        touching = self.game_state.check_collision(self.game_state.current_piece, 0, 1)
        if touching:
            self._handle_piece_touching_ground(current_time)
        else:
            self.lock_timer = None; self.landing_y = None
            soft = self.input_handler.is_soft_drop_active()
            delay = self.fall_speed / self.level * (0.1 if soft else 1)
            if current_time - self.last_fall_time > delay:
                if self.game_state.attempt_move(0, 1) and soft:
                    self.score += 1
                self.last_fall_time = current_time

    def _handle_piece_touching_ground(self, current_time: float):
        if self.lock_timer is None:
            self.lock_timer = current_time; self.landing_y = self.game_state.current_piece.y
        elif self.game_state.current_piece.y != self.landing_y:
            self.lock_timer = current_time; self.landing_y = self.game_state.current_piece.y
        if current_time - self.lock_timer >= self.lock_delay:
            self._lock_current_piece(current_time)

    def send_board_state_update(self):
        current_time = time.time()
        if (self.client_socket and current_time - self.last_board_update_time > self.board_update_interval):
            flat = ",".join(str(cell) for row in self.game_state.board for cell in row)
            piece_info = (
                f"{self.game_state.current_piece.type},{self.game_state.current_piece.x},{self.game_state.current_piece.y},0,{self.game_state.current_piece.color}" if self.game_state.current_piece else "NONE"
            )
            body = f"BOARD_STATE:{self.score}:{flat}:{piece_info}".encode()
            payload = body
            if self.privkey:
                sig = self.privkey.sign(body)
                payload += b"|SIG:" + base64.b64encode(sig)
            self.client_socket.sendall(payload)
            self.last_board_update_time = current_time

    def update(self):
        cmd = self.process_network_messages()
        if cmd:
            return cmd
        self.update_difficulty()
        c = self.handle_input()
        if c in ("quit","game_over"):
            return c
        self.update_piece_gravity()
        self.send_board_state_update()
        if self.game_state.game_over:
            return "game_over"
        return None

    def render(self):
        now = time.time()
        if not self.renderer.draw_board(
            self.game_state.board, self.score, self.level,
            self.combo_system.get_display(), self.player_name
        ):
            return
        self.renderer.draw_piece(self.game_state.current_piece, self.game_state.board, ghost=True)
        self.renderer.draw_next_and_held(self.game_state.next_piece, self.game_state.held_piece)
        self.renderer.draw_pending_garbage_indicator(self.game_state.pending_garbage)
        if self.peer_boards and self.peer_boards_lock:
            self.renderer.draw_other_players_boards(self.peer_boards, self.peer_boards_lock)
        self.renderer.draw_combo_message(self.combo_system, now)

    def get_stats(self) -> dict:
        if self.game_state.game_over and self.survival_time == 0:
            self.survival_time = time.time() - self.start_time
        elif not self.game_state.game_over:
            self.survival_time = time.time() - self.start_time
        return {'survival_time': self.survival_time,
                'attacks_sent': self.attacks_sent,
                'attacks_received': self.attacks_received,
                'score': self.score,
                'level': self.level}
