"""A small generic finite state machine.

Used by both the task lifecycle (§8 of the design doc) and the
per-subtask tool-execution lifecycle, so transition rules live in one
tested place instead of being re-implemented ad hoc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

S = TypeVar("S")  # state type (typically an Enum)
E = TypeVar("E")  # event type (typically a str or Enum)


class InvalidTransitionError(Exception):
    """Raised when an event is not allowed from the current state."""


@dataclass
class StateMachine(Generic[S, E]):
    """Explicit transition table, no implicit/default transitions.

    ``transitions`` maps (current_state, event) -> next_state. Any event
    not present in the table for the current state raises rather than
    silently no-op'ing, so bugs surface immediately.
    """

    initial_state: S
    transitions: dict[tuple[S, E], S]
    _state: S = field(init=False)

    def __post_init__(self) -> None:
        self._state = self.initial_state

    @property
    def state(self) -> S:
        return self._state

    def can_fire(self, event: E) -> bool:
        return (self._state, event) in self.transitions

    def fire(self, event: E) -> S:
        key = (self._state, event)
        if key not in self.transitions:
            raise InvalidTransitionError(
                f"Event {event!r} not allowed from state {self._state!r}"
            )
        self._state = self.transitions[key]
        return self._state

    def reset(self, state: S | None = None) -> None:
        self._state = state if state is not None else self.initial_state
