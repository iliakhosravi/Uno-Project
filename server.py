import socket
import threading
import sqlite3
from uno import UnoGame, UnoCard


class UnoServer:
    def __init__(self, host='127.0.0.1', port=5555):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host, port))
        self.server_socket.listen(5)
        self.clients = []
        self.game = None
        self.lock = threading.Lock()
        self.running = True
        self.usernames = {}

    def setup_database(self):
        """
        Create database tables if they do not exist.
        """
        conn = sqlite3.connect("uno_game.db")
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0
            )
        """)

        # Create game history table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS game_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                winner_username TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def start_game(self, num_players):
        self.game = UnoGame(num_players)
        print("Game started with {} players.".format(num_players))

    def login_or_register(self, client_socket):
        """
        Handle user login or registration.
        """
        conn = sqlite3.connect("uno_game.db")
        cursor = conn.cursor()

        while True:
            client_socket.send("Do you want to login or register? (login/register): ".encode('utf-8'))
            choice = client_socket.recv(1024).decode('utf-8').strip().lower()

            if choice == "login":
                client_socket.send("Enter username: ".encode('utf-8'))
                username = client_socket.recv(1024).decode('utf-8').strip()
                client_socket.send("Enter password: ".encode('utf-8'))
                password = client_socket.recv(1024).decode('utf-8').strip()

                cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
                user = cursor.fetchone()

                if user:
                    self.usernames[client_socket] = username
                    client_socket.send(f"Welcome back, {username}! Here is your game history:\n".encode('utf-8'))

                    # Fetch game history
                    cursor.execute("SELECT * FROM game_history WHERE winner_username = ?", (username,))
                    games = cursor.fetchall()

                    if games:
                        for game in games:
                            client_socket.send(f"Game ID: {game[0]}, Won on: {game[2]}\n".encode('utf-8'))
                    else:
                        client_socket.send("No games won yet.\n".encode('utf-8'))
                    conn.close()
                    return username
                else:
                    client_socket.send("Invalid credentials. Try again.\n".encode('utf-8'))

            elif choice == "register":
                client_socket.send("Enter a new username: ".encode('utf-8'))
                username = client_socket.recv(1024).decode('utf-8').strip()
                client_socket.send("Enter a new password: ".encode('utf-8'))
                password = client_socket.recv(1024).decode('utf-8').strip()

                try:
                    cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                    conn.commit()
                    self.usernames[client_socket] = username
                    client_socket.send(f"Registration successful! Welcome, {username}.\n".encode('utf-8'))
                    conn.close()
                    return username
                except sqlite3.IntegrityError:
                    client_socket.send("Username already exists. Try again.\n".encode('utf-8'))

    def update_game_results(self, winner_username):
        """
        Update the database with game results.
        """
        conn = sqlite3.connect("uno_game.db")
        cursor = conn.cursor()

        # Update user statistics
        cursor.execute("UPDATE users SET games_played = games_played + 1 WHERE username = ?", (winner_username,))
        cursor.execute("UPDATE users SET games_won = games_won + 1 WHERE username = ?", (winner_username,))

        # Insert into game history
        cursor.execute("INSERT INTO game_history (winner_username) VALUES (?)", (winner_username,))

        conn.commit()
        conn.close()

    def send_player_hands(self):
        """
        Send each player's hand to them at the beginning of their turn.
        """
        for player, client in zip(self.game.players, self.clients):
            username = self.usernames[client]
            hand = f"Your hand ({username}): " + ", ".join(str(card) for card in player.hand)
            try:
                client.send(hand.encode('utf-8'))
            except Exception as e:
                print(f"Error sending hand to {username}: {e}")

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

    def show_turn(self):
        """
        Notify all players whose turn it is.
        """
        current_player = self.game.current_player
        current_socket = self.clients[self.game.players.index(current_player)]
        current_username = self.usernames[current_socket]
        turn_message = f"It's {current_username}'s turn!"
        print(turn_message)
        self.broadcast(turn_message)

    def handle_client(self, client_socket, player_id):
        """
        Handle communication with a single client.
        """
        username = self.login_or_register(client_socket)

        try:
            while self.running:
                data = client_socket.recv(1024).decode('utf-8')
                if not data:
                    break
                print(f"Received from {username}: {data}")
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
            print(f"{username} disconnected.")
        finally:
            client_socket.close()
            
    def update_game_state(self):
        """
        Send updated game state to all players, including the current card.
        """
        self.send_player_hands()
        current_card = f"Current card: {self.game.current_card} (Color: {self.game.current_card._color})"
        self.broadcast(current_card)
        self.show_turn()

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
        for player, client in zip(self.game.players, self.clients):
            if len(player.hand) == 0:  # Player has no cards left
                winner_username = self.usernames[client]
                winner_message = f"{winner_username} wins!"
                print(winner_message)
                self.broadcast(winner_message)

                # Update the database
                self.update_game_results(winner_username)

                self.running = False
                return True
        return False

    def start(self):
        """
        Start the server and accept connections.
        """
        self.setup_database()
        print("Server is running...")

        while True:
            client_socket, addr = self.server_socket.accept()
            print(f"Connection from {addr}")

            if len(self.clients) < len(self.game.players):
                self.clients.append(client_socket)
                threading.Thread(target=self.handle_client, args=(client_socket, len(self.clients) - 1)).start()

                # Start the game once all players have logged in
                if len(self.clients) == len(self.game.players):
                    # Wait until all players have registered/logged in
                    while len(self.usernames) < len(self.clients):
                        continue  # Busy-wait until all players finish logging in

                    self.broadcast("Game is starting!")
                    self.update_game_state()  # Announce the initial game state and turn
            else:
                client_socket.send("Game is full. Try again later.".encode('utf-8'))
                client_socket.close()


if __name__ == '__main__':
    server = UnoServer()
    num_players = int(input("Enter number of players: "))
    server.start_game(num_players)
    server.start()
