import redis.asyncio as redis
import os
from src.settings import CONNECTION_DETAILS, ENV_SERVICE_IN_CHANNEL
from src.ray_handler.service_actor import ServiceExecutor
from src.ray_handler.redis_actor import RedisSubscriber
import ray
import json
import inspect
from typing import Callable, Any, Coroutine, TypeVar, overload  # noqa: UP035
import sys
from src.base_models import Input, Config, Output


InputT = TypeVar("InputT", bound=Input)
ConfigT = TypeVar("ConfigT", bound=Config)
OutputT = TypeVar("OutputT", bound=Output)

ServiceCallable = Callable[[InputT, ConfigT], OutputT]
ServiceCallableSyncAsync = Callable[
    [InputT, ConfigT],
    OutputT | Coroutine[Any, Any, OutputT],
]


service_registry = {}


@overload
def service(func: ServiceCallableSyncAsync) -> ServiceCallableSyncAsync: ...


@overload
def service(
    **service_kwargs: Any,
) -> Callable[[ServiceCallableSyncAsync], ServiceCallableSyncAsync]: ...


# Service decorator definition
def service(
    func: ServiceCallableSyncAsync | None = None,
    **service_kwargs: Any,
) -> (
    Callable[[ServiceCallableSyncAsync], ServiceCallableSyncAsync]
    | ServiceCallableSyncAsync
):
    def decorator(
        func: ServiceCallableSyncAsync,
    ) -> ServiceCallableSyncAsync:
        _register_service(func, **service_kwargs)

        # Automatically run the service if this script is executed
        if len(sys.argv) > 1 and sys.argv[1] == func.__name__:
            print(f"Running Service Name: {func.__name__}")
            input_type = service_registry[func.__name__]["input_type"]
            config_type = service_registry[func.__name__]["config_type"]
            service_func = service_registry[func.__name__]["service_func"]

            config_data = _load_config_from_args()
            valid_config_data = config_type.from_dict(config_data)

            ray.init(address="local")

            # # Start ServiceExecutor Actor
            service_executor = ServiceExecutor.remote(
                service_func,
                input_type,
                valid_config_data,
            )

            # # Start RedisSubscriber Actor
            channel_name = _get_channel_name(service_func.__name__)
            # # redis_details = {
            # #     "host": os.getenv("REDIS_HOST", "localhost"),
            # #     "port": int(os.getenv("REDIS_PORT", 6379)),
            # #     "password": os.getenv("REDIS_PASSWORD", None),
            # # }
            redis_conn = redis.Redis(**CONNECTION_DETAILS)
            redis_subscriber = RedisSubscriber.remote(
                redis_conn,
                channel_name,
                service_executor,
            )
            ray.get(redis_subscriber.run.remote())  # type: ignore # noqa: PGH003

        else:
            print(
                f"No service execution requested for '{func.__name__}' > assuming build only mode",  # noqa: E501
            )

        return func

    if func is not None and callable(func):
        return decorator(func)

    return decorator


def _register_service(func, **service_kwargs):
    print("registering service: ", func.__name__)
    signature = inspect.signature(func)
    input_type = next(iter(signature.parameters.values())).annotation
    config_type = list(signature.parameters.values())[1].annotation
    output_type = signature.return_annotation

    # Register the service with its name, input, and output types
    service_registry[func.__name__] = {
        "service_func": func,
        "input_type": input_type,
        "config_type": config_type,
        "output_type": output_type,
        "service_kwargs": service_kwargs,
    }

    print(f"Service Registry Snapshot: {service_registry}")


def _load_config_from_args():
    config_data = {}

    if len(sys.argv) > 2:  # noqa: PLR2004
        config_data_string = sys.argv[2]
        config_data = json.loads(config_data_string)
        print("Config provided", config_data)
    else:
        print("No config provided")

    return config_data


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
