import time


# ComboSystem class to handle combo logic
class ComboSystem:
    def __init__(self, debug_mode=False):
        self.combo_count = 0
        self.debug_message = ""
        self.debug_time = 0
        self.debug_display_time = 5.0  # Display debug message for 5 seconds
        # Track if we've cleared lines in the last placement
        self.last_placement_cleared_lines = False
        # Track total garbage lines sent in this combo
        self.total_combo_garbage_sent = 0
        self.debug_mode = debug_mode  # Store debug mode
        if self.debug_mode:
            print("[COMBO DEBUG] Initialized combo system")

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
            if self.last_placement_cleared_lines:
                # Previous placement also cleared lines, so increment combo
                self.combo_count += 1
                if self.debug_mode:
                    print(
                        f"[COMBO DEBUG]  - Previous placement cleared lines too. Incrementing combo to {self.combo_count}"
                    )

                # Show combo message if 2 or more in combo count
                if (
                    self.combo_count >= 1
                ):  # In Jstris, even the first combo (consecutive clears) gets a message
                    debug_message = f"COMBO x{self.combo_count}!"
            elif lines_cleared > 1:
                debug_message = f"COMBO x{lines_cleared}!"
                self.combo_count = lines_cleared
                if self.debug_mode:
                    print(
                        f"[COMBO DEBUG]  - New combo started with {lines_cleared} lines"
                    )
            else:
                # First line clear in a potential combo
                self.combo_count = (
                    0  # Reset to 0 as this is potentially the first part of a new combo
                )
                if self.debug_mode:
                    print(
                        f"[COMBO DEBUG]  - First line clear, setting combo to {self.combo_count}"
                    )

            # Remember that this placement cleared lines
            self.last_placement_cleared_lines = True
        else:
            # No lines cleared, reset combo
            if self.combo_count > 0 or self.last_placement_cleared_lines:
                if self.debug_mode:
                    print(
                        f"[COMBO DEBUG]  - No lines cleared, resetting combo from {self.combo_count} to 0"
                    )
            self.combo_count = 0
            self.last_placement_cleared_lines = False
            self.total_combo_garbage_sent = 0  # Reset garbage tracking for the combo

        # Set debug message if one was generated
        if debug_message:
            self.debug_message = debug_message
            self.debug_time = current_time

        # Add detailed logging at the end of the update
        if self.debug_mode:
            print(
                f"[COMBO DEBUG]  - After: count={self.combo_count}, last_cleared={self.last_placement_cleared_lines}"
            )

        # Return current combo count (for display) and any debug message
        return {
            "combo_count": self.combo_count,
            "debug_message": debug_message,
            "is_combo_active": self.last_placement_cleared_lines,
        }

    def get_display(self):
        """Get the string to display for the current combo state"""
        if self.combo_count > 0:
            return f"{self.combo_count}"
        elif self.last_placement_cleared_lines:
            return "0"  # Show 0 when we've cleared lines but no combo yet
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
        if self.debug_mode:
            print(f"[ATTACK CALC] Combo Count: {combo_num}")

        if lines_cleared > 0 and combo_num >= 1:
            # Combo values: 0=0, 1=0, 2=1, 3=1, 4=1, 5=2, 6=2, 7=3, 8=3, 9=4, 10=4, 11=4, 12+=5
            if combo_num <= 1:
                combo_bonus_garbage = 0
            elif combo_num <= 4:
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
            attack_sent = max(base_attack, combo_bonus_garbage)
        else:
            attack_sent = base_attack  # No combo or no lines cleared, use base attack

        if self.debug_mode:
            print(f"[ATTACK CALC] Final Attack Value (Pre-Cancel): {attack_sent}")
        return attack_sent
