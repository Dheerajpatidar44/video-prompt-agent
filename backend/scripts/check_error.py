import sys
sys.path.insert(0, ".")
import asyncio
from app.db.database import get_db
from app.api.routes.scripts import _get_state_values

async def main():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, title, status FROM projects ORDER BY created_at DESC LIMIT 3")
    rows = c.fetchall()
    print("Recent projects:", [(r[0], r[1], r[2]) for r in rows])
    conn.close()

    for row in rows:
        proj_id = row[0]
        try:
            values = await _get_state_values(proj_id)
            print(f"\n--- State for {proj_id} ---")
            print("Status:", values.get("status"))
            print("Error:", values.get("error"))
            print("Keys:", list(values.keys()))
        except Exception as e:
            print(f"Error fetching state for {proj_id}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
