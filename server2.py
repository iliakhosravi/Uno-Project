import socket
import threading
from uno import UnoGame, UnoCard

class UnoServer:
    def __init__(self, host='127.0.0.1', port=5555):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind((host, port))
        self.server_socket.listen(5)
        self.clients = []
        self.game = None
        self.lock = threading.Lock()
        self.running = True

    def start_game(self, num_players):
        self.game = UnoGame(num_players)
        print("Game started with {} players.".format(num_players))

    def send_player_hands(self):
        """
        Send each player's hand to them at the beginning of their turn.
        """
        for player_id, client in enumerate(self.clients):
            player = self.game.players[player_id]
            hand = "Your hand: " + ", ".join(str(card) for card in player.hand)
            try:
                client.send(hand.encode('utf-8'))
            except Exception as e:
                print(f"Error sending hand to player {player_id}: {e}")

    def broadcast(self, message, exclude_client=None):
        """
        Send a message to all connected clients except the excluded one.
        """
        for client in self.clients:
            if client != exclude_client:
                try:
                    client.send(message.encode('utf-8'))
                except Exception as e:
                    print(f"Error sending message to a client: {e}")

    def handle_client(self, client_socket, player_id):
        """
        Handle communication with a single client.
        """
        try:
            while self.running:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                print(f"Received from player {player_id}: {data}")
                response, broadcast_message = self.process_action(player_id, data)

                # Send the response to the specific client
                if response:
                    client_socket.send(response.encode('utf-8'))

                # Broadcast game updates to all other clients
                if broadcast_message:
                    self.broadcast(broadcast_message, exclude_client=client_socket)

                # Check for a winner and end the game if necessary
                if self.check_winner():
                    break

                # Send updated game state
                self.update_game_state()
        except ConnectionResetError:
            print(f"Player {player_id} disconnected.")
        finally:
            client_socket.close()

    def update_game_state(self):
        """
        Send updated game state to all players, including the current card.
        """
        self.send_player_hands()
        current_card = f"Current card: {self.game.current_card} (Color: {self.game.current_card._color})"
        self.broadcast(current_card)

    def process_action(self, player_id, action):
        """
        Process player actions and return:
        - A specific response for the acting player
        - A broadcast message for all other players
        """
        with self.lock:
            player = self.game.players[player_id]
            if self.game.current_player != player:
                return "Not your turn.", None

            if action == "pick":
                self.game.play(player_id, card=None)
                return f"You picked a card.", f"Player {player_id} picked a card."

            # Assume action format: "play <card_index> [new_color]"
            parts = action.split()
            if parts[0] == "play":
                try:
                    card_index = int(parts[1])
                    new_color = parts[2] if len(parts) > 2 else None
                    played_card = player.hand[card_index]
                    self.game.play(player_id, card=card_index, new_color=new_color)
                    return (
                        f"You played {played_card}.",
                        f"Player {player_id} played {played_card}."
                    )
                except (IndexError, ValueError) as e:
                    return f"Invalid action: {e}", None
                except Exception as e:
                    return f"Error: {e}", None

            return "Invalid action.", None

    def check_winner(self):
        """
        Check if any player has won the game. If so, announce the winner and end the game.
        """
        for player_id, player in enumerate(self.game.players):
            if len(player.hand) == 0:  # Player has no cards left
                winner_message = f"Player {player_id} wins!"
                print(winner_message)
                self.broadcast(winner_message)
                self.running = False
                return True
        return False

    def start(self):
        """
        Start the server and accept connections.
        """
        print("Server is running...")
        while True:
            client_socket, addr = self.server_socket.accept()
            player_id = len(self.clients)
            self.clients.append(client_socket)
            print(f"Player {player_id} connected from {addr}")
            if len(self.clients) == len(self.game.players):
                self.broadcast("Game is starting!")
                self.update_game_state()  # Initial game state
            threading.Thread(target=self.handle_client, args=(client_socket, player_id)).start()

if __name__ == '__main__':
    server = UnoServer()
    num_players = int(input("Enter number of players: "))
    server.start_game(num_players)
    server.start()
