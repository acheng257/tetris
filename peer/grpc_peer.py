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
        # My IP addresses (for self-connection detection)
        self.my_ips = self._get_my_ip_addresses()
        # Track persistent peers that should be reconnected if they drop
        self.persistent_peers = set()
        # Reconnection timers
        self.reconnect_timers = {}

        try:
            _, port_str = listen_addr.rsplit(":", 1)
            self.listen_port = int(port_str)
        except Exception:
            self.listen_port = None

        print(f"[DEBUG] My IP addresses: {self.my_ips}")
        print(f"[DEBUG] My listen port: {self.listen_port}")

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

            # Add to persistent peers list for reconnection
            self.persistent_peers.add(addr)

            # Try to connect to this peer
            self._connect_to_peer(addr)

    def _get_my_ip_addresses(self):
        """Get all IP addresses of this machine for better self-connection detection"""
        import socket

        my_ips = set(["localhost", "127.0.0.1", "::", "::1", "[::1]", "[::])"])

        try:
            # Get hostname and local IPs
            hostname = socket.gethostname()
            my_ips.add(hostname)

            # Get all local IP addresses
            for ip in socket.gethostbyname_ex(hostname)[2]:
                my_ips.add(ip)

            # Try to get the external IP if possible
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))  # Google's DNS server
                my_ips.add(s.getsockname()[0])
                s.close()
            except:
                pass

        except Exception as e:
            print(f"[ERROR] Failed to get IP addresses: {e}")

        return my_ips

    def _is_self_addr(self, addr, host, port):
        """More robust check for self-connections"""
        # Clean up the host to handle various formats
        clean_host = host
        if host.startswith("[") and host.endswith("]"):
            clean_host = host[1:-1]

        # Check if it matches any of our IPs
        if clean_host in self.my_ips:
            if self.listen_port is not None and port == self.listen_port:
                return True

        # If matching the listen port but on any interface
        if port == self.listen_port and (clean_host in ["0.0.0.0", "::", "*"]):
            return True

        # Direct comparison with listen_addr
        if addr == self.listen_addr:
            return True

        return False

    def _connect_to_peer(self, addr):
        """Connect to a peer at the given address"""
        try:
            peer_identity = self._get_peer_identity(addr)

            # Check if we already have a connection to this peer
            if self._is_duplicate_connection(addr):
                print(
                    f"[DEBUG] Already have a connection to peer with identity {peer_identity}, skipping {addr}"
                )
                return

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
            print(
                f"[DEBUG] Connected to peer stub at {addr} (identity: {peer_identity})"
            )
        except Exception as e:
            print(f"[ERROR] Failed to connect to peer {addr}: {e}")
            if addr in self.out_queues:
                del self.out_queues[addr]

            # Try again later if this is an important peer
            if addr in self.persistent_peers:
                self._schedule_reconnect(addr)

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
                # Remove from unique_peers if it was there
                peer_identity = self._get_peer_identity(addr)
                for peer in list(self.unique_peers):
                    if self._get_peer_identity(peer) == peer_identity:
                        self.unique_peers.remove(peer)
                        print(
                            f"[DEBUG] Removed {peer} from unique_peers due to connection failure"
                        )

            # Try to reconnect if this is a persistent peer
            if addr in self.persistent_peers:
                self._schedule_reconnect(addr)

    # gRPC service handler: peers call this on our server
    def Play(self, request_iterator, context):
        peer_id = context.peer()
        peer_identity = self._get_peer_identity(peer_id)

        # Check if we already have a connection from this peer
        with self.lock:
            if self._is_duplicate_connection(peer_id):
                print(
                    f"[DEBUG] Duplicate connection from {peer_id} (identity: {peer_identity}), rejecting"
                )
                context.abort(grpc.StatusCode.ALREADY_EXISTS, "Duplicate connection")
                return

            self.unique_peers.add(peer_id)
            q = queue.Queue()
            self.out_queues[peer_id] = q

        print(f"[DEBUG] Peer {peer_id} connected inbound (identity: {peer_identity})")

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

                    print(
                        f"[DEBUG] Peer {peer_id} disconnected (identity: {peer_identity})"
                    )

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

    def send(self, target_addr, msg):
        """Send a message to a specific peer"""
        with self.lock:
            if target_addr in self.out_queues:
                if hasattr(msg, "type") and msg.type == tetris_pb2.GARBAGE:
                    print(
                        f"[P2P DEBUG] Sending GARBAGE to {target_addr}: {msg.garbage} lines"
                    )
                self.out_queues[target_addr].put(msg)
            else:
                print(f"[ERROR] No connection to {target_addr}")

    def _normalize_peer_addr(self, addr):
        """Normalize a peer address to a standard format to help with deduplication"""
        try:
            # Handle gRPC prefixes
            if addr.startswith("ipv4:") or addr.startswith("ipv6:"):
                addr = addr.split(":", 1)[1]

            # Extract host and port
            if addr.startswith("[") and "]:" in addr:
                # IPv6 address in brackets
                host = addr[: addr.find("]") + 1]
                port = addr.split("]:", 1)[1]
            else:
                # IPv4 address or hostname
                host, port = addr.rsplit(":", 1)

            # Clean up IPv6 brackets if present
            if host.startswith("[") and host.endswith("]"):
                host = host[1:-1]

            # Return standardized format
            return f"{host.lower()}:{port}"
        except Exception as e:
            print(f"[ERROR] Failed to normalize peer address {addr}: {e}")
            return addr

    def _get_peer_identity(self, addr):
        """
        Extract a unique identity that properly handles different network representations
        of the same peer, especially on localhost.

        Normalized identity format should be host:port, with special handling for localhost
        """
        try:
            # Handle URL-encoded characters (from gRPC representation)
            if "%5B" in addr:  # URL-encoded '['
                addr = addr.replace("%5B", "[").replace("%5D", "]")

            # Remove protocol prefix if present (ipv4:, ipv6:)
            if ":" in addr and addr.split(":", 1)[0] in ("ipv4", "ipv6"):
                addr = addr.split(":", 1)[1]

            # Extract host and port
            host, port = None, None

            # Handle IPv6 addresses with brackets [::1]:port
            if addr.startswith("[") and "]:" in addr:
                # Format: [ipv6_addr]:port
                ipv6_end = addr.find("]")
                host = addr[1:ipv6_end]  # Remove brackets
                port = addr[ipv6_end + 2 :]  # Skip the ":" after "]"
            elif addr.startswith("[") and addr.endswith("]"):
                # Format: [ipv6_addr] without port
                host = addr[1:-1]  # Remove brackets
                port = str(self.listen_port)  # Use listen port as this is likely server
            elif ":" in addr:
                # Format: host:port
                parts = addr.rsplit(
                    ":", 1
                )  # Split on last colon to handle IPv6 with colons
                host = parts[0]
                port = parts[1]
            else:
                # No port specified
                host = addr
                port = "0"

            # Normalize localhost variations
            if host in ("127.0.0.1", "localhost", "::1", "::", "0.0.0.0"):
                host = "localhost"

            # Combine and normalize
            canonical_id = f"{host.lower()}:{port}"
            return canonical_id

        except Exception as e:
            print(f"[ERROR] Failed to normalize peer identity from {addr}: {e}")
            return addr.lower()  # Fall back to lowercased original

    def _is_duplicate_connection(self, peer_id):
        """Check if we already have a connection to this peer's identity"""
        peer_identity = self._get_peer_identity(peer_id)

        with self.lock:
            # Check all existing connections
            for existing in self.unique_peers:
                if peer_identity == self._get_peer_identity(existing):
                    return True

        return False

    def _schedule_reconnect(self, addr, delay=5):
        """Schedule a reconnection attempt to a peer after a delay"""
        # Cancel any existing timer
        if addr in self.reconnect_timers:
            self.reconnect_timers[addr].cancel()

        def reconnect_task():
            print(f"[DEBUG] Attempting to reconnect to {addr}")
            self._connect_to_peer(addr)
            # Remove from timers if successful (otherwise it will be rescheduled)
            if addr in self.reconnect_timers:
                del self.reconnect_timers[addr]

        # Create a new timer
        timer = threading.Timer(delay, reconnect_task)
        timer.daemon = True
        self.reconnect_timers[addr] = timer
        timer.start()
        print(f"[DEBUG] Scheduled reconnection to {addr} in {delay} seconds")
