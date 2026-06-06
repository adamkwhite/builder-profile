"""Example tests to demonstrate HTML test reports."""

import pytest

from your_agent import add, greet


def test_greet():
    """Test greeting function."""
    assert greet("World") == "Hello, World!"
    assert greet("Alice") == "Hello, Alice!"


def test_add():
    """Test addition function."""
    assert add(2, 2) == 4
    assert add(10, 5) == 15
    assert add(-1, 1) == 0


def test_basic_math():
    """Test basic mathematical operations."""
    assert 2 + 2 == 4
    assert 10 - 5 == 5
    assert 3 * 4 == 12


def test_string_operations():
    """Test string manipulation."""
    text = "Hello, World!"
    assert text.upper() == "HELLO, WORLD!"
    assert text.lower() == "hello, world!"
    assert len(text) == 13


def test_list_operations():
    """Test list functionality."""
    numbers = [1, 2, 3, 4, 5]
    assert len(numbers) == 5
    assert sum(numbers) == 15
    assert max(numbers) == 5


@pytest.mark.slow
def test_slow_operation():
    """Test marked as slow (for demonstration)."""
    import time

    time.sleep(0.1)
    assert True


class TestExample:
    """Example test class."""

    def test_class_method(self):
        """Test inside a class."""
        assert "test" in "this is a test"

    def test_with_fixture(self, tmp_path):
        """Test using pytest fixture."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("example content")
        assert test_file.read_text() == "example content"
