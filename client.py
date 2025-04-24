import sys
import time
import select
import queue
from network import connect_to_server, seed_queue, garbage_queue, DEFAULT_PORT, DEFAULT_HOST
from tetris_game import create_piece_generator, run_game

def print_help():
    print("\nCommands:")
    print("  ready    - Signal that you are ready to play")
    print("  start    - Manually start the game (even if not all players are ready)")
    print("  quit     - Exit the program")
    print()

def clear_queue(q):
    while not q.empty():
        try:
            q.get_nowait()
        except queue.Empty:
            break

def run_lobby(existing_socket=None):
    if existing_socket is None:
        client_socket = connect_to_server(DEFAULT_HOST, DEFAULT_PORT)
    else:
        client_socket = existing_socket

    clear_queue(seed_queue)
    print_help()
    waiting_for_game = True
    ready_sent = False
    printed_prompt = False

    while waiting_for_game:
        try:
            seed_or_message = seed_queue.get_nowait()
            if isinstance(seed_or_message, int):
                seed = seed_or_message
                waiting_for_game = False
                break
            elif seed_or_message is None:
                print("Could not join game. Exiting.")
                client_socket.close()
                sys.exit(1)
        except queue.Empty:
            pass

        if not printed_prompt:
            print("> ", end="", flush=True)
            printed_prompt = True

        rlist, _, _ = select.select([sys.stdin], [], [], 1)
        if rlist:
            cmd = sys.stdin.readline().strip().lower()
            printed_prompt = False
            if cmd == "ready" and not ready_sent:
                client_socket.sendall("READY\n".encode())
                print("Sent READY to server. Waiting for game to start...")
                ready_sent = True
            elif cmd == "start":
                client_socket.sendall("START\n".encode())
                print("Sent START command. Manually starting the game...")
            elif cmd == "quit":
                print("Exiting...")
                client_socket.close()
                sys.exit(0)
            elif cmd == "help":
                print_help()
            else:
                print("Unknown command. Type 'help' for available commands.")

    if waiting_for_game:
        seed_or_message = seed_queue.get()
        if seed_or_message is None:
            print("Could not join game. Exiting.")
            client_socket.close()
            sys.exit(1)
        elif isinstance(seed_or_message, int):
            seed = seed_or_message
        else:
            seed = None

    print(f"Received game seed: {seed}")
    return client_socket, seed

def run_game_session(existing_socket=None):
    client_socket, seed = run_lobby(existing_socket)
    get_next_piece = create_piece_generator(seed)
    # Pass garbage_queue as the net_queue for processing garbage messages.
    final_score = run_game(get_next_piece, client_socket, garbage_queue)
    print("Your game has ended!")
    print(f"Final Score: {final_score}")
    client_socket.sendall(f"LOSE:{final_score}\n".encode())
    print("Waiting for final game results from the server...\n")
    game_results = None
    while True:
        try:
            message = seed_queue.get()
            if isinstance(message, str) and message.startswith("GAME_RESULTS:"):
                game_results = message[len("GAME_RESULTS:"):].strip()
                break
        except KeyboardInterrupt:
            print("Interrupted while waiting for final results.")
            break

    if game_results:
        print("\n=== GAME RESULTS ===")
        print(game_results)
        print("====================\n")
    else:
        print("No final game results received.")
    return client_socket

def main():
    client_socket = None
    while True:
        client_socket = run_game_session(existing_socket=client_socket)
        print("Returning to lobby for a new round...\n")
        clear_queue(seed_queue)
        clear_queue(garbage_queue)
        time.sleep(3)
    if client_socket:
        client_socket.close()

if __name__ == "__main__":
    main()
