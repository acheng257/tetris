import socket
import threading
import queue
import random
from tetris_game import TETROMINOES

# ----------------------- Global Variables ----------------------- #
# For the lobby/room system:
lock = threading.Lock()
room_clients = {}      # Maps client socket to ready state (True/False)
MAX_PLAYERS = 2        # Set the desired number of players for the room
game_started = False   # Flag set once the room is full and the game is started
game_seed = None       # Seed to be used for piece generation

seed_queue = queue.Queue()  # Clients wait for the game seed via this queue

DEFAULT_PORT = 9999
DEFAULT_HOST = 'localhost'

# ----------------------- Server Functions ----------------------- #

def start_server(host='0.0.0.0', port=DEFAULT_PORT):
    """
    Start a server that accepts clients into a room.
    The server waits until MAX_PLAYERS clients are ready before starting the game.
    """
    global room_clients, game_started
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(5)
    print(f"Server started on {host}:{port} – waiting for {MAX_PLAYERS} players to be ready...")
    threading.Thread(target=accept_clients, args=(server_socket,), daemon=True).start()

def accept_clients(server_socket):
    global room_clients
    while True:
        try:
            client, addr = server_socket.accept()
            with lock:
                room_clients[client] = False
            print(f"Client connected from {addr}")
            # For every new client, start a thread that waits for its "READY" signal.
            threading.Thread(target=handle_client, args=(client,), daemon=True).start()
        except Exception as e:
            print("Error accepting client:", e)
            break

def handle_client(client):
    global room_clients, game_started, game_seed
    try:
        while True:
            data = client.recv(1024).decode()
            print(f"Received data: '{data}'")
            if not data:
                print("No data received, breaking connection")
                break
            for line in data.splitlines():
                print(f"Processing line: '{line}'")
                if line.strip().upper() == "READY":
                    print("READY command detected")
                    with lock:
                        room_clients[client] = True
                        print(f"Client {client.getpeername()} marked as READY")
                        print(f"Room status: {len(room_clients)}/{MAX_PLAYERS} clients, all ready: {all(room_clients.values())}")
                        # Check if all clients in the room are ready and if room is full
                        if (len(room_clients) >= MAX_PLAYERS and 
                            all(room_clients.values()) and not game_started):
                            # All are ready, start the game
                            game_seed = random.randint(0, 1000000)
                            print(f"Starting game with seed {game_seed}")
                            broadcast_message(f"START:{game_seed}")
                            game_started = True
                            print(f"All players ready. Broadcasting START with seed {game_seed}.")
                    break  # Exit the for-loop after handling READY
    except Exception as e:
        print(f"Error in handle_client: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # remove the client if the connection drops.
        with lock:
            if client in room_clients:
                del room_clients[client]
                print(f"Client {client.getpeername()} removed from room")

def broadcast_message(message):
    """
    Send a message (e.g. the start command) to all connected clients.
    """
    global room_clients
    remove_list = []
    for client in list(room_clients.keys()):
        try:
            client.sendall((message + "\n").encode())
        except Exception as e:
            remove_list.append(client)
    for client in remove_list:
        with lock:
            if client in room_clients:
                del room_clients[client]

# ----------------------- Client Functions ----------------------- #

def connect_to_server(host, port=DEFAULT_PORT):
    """
    Connect to the server and start a listener thread.
    """
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((host, port))
    threading.Thread(target=client_listener, args=(client_socket,), daemon=True).start()
    print(f"Connected to server at {host}:{port}")
    return client_socket

def client_listener(client_socket):
    """
    Listen for messages from the server.
    We expect a message like "START:<seed>".
    """
    global seed_queue
    buffer = ""
    while True:
        try:
            data = client_socket.recv(1024).decode()
            if not data:
                break
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line.startswith("START:"):
                    _, seed_str = line.split(":", 1)
                    seed = int(seed_str.strip())
                    seed_queue.put(seed)
        except Exception as e:
            print("Client listener error:", e)
            break
