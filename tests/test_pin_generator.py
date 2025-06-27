# Directory: utils/
# Filename: test_pin_generator.py

#############################################################
##
## This test file is designed to systematically cover every function
## in utils/pin_generator.py.
##
## Run this test with the following command:
## pytest tests/test_pin_generator.py --cov=utils.pin_generator --cov-report term-missing
##
#############################################################

import pytest
from unittest.mock import Mock
from utils.pin_generator import PINGenerator, PIN_TEMPLATE

@pytest.fixture
def mock_dut():
    mock = Mock()
    mock.self_destruct_pin = ["1", "2", "3", "4"]
    return mock

def test_init_valid(mock_dut):
    gen = PINGenerator(mock_dut)
    assert gen.dut_model == mock_dut

def test_init_invalid():
    with pytest.raises(TypeError):
        PINGenerator(object())

def test_is_pin_invalid_self_destruct(mock_dut):
    gen = PINGenerator(mock_dut)
    invalid, reason = gen._is_pin_invalid("1234")
    assert invalid
    assert "Self-Destruct" in reason

def test_is_pin_invalid_repeating(mock_dut):
    mock_dut.self_destruct_pin = []
    gen = PINGenerator(mock_dut)
    invalid, reason = gen._is_pin_invalid("7777")
    assert invalid
    assert reason == "is repeating"

def test_is_pin_invalid_sequential(mock_dut):
    mock_dut.self_destruct_pin = []
    gen = PINGenerator(mock_dut)
    assert gen._is_pin_invalid("012345")[0]
    assert gen._is_pin_invalid("987654")[0]

def test_is_pin_valid_random(mock_dut):
    mock_dut.self_destruct_pin = []
    gen = PINGenerator(mock_dut)
    valid, reason = gen._is_pin_invalid("4712")
    assert not valid
    assert reason == "is valid"

def test_populate_pin_info_valid(mock_dut):
    mock_dut.self_destruct_pin = []
    gen = PINGenerator(mock_dut)
    pin_info = gen._populate_pin_info("4291")
    assert pin_info['string'] == "4291"
    assert pin_info['digit'] == 4
    assert pin_info['valid'] is True
    assert "key4" in pin_info['keypress']
    assert pin_info['sequence'][-1] == "unlock"

def test_generate_valid_pin_length_constraints(mock_dut):
    gen = PINGenerator(mock_dut)
    with pytest.raises(ValueError):
        gen.generate_valid_pin(1)
    with pytest.raises(ValueError):
        gen.generate_valid_pin(17)

def test_generate_valid_pin_success(mock_dut):
    mock_dut.self_destruct_pin = ["1", "1", "1", "1"]
    gen = PINGenerator(mock_dut)
    pin_info = gen.generate_valid_pin(4)
    assert pin_info['valid'] is True
    assert len(pin_info['string']) == 4

def test_generate_valid_pin_failure(monkeypatch, mock_dut):
    monkeypatch.setattr("random.choices", lambda *a, **k: list("1111"))
    mock_dut.self_destruct_pin = ["1", "1", "1", "1"]
    gen = PINGenerator(mock_dut)
    with pytest.raises(RuntimeError):
        gen.generate_valid_pin(4)

def test_generate_invalid_pin_repeating(mock_dut):
    gen = PINGenerator(mock_dut)
    pin_info = gen.generate_invalid_pin("repeating", 5)
    assert pin_info['valid'] is False
    assert pin_info['reason'] == "is repeating"
    assert len(set(pin_info['string'])) == 1

def test_generate_invalid_pin_sequential_forward(monkeypatch):
    mock_dut = Mock()
    mock_dut.self_destruct_pin = ["9", "9", "9", "9"]  # avoid any overlap with sequential values
    gen = PINGenerator(mock_dut)

    # Monkeypatch randint to ensure deterministic output (e.g., start at 1 → 1234)
    monkeypatch.setattr("random.randint", lambda a, b: 1)
    pin_info = gen.generate_invalid_pin("sequential", 4, reverse=False)

    assert pin_info['string'] == "1234"
    assert pin_info['valid'] is False
    assert pin_info['reason'] == "is sequential"

def test_generate_invalid_pin_sequential_random_direction(monkeypatch):
    mock_dut = Mock()
    mock_dut.self_destruct_pin = ["9", "9", "9", "9"]  # Ensures no conflict with sequential
    gen = PINGenerator(mock_dut)

    monkeypatch.setattr("random.choice", lambda opts: True)  # Force reverse=True
    pin_info = gen.generate_invalid_pin("sequential", 4)
    assert pin_info['valid'] is False
    assert pin_info['reason'] == "is sequential"

    monkeypatch.setattr("random.choice", lambda opts: False)  # Force reverse=False
    pin_info = gen.generate_invalid_pin("sequential", 4)
    assert pin_info['valid'] is False
    assert pin_info['reason'] == "is sequential"


def test_generate_invalid_pin_sequential_reverse(mock_dut):
    gen = PINGenerator(mock_dut)
    pin_info = gen.generate_invalid_pin("sequential", 4, reverse=True)
    assert pin_info['valid'] is False
    assert pin_info['reason'] == "is sequential"

def test_generate_invalid_pin_type_error(mock_dut):
    gen = PINGenerator(mock_dut)
    with pytest.raises(ValueError):
        gen.generate_invalid_pin("unknown", 4)

def test_generate_invalid_pin_sequential_length_error(mock_dut):
    gen = PINGenerator(mock_dut)
    with pytest.raises(ValueError):
        gen.generate_invalid_pin("sequential", 11)

def test_get_self_destruct_pin_info(mock_dut):
    gen = PINGenerator(mock_dut)
    info = gen.get_self_destruct_pin_info()
    assert info is not None
    assert info['string'] == "1234"
    assert info['valid'] is False
    assert "Self-Destruct" in info['reason']


def test_get_self_destruct_pin_info_none():
    mock = Mock()
    mock.self_destruct_pin = []
    gen = PINGenerator(mock)
    assert gen.get_self_destruct_pin_info() is None