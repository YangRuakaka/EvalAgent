from pydantic import BaseModel
from datetime import datetime

class EchoRequest(BaseModel):
    message: str

class EchoResponse(BaseModel):
    message: str
    server_time: datetime
