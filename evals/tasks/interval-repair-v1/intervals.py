"""Integer interval utilities (interval-repair-v1)."""


def coalesce(ranges):
    """Validate and return intervals in ascending order."""
    if not isinstance(ranges, (list, tuple)):
        raise ValueError("ranges must be a list or tuple")
    copied = []
    for pair in ranges:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("each range must be a pair")
        start, end = pair
        if type(start) is not int or type(end) is not int or start > end:
            raise ValueError("endpoints must be ordered integers")
        copied.append((start, end))
    return sorted(copied)
