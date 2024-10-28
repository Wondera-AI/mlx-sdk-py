import uuid
import ray
import asyncio
import json
import pydantic
import redis.asyncio as redis
import os
from src.service import ServiceCallableSyncAsync
from src.redis_logger import redirect_stdout
from src.settings import CONNECTION_DETAILS, ENV_SERVICE_IN_CHANNEL

STOPWORD = "stop"


@ray.remote
def handle_message(
    service: ServiceCallableSyncAsync,
    task_message: str,
    input_type,
    run_config,
):
    try:
        # from src.remote import log_key_var

        task_data = json.loads(task_message)

        log_key = task_data["log_key"]
        # log_key_var.set(log_key)

        response_channel = task_data["response_channel"]
        request_data = json.loads(task_data["request_data"])
        request_body = request_data["body"]
        with redirect_stdout(log_key):
            print(
                f"Received request for '{service.__name__}' with input: {request_body}",
            )

            try:
                valid_input_data = input_type(**request_body)
                if asyncio.iscoroutinefunction(service):
                    # result = asyncio.run_coroutine_threadsafe(
                    #     service(valid_input_data, run_config),
                    #     asyncio.get_event_loop(),
                    # ).result()

                    result = asyncio.run(service(valid_input_data, run_config))
                    # result = run_async_in_new_loop(service(valid_input_data, run_config))
                    # result = await service(valid_input_data, run_config)

                else:
                    result = service(valid_input_data, run_config)

                result_json = (
                    result.model_dump_json()
                    if isinstance(result, pydantic.BaseModel)
                    else json.dumps(result)
                )
                print(f"Service '{service.__name__}' Output: {result_json}")
                return response_channel, result_json

            except pydantic.ValidationError as e:
                error_message = f"Input data validation error: {str(e)}"
                print(error_message)
                return response_channel, error_message

            except Exception as e:
                error_message = f"Error calling service: {str(e)}"
                print(error_message)
                return response_channel, error_message

    except Exception as e:
        return None, f"Unexpected error: {str(e)}"


async def process_result(redis_conn: redis.Redis, task_future):
    # Wait for Ray task to complete and process result
    response_channel, result = await task_future

    if response_channel is None:
        return
    if result:
        await redis_conn.publish(response_channel, result)

    # ray.internal.free([task_future])


async def run_service(
    service: ServiceCallableSyncAsync,
    input_type,
    run_config,
):
    ray.shutdown()
    ray.init(address="local")

    channel_name = _get_channel_name(service.__name__)
    redis_conn = redis.Redis(**CONNECTION_DETAILS)

    async with redis_conn.pubsub() as pubsub:
        await pubsub.subscribe(channel_name)

        async for message in pubsub.listen():
            if message["type"] == "message":
                task_message = message["data"].decode("utf-8")
                if task_message == STOPWORD:
                    break

                # Dispatch to Ray without awaiting
                task_future = handle_message.remote(
                    service,
                    task_message,
                    input_type,
                    run_config,
                )

                # Create async task to process the result without blocking main loop
                asyncio.create_task(process_result(redis_conn, task_future))  # noqa: RUF006
                # await process_result(redis_conn, task_future)


def _get_channel_name(func_name: str) -> str:
    # [service]-[name]-[version]-[func_name]
    # first 3 set by env var, last set by service decorator
    service_in_channel = os.getenv(ENV_SERVICE_IN_CHANNEL)

    print(f"OS-ENV service-in-channel: {service_in_channel}")
    if not service_in_channel:
        service_in_channel = "service-test-1"

    service_in_channel = service_in_channel + "-" + func_name
    print(f"Subscribing to service-in-channel: {service_in_channel}")

    return service_in_channel
