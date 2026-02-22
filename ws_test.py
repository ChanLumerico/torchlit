import asyncio
import websockets
import json


async def test():
    print("Connecting to ws://localhost:8000/ws/stream/dummy_test...")
    try:
        async with websockets.connect("ws://localhost:8000/ws/stream/dummy_test") as ws:
            # read the first few messages
            for _ in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                data = json.loads(msg)
                step = data.get("step")
                mi = data.get("model_info", {})
                print(f"Received step {step}. model_info keys: {list(mi.keys())}")
                if mi and "architecture" in mi:
                    print("Architecture payload received!")
    except Exception as e:
        import traceback

        print(f"Error: {repr(e)}")
        traceback.print_exc()


asyncio.run(test())
