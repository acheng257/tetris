import sys
import select
import random
import queue
import time
from proto import tetris_pb2
from peer.grpc_peer import P2PNetwork
from tetris_game import create_piece_generator, run_game


def main(listen_port, peer_addrs):
    listen_addr = f"[::]:{listen_port}"
    net = P2PNetwork(listen_addr, peer_addrs)

    # Full list of peer addresses (including this one)
    all_addrs = sorted(peer_addrs)

    while True:
        # Reset state each round
        ready = set()
        game_started = False
        seed = None
        results_received = False

        print("Type 'ready' to join lobby. Once everyone is ready, leader auto-starts.")

        while not game_started:
            try:
                peer_id, msg = net.incoming.get(timeout=0.1)
                if msg.type == tetris_pb2.READY:
                    ready.add(peer_id)
                    print(f"[LOBBY] {peer_id} READY ({len(ready)}/{len(all_addrs)})")
                elif msg.type == tetris_pb2.START:
                    seed = msg.seed
                    game_started = True
                    print(f"[LOBBY] Received START, seed = {seed}")
            except queue.Empty:
                pass

            if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                cmd = sys.stdin.readline().strip().lower()
                if cmd == 'ready':
                    net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.READY))
                    ready.add(listen_addr)
                    print(f"[LOBBY] You are READY ({len(ready)}/{len(all_addrs)})")
                elif cmd == 'start':
                    leader = min(all_addrs)
                    if listen_addr == leader or f"localhost:{listen_port}" == leader:
                        if len(ready) == len(all_addrs):
                            seed = random.randint(0, 1_000_000)
                            net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.START, seed=seed))
                            game_started = True
                            print(f"[LOBBY] You (leader) START, seed = {seed}")
                        else:
                            print(f"[LOBBY] Cannot start: waiting for {len(all_addrs) - len(ready)} more players to be ready")
                    else:
                        print(f"[LOBBY] Only leader ({leader}) can START")
                elif cmd == 'quit':
                    print("[LOBBY] Exiting...")
                    sys.exit(0)
                else:
                    print("[LOBBY] Unknown command. Use 'ready', 'start', or 'quit'.")

            if not game_started and len(ready) == len(all_addrs):
                leader = min(all_addrs)
                if listen_addr == leader or f"localhost:{listen_port}" == leader:
                    seed = random.randint(0, 1_000_000)
                    net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.START, seed=seed))
                    game_started = True
                    print(f"[LOBBY] All ready. Leader auto START, seed = {seed}")

        print("=== GAME STARTED ===")
        get_next_piece = create_piece_generator(seed)

        class NetQueueAdapter(queue.Queue):
            def get_nowait(self):
                _, msg = net.incoming.get_nowait()
                return msg

        class PeerSocket:
            def sendall(self, data: bytes):
                s = data.decode().strip()
                if s.startswith("GARBAGE:"):
                    n = int(s.split(":",1)[1])
                    if n > 0:
                        net.broadcast(tetris_pb2.TetrisMessage(
                            type=tetris_pb2.GARBAGE, 
                            garbage=n,
                            sender=listen_addr  # Include sender for self-identification
                        ))
                elif s.startswith("LOSE:"):
                    sc = int(s.split(":",1)[1])
                    net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.LOSE, score=sc))

        final_score = run_game(get_next_piece, PeerSocket(), NetQueueAdapter(), listen_port)
        print(f"[RESULTS] Your score = {final_score}")
        
        net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.LOSE, score=final_score))

        scores = {listen_addr: final_score}
        results_timeout = time.time() + 10  # 10 second timeout
        
        leader = min(all_addrs)
        is_leader = (listen_addr == leader or f"localhost:{listen_port}" == leader)
        
        while len(scores) < len(all_addrs) and time.time() < results_timeout:
            try:
                peer_id, msg = net.incoming.get(timeout=0.5)
                if msg.type == tetris_pb2.LOSE and peer_id not in scores:
                    scores[peer_id] = msg.score
                    print(f"[RESULTS] {peer_id} scored = {msg.score}")
                elif msg.type == tetris_pb2.GAME_RESULTS:
                    print("=== FINAL RESULTS ===")
                    print(msg.results)
                    print("=====================")
                    results_received = True
                    break
            except queue.Empty:
                continue

        # Leader broadcasts results
        if is_leader and not results_received:
            results_str = " | ".join(f"{pid}: {sc}" for pid, sc in sorted(scores.items(), key=lambda x: -x[1]))
            net.broadcast(tetris_pb2.TetrisMessage(type=tetris_pb2.GAME_RESULTS, results=results_str))
            print(f"[RESULTS] Leader broadcasting = {results_str}")

        results_timeout = time.time() + 5
        while not results_received and time.time() < results_timeout:
            try:
                peer_id, msg = net.incoming.get(timeout=0.5)
                if msg.type == tetris_pb2.GAME_RESULTS:
                    print("=== FINAL RESULTS ===")
                    print(msg.results)
                    print("=====================")
                    results_received = True
                    break
            except queue.Empty:
                continue
        
        if not results_received:
            print("=== PARTIAL RESULTS (timeout) ===")
            sorted_scores = sorted(scores.items(), key=lambda x: -x[1])
            for peer_id, score in sorted_scores:
                print(f"{peer_id}: {score}")
            print("================================")

        while not net.incoming.empty():
            try:
                net.incoming.get_nowait()
            except queue.Empty:
                break

        print("Returning to lobby for a new game...")