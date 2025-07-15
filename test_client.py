import argparse
import asyncio
import base64
import json
import contextlib
import logging
import os
import random
from typing import Any, Callable

from httpx import AsyncClient
from httpx_ws import aconnect_ws

logging.basicConfig(
    level=logging.DEBUG,
    format=('%(asctime)s.%(msecs)03d %(name)s(%(process)d):'
            '%(levelname)s: %(message)s'),
    datefmt='%H:%M:%S'
)
log = logging.getLogger("Coordinator")


class HoudiniWorker:
    def __init__(self, port: int = 8765, timeout: float = 60.0):
        self.port = port
        self.timeout = timeout
        self.websocket = None
        self.client = None

    async def __aenter__(self):
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._disconnect()
        return False

    async def _connect(self):
        self.client = AsyncClient()
        try:
            log.info(f"Connecting to localhost:{self.port}")
            self.async_stack = contextlib.AsyncExitStack()
            self.websocket = await self.async_stack.enter_async_context(
                aconnect_ws(f"ws://localhost:{self.port}", self.client))
            log.info("Connection successful")
        except Exception as e:
            log.error(f"Connection failed: {e}")
            await self.client.aclose()
            raise

    async def _disconnect(self):
        if self.websocket:
            await self.stack.aclose()
            self.websocket = None

        if self.async_stack:
            await self.async_stack.aclose()
            self.async_stack = None

        if self.client:
            await self.client.aclose()
            self.client = None

    async def send_message(self,
                           data: Any,
                           process_response: Callable[[Any], bool]) -> bool:
        try:
            log.debug("Sending message: %s", data)
            await self.websocket.send_text(json.dumps(data))

            while True:
                try:
                    message = await asyncio.wait_for(
                        self.websocket.receive_text(),
                        timeout=self.timeout
                    )
                    response_data = json.loads(message)
                    log.debug("Received response: %s", response_data)

                    completed = process_response(response_data)
                    if completed:
                        return True
                except asyncio.TimeoutError:
                    log.error("Read timeout while waiting for data")
                    return False
        except Exception as e:
            log.error("Communication error: %s", e)
            return False


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",
                        type=int,
                        default=8765,
                        help="Port number for WebSocket connection")
    return parser.parse_args()


async def main():
    args = parse_args()

    async with HoudiniWorker(port=args.port) as worker:
        def process_response(response: Any) -> bool:
            completed = response["op"] == "automation" and \
                response["data"] == "end"
            return completed

        # Upload HDA file
        hda_file_id = "file_test_hda"
        hda_path = "assets/test_cube.hda"
        base64_content = None
        with open(hda_path, "rb") as f:
            file_content = f.read()
            base64_content = base64.b64encode(file_content).decode('utf-8')

        upload_message = {
            "op": "file_upload",
            "data": {
                "file_id": hda_file_id,
                "content_type": "application/hda",
                "content_base64": base64_content
            }
        }
        log.info("Uploading HDA file")
        success = await worker.send_message(
            upload_message,
            process_response)
        assert success
        log.info("HDA file uploaded")

        # Upload USDZ file
        input_file_id = "file_test_input0"
        input_path = "assets/cube.usdz"
        base64_content = None
        with open(input_path, "rb") as f:
            file_content = f.read()
            base64_content = base64.b64encode(file_content).decode('utf-8')

        upload_message = {
            "op": "file_upload",
            "data": {
                "file_id": input_file_id,
                "content_type": "application/usdz",
                "content_base64": base64_content
            }
        }
        log.info("Uploading USDZ file")
        success = await worker.send_message(
            upload_message,
            process_response)
        assert success
        log.info("USDZ file uploaded")

        # Cook HDA
        test_message = {
            "op": "cook",
            "data": {
                "hda_path": {
                    "file_id": hda_file_id,
                },
                "definition_index": 0,
                "format": "raw",
                "input0": {
                    "file_id": input_file_id,
                },
                "test_int": 5,
                "test_float": 2.0,
                "test_string": "test",
                "test_bool": True,
            }
        }

        while True:
            log.info("Requesting automation")
            success = await worker.send_message(
                test_message,
                process_response)
            assert success
            log.info("Automation completed")
            await asyncio.sleep(random.uniform(3, 5))


if __name__ == "__main__":
    asyncio.run(main())
