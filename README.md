# mlx-sdk

Python SDK to define Endpoint and Function Services with multi-step support where each Service will run in its own pod with fine-grained resource control.

## Installation 
Install package
```bash
pdm add git+https://github.com/Wondera-AI/mlx-sdk-py.git@main
```
Or add as pyproject.toml dependency
```toml
dependencies = [
  "mlx-sdk @ git+https://github.com/Wondera-AI/mlx-sdk-py.git@main",
]
```

## Usage
```python
# src/service.py

import mlx-sdk as mlx

class InputA(mlx.Input):
    foo: str = "foo"

class ConfigA(mlx.Config):
    smoothing: float = 0.1

class OutputA(mlx.Output):
    bar: str = "bar"

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

@mlx.service(gpu_limit=2)
def service_b(input: InputB, config: ConfigB) -> OutputB:
    print(f"Inside Service B: {input}")
    print(f"w/ Config B: {config}")
    print(f"Variable: {variable}")
    return OutputB(bar=input.foo)
```

## Noteworthy Observations
- define Input, Output and Config using base classes
- Config are dynamic program arguments when starting the service defined in `mlx.toml`
- define a sevice using the `@mlx.service`
- define as many services as you want
- each service will be deployed into a respective service pod
- `@mlx.service` takes optional args (below) to have fine grain control over each service
- without arguments the service pod will default to the `mlx.toml` config
- service entrypoint should be defined in the `src/service.py` of any repo
- under the hood the mlx client will start each service using `python service.py service_a '{"smoothing": 0.1}'`
- multi-step service is supported using `mlx.remote("service_func", input={...})`
- multi-step only currently supports locally defined services

## @mlx.service( *arguments* )
- cpu_limit: float - max cpu node count
- gpu_limit: int - max gpu node count
- mem_limit: int - max memory limit
- min_pods: [0,1] - set to 0 for pod autoscale shutdown
- endpoint: bool - set to False to guard http service discovery of the pod

## Future Improvement
- multi-step could support global services using namespace addressing `mlx.remote("service_name.service_func", input={...})`
- SIMD like operations with map and reduce across service pods for better distributed workloads
- typed response from multi-step
- @mlx.trainer for trainer part of the SDK
