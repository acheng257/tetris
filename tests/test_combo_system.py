import pytest
import time
from game.combo import ComboSystem

# --- Expanded ComboSystem Tests ---

def test_combo_initialization():
    combo = ComboSystem(debug_mode=False)
    assert combo.combo_count == 0
    assert combo.debug_message == ""
    assert combo.get_display() == "-"
    assert combo.total_combo_garbage_sent == 0


def test_combo_no_lines_cleared():
    combo = ComboSystem()
    t0 = time.time()
    result = combo.update(lines_cleared=0, current_time=t0)
    # No combo, no message
    assert result["combo_count"] == 0
    assert result["debug_message"] is None
    assert not result["is_combo_active"]
    assert combo.combo_count == 0
    assert combo.get_display() == "-"


def test_combo_first_clear_sets_count_and_display():
    for cleared in (1, 2, 3, 4):
        combo = ComboSystem()
        t0 = time.time()
        result = combo.update(lines_cleared=cleared, current_time=t0)
        assert result["combo_count"] == 1
        assert result["debug_message"] is None
        assert result["is_combo_active"]
        assert combo.combo_count == 1
        assert combo.get_display() == "1"


def test_combo_continuation_and_debug_messages():
    combo = ComboSystem()
    t1 = time.time()
    combo.update(lines_cleared=1, current_time=t1)
    for idx, lines in enumerate((2, 3, 4), start=2):
        t = t1 + idx * 0.1
        result = combo.update(lines_cleared=lines, current_time=t)
        # combo_count increments
        assert result["combo_count"] == idx
        # for idx >= 2 debug message
        assert result["debug_message"] == f"COMBO x{idx}!"
        assert combo.combo_count == idx
        assert combo.get_display() == str(idx)


def test_combo_break_generates_end_message_only_after_combo_gt1():
    combo = ComboSystem()
    # Test break after combo=1
    t0 = time.time()
    combo.update(lines_cleared=1, current_time=t0)
    res1 = combo.update(lines_cleared=0, current_time=t0+0.1)
    assert res1["combo_count"] == 0
    assert res1["debug_message"] is None
    assert combo.get_display() == "-"

    # Test break after combo=2
    combo = ComboSystem()
    t1 = time.time()
    combo.update(lines_cleared=2, current_time=t1)  # combo=1
    res2 = combo.update(lines_cleared=3, current_time=t1+0.1)  # combo=2
    res3 = combo.update(lines_cleared=0, current_time=t1+0.2)
    assert res3["combo_count"] == 0
    assert res3["debug_message"] == "COMBO ENDED (2)"
    assert combo.debug_message == "COMBO ENDED (2)"
    assert combo.get_display() == "-"
    assert combo.total_combo_garbage_sent == 0


def test_check_debug_timeout_clears_message_after_display_time():
    combo = ComboSystem()
    # simulate a message
    combo.debug_message = "COMBO x3!"
    combo.debug_time = 1000.0
    combo.debug_display_time = 2.0
    # before timeout
    assert not combo.check_debug_timeout(1001.0)
    assert combo.debug_message == "COMBO x3!"
    # after timeout
    assert combo.check_debug_timeout(1003.1)
    assert combo.debug_message == ""


def test_get_garbage_count_various_combo_thresholds():
    combo = ComboSystem()
    table = {
        2: 1,
        3: 1,
        4: 1,
        5: 2,
        6: 2,
        7: 3,
        8: 3,
        9: 4,
        10: 4,
        11: 4,
        12: 5,
        15: 5,
    }
    for combo_num, expected in table.items():
        # lines_cleared irrelevant for bonus
        assert combo.get_garbage_count(lines_cleared=1, combo_num=combo_num, base_attack=0) == expected


def test_get_garbage_count_ignores_base_attack():
    combo = ComboSystem()
    # base_attack should not affect bonus output
    assert combo.get_garbage_count(lines_cleared=1, combo_num=5, base_attack=10) == 2
    assert combo.get_garbage_count(lines_cleared=0, combo_num=6, base_attack=3) == 2


def test_combo_multiple_resets_no_persistence():
    combo = ComboSystem()
    # start and break
    combo.update(lines_cleared=3, current_time=0)
    combo.update(lines_cleared=0, current_time=1)
    # further zeros should not re-trigger end messages
    combo.update(lines_cleared=0, current_time=2)
    assert combo.combo_count == 0
    assert combo.debug_message == ""


def test_get_garbage_count_combo_below_threshold():
    combo = ComboSystem()
    for cnum in (0, 1):
        # combo_num <2 => no bonus
        assert combo.get_garbage_count(lines_cleared=1, combo_num=cnum, base_attack=5) == 0


def test_update_return_structure():
    combo = ComboSystem()
    res = combo.update(lines_cleared=2, current_time=123.456)
    # ensure return has exactly these keys
    assert set(res.keys()) == {"combo_count", "debug_message", "is_combo_active"}


def test_check_debug_timeout_exact_threshold():
    combo = ComboSystem()
    combo.debug_message = "TEST"
    combo.debug_time = 100.0
    combo.debug_display_time = 5.0
    # at exactly threshold, should not yet clear
    assert combo.check_debug_timeout(105.0) is False
    assert combo.debug_message == "TEST"
    

def test_debug_mode_update_and_prints(capsys):
    combo = ComboSystem(debug_mode=True)
    # Call update to trigger debug prints
    t0 = time.time()
    combo.update(lines_cleared=1, current_time=t0)
    combo.update(lines_cleared=2, current_time=t0+0.1)
    captured = capsys.readouterr()
    # Check that debug messages were printed
    assert "[COMBO DEBUG]" in captured.out


def test_debug_mode_garbage_count_prints(capsys):
    combo = ComboSystem(debug_mode=True)
    # Call get_garbage_count to trigger debug prints
    _ = combo.get_garbage_count(lines_cleared=4, combo_num=5, base_attack=1)
    captured = capsys.readouterr()
    assert "[ATTACK CALC] Combo Count: 5, Base Attack: 1" in captured.out


def test_total_combo_garbage_sent_unchanged():
    combo = ComboSystem()
    # total_combo_garbage_sent is not used internally, should stay at 0
    combo.update(lines_cleared=3, current_time=0)
    combo.update(lines_cleared=4, current_time=1)
    assert combo.total_combo_garbage_sent == 0


def test_get_display_after_multiple_updates():
    combo = ComboSystem()
    combo.update(lines_cleared=1, current_time=0)
    assert combo.get_display() == "1"
    combo.update(lines_cleared=0, current_time=1)
    assert combo.get_display() == "-"
