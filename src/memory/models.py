from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

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

    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )
