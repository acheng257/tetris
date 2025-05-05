import time


# ComboSystem class to handle combo logic (Jstris-compatible)
class ComboSystem:
    def __init__(self, debug_mode=False):
        self.combo_count = 0
        self.debug_message = ""
        self.debug_time = 0
        self.debug_display_time = 5.0  # Display debug message for 5 seconds
        # Track total garbage lines sent in this combo
        self.total_combo_garbage_sent = 0
        self.debug_mode = debug_mode  # Store debug mode
        if self.debug_mode:
            print("[COMBO DEBUG] Initialized Jstris-compatible combo system")

    def update(self, lines_cleared, current_time):
        """Update combo state based on lines cleared at current time"""
        debug_message = None

        # Add detailed logging at the start of the update
        if self.debug_mode:
            print(
                f"[COMBO DEBUG] update called: lines_cleared={lines_cleared}, time={current_time:.2f}"
            )
            print(f"[COMBO DEBUG]  - Before: count={self.combo_count}")

        if lines_cleared > 0:
            # Lines cleared in this placement
            if self.combo_count > 0:
                # We already have a combo going, increment it
                self.combo_count += 1
                debug_message = f"COMBO x{self.combo_count}!"
                if self.debug_mode:
                    print(f"[COMBO DEBUG]  - Continuing combo, now at {self.combo_count}")
            else:
                # Starting a new combo
                self.combo_count = 1  # First clear starts at 1
                # In Jstris, the first combo doesn't show a message, only from 2+
                if self.debug_mode:
                    print(f"[COMBO DEBUG]  - Starting new combo at {self.combo_count}")
        else:
            # No lines cleared, reset combo
            if self.combo_count > 0:
                if self.debug_mode:
                    print(f"[COMBO DEBUG]  - No lines cleared, resetting combo from {self.combo_count} to 0")
                if self.combo_count > 1:
                    debug_message = f"COMBO ENDED ({self.combo_count})"
                self.combo_count = 0
                self.total_combo_garbage_sent = 0  # Reset garbage tracking for the combo

        # Set debug message if one was generated
        if debug_message:
            self.debug_message = debug_message
            self.debug_time = current_time

        # Add detailed logging at the end of the update
        if self.debug_mode:
            print(
                f"[COMBO DEBUG]  - After: count={self.combo_count}, lines_cleared={lines_cleared}"
            )

        # Return current combo count (for display) and any debug message
        return {
            "combo_count": self.combo_count,
            "debug_message": debug_message,
            "is_combo_active": self.combo_count > 0,
        }

    def get_display(self):
        """Get the string to display for the current combo state"""
        if self.combo_count > 0:
            return f"{self.combo_count}"
        else:
            return "-"  # Show dash when no active combo

    def check_debug_timeout(self, current_time):
        """Check if debug message should be cleared due to timeout"""
        if (
            self.debug_message
            and current_time - self.debug_time > self.debug_display_time
        ):
            self.debug_message = ""
            return True
        return False

    def get_garbage_count(self, lines_cleared, combo_num, base_attack):
        """Calculate garbage to send based on combo count - Jstris compatible"""
        if self.debug_mode:
            print(f"[ATTACK CALC] Combo Count: {combo_num}, Base Attack: {base_attack}")

        combo_bonus_garbage = 0
        
        # Only apply combo bonus if we have a valid combo (at least 2)
        if combo_num >= 2:
            # Jstris combo table:
            # 2=1, 3=1, 4=1, 5=2, 6=2, 7=3, 8=3, 9=4, 10=4, 11=4, 12+=5
            if combo_num <= 4:
                combo_bonus_garbage = 1
            elif combo_num <= 6:
                combo_bonus_garbage = 2
            elif combo_num <= 8:
                combo_bonus_garbage = 3
            elif combo_num <= 11:
                combo_bonus_garbage = 4
            else:  # 12+
                combo_bonus_garbage = 5
                
            if self.debug_mode:
                print(f"[ATTACK CALC] Combo Bonus Garbage: {combo_bonus_garbage}")
        
        if self.debug_mode:
            print(f"[ATTACK CALC] Final Combo Bonus: {combo_bonus_garbage}")
        
        return combo_bonus_garbage  # Return just the bonus part