import sys
from network import start_server

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9999
    start_server(port=port)
    print("Server is running. It is only providing the game seed to clients.")
    try:
        while True:
            pass  # Keep the server running.
    except KeyboardInterrupt:
        print("Server shutting down.")
