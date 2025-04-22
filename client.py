import sys
import time
from network import connect_to_server, DEFAULT_PORT, seed_queue
from tetris_game import create_piece_generator, run_game

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT
    
    connect_to_server(host, port)
    print("Waiting for game seed from the server...")
    seed = seed_queue.get()  # block until seed is received
    print(f"Received seed: {seed}")
    
    get_next_piece = create_piece_generator(seed)
    final_score = run_game(get_next_piece)
    print("Game Over!")
    print(f"Final Score: {final_score}")
