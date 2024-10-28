import time


def service_b(input_data):
    print(f"Running service_b with input: {input_data}")
    time.sleep(5)  # Simulate some work being done
    print(f"Service_b completed with input: {input_data}")
    return {"foo": input_data}


def string_function(input_data):
    return input_data + "_processed"


def sum_function(a, b):
    return a + b


if __name__ == "__main__":
    import sys

    service_name = sys.argv[1] if len(sys.argv) > 1 else None
    input_data = sys.argv[2] if len(sys.argv) > 2 else None  # noqa: PLR2004

    if service_name == "service_b":
        service_b(input_data)
    else:
        print("No service provided, exiting.")
