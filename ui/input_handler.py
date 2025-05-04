import curses
import time


class InputHandler:
    """Handles keyboard input and manages key states"""

    def __init__(self, stdscr, debug_mode=False):
        self.stdscr = stdscr
        self.debug_mode = debug_mode  # Store debug mode

        # Key state tracking
        self.pressed_keys = set()
        self.first_press_keys = set()
        self.last_key_time = time.time()
        self.last_move_time = time.time()
        self.move_delay = 0.15  # Delay for continuous movement
        self.key_timeout = 0.1  # Time to consider key as released if no repeat

        # Store the previous key for change detection
        self.previous_key = None

    def process_input(self):
        """Process keyboard input and update key states

        Returns:
            int: The last pressed key code, or -1 if no key was pressed
        """
        current_time = time.time()
        key = self.stdscr.getch()

        # Handle key state changes
        if key != -1 and key != self.previous_key:
            # Process change in key
            if key in (curses.KEY_LEFT, curses.KEY_RIGHT):
                self.first_press_keys.discard(curses.KEY_LEFT)
                self.first_press_keys.discard(curses.KEY_RIGHT)
            elif key == curses.KEY_UP:
                self.first_press_keys.discard(curses.KEY_UP)

            self.previous_key = key

        # Process new key presses
        if key != -1:
            if key == curses.KEY_LEFT:
                if key not in self.pressed_keys:
                    self.first_press_keys.add(key)
                self.pressed_keys.add(key)
                self.last_key_time = current_time
            elif key == curses.KEY_RIGHT:
                if key not in self.pressed_keys:
                    self.first_press_keys.add(key)
                self.pressed_keys.add(key)
                self.last_key_time = current_time
            elif key == curses.KEY_DOWN:
                self.pressed_keys.add(key)
                self.last_key_time = current_time
            elif key == curses.KEY_UP:
                self.first_press_keys.add(key)
                self.last_key_time = current_time

        # Check for key timeouts
        if current_time - self.last_key_time > self.key_timeout:
            # Clear pressed states for cursor keys if no recent input
            for k in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_DOWN):
                self.pressed_keys.discard(k)
                self.first_press_keys.discard(k)

        return key

    def is_pressed(self, key):
        """Check if a key is currently pressed"""
        return key in self.pressed_keys

    def is_first_press(self, key):
        """Check if this is the first detection of a key press

        Note: This will also consume the first press status
        """
        if key in self.first_press_keys:
            self.first_press_keys.discard(key)
            return True
        return False

    def consume_first_press(self, key):
        """Clear the first press status of a key"""
        self.first_press_keys.discard(key)

    def is_soft_drop_active(self):
        """Check if soft drop is active (down key is pressed)"""
        return curses.KEY_DOWN in self.pressed_keys

    def update_move_time(self):
        """Update the last movement time"""
        self.last_move_time = time.time()

    def should_move_continuously(self):
        """Check if enough time has passed for continuous movement"""
        return time.time() - self.last_move_time > self.move_delay
