
import threading
import uvicorn
import logging
from .host.app import app

log = logging.getLogger(__name__)
server_thread = None

def run_server():
    # Ensure the app is imported and initialized
    if not hasattr(app, 'state'):
        app.state = {}

    # Run the FastAPI server
    log.info("Starting FastAPI server on http://localhost:8765")
    uvicorn.run(
        app,
        host="localhost",
        port=8765,
        log_level="info",
        reload_dirs=["."],
        reload_excludes=["__pycache__", ".git", ".idea", ".vscode"])      

def register():
    global server_thread
    if server_thread is not None and server_thread.is_alive():
        log.info("FastAPI server is already running.")
        return
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

def unregister():
    log.info("Unregistering host module, server will continue running.")