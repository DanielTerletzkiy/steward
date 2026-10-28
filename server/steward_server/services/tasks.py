"""Tasks: simple to-dos with categories, due dates and assignees."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Task
from ..schemas import TaskIn, TaskPatch
from ..timeutil import utcnow
from . import NotFound


async def list_tasks(session: AsyncSession, include_done: bool = True) -> list[Task]:
    query = select(Task).order_by(Task.done_at.is_not(None), Task.due_date.is_(None), Task.due_date, Task.id)
    if not include_done:
        query = query.where(Task.done_at.is_(None))
    return list((await session.scalars(query)).all())


async def create_task(session: AsyncSession, hub: EventHub, data: TaskIn) -> Task:
    task = Task(**data.model_dump())
    session.add(task)
    await session.commit()
    hub.publish("tasks")
    return task


async def update_task(session: AsyncSession, hub: EventHub, task_id: int, patch: TaskPatch) -> Task:
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFound(f"Task {task_id} not found")
    values = patch.model_dump(exclude_unset=True)
    if "done" in values:
        done = values.pop("done")
        task.done_at = (task.done_at or utcnow()) if done else None
    for key, value in values.items():
        setattr(task, key, value)
    await session.commit()
    hub.publish("tasks")
    return task


async def delete_task(session: AsyncSession, hub: EventHub, task_id: int) -> None:
    task = await session.get(Task, task_id)
    if task is None:
        raise NotFound(f"Task {task_id} not found")
    await session.delete(task)
    await session.commit()
    hub.publish("tasks")
