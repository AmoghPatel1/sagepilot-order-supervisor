from temporalio import activity

@activity.defn
def say_hello(name: str) -> str:
    return f"Hello, {name}!"