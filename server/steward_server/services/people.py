"""People, mirrored from Home Assistant `person` entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..events import EventHub
from ..models import Person
from ..schemas import PersonIn
from .chores import refresh_assignees


async def list_people(session: AsyncSession, include_inactive: bool = False) -> list[Person]:
    query = select(Person).order_by(Person.name)
    if not include_inactive:
        query = query.where(Person.active.is_(True))
    return list((await session.scalars(query)).all())


async def sync(session: AsyncSession, hub: EventHub, people: list[PersonIn]) -> list[Person]:
    """Replace the set of people with HA's. Removed people are deactivated, keeping their history."""
    known = {p.id: p for p in (await session.scalars(select(Person))).all()}
    seen = set()
    for data in people:
        seen.add(data.id)
        person = known.get(data.id)
        if person is None:
            person = Person(id=data.id)
            session.add(person)
        person.name = data.name
        person.user_id = data.user_id
        person.picture = data.picture
        person.state = data.state
        person.active = True
    for person_id, person in known.items():
        if person_id not in seen:
            person.active = False
    await session.flush()
    await refresh_assignees(session)
    await session.commit()
    hub.publish("people")
    hub.publish("chores")
    return await list_people(session)


async def person_for_user(session: AsyncSession, user_id: str | None) -> Person | None:
    """The person linked to an HA user (from the ingress headers)."""
    if not user_id:
        return None
    return await session.scalar(select(Person).where(Person.user_id == user_id))
