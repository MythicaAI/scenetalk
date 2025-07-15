from fastapi import FastAPI
import ws_app
from log_config import setup_logging

app = FastAPI()
app.include_router(ws_app.router)

setup_logging()
