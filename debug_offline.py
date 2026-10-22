
import socket
import traceback

def block_network(*args, **kwargs):
    print("\n=== NETWORK CONNECTION ATTEMPT ===")
    traceback.print_stack()
    raise RuntimeError("NETWORK_BLOCKED")

socket.create_connection = block_network
socket.socket.connect = block_network
socket.socket.connect_ex = block_network

from simple_translator import translate

try:
    print(translate("Hello, how are you?"))
except Exception:
    traceback.print_exc()
