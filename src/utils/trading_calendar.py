from datetime import date, timedelta

# NSE Holidays — update each year from:
# https://www.nseindia.com/resources/exchange-communication-holidays

NSE_HOLIDAYS = {
    # 2025
    date(2025, 1, 26),   # Republic Day
    date(2025, 2, 19),   # Chhatrapati Shivaji Maharaj Jayanti
    date(2025, 2, 26),   # Mahashivratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-Ul-Fitr
    date(2025, 4, 14),   # Dr. Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 27),   # Ganesh Chaturthi
    date(2025, 10, 2),   # Gandhi Jayanti
    date(2025, 10, 20),  # Diwali Laxmi Pujan
    date(2025, 10, 21),  # Diwali Balipratipada
    date(2025, 11, 5),   # Gurunanak Jayanti
    date(2025, 12, 25),  # Christmas

    # 2026 — verify at start of year
    date(2026, 1, 26),   # Republic Day
    date(2026, 3, 20),   # Holi (approximate)
    date(2026, 4, 3),    # Good Friday (approximate)
    date(2026, 4, 14),   # Dr. Ambedkar Jayanti
    date(2026, 5, 1),    # Maharashtra Day
    date(2026, 8, 15),   # Independence Day
    date(2026, 10, 2),   # Gandhi Jayanti
    date(2026, 11, 9),   # Diwali (approximate)
    date(2026, 12, 25),  # Christmas
}


def is_trading_day(d=None):
    if d is None:
        d = date.today()
    if d.weekday() >= 5:  # Saturday=5 Sunday=6
        return False
    if d in NSE_HOLIDAYS:
        return False
    return True


def next_trading_day(d=None):
    if d is None:
        d = date.today()
    next_day = d + timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += timedelta(days=1)
    return next_day


def trading_days_between(start, end):
    count = 0
    current = start + timedelta(days=1)
    while current <= end:
        if is_trading_day(current):
            count += 1
        current += timedelta(days=1)
    return count


def t1_date(entry_date=None):
    if entry_date is None:
        entry_date = date.today()
    return next_trading_day(entry_date)


def is_t1_ready(entry_time):
    if entry_time is None:
        return False
    entry_date = entry_time.date()
    t1 = t1_date(entry_date)
    return date.today() >= t1
