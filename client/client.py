import sys
import time
import select
from proto import tetris_pb2
from client.grpc_client import TetrisClient
from tetris_game import create_piece_generator, run_game

def print_help():
    print("\nCommands:")
    print("  ready    - Signal that you are ready to play")
    print("  start    - Manually start the game (even if not all players are ready)")
    print("  quit     - Exit the program")
    print()

def run_lobby(grpc_client):
    print_help()
    seed = None

    while seed is None:
        # Poll for incoming messages from the server.
        msg = grpc_client.get_message(timeout=1)
        if msg:
            if msg.type == tetris_pb2.GAME_STARTED:
                seed = msg.seed
                print(f"[DEBUG] Received game seed: {seed}")
            elif msg.type == tetris_pb2.GAME_ALREADY_STARTED:
                print("[DEBUG] Game already started, cannot join. Exiting.")
                grpc_client.close()
                sys.exit(1)
            else:
                print(f"[DEBUG] Received unexpected message: {msg}")

        # Always check if the user entered a command.
        if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
            cmd = sys.stdin.readline().strip().lower()
            if cmd == "ready":
                grpc_client.send_message(tetris_pb2.TetrisMessage(type=tetris_pb2.READY))
                print("[DEBUG] Sent READY to server. Waiting for game to start...")
            elif cmd == "start":
                grpc_client.send_message(tetris_pb2.TetrisMessage(type=tetris_pb2.START))
                print("[DEBUG] Sent START command. Manually starting the game...")
            elif cmd == "quit":
                print("[DEBUG] Exiting...")
                grpc_client.close()
                sys.exit(0)
            elif cmd == "help":
                print_help()
            else:
                print("[DEBUG] Unknown command. Type 'help' for available commands.")
    return seed

class GRPCSocketWrapper:
    def __init__(self, grpc_client):
        self.grpc_client = grpc_client

    def sendall(self, data):
        # data is a byte-string (e.g., "LOSE:123\n" or "GARBAGE:2\n")
        message = data.decode().strip()
        print(f"[DEBUG] GRPCSocketWrapper received data to send: {message}")
        if message.startswith("LOSE:"):
            try:
                score = int(message.split(":", 1)[1].strip())
            except ValueError:
                score = 0
            msg = tetris_pb2.TetrisMessage(type=tetris_pb2.LOSE, score=score)
            self.grpc_client.send_message(msg)
            print(f"[DEBUG] Sent LOSE message with score: {score}")
        elif message.startswith("GARBAGE:"):
            try:
                n = int(message.split(":", 1)[1].strip())
            except ValueError:
                n = 0
            msg = tetris_pb2.TetrisMessage(type=tetris_pb2.GARBAGE, garbage=n)
            self.grpc_client.send_message(msg)
            print(f"[DEBUG] Sent GARBAGE message with value: {n}")
        else:
            print(f"[DEBUG] Unhandled message: {message}")

def run_game_session():
    grpc_client = TetrisClient()
    grpc_client.connect()
    print("[DEBUG] Connected to gRPC server.")

    # Enter the lobby and wait until we get a GAME_STARTED message with the seed.
    seed = run_lobby(grpc_client)
    
    grpc_socket_wrapper = GRPCSocketWrapper(grpc_client)
    get_next_piece = create_piece_generator(seed)
    
    final_score = run_game(get_next_piece, grpc_socket_wrapper, grpc_client.incoming_queue)
    
    print("[DEBUG] Your game has ended!")
    print(f"Final Score: {final_score}")
    grpc_socket_wrapper.sendall(f"LOSE:{final_score}\n".encode())
    print("[DEBUG] Waiting for final game results from the server...\n")
    
    game_results = None
    while True:
        msg = grpc_client.get_message(timeout=1)
        if msg and msg.type == tetris_pb2.GAME_RESULTS:
            game_results = msg.results
            break

    if game_results:
        print("\n=== GAME RESULTS ===")
        print(game_results)
        print("====================\n")
    else:
        print("[DEBUG] No final game results received.")
    
    return grpc_client

def main():
    while True:
        client = run_game_session()
        print("[DEBUG] Returning to lobby for a new round...\n")
        time.sleep(3)
        client.close()

if __name__ == "__main__":
    main()
