import threading
import queue
import grpc
from concurrent import futures

from proto import tetris_pb2, tetris_pb2_grpc


class P2PNetwork(tetris_pb2_grpc.TetrisServiceServicer):
    """
    P2P networking layer: each peer runs a gRPC server and also
    dials out to every other peer to form a full mesh.
    """

    def __init__(self, listen_addr, peer_addrs):
        # Shared incoming queue for all peers: (peer_id, TetrisMessage)
        self.incoming = queue.Queue()
        # Outgoing queues for each peer (address -> Queue)
        self.out_queues = {}
        self.lock = threading.RLock()
        # Track unique peer connections to avoid duplicates
        self.unique_peers = set()
        # My listening address
        self.listen_addr = listen_addr

        try:
            _, port_str = listen_addr.rsplit(":", 1)
            self.listen_port = int(port_str)
        except Exception:
            self.listen_port = None

        self.server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        tetris_pb2_grpc.add_TetrisServiceServicer_to_server(self, self.server)
        self.server.add_insecure_port(listen_addr)
        self.server.start()
        print(f"[DEBUG] P2P server listening on {listen_addr}")

        # Make a copy of peer_addrs to avoid modification during iteration
        for addr in list(peer_addrs):
            try:
                host, port_s = addr.rsplit(":", 1)
                port = int(port_s)
            except Exception:
                host, port = addr, None

            # Skip self-connections with more robust checks
            if self._is_self_addr(addr, host, port):
                print(f"[DEBUG] Skipping dial to self at {addr}")
                continue

            # Try to connect to this peer
            self._connect_to_peer(addr)

    def _is_self_addr(self, addr, host, port):
        """More robust check for self-connections"""
        if self.listen_port is not None and port == self.listen_port:
            # Check various localhost representations
            if host in ("localhost", "127.0.0.1", "::1", "[::1]"):
                return True

            # Check if the host is our own IP (used when connecting from another machine)
            try:
                if host == self.listen_addr.split(":")[0]:
                    return True
            except Exception:
                pass

        # Direct comparison with listen_addr
        if addr == self.listen_addr:
            return True

        return False

    def _connect_to_peer(self, addr):
        """Connect to a peer at the given address"""
        try:
            q = queue.Queue()
            self.out_queues[addr] = q
            channel = grpc.insecure_channel(addr)
            stub = tetris_pb2_grpc.TetrisServiceStub(channel)

            def outbound_gen(q=q):
                while True:
                    msg = q.get()
                    # Skip debug output for GAME_STATE messages
                    if not hasattr(msg, "type") or msg.type != tetris_pb2.GAME_STATE:
                        print(f"[DEBUG] OUT → {addr}: {msg.type}")
                    yield msg

            response_iter = stub.Play(outbound_gen())
            threading.Thread(
                target=self._recv_thread, args=(addr, response_iter), daemon=True
            ).start()
            print(f"[DEBUG] Connected to peer stub at {addr}")
        except Exception as e:
            print(f"[ERROR] Failed to connect to peer {addr}: {e}")
            if addr in self.out_queues:
                del self.out_queues[addr]

    def _recv_thread(self, addr, response_iter):
        """Receive messages from stub.Play() and enqueue them."""
        try:
            for msg in response_iter:
                # Skip debug output for GAME_STATE messages
                if not hasattr(msg, "type") or msg.type != tetris_pb2.GAME_STATE:
                    print(f"[DEBUG] IN  ← {addr}: {msg.type}")
                self.incoming.put((addr, msg))
        except Exception as e:
            print(f"[ERROR] _recv_thread for {addr} crashed: {e}")
            # Remove from out_queues if the connection is broken
            with self.lock:
                if addr in self.out_queues:
                    del self.out_queues[addr]

    # gRPC service handler: peers call this on our server
    def Play(self, request_iterator, context):
        peer_id = context.peer()

        # Check if we already have a connection from this peer
        with self.lock:
            if peer_id in self.unique_peers:
                print(f"[DEBUG] Duplicate connection from {peer_id}, rejecting")
                context.abort(grpc.StatusCode.ALREADY_EXISTS, "Duplicate connection")
                return

            self.unique_peers.add(peer_id)
            q = queue.Queue()
            self.out_queues[peer_id] = q

        print(f"[DEBUG] Peer {peer_id} connected inbound")

        def reader():
            try:
                for msg in request_iterator:
                    # Skip debug output for GAME_STATE messages
                    if not hasattr(msg, "type") or msg.type != tetris_pb2.GAME_STATE:
                        print(f"[DEBUG] IN  ← {peer_id}: {msg.type}")
                    self.incoming.put((peer_id, msg))
            except Exception as e:
                print(f"[ERROR] inbound reader for {peer_id} crashed: {e}")
            finally:
                # Clean up when connection ends
                with self.lock:
                    if peer_id in self.unique_peers:
                        self.unique_peers.remove(peer_id)
                    if peer_id in self.out_queues:
                        del self.out_queues[peer_id]

        threading.Thread(target=reader, daemon=True).start()

        # Stream outbound messages to this peer
        try:
            while True:
                msg = q.get()
                yield msg
        except Exception as e:
            print(f"[ERROR] outbound stream to {peer_id} failed: {e}")
            # Clean up if the stream fails
            with self.lock:
                if peer_id in self.unique_peers:
                    self.unique_peers.remove(peer_id)
                if peer_id in self.out_queues:
                    del self.out_queues[peer_id]

    def broadcast(self, msg):
        """Broadcast a TetrisMessage to all connected peers."""
        # Add debug logging for garbage messages
        if hasattr(msg, "type") and msg.type == 2:  # GARBAGE type
            print(
                f"[P2P DEBUG] Broadcasting GARBAGE message: {msg.garbage} lines to {len(self.out_queues)} peers"
            )
            if hasattr(msg, "sender"):
                print(f"[P2P DEBUG] - Sender: {msg.sender}")

        with self.lock:
            for addr, q in self.out_queues.items():
                q.put(msg)
