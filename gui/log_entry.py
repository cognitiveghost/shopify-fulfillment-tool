"""One line in the log viewer, whatever stream produced it.

Activity (what the operator did) and Execution (what the program logged)
differ by which value lands in `source`, not by shape. Keeping one dataclass
is what lets the level filter and the error tint work on both sources.

Spec: docs/superpowers/specs/2026-09-07-phase9-bundle7-info-becomes-logs-design.md
"""

import logging
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: datetime
    level: int
    source: str
    message: str

    @property
    def level_name(self) -> str:
        return logging.getLevelName(self.level)

    @classmethod
    def activity(cls, op_type: str, desc: str) -> "LogEntry":
        """An operator action. Always INFO -- the stream has no severity."""
        return cls(
            timestamp=datetime.now().astimezone(),
            level=logging.INFO,
            source=op_type,
            message=desc,
        )
