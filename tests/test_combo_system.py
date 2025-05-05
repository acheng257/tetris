import pytest
import time
from game.combo import ComboSystem


# Fixture for a ComboSystem instance
@pytest.fixture
def combo_system():
    # Use debug_mode=True to see the print statements during testing if needed
    return ComboSystem(debug_mode=False)


def test_combo_initialization(combo_system):
    """Test initial state of the ComboSystem."""
    assert combo_system.combo_count == 0
    assert combo_system.debug_message == ""
    assert not combo_system.last_placement_cleared_lines
    assert combo_system.total_combo_garbage_sent == 0
    assert combo_system.get_display() == "-"


def test_combo_no_lines_cleared(combo_system):
    """Test update when no lines are cleared."""
    result = combo_system.update(lines_cleared=0, current_time=time.time())
    assert result["combo_count"] == 0
    assert result["debug_message"] is None
    assert not result["is_combo_active"]
    assert combo_system.combo_count == 0
    assert not combo_system.last_placement_cleared_lines
    assert combo_system.get_display() == "-"


def test_combo_single_line_clear_starts(combo_system):
    """Test update when a single line is cleared for the first time."""
    current_time = time.time()
    result = combo_system.update(lines_cleared=1, current_time=current_time)

    # A single clear doesn't start a combo count > 0 immediately, but marks active
    assert result["combo_count"] == 0
    assert result["debug_message"] is None
    assert result["is_combo_active"] is True  # It *did* clear lines

    assert combo_system.combo_count == 0  # Internal count remains 0 for first clear
    assert combo_system.last_placement_cleared_lines is True
    assert combo_system.get_display() == "0"  # Display shows "0" after first clear


def test_combo_multi_line_clear_starts_combo(combo_system):
    """Test update when multiple lines are cleared, starting a combo immediately."""
    current_time = time.time()
    result = combo_system.update(lines_cleared=4, current_time=current_time)  # Tetris

    # Multi-line clear starts combo immediately with lines_cleared count
    assert result["combo_count"] == 4
    assert result["debug_message"] == "COMBO x4!"
    assert result["is_combo_active"] is True

    assert combo_system.combo_count == 4
    assert combo_system.last_placement_cleared_lines is True
    assert combo_system.debug_message == "COMBO x4!"
    assert combo_system.debug_time == current_time
    assert combo_system.get_display() == "4"


def test_combo_continuation(combo_system):
    """Test combo incrementing with consecutive line clears."""
    t1 = time.time()
    combo_system.update(
        lines_cleared=2, current_time=t1
    )  # First clear (Double) -> combo 2
    assert combo_system.combo_count == 2
    assert combo_system.get_display() == "2"

    t2 = t1 + 1
    result = combo_system.update(
        lines_cleared=1, current_time=t2
    )  # Second clear (Single)

    # Combo should increment because previous placement cleared lines
    assert result["combo_count"] == 3  # 2 (initial) + 1 (increment)
    assert result["debug_message"] == "COMBO x3!"
    assert result["is_combo_active"] is True

    assert combo_system.combo_count == 3
    assert combo_system.last_placement_cleared_lines is True
    assert combo_system.get_display() == "3"

    t3 = t2 + 1
    result = combo_system.update(
        lines_cleared=3, current_time=t3
    )  # Third clear (Triple)
    assert result["combo_count"] == 4  # 3 + 1
    assert result["debug_message"] == "COMBO x4!"
    assert combo_system.combo_count == 4
    assert combo_system.get_display() == "4"


def test_combo_break(combo_system):
    """Test that the combo breaks when a placement clears no lines."""
    t1 = time.time()
    combo_system.update(lines_cleared=2, current_time=t1)  # Start combo
    assert combo_system.combo_count == 2

    t2 = t1 + 1
    combo_system.update(lines_cleared=1, current_time=t2)  # Continue combo
    assert combo_system.combo_count == 3

    t3 = t2 + 1
    result = combo_system.update(lines_cleared=0, current_time=t3)  # Break combo

    assert result["combo_count"] == 0
    assert result["debug_message"] is None
    assert not result["is_combo_active"]

    assert combo_system.combo_count == 0
    assert not combo_system.last_placement_cleared_lines
    assert combo_system.total_combo_garbage_sent == 0  # Garbage tracking reset
    assert combo_system.get_display() == "-"


