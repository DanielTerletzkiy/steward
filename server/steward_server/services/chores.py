"""Chores: schedules, assignment and tracking."""

from __future__ import annotations

import calendar
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Chore, ChoreLog, Person
from ..schemas import ChoreIn, ChoreOut, ChorePatch
from ..timeutil import LOCAL_TZ, as_utc, today, utcnow
from . import Invalid, NotFound
from .stock import consume

SCHEDULES = ("manual", "daily", "weekly", "monthly", "dynamic")
ASSIGNMENTS = ("none", "fixed", "least_done", "rotation")
DUE_SOON_DAYS = 2


def _local_midnight(day) -> datetime:
    # Stored as UTC: SQLite keeps no time zone, values read back are treated as UTC.
    return datetime.combine(day, time.min, tzinfo=LOCAL_TZ).astimezone(UTC)


def next_due_after(chore: Chore, done_at: datetime) -> datetime | None:
    """When the chore is due next, given it was last done at `done_at`."""
    done_day = done_at.astimezone(LOCAL_TZ).date()
    interval = max(chore.interval, 1)
    match chore.schedule:
        case "manual":
            return None
        case "dynamic":
            return done_at + timedelta(days=interval)
        case "daily":
            return _local_midnight(done_day + timedelta(days=interval))
        case "weekly":
            weekdays = set(chore.weekdays) or {done_day.weekday()}
            offset = next(d for d in range(1, 8) if (done_day + timedelta(days=d)).weekday() in weekdays)
            # Every `interval` weeks: the next matching weekday, pushed out by the extra weeks.
            return _local_midnight(done_day + timedelta(days=offset, weeks=interval - 1))
        case "monthly":
            month_index = done_day.month - 1 + interval
            year, month = done_day.year + month_index // 12, month_index % 12 + 1
            day = min(done_day.day, calendar.monthrange(year, month)[1])
            return _local_midnight(done_day.replace(year=year, month=month, day=day))
    raise Invalid(f"Unknown schedule {chore.schedule}")


def _status(next_due: datetime | None) -> str:
    if next_due is None:
        return "manual"
    due_day = as_utc(next_due).astimezone(LOCAL_TZ).date()
    if as_utc(next_due) < utcnow() and due_day < today():
        return "overdue"
    if due_day <= today():
        return "due_today"
    if due_day <= today() + timedelta(days=DUE_SOON_DAYS):
        return "due_soon"
    return "scheduled"


async def _done_counts(session: AsyncSession, chore_id: int) -> dict[str, int]:
    rows = await session.execute(
        select(ChoreLog.done_by, func.count())
        .where(ChoreLog.chore_id == chore_id, ChoreLog.skipped.is_(False))
        .group_by(ChoreLog.done_by)
    )
    return {person: count for person, count in rows.all() if person}


async def _pick_assignee(session: AsyncSession, chore: Chore, last_by: str | None) -> str | None:
    people = (await session.scalars(select(Person).where(Person.active.is_(True)).order_by(Person.name))).all()
    active = [p.id for p in people]
    # No explicit assignees means "everyone in the household".
    assignees = [a for a in chore.assignees if a in active] if chore.assignees else active
    if not assignees or chore.assignment == "none":
        return None
    if chore.assignment == "fixed":
        return assignees[0]
    if chore.assignment == "rotation":
        current = last_by if last_by in assignees else chore.next_assignee
        if current not in assignees:
            return assignees[0]
        return assignees[(assignees.index(current) + 1) % len(assignees)]
    # least_done: whoever has done it least often; ties go by list order.
    counts = await _done_counts(session, chore.id)
    return min(assignees, key=lambda person: (counts.get(person, 0), assignees.index(person)))


async def to_out(session: AsyncSession, chore: Chore) -> ChoreOut:
    last = await session.scalar(
        select(ChoreLog)
        .where(ChoreLog.chore_id == chore.id, ChoreLog.skipped.is_(False))
        .order_by(ChoreLog.done_at.desc())
        .limit(1)
    )
    next_due = as_utc(chore.next_due) if chore.next_due else None
    return ChoreOut(
        id=chore.id,
        name=chore.name,
        description=chore.description,
        icon=chore.icon,
        schedule=chore.schedule,
        interval=chore.interval,
        weekdays=chore.weekdays,
        assignment=chore.assignment,
        assignees=chore.assignees,
        next_assignee=chore.next_assignee,
        next_due=next_due,
        status=_status(next_due),
        last_done=as_utc(last.done_at) if last else None,
        last_done_by=last.done_by if last else None,
        points=chore.points,
    )


async def list_chores(session: AsyncSession) -> list[ChoreOut]:
    chores = (await session.scalars(select(Chore))).all()
    result = [await to_out(session, chore) for chore in chores]
    far_future = datetime.max.replace(tzinfo=LOCAL_TZ)
    return sorted(result, key=lambda c: (c.next_due or far_future, c.name))


