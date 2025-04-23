import socket
import threading
import queue
import random
from tetris_game import TETROMINOES

# ----------------------- Global Variables ----------------------- #
# For the lobby/room system:
lock = threading.Lock()
room_clients = {}      # Maps client socket to ready state (True/False)
MAX_PLAYERS = 4        # Default max number of players for the room
game_started = False   # Flag set once the room is started
game_seed = None       # Seed to be used for piece generation

# Used for clients:
seed_queue = queue.Queue()  # Clients wait for the game seed via this queue

DEFAULT_PORT = 9999
DEFAULT_HOST = 'localhost'

# ----------------------- Server Functions ----------------------- #

def start_server(host='0.0.0.0', port=DEFAULT_PORT, max_players=4):
    """
    Start a server that accepts clients into a room.
    The server waits until MAX_PLAYERS clients are ready before starting the game,
    or until any player manually starts the game.
    """
    global room_clients, game_started, MAX_PLAYERS
    MAX_PLAYERS = max_players
    game_started = False  # Reset game_started flag when server starts
    
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
            # Check if we should stop accepting connections
            with lock:
                if game_started or len(room_clients) >= MAX_PLAYERS:
                    # If game has started or room is full, don't accept more clients
                    if game_started:
                        # Sleep a bit to reduce CPU usage in this loop
                        threading.Event().wait(1.0)
                        continue
            
            # Accept connection with timeout to periodically check if game started
            server_socket.settimeout(1.0)
            try:
                client, addr = server_socket.accept()
                with lock:
                    if game_started:
                        # Game started while we were waiting, reject this client
                        client.sendall("GAME_ALREADY_STARTED\n".encode())
                        client.close()
                        continue
                    
                    # Add the client to the room
                    room_clients[client] = False  # Initially not ready
                    print(f"Client connected from {addr} ({len(room_clients)}/{MAX_PLAYERS})")
                
                # Start a thread to handle this client
                threading.Thread(target=handle_client, args=(client,), daemon=True).start()
            
            except socket.timeout:
                # This is just the periodic timeout to check game_started, continue the loop
                continue
                
        except Exception as e:
            print("Error accepting client:", e)
            if not game_started:  # Only break if game hasn't started
                break

def handle_client(client):
    """
    Wait for the client to send a "READY" or "START" message.
    - "READY": Mark the client as ready and check if all clients are ready
    - "START": Force-start the game even if not all clients are ready
    """
    global room_clients, game_started, game_seed
    
    try:
        client_addr = client.getpeername()
        print(f"Handling client {client_addr}")
        
        while True:
            data = client.recv(1024).decode()
            print(f"Received data from {client_addr}: '{data}'")
            
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
                        
                        # Check if all clients in the room are ready and if room is full
                        if (len(room_clients) >= MAX_PLAYERS and 
                            all(room_clients.values()) and not game_started):
                            # All are ready and room is full, start the game
                            start_game()
                
                elif line == "START":
                    with lock:
                        if not game_started:
                            print(f"Client {client_addr} requested to start the game manually")
                            start_game()
                        else:
                            print(f"Ignoring START from {client_addr}, game already started")
    
    except Exception as e:
        print(f"Error in handle_client for {client_addr}: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Remove the client if the connection drops
        with lock:
            if client in room_clients:
                del room_clients[client]
                print(f"Client {client_addr} removed from room")
                # If the game has started and no clients left, reset game state
                if game_started and not room_clients:
                    reset_game_state()

def start_game():
    """
    Start the game with the current set of players.
    """
    global game_started, game_seed
    
    if not game_started:
        game_seed = random.randint(0, 1000000)
        print(f"Starting game with seed {game_seed}")
        broadcast_message(f"START:{game_seed}")
        game_started = True
        print(f"Game started with {len(room_clients)} players, seed {game_seed}")

def reset_game_state():
    """
    Reset the game state so a new game can be started.
    """
    global game_started, game_seed
    game_started = False
    game_seed = None
    print("Game state reset, ready for new game")

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
            print(f"Error broadcasting to client: {e}")
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
    We expect messages like:
    - "START:<seed>" - Game is starting with the given seed
    - "GAME_ALREADY_STARTED" - Can't join because game already started
    """
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
                    seed_queue.put(None)  # Signal that we can't join
        
        except Exception as e:
            print("Client listener error:", e)
            break
    
    # If the connection is closed without receiving a start message,
    # put None in the queue to unblock any waiting code
    if seed_queue.empty():
        seed_queue.put(None)