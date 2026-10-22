import sys
sys.path.insert(0, ".")
import asyncio
from app.api.routes.scripts import _get_state_values

async def main():
    vals = await _get_state_values("1982f14b-5f0a-4074-9244-47d1e48fe918")
    ps = vals.get("prompt_set")
    if not ps:
        print("No prompt set found")
        return
    for p in ps.prompts:
        print(f"=== Shot {p.sequence_number} ({p.prompt_id}) - Duration: {p.duration_seconds}s ===")
        print(p.prompt_text)
        print()

if __name__ == "__main__":
    asyncio.run(main())
