import asyncio
import concurrent.futures
from temporalio.client import Client
from temporalio.worker import Worker

# Import the activity and workflow from our other files
from activities import say_hello
from workflows import SayHello

async def main():
    # Create client connected to server at the given address
    client = await Client.connect("localhost:7233")

    # Run the worker
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as activity_executor:
        worker = Worker(
          client,
          task_queue="my-task-queue",
          workflows=[SayHello],
          activities=[say_hello],
          activity_executor=activity_executor,
        )
        await worker.run()

if __name__ == "__main__":
    asyncio.run(main())