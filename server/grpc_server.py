import threading
import random
import queue
import time
import grpc
from concurrent import futures

from proto import tetris_pb2
from proto import tetris_pb2_grpc

lock = threading.RLock()
# Dictionary mapping client id (from context.peer()) to a dict with:
#   'ready': boolean readiness flag,
#   'queue': queue.Queue() for outgoing messages.
clients = {}

MAX_PLAYERS = 4
game_started = False
game_seed = None
players_results = {}

def reset_game_state():
    global game_started, game_seed, players_results
    game_started = False
    game_seed = None
    players_results = {}
    print("[DEBUG] Game state reset, ready for a new game.")

def broadcast_message(message):
    with lock:
        to_remove = []
        for client_id, info in clients.items():
            try:
                print(f"[DEBUG] Broadcasting message to {client_id}: {message}")
                info['queue'].put(message)
            except Exception as e:
                print(f"[ERROR] Could not broadcast to {client_id}: {e}")
                to_remove.append(client_id)
        for client_id in to_remove:
            del clients[client_id]

def broadcast_results():
    with lock:
        sorted_results = sorted(players_results.items(), key=lambda item: item[1], reverse=True)
        results_list = " | ".join(f"{cid}: {score}" for cid, score in sorted_results)
        msg = tetris_pb2.TetrisMessage(
            type=tetris_pb2.GAME_RESULTS,
            results=results_list
        )
        print("[DEBUG] Broadcasting final results: " + results_list)
        broadcast_message(msg)
        reset_game_state()

def start_game():
    global game_started, game_seed
    with lock:
        print("[DEBUG] Entering start_game(): game_started =", game_started)
        if not game_started:
            game_seed = random.randint(0, 1000000)
            game_started = True
            msg = tetris_pb2.TetrisMessage(
                type=tetris_pb2.GAME_STARTED,
                seed=game_seed
            )
            print(f"[DEBUG] Starting game with seed {game_seed}")
            broadcast_message(msg)
        else:
            print("[DEBUG] Game already started, not starting again.")


class TetrisServiceServicer(tetris_pb2_grpc.TetrisServiceServicer):
    def Play(self, request_iterator, context):
        client_id = context.peer()
        client_queue = queue.Queue()
        with lock:
            if game_started:
                print(f"[DEBUG] Client {client_id} connected after game started; sending GAME_ALREADY_STARTED.")
                client_queue.put(tetris_pb2.TetrisMessage(type=tetris_pb2.GAME_ALREADY_STARTED))
            clients[client_id] = {'ready': False, 'queue': client_queue}
        print(f"[DEBUG] Client {client_id} connected.")

        def process_incoming():
            try:
                for msg in request_iterator:
                    print(f"[DEBUG] Received message from {client_id}: {msg}")
                    if msg.type == tetris_pb2.READY:
                        with lock:
                            clients[client_id]['ready'] = True
                            ready_count = sum(1 for info in clients.values() if info['ready'])
                            print(f"[DEBUG] Client {client_id} marked as READY. Ready count: {ready_count}/{len(clients)}")
                    elif msg.type == tetris_pb2.START:
                        print(f"[DEBUG] Client {client_id} requested to start the game manually.")
                        with lock:
                            if not game_started:
                                print(f"[DEBUG] Starting game due to manual request from {client_id}.")
                                start_game()
                            else:
                                print(f"[DEBUG] Game already started; sending GAME_ALREADY_STARTED to {client_id}.")
                                client_queue.put(tetris_pb2.TetrisMessage(type=tetris_pb2.GAME_ALREADY_STARTED))
                    elif msg.type == tetris_pb2.LOSE:
                        with lock:
                            players_results[client_id] = msg.score
                            print(f"[DEBUG] Recorded LOSE from {client_id} with score {msg.score}")
                            if len(players_results) == len(clients):
                                print("[DEBUG] All players reported loss; broadcasting final results.")
                                broadcast_results()
                    elif msg.type == tetris_pb2.GARBAGE:
                        with lock:
                            garbage_msg = tetris_pb2.TetrisMessage(
                                type=tetris_pb2.GARBAGE,
                                garbage=msg.garbage
                            )
                            print(f"[DEBUG] Broadcasting GARBAGE from {client_id}: {msg.garbage}")
                            for cid, info in clients.items():
                                if cid != client_id:
                                    info['queue'].put(garbage_msg)
                    else:
                        print(f"[DEBUG] Unknown message type from {client_id}: {msg}")
            except Exception as e:
                print(f"[ERROR] Error processing messages from {client_id}: {e}")

        incoming_thread = threading.Thread(target=process_incoming, daemon=True)
        incoming_thread.start()

        try:
            while context.is_active():
                try:
                    out_msg = client_queue.get(timeout=0.1)
                    print(f"[DEBUG] Yielding message to {client_id}: {out_msg}")
                    yield out_msg
                except queue.Empty:
                    continue
        except Exception as e:
            print(f"[ERROR] Error streaming messages to {client_id}: {e}")
        finally:
            with lock:
                if client_id in clients:
                    del clients[client_id]
            print(f"[DEBUG] Client {client_id} disconnected.")

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    tetris_pb2_grpc.add_TetrisServiceServicer_to_server(TetrisServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    print("gRPC Tetris server started on port 50051.")
    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        server.stop(0)
        print("Server stopped.")

if __name__ == '__main__':
    serve()
