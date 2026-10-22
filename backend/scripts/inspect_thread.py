import sys
sys.path.insert(0, ".")
import asyncio
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.graph.graph import serde

async def main():
    thread_id = "9b776aa0-c221-4bbb-9d84-1653db6431b7"
    config = {"configurable": {"thread_id": thread_id}}
    async with aiosqlite.connect("data/memory.sqlite") as conn:
        saver = AsyncSqliteSaver(conn, serde=serde)
        await saver.setup()
        async for checkpoint in saver.alist(config):
            step = checkpoint.metadata.get("step")
            source = checkpoint.metadata.get("source")
            writes = checkpoint.metadata.get("writes")
            print(f"Step {step}: source={source}, writes={writes}")
            state_vals = checkpoint.checkpoint.get("channel_values", {})
            print("  status:", state_vals.get("status"))
            print("  error:", state_vals.get("error"))

if __name__ == "__main__":
    asyncio.run(main())
