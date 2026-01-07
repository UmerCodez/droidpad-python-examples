import socket

HOST = '0.0.0.0'
PORT = 8080

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen()
print(f"TCP Server listening on {HOST}:{PORT}")

try:
    while True:
        print("Waiting for a new client...")
        client_socket, client_address = server_socket.accept()
        print(f"Connection established with {client_address}")

        try:
            while True:
                message = client_socket.recv(1024).decode('utf-8')
                if not message:  # client disconnected
                    print(f"Client {client_address} disconnected")
                    break
                print(message)
        except Exception as e:
            print(f"Error with client {client_address}: {e}")
        finally:
            client_socket.close()

except KeyboardInterrupt:
    print("\nShutting down the server...")

finally:
    server_socket.close()

