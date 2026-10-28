"""Calendars: chores, best-before dates, tasks, warranty ends and the meal plan."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import StewardConfigEntry
from .entity import StewardEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: StewardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        [ChoresCalendar(entry), DueDatesCalendar(entry), TasksCalendar(entry), WarrantyCalendar(entry), MealPlanCalendar(entry)]
    )


def _all_day(day: date, summary: str, uid: str, description: str | None = None) -> CalendarEvent:
    return CalendarEvent(start=day, end=day + timedelta(days=1), summary=summary, uid=uid, description=description)


class _StewardCalendar(StewardEntity, CalendarEntity):
    def _events(self) -> list[CalendarEvent]:
        raise NotImplementedError

    @property
    def event(self) -> CalendarEvent | None:
        today = dt_util.now().date()
        upcoming = [e for e in self._events() if _end_date(e) > today]
        return min(upcoming, key=_start_date, default=None)

    async def async_get_events(self, hass: HomeAssistant, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
        start, end = start_date.date(), end_date.date()
        return [e for e in self._events() if _start_date(e) <= end and _end_date(e) >= start]


def _start_date(event: CalendarEvent) -> date:
    return event.start if not isinstance(event.start, datetime) else dt_util.as_local(event.start).date()


def _end_date(event: CalendarEvent) -> date:
    return event.end if not isinstance(event.end, datetime) else dt_util.as_local(event.end).date()


class ChoresCalendar(_StewardCalendar):
    _attr_translation_key = "chores"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "calendar_chores")

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        events = []
        for chore in data.chores:
            if not chore["next_due"]:
                continue
            day = dt_util.as_local(dt_util.parse_datetime(chore["next_due"])).date()
            who = data.person_name(chore.get("next_assignee"))
            events.append(_all_day(day, chore["name"], f"chore-{chore['id']}", f"Next: {who}" if who else None))
        return events


class DueDatesCalendar(_StewardCalendar):
    _attr_translation_key = "due_dates"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "calendar_due_dates")

    def _events(self) -> list[CalendarEvent]:
        events = []
        for item in self.coordinator.data.stock:
            for entry in item["entries"]:
                if entry["due_date"]:
                    events.append(
                        _all_day(
                            date.fromisoformat(entry["due_date"]),
                            f"{item['product']['name']} expires",
                            f"due-{entry['id']}",
                            f"{entry['amount']:g} {item['product']['unit']}",
                        )
                    )
        return events


class TasksCalendar(_StewardCalendar):
    _attr_translation_key = "tasks"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "calendar_tasks")

    def _events(self) -> list[CalendarEvent]:
        return [
            _all_day(date.fromisoformat(task["due_date"]), task["name"], f"task-{task['id']}", task.get("notes"))
            for task in self.coordinator.data.tasks
            if task["due_date"] and not task.get("done_at")
        ]


class WarrantyCalendar(_StewardCalendar):
    _attr_translation_key = "warranties"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "calendar_warranties")

    def _events(self) -> list[CalendarEvent]:
        return [
            _all_day(
                date.fromisoformat(item["warranty_until"]),
                f"Warranty ends: {item['name']}",
                f"warranty-{item['id']}",
                " ".join(filter(None, (item.get("brand"), item.get("model")))) or None,
            )
            for item in self.coordinator.data.equipment
            if item.get("warranty_until")
        ]


# Meal times for the calendar; the meal plan itself only knows the slot.
SLOT_TIMES = {"breakfast": (7, 30), "lunch": (12, 30), "dinner": (19, 0), "snack": (16, 0)}


class MealPlanCalendar(_StewardCalendar):
    _attr_translation_key = "meal_plan"

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "calendar_meal_plan")

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        events = []
        for meal in data.meal_plan:
            hour, minute = SLOT_TIMES.get(meal["slot"], (12, 0))
            start = datetime.combine(
                date.fromisoformat(meal["day"]), time(hour, minute), tzinfo=dt_util.get_default_time_zone()
            )
            title = data.recipe_name(meal.get("recipe_id")) or meal.get("note") or meal["slot"]
            events.append(
                CalendarEvent(
                    start=start,
                    end=start + timedelta(hours=1),
                    summary=title,
                    uid=f"meal-{meal['id']}",
                    description=meal["slot"].title() + (" · done" if meal["done"] else ""),
                )
            )
        return events
