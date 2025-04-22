import socket
import threading
import queue
from tetris_game import TETROMINOES

# ----------------------- Global Variables ----------------------- #
client_sockets = []         # Used only in server mode
seed_queue = queue.Queue()  # Used by clients to receive the game seed
game_seed = None            # Server-generated seed; new clients get this value

DEFAULT_PORT = 9999
DEFAULT_HOST = 'localhost'

# ----------------------- Server Functions ----------------------- #

def start_server(host='0.0.0.0', port=DEFAULT_PORT):
    """
    Start the server to accept client connections.
    Generate a random seed and store it.
    New clients will receive this seed upon connection.
    """
    import random
    global client_sockets, game_seed
    game_seed = random.randint(0, 1000000)  # Generate a random seed.
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(5)
    threading.Thread(target=accept_clients, args=(server_socket,), daemon=True).start()
    print(f"Server started on {host}:{port} with seed {game_seed}")

def accept_clients(server_socket):
    global client_sockets, game_seed
    while True:
        try:
            client, addr = server_socket.accept()
            print(f"Client connected from {addr}")
            # Immediately send the seed to the new client.
            client.sendall(f"SEED:{game_seed}\n".encode())
            client_sockets.append(client)
        except Exception as e:
            print("Error accepting client:", e)
            break

def broadcast_message(message):
    """
    Send a message to all connected clients.
    """
    global client_sockets
    remove_list = []
    for client in client_sockets:
        try:
            client.sendall((message + "\n").encode())
        except Exception as e:
            remove_list.append(client)
    for client in remove_list:
        client_sockets.remove(client)

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
    We expect a message like "SEED:<seed>".
    """
    global seed_queue
    buffer = ""
    while True:
        try:
            data = client_socket.recv(1024).decode()
            if not data:
                break  # Connection closed
            buffer += data
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line.startswith("SEED:"):
                    _, seed_str = line.split(":", 1)
                    seed = int(seed_str.strip())
                    seed_queue.put(seed)
        except Exception as e:
            print("Client listener error:", e)
            break
