import sys
from network import connect_to_server, seed_queue, DEFAULT_PORT, DEFAULT_HOST
from tetris_game import create_piece_generator, run_game

if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    port = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT

    client_socket = connect_to_server(host, port)
    
    # Send READY message to the server
    client_socket.sendall("READY\n".encode())
    print("Sent READY to server. Waiting for game to start...")
    
    # Wait for the seed from the queue (filled by client_listener thread)
    seed = seed_queue.get()
    print(f"Received game seed: {seed}")
    
    # Create piece generator with the seed and run game
    get_next_piece = create_piece_generator(seed)
    final_score = run_game(get_next_piece)
    print("Game Over!")
    print(f"Final Score: {final_score}")
    
    client_socket.close()