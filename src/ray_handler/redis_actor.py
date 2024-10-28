import asyncio
import ray
import json


@ray.remote
class RedisSubscriber:
    def __init__(self, redis_conn, channel_name, service_executor):
        self.redis_conn = redis_conn
        self.channel_name = channel_name
        self.service_executor = service_executor
        self.listen_task = asyncio.create_task(self.start_listening())

    async def start_listening(self):
        async with self.redis_conn.pubsub() as pubsub:
            await pubsub.subscribe(self.channel_name)

            async for message in pubsub.listen():
                if message["type"] == "message":
                    task_message = message["data"].decode("utf-8")

                    if task_message == "stop":
                        break

                    asyncio.create_task(self.handle_message(task_message))  # noqa: RUF006

    async def handle_message(self, task_message: str):
        try:
            (
                response_channel,
                result,
            ) = await self.service_executor.process_request.remote(
                task_message,
            )

            if response_channel is None:
                return

            if result:
                await self.redis_conn.publish(response_channel, result)

        except json.JSONDecodeError as e:
            print(f"JSONDecodeError for message: {task_message} - {str(e)}")  # noqa: RUF010

        except Exception as e:
            print(f"Error processing message: {task_message} - {str(e)}")  # noqa: RUF010

    async def run(self):
        await self.listen_task
