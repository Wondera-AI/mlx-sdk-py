import asyncio
import json
import os
from typing import Any
import redis.asyncio as redis
import secrets
import hashlib
from src.settings import CONNECTION_DETAILS, ENV_SERVICE_IN_CHANNEL
import contextvars

# safely pass log_key for unique job as per thread context
log_key_var = contextvars.ContextVar("log_key")


async def remote_call(
    service_func_name: str,
    input: dict[str, Any],
    timeout: float = 5.0,
) -> Any:
    print(f"Remote call to {service_func_name} with input: {input}")
    # if service_func_name not in service_registry:
    #     raise ValueError(
    #         f"Service {service_func_name} not registered, only local services are supported currently.",  # noqa: E501
    #     )

    redis_conn = redis.Redis(**CONNECTION_DETAILS)
    # 1. get os ENV_SERVICE_IN_CHANNEL
    full_input_channel = os.getenv(ENV_SERVICE_IN_CHANNEL)

    # 2. replace [function_name] with service_func_name
    parts = (
        full_input_channel.split("-")[:-1]
        if full_input_channel
        else ["service", "test", "1"]
    )
    next_service_channel = f"{'-'.join(parts)}-{service_func_name}"

    # random response channel
    response_channel = hashlib.sha256(secrets.token_bytes(64)).hexdigest()

    # 3. create message for next service
    try:
        msg = {
            "request_data": json.dumps({"body": input}),
            "response_channel": response_channel,
            "log_key": log_key_var.get(),
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

    print(f"Next service channel: {next_service_channel}")

    async with redis_conn.pubsub() as pubsub:
        await pubsub.subscribe(response_channel)

        # 4. publish input to channel
        await redis_conn.publish(next_service_channel, json.dumps(msg))
        print(f"Remote publish to {next_service_channel} with msg: \n {msg}")

        # Step 5: Wait for a response on the response channel
        try:
            response = await asyncio.wait_for(pubsub_listen(pubsub), timeout=timeout)
            return response

        except TimeoutError:
            print(
                f"Timeout: No response from {next_service_channel} within {timeout} seconds.",  # noqa: E501
            )
            raise

        except Exception as e:
            print(f"Remote call pubsub listen error: {e}")
            raise e

        finally:
            await pubsub.unsubscribe(response_channel)
            await pubsub.reset()


async def pubsub_listen(pubsub):
    async for message in pubsub.listen():
        if message["type"] == "message":
            response_data = message["data"].decode("utf-8")
            print(f"Remote call response: {response_data}")

            try:
                response = json.loads(response_data)
                return response

            except json.JSONDecodeError as e:
                print(f"Failed to decode JSON response: {e}")
                raise e


# TODO handle service_func_name = "mnist.4.service_b"
# pattern service-in-channel
# "service-mnist_4-input" - OLD
# "service-input-mnist-4-preprocess" - NEW
# "service-input-[service_name]-[version]-[function_name]" - PATTERN
# TODO update server to handle pattern