def test_combo_debug_message_timeout(combo_system):
    """Test that the debug message clears after the display time."""
    t1 = time.time()
    combo_system.update(
        lines_cleared=4, current_time=t1
    )  # Generate message "COMBO x4!"
    assert combo_system.debug_message == "COMBO x4!"

    # Check immediately, should still be there
    assert not combo_system.check_debug_timeout(t1 + 1.0)
    assert combo_system.debug_message == "COMBO x4!"

    # Check after timeout, should be cleared
    assert combo_system.check_debug_timeout(t1 + combo_system.debug_display_time + 0.1)
    assert combo_system.debug_message == ""


def test_get_garbage_count_no_combo(combo_system):
    """Test garbage calculation when there's no active combo."""
    # Base attack only
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=0, base_attack=0) == 0
    )
    assert (
        combo_system.get_garbage_count(lines_cleared=2, combo_num=0, base_attack=1) == 1
    )
    assert (
        combo_system.get_garbage_count(lines_cleared=3, combo_num=0, base_attack=2) == 2
    )
    assert (
        combo_system.get_garbage_count(lines_cleared=4, combo_num=0, base_attack=4) == 4
    )
    # No lines cleared
    assert (
        combo_system.get_garbage_count(lines_cleared=0, combo_num=0, base_attack=0) == 0
    )


def test_get_garbage_count_with_combo(combo_system):
    """Test garbage calculation with different combo levels compared to base attack."""
    # Base attack = 0 (e.g., single clear)
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=1, base_attack=0) == 0
    )  # Combo 1 bonus = 0
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=2, base_attack=0) == 1
    )  # Combo 2 bonus = 1
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=4, base_attack=0) == 1
    )  # Combo 4 bonus = 1
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=5, base_attack=0) == 2
    )  # Combo 5 bonus = 2
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=7, base_attack=0) == 3
    )  # Combo 7 bonus = 3
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=9, base_attack=0) == 4
    )  # Combo 9 bonus = 4
    assert (
        combo_system.get_garbage_count(lines_cleared=1, combo_num=12, base_attack=0)
        == 5
    )  # Combo 12 bonus = 5

    # Base attack = 1 (e.g., double clear)
    assert (
        combo_system.get_garbage_count(lines_cleared=2, combo_num=1, base_attack=1) == 1
    )  # Combo 1 bonus = 0, max(1,0)=1
    assert (
        combo_system.get_garbage_count(lines_cleared=2, combo_num=2, base_attack=1) == 1
    )  # Combo 2 bonus = 1, max(1,1)=1
    assert (
        combo_system.get_garbage_count(lines_cleared=2, combo_num=5, base_attack=1) == 2
    )  # Combo 5 bonus = 2, max(1,2)=2

    # Base attack = 4 (e.g., Tetris)
    assert (
        combo_system.get_garbage_count(lines_cleared=4, combo_num=1, base_attack=4) == 4
    )  # Combo 1 bonus = 0, max(4,0)=4
    assert (
        combo_system.get_garbage_count(lines_cleared=4, combo_num=7, base_attack=4) == 4
    )  # Combo 7 bonus = 3, max(4,3)=4
    assert (
        combo_system.get_garbage_count(lines_cleared=4, combo_num=9, base_attack=4) == 4
    )  # Combo 9 bonus = 4, max(4,4)=4
    assert (
        combo_system.get_garbage_count(lines_cleared=4, combo_num=12, base_attack=4)
        == 5
    )  # Combo 12 bonus = 5, max(4,5)=5


def test_get_garbage_count_no_lines_cleared_with_combo(combo_system):
    """Test garbage calculation when combo is active but no lines were cleared."""
    # Even if combo_num is high, if lines_cleared is 0, attack should be base_attack (which is 0 here)
    assert (
        combo_system.get_garbage_count(lines_cleared=0, combo_num=5, base_attack=0) == 0
    )
    assert (
        combo_system.get_garbage_count(lines_cleared=0, combo_num=12, base_attack=0)
        == 0
    )
