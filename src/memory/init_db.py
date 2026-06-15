from src.memory.db import engine
from src.memory.models import Base
from src.utils.cost_calculator import calculate_trade_costs


def _add_column_if_missing(connection, table, column, ddl):
    existing = {
        row[1]
        for row in connection.exec_driver_sql(
            f"PRAGMA table_info({table})"
        )
    }

    if column not in existing:
        connection.exec_driver_sql(
            f"ALTER TABLE {table} ADD COLUMN {ddl}"
        )


def init_db():
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        _add_column_if_missing(
            connection,
            "trades",
            "entry_snapshot",
            "entry_snapshot TEXT"
        )
        _add_column_if_missing(
            connection,
            "trades",
            "net_pnl",
            "net_pnl FLOAT"
        )

        closed_without_net = connection.exec_driver_sql(
            """
            SELECT id, entry_price, exit_price, quantity, pnl
            FROM trades
            WHERE status = 'closed'
              AND net_pnl IS NULL
              AND entry_price IS NOT NULL
              AND exit_price IS NOT NULL
              AND quantity IS NOT NULL
              AND pnl IS NOT NULL
            """
        )

        for trade in closed_without_net:
            costs = calculate_trade_costs(
                trade.entry_price * trade.quantity,
                trade.exit_price * trade.quantity,
                trade.pnl
            )
            connection.exec_driver_sql(
                "UPDATE trades SET net_pnl = ? WHERE id = ?",
                (costs["net_pnl"], trade.id)
            )

    print("Database initialized successfully!")


if __name__ == "__main__":
    init_db()
