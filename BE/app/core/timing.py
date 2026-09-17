import time


def elapsed_ms(start_time: float, end_time: float | None = None) -> float:
    finished_at = time.perf_counter() if end_time is None else end_time
    return round((finished_at - start_time) * 1000, 2)
