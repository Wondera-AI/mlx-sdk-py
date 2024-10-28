import sys
import os

# # Add the src directory to PYTHONPATH for all tests
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src as mlx


# USERLAND
class InputA(mlx.Input):
    foo: str = "foo"


class ConfigA(mlx.Config):
    smoothing: float = 0.1


class OutputA(mlx.Output):
    bar: str = "bar"


# pdm run service.py service_a '{"smoothing": 0.1}'
@mlx.service
async def service_a(input: InputA, config: ConfigA) -> OutputA:
    print(f"Inside Service A: {input}")
    print(f"w/ Config A: {config}")
    response = await mlx.remote_call("service_b", input={"foo": input.foo})
    print(f"Response from B in Service A: {response}")
    return OutputA(bar=response["bar"])


class InputB(mlx.Input):
    foo: str = "foo"


class ConfigB(mlx.Config):
    smoothing: float = 0.1


class OutputB(mlx.Output):
    bar: str = "bar"


variable = [1, 2, 3]


@mlx.service(gpu=True)
def service_b(input: InputB, config: ConfigB) -> OutputB:
    print(f"Inside Service B: {input}")
    print(f"w/ Config B: {config}")
    print(f"Variable: {variable}")
    return OutputB(bar=input.foo)


# @mlx.trainer
# def step(data_shard):
#     pass
