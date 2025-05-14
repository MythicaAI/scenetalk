# main.py
import argparse
import asyncio
import logging
import signal
import sys

import uvicorn
from fastapi import FastAPI

import ws_app

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Async server')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind')
    parser.add_argument('--port', type=int, default=8765, help='Port to bind')
    args = parser.parse_args()

    uvicorn.run(
        'app:app',
        host=args.host,
        port=args.port,
        reload=True,
        ws_ping_interval=None,
        ws_ping_timeout=None)


if __name__ == "__main__":
    main()