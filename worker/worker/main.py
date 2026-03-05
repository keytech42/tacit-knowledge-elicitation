import asyncio
import logging
import uuid

from fastapi import FastAPI, HTTPException

from worker.schemas import (
    GenerateQuestionsRequest,
    ReviewAssistRequest,
    ScaffoldOptionsRequest,
    TaskResponse,
    TaskStatusResponse,
)
from worker.tasks.question_gen import run_question_generation
from worker.tasks.answer_scaffold import run_answer_scaffolding
from worker.tasks.review_assist import run_review_assist

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Knowledge Elicitation Worker", version="0.1.0")

# In-memory task tracking
_tasks: dict[str, dict] = {}


def _create_task(coro) -> str:
    task_id = str(uuid.uuid4())
    _tasks[task_id] = {"status": "accepted", "result": None, "error": None}

    async def _wrapper():
        _tasks[task_id]["status"] = "running"
        try:
            result = await coro
            _tasks[task_id]["status"] = "completed"
            _tasks[task_id]["result"] = result
        except Exception as e:
            logger.exception(f"Task {task_id} failed")
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(e)

    asyncio.create_task(_wrapper())
    return task_id


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/tasks/generate-questions", response_model=TaskResponse, status_code=202)
async def trigger_generate_questions(request: GenerateQuestionsRequest):
    task_id = _create_task(run_question_generation(
        topic=request.topic,
        domain=request.domain,
        count=request.count,
        context=request.context,
    ))
    return TaskResponse(task_id=task_id, status="accepted")


@app.post("/tasks/scaffold-options", response_model=TaskResponse, status_code=202)
async def trigger_scaffold_options(request: ScaffoldOptionsRequest):
    task_id = _create_task(run_answer_scaffolding(
        question_id=request.question_id,
        num_options=request.num_options,
    ))
    return TaskResponse(task_id=task_id, status="accepted")


@app.post("/tasks/review-assist", response_model=TaskResponse, status_code=202)
async def trigger_review_assist(request: ReviewAssistRequest):
    task_id = _create_task(run_review_assist(
        answer_id=request.answer_id,
    ))
    return TaskResponse(task_id=task_id, status="accepted")


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(
        task_id=task_id,
        status=task["status"],
        result=task["result"],
        error=task["error"],
    )