def _check(schedule: str, assignment: str) -> None:
    if schedule not in SCHEDULES:
        raise Invalid(f"schedule must be one of {SCHEDULES}")
    if assignment not in ASSIGNMENTS:
        raise Invalid(f"assignment must be one of {ASSIGNMENTS}")


async def create_chore(session: AsyncSession, hub: EventHub, data: ChoreIn) -> ChoreOut:
    _check(data.schedule, data.assignment)
    chore = Chore(**data.model_dump(exclude={"first_due"}))
    if data.first_due is not None:
        chore.next_due = data.first_due
    elif chore.schedule != "manual":
        chore.next_due = _local_midnight(today())
    session.add(chore)
    await session.flush()
    chore.next_assignee = await _pick_assignee(session, chore, None)
    await session.commit()
    hub.publish("chores")
    return await to_out(session, chore)


async def update_chore(session: AsyncSession, hub: EventHub, chore_id: int, patch: ChorePatch) -> ChoreOut:
    chore = await session.get(Chore, chore_id)
    if chore is None:
        raise NotFound(f"Chore {chore_id} not found")
    changes = patch.model_dump(exclude_unset=True)
    if changes.get("name") is not None and not changes["name"].strip():
        raise Invalid("Name must not be empty")
    _check(changes.get("schedule") or chore.schedule, changes.get("assignment") or chore.assignment)
    was_manual = chore.schedule == "manual"
    who = (chore.assignment, list(chore.assignees))
    for key, value in changes.items():
        if value is not None or key in ("description", "icon"):
            setattr(chore, key, value)
    chore.interval = max(chore.interval, 1)
    # The due date stays unless it is given; a chore that turns manual has none, one that stops being manual is due today.
    if chore.schedule == "manual":
        chore.next_due = None
    elif patch.next_due is None and (was_manual or chore.next_due is None):
        chore.next_due = _local_midnight(today())
    if (chore.assignment, chore.assignees) != who:
        # Rotation keeps whoever is next if they are still part of it; everything else is picked afresh.
        keeps = chore.assignment == "rotation" and chore.next_assignee and (
            not chore.assignees or chore.next_assignee in chore.assignees
        )
        if not keeps:
            chore.next_assignee = await _pick_assignee(session, chore, None)
    await session.commit()
    hub.publish("chores")
    return await to_out(session, chore)


async def delete_chore(session: AsyncSession, hub: EventHub, chore_id: int) -> None:
    chore = await session.get(Chore, chore_id)
    if chore is None:
        raise NotFound(f"Chore {chore_id} not found")
    await session.delete(chore)
    await session.commit()
    hub.publish("chores")


async def execute(
    session: AsyncSession,
    hub: EventHub,
    chore_id: int,
    *,
    person_id: str | None = None,
    skipped: bool = False,
    source: str = "ui",
    at: datetime | None = None,
) -> ChoreOut:
    chore = await session.get(Chore, chore_id)
    if chore is None:
        raise NotFound(f"Chore {chore_id} not found")
    done_at = at or utcnow()
    done_by = person_id or chore.next_assignee
    session.add(ChoreLog(chore_id=chore.id, done_at=done_at, done_by=done_by, skipped=skipped, source=source))
    chore.next_due = next_due_after(chore, done_at)
    await session.flush()
    chore.next_assignee = await _pick_assignee(session, chore, done_by)
    if chore.consume_product_id and not skipped:
        try:
            await consume(session, hub, chore.consume_product_id, chore.consume_amount, source="chore", commit=False)
        except Invalid:
            pass  # Nothing left to consume; the chore still counts.
    await session.commit()
    hub.publish("chores", chore_id=chore.id)
    if chore.consume_product_id:
        hub.publish("stock")
    return await to_out(session, chore)


async def make_due(session: AsyncSession, hub: EventHub, chore_id: int, at: datetime | None = None) -> None:
    """Due now, e.g. "empty the dishwasher" once the dishwasher has finished. Caller commits."""
    chore = await session.get(Chore, chore_id)
    if chore is None:
        return
    now = at or utcnow()
    if chore.next_due is None or as_utc(chore.next_due) > now:
        chore.next_due = now
    hub.publish("chores", chore_id=chore.id)


async def refresh_assignees(session: AsyncSession) -> None:
    """Recompute who is next for every chore, e.g. after people were added or removed. Caller commits."""
    for chore in (await session.scalars(select(Chore))).all():
        last = await session.scalar(
            select(ChoreLog.done_by).where(ChoreLog.chore_id == chore.id).order_by(ChoreLog.done_at.desc()).limit(1)
        )
        chore.next_assignee = await _pick_assignee(session, chore, last)


async def history(session: AsyncSession, chore_id: int | None = None, limit: int = 100) -> list[ChoreLog]:
    query = select(ChoreLog).order_by(ChoreLog.done_at.desc()).limit(limit)
    if chore_id is not None:
        query = query.where(ChoreLog.chore_id == chore_id)
    return list((await session.scalars(query)).all())
