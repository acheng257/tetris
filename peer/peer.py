import argparse
import sys
import os
import socket  # Added for hostname
import random  # Added for player name generation
from peer.lobby import run_lobby_ui_and_game


# --- Player Name Generation ---
def generate_random_name():
    """Generate a random player name"""
    adjectives = [
        "Cool",
        "Swift",
        "Mighty",
        "Quick",
        "Brave",
        "Agile",
        "Epic",
        "Fast",
        "Grand",
        "Noble",
        "Rapid",
        "Super",
        "Power",
        "Prime",
        "Elite",
        "Neon",
        "Pixel",
        "Cyber",
        "Retro",
        "Hyper",
        "Ultra",
        "Mega",
        "Alpha",
        "Beta",
    ]

    nouns = [
        "Player",
        "Master",
        "Knight",
        "Falcon",
        "Tiger",
        "Dragon",
        "Eagle",
        "Wolf",
        "Wizard",
        "Hunter",
        "Ninja",
        "Gamer",
        "Hero",
        "Legend",
        "Warrior",
        "Commander",
        "Captain",
        "Pilot",
        "Ranger",
        "Titan",
        "Phoenix",
        "Cobra",
        "Viper",
        "Monarch",
    ]

    return f"{random.choice(adjectives)}{random.choice(nouns)}"


player_name = generate_random_name()

# --- Logging Setup ---
# Initialize logging as early as possible
log_file_path = "game.log"
try:
    original_stdout = sys.stdout  # Save original stdout
    original_stderr = sys.stderr  # Save original stderr
    log_file = open(log_file_path, "w")
    sys.stdout = log_file
    sys.stderr = log_file  # Redirect stderr as well
    print(f"--- Log Start ({player_name}) ---")
    print(f"Arguments: {sys.argv}")
    print(f"Initial CWD: {os.getcwd()}")
except Exception as e:
    # If logging setup fails, print to original stderr and exit
    if "original_stderr" in locals() and original_stderr:
        print(
            f"FATAL: Failed to setup logging to {log_file_path}: {e}",
            file=original_stderr,
        )
    else:
        print(f"FATAL: Failed to setup logging to {log_file_path}: {e}")
    sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P2P Tetris Peer")
    parser.add_argument("--port", required=True, help="Port to listen on (e.g. 50051)")
    parser.add_argument(
        "--peers",
        nargs="+",
        required=True,
        help="List of peer addresses (host:port) including yourself. Can be space or comma separated.",
    )
    args = parser.parse_args()

    # Process peer list to handle both space and comma separation
    peer_list = []
    for peer in args.peers:
        # Split by comma and strip whitespace
        for p in peer.split(","):
            p = p.strip()
            if p:  # Only add non-empty strings
                peer_list.append(p)

    print(f"Player Name: {player_name}")
    print(f"Listen Port: {args.port}")
    print(f"Peer List: {peer_list}")

    try:
        # Call the new main function that handles curses UI
        run_lobby_ui_and_game(args.port, peer_list, player_name)
    except Exception as e:
        print(f"FATAL ERROR in run_lobby_ui_and_game: {e}")
        import traceback

        print(traceback.format_exc())
        # Ensure curses is ended if an error occurs at the top level
        try:
            import curses

            if curses.isendwin() is False:
                curses.endwin()
        except:
            pass  # Ignore errors during cleanup
    finally:
        # --- Restore stdout/stderr and close log file ---
        print(f"--- Log End ({player_name}) ---")
        if "original_stdout" in locals():
            sys.stdout = original_stdout
        if "original_stderr" in locals():
            sys.stderr = original_stderr
        if "log_file" in locals() and not log_file.closed:
            log_file.close()
