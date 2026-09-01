from typing import Callable
from functools import wraps
import random
import time
import asyncio

# decorator to fix endpoint response time based on random range
def response_time_fixer(time_range_start: float, time_range_end: float):
    def wrapper(func: Callable):
        @wraps(func)
        async def inner(*args, **kwargs):
            raise_ex = None

            # get const random time range
            const_time = random.uniform(time_range_start, time_range_end)
            # await func and meansure work time
            time_start = time.perf_counter()
            try:
                res = await func(*args, **kwargs)
            # set raise ex
            except Exception as ex:
                raise_ex = ex

            time_end = time.perf_counter()

            work_time = time_end - time_start
            print("work time:", work_time)
            
            # get times diff between work and const times
            times_diff = const_time - work_time

            # sleep diff
            if times_diff > 0:
                await asyncio.sleep(times_diff)

            # raise ex from route
            if raise_ex:
                raise raise_ex

            return res
        return inner
    return wrapper