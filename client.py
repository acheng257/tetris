import sys
import time
import select
import queue
from network import connect_to_server, seed_queue, DEFAULT_PORT, DEFAULT_HOST
from tetris_game import create_piece_generator, run_game

def print_help():
    print("\nCommands:")
    print("  ready    - Signal that you are ready to play")
    print("  start    - Manually start the game (even if not all players are ready)")
    print("  quit     - Exit the program")
    print()

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

    try:
        client_socket = connect_to_server(host, port)
    except ConnectionRefusedError:
        print(f"Could not connect to server at {host}:{port}")
        sys.exit(1)
    
    print_help()
    
    waiting_for_game = True
    ready_sent = False
    printed_prompt = False

    while waiting_for_game:
        # Check for seed from the server (non-blocking)
        try:
            seed = seed_queue.get_nowait()
            if seed is None:
                print("Could not join game. Exiting.")
                client_socket.close()
                sys.exit(1)
            waiting_for_game = False
            break  # Exit loop; game is starting
        except queue.Empty:
            pass  # No seed yet; continue with command loop

        if not printed_prompt:
            print("> ", end="", flush=True)
            printed_prompt = True

        # Wait for input with a 1-second timeout
        rlist, _, _ = select.select([sys.stdin], [], [], 1)
        if rlist:
            # User pressed a key; read the input and reset the prompt flag
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

    print("Game is starting!")
    
    if waiting_for_game:
        seed = seed_queue.get()
        if seed is None:
            print("Could not join game. Exiting.")
            client_socket.close()
            sys.exit(1)
    
    print(f"Received game seed: {seed}")
    
    get_next_piece = create_piece_generator(seed)
    final_score = run_game(get_next_piece)
    print("Game Over!")
    print(f"Final Score: {final_score}")
    
    client_socket.close()
