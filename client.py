import socket
import threading

class UnoClient:
    def __init__(self, host='127.0.0.1', port=5555):
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.connect((host, port))
        self.running = True

    def send_data(self, data):
        self.client_socket.send(data.encode('utf-8'))

    def receive_data(self):
        while self.running:
            try:
                data = self.client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                print("Server:", data)
            except ConnectionResetError:
                print("Disconnected from server.")
                self.running = False
                break

    def start(self):
        threading.Thread(target=self.receive_data).start()
        print("Game has started!")
        while self.running:
            print("\nAvailable actions: ")
            print("1. play <card_index> [new_color] - To play a card.")
            print("2. pick - To pick a card.")
            print("3. exit - To exit the game.")
            message = input("Your action: ")
            if message.lower() == "exit":
                self.running = False
                break
            self.send_data(message)
        self.client_socket.close()

if __name__ == '__main__':
    client = UnoClient()
    client.start()
