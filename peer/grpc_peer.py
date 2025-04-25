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

        for addr in peer_addrs:
            try:
                host, port_s = addr.rsplit(":", 1)
                port = int(port_s)
            except Exception:
                host, port = addr, None

            if (self.listen_port is not None and port == self.listen_port
                    and host in ("localhost", "127.0.0.1", "::1", "[::1]")):
                print(f"[DEBUG] Skipping dial to self at {addr}")
                continue

            q = queue.Queue()
            self.out_queues[addr] = q
            channel = grpc.insecure_channel(addr)
            stub = tetris_pb2_grpc.TetrisServiceStub(channel)

            def outbound_gen(q=q):
                while True:
                    msg = q.get()
                    print(f"[DEBUG] OUT → {addr}: {msg}")
                    yield msg

            response_iter = stub.Play(outbound_gen())
            threading.Thread(
                target=self._recv_thread,
                args=(addr, response_iter),
                daemon=True
            ).start()
            print(f"[DEBUG] Connected to peer stub at {addr}")

    def _recv_thread(self, addr, response_iter):
        """Receive messages from stub.Play() and enqueue them."""
        try:
            for msg in response_iter:
                print(f"[DEBUG] IN  ← {addr}: {msg}")
                self.incoming.put((addr, msg))
        except Exception as e:
            print(f"[ERROR] _recv_thread for {addr} crashed: {e}")

    # gRPC service handler: peers call this on our server
    def Play(self, request_iterator, context):
        peer_id = context.peer()
        q = queue.Queue()
        with self.lock:
            self.out_queues[peer_id] = q
        print(f"[DEBUG] Peer {peer_id} connected inbound")

        def reader():
            try:
                for msg in request_iterator:
                    print(f"[DEBUG] IN  ← {peer_id}: {msg}")
                    self.incoming.put((peer_id, msg))
            except Exception as e:
                print(f"[ERROR] inbound reader for {peer_id} crashed: {e}")

        threading.Thread(target=reader, daemon=True).start()

        # Stream outbound messages to this peer
        while True:
            msg = q.get()
            yield msg

    def broadcast(self, msg):
        """Broadcast a TetrisMessage to all connected peers."""
        with self.lock:
            for addr, q in self.out_queues.items():
                q.put(msg)
