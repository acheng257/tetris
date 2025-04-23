import socket
import threading
import queue
import random
from tetris_game import TETROMINOES

# ----------------------- Global Variables ----------------------- #
lock = threading.Lock()
room_clients = {}      # Maps client socket to ready state (True/False)
MAX_PLAYERS = 4        # Default max number of players for the room
game_started = False   # Flag set once the room is started
game_seed = None       # Seed to be used for piece generation

seed_queue = queue.Queue()  # Clients wait for the game seed or messages via this queue

DEFAULT_PORT = 9999
DEFAULT_HOST = 'localhost'

players_results = {}

# ----------------------- Server Functions ----------------------- #
def start_server(host='0.0.0.0', port=DEFAULT_PORT, max_players=4):
    global room_clients, game_started, MAX_PLAYERS
    MAX_PLAYERS = max_players
    game_started = False  # Reset game state when server starts
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(5)
    print(f"Server started on {host}:{port} – waiting for up to {MAX_PLAYERS} players")
    print("Game will start when all players are ready or when any player sends START command")
    threading.Thread(target=accept_clients, args=(server_socket,), daemon=True).start()

def accept_clients(server_socket):
    global room_clients, game_started
    while True:
        try:
            with lock:
                if game_started or len(room_clients) >= MAX_PLAYERS:
                    if game_started:
                        threading.Event().wait(1.0)
                        continue
            server_socket.settimeout(1.0)
            try:
                client, addr = server_socket.accept()
                with lock:
                    if game_started:
                        client.sendall("GAME_ALREADY_STARTED\n".encode())
                        client.close()
                        continue
                    room_clients[client] = False  # Initially not ready
                    print(f"Client connected from {addr} ({len(room_clients)}/{MAX_PLAYERS})")
                threading.Thread(target=handle_client, args=(client,), daemon=True).start()
            except socket.timeout:
                continue
        except Exception as e:
            print("Error accepting client:", e)
            if not game_started:
                break

def handle_client(client):
    global room_clients, game_started, game_seed, players_results
    try:
        client_addr = client.getpeername()
        print(f"Handling client {client_addr}")
        while True:
            data = client.recv(1024).decode()
            if not data:
                print(f"No data received from {client_addr}, closing connection")
                break
            for line in data.splitlines():
                line = line.strip().upper()
                print(f"Processing line from {client_addr}: '{line}'")
                
                if line == "READY":
                    with lock:
                        room_clients[client] = True
                        ready_count = sum(1 for ready in room_clients.values() if ready)
                        print(f"Client {client_addr} marked as READY ({ready_count}/{len(room_clients)} ready)")
                        if (len(room_clients) >= MAX_PLAYERS and all(room_clients.values()) and not game_started):
                            start_game()
                
                elif line == "START":
                    with lock:
                        if not game_started:
                            print(f"Client {client_addr} requested to start the game manually")
                            start_game()
                        else:
                            print(f"Ignoring START from {client_addr}, game already started")
                elif line.startswith("LOSE:"):
                    try:
                        score = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        score = 0
                    with lock:
                        players_results[client_addr] = score
                        print(f"Recorded loss from {client_addr} with score {score}")
                        # When every connected client has reported a loss, broadcast final results.
                        if len(players_results) == len(room_clients):
                            broadcast_results()
                else:
                    print(f"Unrecognized command from {client_addr}: '{line}'")
    except Exception as e:
        print(f"Error in handle_client for {client_addr}: {e}")
    finally:
        with lock:
            if client in room_clients:
                del room_clients[client]
                print(f"Client {client_addr} removed from room")
            # In case a client disconnects without sending its score.
            if client_addr not in players_results:
                players_results[client_addr] = 0
            if game_started and not room_clients:
                reset_game_state()

def start_game():
    global game_started, game_seed
    if not game_started:
        game_seed = random.randint(0, 1000000)
        print(f"Starting game with seed {game_seed}")
        broadcast_message(f"START:{game_seed}")
        game_started = True
        print(f"Game started with {len(room_clients)} players, seed {game_seed}")

def reset_game_state():
    global game_started, game_seed, players_results
    game_started = False
    game_seed = None
    players_results = {}
    print("Game state reset, ready for new game")

def broadcast_message(message):
    global room_clients
    remove_list = []
    for client in list(room_clients.keys()):
        try:
            client.sendall((message + "\n").encode())
        except Exception as e:
            print(f"Error broadcasting to client: {e}")
            remove_list.append(client)
    for client in remove_list:
        with lock:
            if client in room_clients:
                del room_clients[client]

def broadcast_results():
    """
    Compile the final results from all players and broadcast to everyone.
    """
    global players_results
    results = "GAME_RESULTS:"
    # Sort results by score (highest first)
    sorted_results = sorted(players_results.items(), key=lambda item: item[1], reverse=True)
    results_list = "\n".join(f"{addr}: {score}" for addr, score in sorted_results)
    results += "\n" + results_list
    print("Broadcasting final results:\n" + results)
    broadcast_message(results)
    # Reset results for next game
    players_results = {}

# ----------------------- Client Functions ----------------------- #
def connect_to_server(host, port=DEFAULT_PORT):
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((host, port))
    threading.Thread(target=client_listener, args=(client_socket,), daemon=True).start()
    print(f"Connected to server at {host}:{port}")
    return client_socket

def client_listener(client_socket):
    global seed_queue
    buffer = ""
    while True:
        try:
            data = client_socket.recv(1024).decode()
            if not data:
                print("Server connection closed")
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                print(f"Client received: '{line}'")
                if line.startswith("START:"):
                    _, seed_str = line.split(":", 1)
                    seed = int(seed_str.strip())
                    seed_queue.put(seed)
                    print(f"Game starting with seed: {seed}")
                elif line == "GAME_ALREADY_STARTED":
                    print("Cannot join: Game already in progress")
                    seed_queue.put(None)
                elif line.startswith("GAME_RESULTS:"):
                    seed_queue.put(line)
        except Exception as e:
            print("Client listener error:", e)
            break
    if seed_queue.empty():
        seed_queue.put(None)