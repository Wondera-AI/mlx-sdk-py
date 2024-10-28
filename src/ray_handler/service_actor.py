import ray
import json
import asyncio
from src.redis_logger import redirect_stdout
import pydantic


@ray.remote
class ServiceExecutor:
    def __init__(self, service, input_type, config):
        self.service = service
        self.input_type = input_type
        self.config = config

    def run_sync_service(self, valid_input_data):
        return self.service(valid_input_data, self.config)

    async def run_async_service(self, valid_input_data):
        return await self.service(valid_input_data, self.config)

    async def process_request(self, task_message: str):
        task_data = json.loads(task_message)
        log_key = task_data["log_key"]
        response_channel = task_data["response_channel"]
        request_data = json.loads(task_data["request_data"])
        request_body = request_data["body"]

        from src.remote import log_key_var

        log_key_var.set(log_key)

        with redirect_stdout(log_key):
            print(
                f"Received request for '{self.service.__name__}' with input: {request_body}",  # noqa: E501
            )

            try:
                valid_input_data = self.input_type(**request_body)

                # Execute the service function (async or sync)
                if asyncio.iscoroutinefunction(self.service):
                    result = await self.run_async_service(valid_input_data)
                else:
                    result = self.run_sync_service(valid_input_data)

                result_json = (
                    result.model_dump_json()
                    if isinstance(result, pydantic.BaseModel)
                    else json.dumps(result)
                )

                print(f"Service '{self.service.__name__}' Output: {result_json}")
                return response_channel, result_json

            except pydantic.ValidationError as e:
                error_message = f"Input data validation error: {str(e)}"  # noqa: RUF010
                print(error_message)
                return response_channel, json.dumps({"error": error_message})

            except Exception as e:
                error_message = f"Error calling service: {str(e)}"  # noqa: RUF010
                print(error_message)
                return response_channel, json.dumps({"error": error_message})
