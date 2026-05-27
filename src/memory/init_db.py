from src.memory.db import engine
from src.memory.models import Base


def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")


if __name__ == "__main__":
    init_db()
