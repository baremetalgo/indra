from __future__ import annotations

import pytest

from indra.core.state_machine import InvalidTransitionError, StateMachine


def test_valid_transition_changes_state() -> None:
    sm = StateMachine(initial_state="A", transitions={("A", "go"): "B"})
    assert sm.state == "A"
    sm.fire("go")
    assert sm.state == "B"


def test_invalid_transition_raises() -> None:
    sm = StateMachine(initial_state="A", transitions={("A", "go"): "B"})
    with pytest.raises(InvalidTransitionError):
        sm.fire("nope")


def test_can_fire_reports_without_mutating_state() -> None:
    sm = StateMachine(initial_state="A", transitions={("A", "go"): "B"})
    assert sm.can_fire("go") is True
    assert sm.can_fire("nope") is False
    assert sm.state == "A"


def test_reset_returns_to_initial_state() -> None:
    sm = StateMachine(initial_state="A", transitions={("A", "go"): "B"})
    sm.fire("go")
    sm.reset()
    assert sm.state == "A"
