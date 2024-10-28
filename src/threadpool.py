import asyncio
import multiprocessing
import json
import pydantic
import redis.asyncio as redis
import os
from src.service import ServiceCallableSyncAsync
from src.redis_logger import redirect_stdout
from src.settings import CONNECTION_DETAILS, ENV_SERVICE_IN_CHANNEL
from concurrent.futures import ProcessPoolExecutor

STOPWORD = "stop"


def _get_channel_name(func_name: str) -> str:
    # [service]-[name]-[version]-[func_name]
    # first 3 set by env var, last set by service decorator
    service_in_channel = os.getenv(ENV_SERVICE_IN_CHANNEL)

    print(f"OS-ENV service-in-channel: {service_in_channel}")
    if not service_in_channel:
        service_in_channel = "service-test-1"

    service_in_channel = service_in_channel + "-" + func_name

    return service_in_channel


async def run_service(service: ServiceCallableSyncAsync, input_type, run_config):
    channel_name = _get_channel_name(service.__name__)
    print(f"Starting service... Subscribing to channel: {channel_name}")

    multiprocessing.set_start_method("spawn", force=True)

    redis_conn = redis.Redis(**CONNECTION_DETAILS)
    async with redis_conn.pubsub() as pubsub:
        await pubsub.subscribe(channel_name)

        with ProcessPoolExecutor() as pool:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    task_message = message["data"].decode("utf-8")

                    if task_message == STOPWORD:
                        break

                    # await handle_message(
                    #     task_message,
                    #     service,
                    #     pool,
                    #     redis_conn,
                    #     input_type,
                    #     run_config,
                    # )
                    asyncio.create_task(
                        handle_message(
                            task_message,
                            service,
                            pool,
                            redis_conn,
                            input_type,
                            run_config,
                        )
                    )


async def handle_message(
    task_message: str,
    service: ServiceCallableSyncAsync,
    pool: ProcessPoolExecutor,
    redis_conn: redis.Redis,
    input_type,
    run_config,
):
    from src.remote import log_key_var

    try:
        task_data = json.loads(task_message)
        request_data = json.loads(task_data["request_data"])
        request_body = request_data["body"]
        response_channel = task_data["response_channel"]
        log_key = task_data["log_key"]
        log_key_var.set(log_key)

        with redirect_stdout(log_key):
            print(f"Received new task: {request_body}")

            result = None
            try:
                valid_input_data = input_type(**request_body)
                print(
                    f"HANDLING-Message for {service.__name__} with input: {valid_input_data}",  # noqa: E501
                )
                if asyncio.iscoroutinefunction(service):
                    result = await service(valid_input_data, run_config)

                else:
                    result = service(valid_input_data, run_config)
                # if asyncio.iscoroutinefunction(service):
                #     # Wrap async service in a pool to handle CPU-bound async tasks
                #     loop = asyncio.get_running_loop()
                #     result = await loop.run_in_executor(
                #         pool,
                #         lambda: asyncio.run(service(valid_input_data, run_config)),
                #     )
                # else:
                #     # Run synchronous tasks directly in the pool
                #     # loop = asyncio.get_running_loop()
                #     result = await asyncio.get_running_loop().run_in_executor(
                #         None,
                #         service,
                #         valid_input_data,
                #         run_config,
                #     )

            except (pydantic.ValidationError, TypeError, ValueError) as e:
                result = f"Error calling service: {service.__name__} with: {str(e)}"  # noqa: RUF010
                print(result)
                await redis_conn.publish(response_channel, result)

            except Exception as e:
                result = (
                    f"Unexpected error: {str(e)} calling service: {service.__name__}"  # noqa: RUF010
                )
                print(result)
                await redis_conn.publish(response_channel, result)

            finally:
                if isinstance(result, pydantic.BaseModel):
                    result_json = result.model_dump_json()
                else:
                    result_json = json.dumps(result)

                print(f"HANDLING-Result: {result}")
                await redis_conn.publish(response_channel, result_json)

    except (KeyError, json.JSONDecodeError) as err:
        error_message = f"Error loading JSON within task: {err}"
        print(error_message)

    except Exception as e:
        error_message = f"Unexpected error within task: {e}"
        print(error_message)


