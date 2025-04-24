import grpc
import threading
import queue
from proto import tetris_pb2
from proto import tetris_pb2_grpc

class TetrisClient:
    def __init__(self, server_address='localhost:50051'):
        self.channel = grpc.insecure_channel(server_address)
        self.stub = tetris_pb2_grpc.TetrisServiceStub(self.channel)
        self.outgoing_queue = queue.Queue()  # For sending messages to the server
        self.incoming_queue = queue.Queue()  # For messages received from the server
        self._closed = False

    def _start_stream(self):
        while not self._closed:
            try:
                msg = self.outgoing_queue.get(timeout=0.1)
                print(f"[DEBUG] Outgoing message: {msg}")
                yield msg
            except queue.Empty:
                continue

    def _receive_messages(self, response_iterator):
        try:
            for msg in response_iterator:
                print(f"[DEBUG] grpc_client received message: {msg}")
                self.incoming_queue.put(msg)
        except Exception as e:
            print("[ERROR] Error receiving messages:", e)

    def connect(self):
        self.call = self.stub.Play(self._start_stream())
        self.receive_thread = threading.Thread(
            target=self._receive_messages, args=(self.call,), daemon=True)
        self.receive_thread.start()
        print("[DEBUG] grpc_client connected and receive thread started")

    def send_message(self, msg):
        print(f"[DEBUG] grpc_client sending message: {msg}")
        self.outgoing_queue.put(msg)

    def get_message(self, timeout=1):
        try:
            return self.incoming_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self):
        self._closed = True
        self.channel.close()

if __name__ == '__main__':
    client = TetrisClient()
    client.connect()
    client.send_message(tetris_pb2.TetrisMessage(type=tetris_pb2.READY))
    try:
        while True:
            msg = client.get_message(timeout=5)
            if msg:
                print(f"[DEBUG] Main loop got message: {msg}")
    except KeyboardInterrupt:
        client.close()
