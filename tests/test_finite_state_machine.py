import pytest
from unittest.mock import MagicMock

from controllers.finite_state_machine import (
    ApricornDeviceFSM,
    DeviceUnderTest,
    TestSession,
    CallableCondition,
)


# Minimal, up-to-date tests aligned with the refactored FSM


@pytest.fixture
def mock_at():
    at = MagicMock()
    # Methods used by various session/fsm utilities
    at.scan_barcode.return_value = "TEST_SERIAL_123"
    at.off.return_value = None
    return at


@pytest.fixture
def dut_instance(mock_at):
    return DeviceUnderTest(at_controller=mock_at)


@pytest.fixture
def session_instance(mock_at, dut_instance):
    return TestSession(at_controller=mock_at, dut_instance=dut_instance)


@pytest.fixture
def fsm(mock_at, dut_instance, session_instance):
    return ApricornDeviceFSM(
        at_controller=mock_at,
        session_instance=session_instance,
        dut_instance=dut_instance,
    )


def test_callable_condition_repr():
    cond = CallableCondition(func=lambda: True, name="my_test_condition")
    assert repr(cond) == "<CallableCondition: my_test_condition>"


def test_device_under_test_init_uses_hardware_config(mock_at):
    # Provide a scanned_serial_number explicitly to avoid triggering an actual scan
    provided_serial = "TEST_SERIAL_123"
    dut = DeviceUnderTest(at_controller=mock_at, scanned_serial_number=provided_serial)
    # Basic invariants that should always hold
    assert dut.at is mock_at
    assert isinstance(dut.name, str) and dut.name
    assert dut.scanned_serial_number == provided_serial


def test_session_start_new_block_and_enums(session_instance):
    # Start first block
    session_instance.start_new_block(block_name="block", current_test_block=1)
    assert session_instance.current_test_block == 1
    if isinstance(session_instance.test_blocks, list):
        assert session_instance.test_blocks == [1]
    else:
        assert session_instance.test_blocks.get(1) == "block"
    # Enumeration counters initialized per-block
    assert session_instance.block_enumeration_totals[1]["mfr"] == 0
    assert session_instance.block_enumeration_totals[1]["oob"] == 0
    assert session_instance.block_enumeration_totals[1]["pin"] == 0
    assert session_instance.block_enumeration_totals[1]["spi"] == 0
    # Logging increments within the active block
    session_instance.log_enumeration("pin")
    assert session_instance.block_enumeration_totals[1]["pin"] == 1


def test_session_key_press_totals(session_instance):
    assert session_instance.key_press_totals == {}
    session_instance.log_key_press("key1")
    session_instance.log_key_press("key1")
    session_instance.log_key_press("lock")
    assert session_instance.key_press_totals["key1"] == 2
    assert session_instance.key_press_totals["lock"] == 1


def test_session_end_session_and_report_no_failures(session_instance, dut_instance, mock_at):
    # Avoid interactive prompt by pre-setting a serial
    dut_instance.serial_number = "123456789012"
    # No failures logged -> returns None
    result = session_instance.end_session_and_report()
    assert result is None
    # Ensures cleanup was attempted
    mock_at.off.assert_any_call("usb3")
    mock_at.off.assert_any_call("connect")


def test_fsm_initializes_with_dependencies(fsm, mock_at, dut_instance):
    # Basic sanity checks without asserting internal state names
    assert fsm.at is mock_at
    assert fsm.dut is dut_instance
    assert hasattr(fsm, "machine")