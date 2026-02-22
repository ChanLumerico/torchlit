import asyncio
import websockets
import json

async def test():
    async with websockets.connect("ws://localhost:8000/ws/stream/dummy_test") as ws:
        msg = await ws.recv()
        data = json.loads(msg)
        print("Model Info keys:", data.get("model_info", {}).keys())
        if "architecture" in data.get("model_info", {}):
            print("Architecture found!")
        else:
            print("Architecture MISSING!")

asyncio.run(test())
