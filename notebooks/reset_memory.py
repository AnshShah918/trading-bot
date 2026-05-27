from src.memory.db import get_db
from src.memory.models import Trade

db = get_db()

deleted = db.query(Trade).delete()

db.commit()
db.close()

print(f"Deleted {deleted} trades")
