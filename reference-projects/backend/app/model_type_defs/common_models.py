from pydantic import BaseModel
from typing import Any


class ApiResponse(BaseModel):
    data: Any = None
    code: int = 0
    message: str = "Success"


class ErrResponse(BaseModel):
    data: Any = None
    code: int = 400
    message: str = "Error"


DayFormat = "%Y-%m-%d"
HourFormat = "%Y-%m-%d %H"
SecondFormat = "%Y-%m-%d %H:%M:%S"