# TODO - old complexity
# async def handle_message(
#     task_message: str,
#     service: ServiceCallableSyncAsync,
#     pool: ProcessPoolExecutor,
#     redis_conn: redis.Redis,
#     input_type,
#     run_config,
# ):
#     from src.remote import log_key_var

#     try:
#         # redis_conn = redis.Redis(**CONNECTION_DETAILS)
#         task_data = json.loads(task_message)
#         request_data = json.loads(task_data["request_data"])
#         request_body = request_data["body"]
#         response_channel = task_data["response_channel"]
#         log_key = task_data["log_key"]
#         log_key_var.set(log_key)

#         # with redirect_stdout(lsog_key):
#         print(f"Received new task: {request_body}")
#         print(f"Foo")
#         valid_input_data = input_type(**request_body)

#         # Wait for the future to finish (either async or sync handled in a task)
#         async def process_log_and_publish_result(result_future):
#             with redirect_stdout(log_key):
#                 print(
#                     f"HANDLING-Message for {service.__name__} with input: {valid_input_data}",  # noqa: E501
#                 )
#                 try:
#                     result = await result_future
#                     print(f"HANDLING-Result: {result}")

#                     if hasattr(result, "model_dump_json"):
#                         result_json = result.model_dump_json()
#                     else:
#                         result_json = json.dumps(result)

#                     await redis_conn.publish(response_channel, result_json)

#                 except (pydantic.ValidationError, TypeError, ValueError) as e:
#                     error_message = (
#                         f"Error calling service: {service.__name__} with: {str(e)}"  # noqa: RUF010
#                     )
#                     print(error_message)
#                     await redis_conn.publish(response_channel, error_message)

#                 except Exception as e:
#                     error_message = f"Unexpected error: {str(e)} calling service: {service.__name__}"  # noqa: E501, RUF010
#                     print(error_message)
#                     await redis_conn.publish(response_channel, error_message)

#             # Handle async and sync service functions
#             # ensure their execution doesn't block the main thread by awaiting in task

#         if asyncio.iscoroutinefunction(service):
#             result_future = asyncio.create_task(
#                 service(valid_input_data, run_config),
#             )

#         else:
#             result_future = asyncio.get_running_loop().run_in_executor(
#                 None,
#                 service,
#                 valid_input_data,
#                 run_config,
#             )

#         # Create task to process the service_caller but dont await it
#         asyncio.create_task(process_log_and_publish_result(result_future))  # noqa: RUF006
#         # await result_future

#     # Dont publish these errors for now so as to not slow main thread
#     except (KeyError, json.JSONDecodeError) as err:
#         error_message = f"Error loading JSON within task: {err}"
#         print(error_message)
#         # await redis_conn.publish(response_channel, error_message)

#     except Exception as e:
#         error_message = f"Unexpected error within task: {e}"
#         print(error_message)


# TODO - incase the lambda error of serialization occurs in the .run_in_executor
# async def ensure_event_loop():
#     try:
#         # Try to get the current event loop
#         return asyncio.get_running_loop()
#     except RuntimeError:
#         # If no running loop, create one manually for this thread
#         loop = asyncio.new_event_loop()
#         asyncio.set_event_loop(loop)
#         return loop

# async def run_service_with_event_loop(
#     service,
#     valid_input_data,
#     run_config,
# ):
#     loop = await ensure_event_loop()
#     return await loop.run_in_executor(
#         None,
#         service,
#         valid_input_data,
#         run_config,
#     )

# result_future = asyncio.create_task(
#     run_service_with_event_loop(
#         service,
#         valid_input_data,
#         run_config,
#     ),
# )
