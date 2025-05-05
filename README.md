# Distributed Tetris Game

This project implements a distributed version of the classic Tetris game using gRPC for communication between peers.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd tetris
    ```

2.  **Install Pipenv (if you don't have it):**
    ```bash
    pip install pipenv
    ```

3.  **Install dependencies using Pipenv:**
    This command will create a virtual environment if one doesn't exist, install the dependencies from the `Pipfile`, and generate a `Pipfile.lock`.
    ```bash
    pipenv install
    ```
    *Note: The `Pipfile` includes `windows-curses` marked as optional for Windows.*

4.  **Activate the virtual environment:**
    ```bash
    pipenv shell
    ```

5.  **Generate Protobuf files:**
    The necessary Python files (`tetris_pb2.py` and `tetris_pb2_grpc.py`) are generated from the `tetris.proto` definition. If you need to regenerate them (e.g., after modifying `tetris.proto`), run the following command from the root directory (inside the `pipenv shell`):
    ```bash
    python -m grpc_tools.protoc -I./proto --python_out=./proto --pyi_out=./proto --grpc_python_out=./proto ./proto/tetris.proto
    ```

## Running the Game

To run the distributed Tetris game, ensure you are inside the `pipenv shell`. 

Open a separate terminal for each player (each also within the `pipenv shell` started in the project directory). Run the following command format in each terminal, replacing `<port>` with a unique port for that player (e.g., 50051, 50052) and `<peer_list>` with the list of all player addresses (including their own):

```bash
python -m peer.peer --port <port> --peers <peer_list>
```

**Example for 3 players on localhost:**

*   **Terminal 1:** `python -m peer.peer --port 50051 --peers localhost:50051 localhost:50052 localhost:50053`
*   **Terminal 2:** `python -m peer.peer --port 50052 --peers localhost:50051 localhost:50052 localhost:50053`
*   **Terminal 3:** `python -m peer.peer --port 50053 --peers localhost:50051 localhost:50052 localhost:50053`

This will launch the game with a `curses`-based lobby UI. Use the **Up/Down arrow keys** to navigate the menu and **Enter** to select an option.

1.  Select **"Ready"** in each terminal.
2.  The game will start automatically once all peers are marked as ready.
3.  You can select **"Quit"** or press **'q'** to exit the lobby.

## Running Tests and Checking Coverage

This project uses `pytest` for testing and `pytest-cov` for coverage analysis.

1.  **Install Test Dependencies:**
    If you haven't already installed the development dependencies, run:
    ```bash
    pipenv install --dev
    ```
    This installs `pytest` and `pytest-cov` as specified in the `Pipfile`'s `[dev-packages]` section.

2.  **Run Tests:**
    To run all tests, execute the following command from the project root directory:
    ```bash
    pytest
    ```

3.  **Check Test Coverage:**
    To run tests and generate a coverage report in the terminal, use:
    ```bash
    pytest --cov=.
    ```
    *   The `--cov=.` flag tells `pytest-cov` to measure coverage for the current directory (`.`, i.e., the project root including `game`, `ui`, `peer`, etc.).

    To generate a more detailed HTML report (which you can open in a browser), use:
    ```bash
    pytest --cov=. --cov-report=html
    ```
    This will create an `htmlcov/` directory containing the report. Open the `htmlcov/index.html` file in your web browser.

## Code Structure

The codebase is organized into several modules:

*   **`peer/`**: Contains the peer-to-peer networking code
    *   `peer.py`: Main entry point for running a peer, handles initial setup and logging.
    *   `lobby.py`: Manages the `curses`-based game lobby UI, player readiness, game start coordination, and network message processing.
    *   `grpc_peer.py`: Implements the P2P network layer using gRPC

*   **`proto/`**: Contains Protocol Buffer definitions
    - `tetris.proto`: Protocol definitions for game messages (READY, START, GARBAGE, etc.)
    - `tetris_pb2.py` and `tetris_pb2_grpc.py`: Generated Protocol Buffer code

*   **`game/`**: Contains game logic
    - `state.py`: Core game state management (board, pieces, scoring, garbage handling).
    - `combo.py`: Handles combo system for clearing multiple lines.
    - `controller.py`: Coordinates game logic updates, input processing, and calls to the renderer.

*   **`ui/`**: Contains user interface code
    - `curses_renderer.py`: Manages rendering the main game board, pieces, scores, and opponent boards using `curses`.
    - `input_handler.py`: Handles keyboard input specifically during the game phase.

*   **`tetris_game.py`**: Contains the main game loop logic (`run_game`) called after the lobby phase.

## Game Controls

**Lobby Menu:**
*   **Up/Down Arrow Keys**: Navigate menu options
*   **Enter**: Select option
*   **Q**: Quit lobby

**In-Game:**
*   **Left/Right Arrow Keys**: Move piece horizontally
*   **Up Arrow Key**: Rotate piece
*   **Down Arrow Key**: Soft drop (accelerate piece downward)
*   **Space**: Hard drop (instantly drop piece to bottom)
*   **C**: Hold piece for later use
*   **Q**: Quit game

## Game Features

*   **Player vs. Player**: Compete against multiple players in real-time.
*   **Curses-based Lobby Menu**: Interactive text-based UI for managing readiness before the game.
*   **Garbage Lines**: Send garbage lines to opponents when you clear multiple lines or achieve combos.
*   **Combo System**: Clear lines consecutively to build combos and send more garbage.
*   **Hold Piece**: Store a piece for later use.
*   **Ghost Piece**: Shows where the current piece will land
*   **Opponent Boards**: View mini-versions of opponents' boards