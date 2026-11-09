from enum import Enum


class RunStatus(str, Enum):
    INVALID = "INVALID"
    SENDING = "SENDING"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    RETRY = "RETRY"
    FAILED = "FAILED"
    MANUAL = "MANUAL"
    DONE = [COMPLETED, FAILED]
