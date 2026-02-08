from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def ms_to_datetime(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def datetime_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def format_timestamp(ms: int) -> str:
    dt = ms_to_datetime(ms)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
