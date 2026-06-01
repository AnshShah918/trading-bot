from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base
from datetime import timezone, datetime

Base = declarative_base()


class Trade(Base):
    __tablename__ = "trades"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    symbol = Column(
        String,
        nullable=False
    )

    entry_price = Column(
        Float,
        nullable=False
    )

    exit_price = Column(
        Float,
        nullable=True
    )

    quantity = Column(
        Integer
    )

    pnl = Column(
        Float,
        nullable=True
    )

    status = Column(
        String
    )

    entry_reason = Column(
        String
    )

    exit_reason = Column(
        String
    )

    entry_time = Column(
        DateTime,
        default=datetime.utcnow
    )

    exit_time = Column(
        DateTime,
        nullable=True
    )

    current_stop = Column(
        Float,
        nullable=True
    )

    highest_price = Column(
        Float,
        nullable=True
    )

    last_known_price = Column(
        Float,
        nullable=True
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )
