from src.settings import CONNECTION_DETAILS
from contextlib import contextmanager
import redis.asyncio as redis
import asyncio
import sys


class RedisWriter:
    def __init__(self, log_key):
        self.redis_client = redis.Redis(**CONNECTION_DETAILS)
        self.log_key = log_key
        self.original_stdout = sys.stdout
        self.encoding = sys.stdout.encoding
        self.append_script = self.redis_client.register_script(
            """
        local current = redis.call('HGET', KEYS[1], ARGV[1])
        if not current then
            current = ""
        end
        local updated = current .. ARGV[2]
        redis.call('HSET', KEYS[1], ARGV[1], updated)
        return updated
        """,
        )

    def write(self, message):
        if message.strip():
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Async context, use create_task to schedule the append
                loop.call_soon_threadsafe(
                    asyncio.create_task,
                    self.append_script(
                        keys=[self.log_key],
                        args=["logs", message + "\n"],
                    ),
                )
            else:
                # Synchronous context, run the append immediately
                loop.run_until_complete(
                    self.append_script(
                        keys=[self.log_key],
                        args=["logs", message + "\n"],
                    ),
                )

        self.original_stdout.write(message)

    def flush(self):
        self.original_stdout.flush()

    def isatty(self):
        return self.original_stdout.isatty()


@contextmanager
def redirect_stdout(log_key):
    redis_writer = RedisWriter(log_key)
    original_stdout = sys.stdout
    sys.stdout = redis_writer
    try:
        yield redis_writer
    finally:
        redis_writer.flush()
        sys.stdout = original_stdout
