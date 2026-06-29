from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import supervisors, runs
from app.services.scheduler import start_scheduler, stop_scheduler
import contextlib

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Start scheduler on app startup
    start_scheduler()
    yield
    # Stop scheduler on app shutdown
    stop_scheduler()

app = FastAPI(title="AI Order Supervisor", lifespan=lifespan)

# Allow Next.js frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(supervisors.router)
app.include_router(runs.router)

@app.get("/health")
def health():
    return {"status": "ok"}