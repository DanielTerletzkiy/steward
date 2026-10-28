"""To-do lists: shopping lists, tasks, and each person's due chores."""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.todo import TodoItem, TodoItemStatus, TodoListEntity, TodoListEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import StewardConfigEntry
from .entity import StewardEntity

CHORES_EVERYONE = "everyone"


async def async_setup_entry(
    hass: HomeAssistant, entry: StewardConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    data = entry.runtime_data.coordinator.data
    entities: list[TodoListEntity] = [ShoppingListTodo(entry, lst["id"], lst["name"]) for lst in data.shopping_lists]
    entities.append(TasksTodo(entry))
    entities.extend(ChoresTodo(entry, person["id"], person["name"]) for person in data.people)
    entities.append(ChoresTodo(entry, CHORES_EVERYONE, None))
    async_add_entities(entities)


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class ShoppingListTodo(StewardEntity, TodoListEntity):
    _attr_icon = "mdi:cart"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, entry: StewardConfigEntry, list_id: int, name: str) -> None:
        super().__init__(entry, f"shopping_{list_id}")
        self._list_id = list_id
        self._attr_name = name

    @property
    def todo_items(self) -> list[TodoItem]:
        items = self.coordinator.data.shopping_items.get(self._list_id, [])
        return [
            TodoItem(
                uid=str(item["id"]),
                summary=item["text"] if item["amount"] == 1 else f"{item['text']} ({item['amount']:g})",
                description=item.get("note"),
                status=TodoItemStatus.COMPLETED if item["done"] else TodoItemStatus.NEEDS_ACTION,
            )
            for item in items
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self.client.post(
            f"api/shopping-lists/{self._list_id}/items", {"text": item.summary, "note": item.description}
        )
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        current = next(i for i in self.coordinator.data.shopping_items[self._list_id] if str(i["id"]) == item.uid)
        patch = {"done": item.status == TodoItemStatus.COMPLETED, "note": item.description}
        shown = current["text"] if current["amount"] == 1 else f"{current['text']} ({current['amount']:g})"
        if item.summary != shown:
            patch["text"] = item.summary
        await self.client.patch(f"api/shopping-items/{item.uid}", patch)
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self.client.delete(f"api/shopping-items/{uid}")
        await self.coordinator.async_request_refresh()


class TasksTodo(StewardEntity, TodoListEntity):
    _attr_translation_key = "tasks"
    _attr_icon = "mdi:clipboard-check-outline"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
        | TodoListEntityFeature.SET_DUE_DATE_ON_ITEM
        | TodoListEntityFeature.SET_DESCRIPTION_ON_ITEM
    )

    def __init__(self, entry: StewardConfigEntry) -> None:
        super().__init__(entry, "tasks")

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=str(task["id"]),
                summary=task["name"],
                description=task.get("notes"),
                due=_parse_date(task.get("due_date")),
                status=TodoItemStatus.COMPLETED if task.get("done_at") else TodoItemStatus.NEEDS_ACTION,
            )
            for task in self.coordinator.data.tasks
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        await self.client.post("api/tasks", _task_payload(item))
        await self.coordinator.async_request_refresh()

    async def async_update_todo_item(self, item: TodoItem) -> None:
        payload = {**_task_payload(item), "done": item.status == TodoItemStatus.COMPLETED}
        await self.client.patch(f"api/tasks/{item.uid}", payload)
        await self.coordinator.async_request_refresh()

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        for uid in uids:
            await self.client.delete(f"api/tasks/{uid}")
        await self.coordinator.async_request_refresh()


def _task_payload(item: TodoItem) -> dict:
    due = item.due.date() if isinstance(item.due, datetime) else item.due
    return {"name": item.summary, "notes": item.description, "due_date": due.isoformat() if due else None}


class ChoresTodo(StewardEntity, TodoListEntity):
    """Chores due now for one person (or for everyone when unassigned). Ticking one off tracks it."""

    _attr_icon = "mdi:broom"
    _attr_supported_features = TodoListEntityFeature.UPDATE_TODO_ITEM

    def __init__(self, entry: StewardConfigEntry, person_id: str, person_name: str | None) -> None:
        super().__init__(entry, f"chores_{person_id}")
        self._person_id = person_id
        if person_name is None:
            self._attr_translation_key = "chores_everyone"
        else:
            self._attr_translation_key = "chores_person"
            self._attr_translation_placeholders = {"person": person_name}

    def _mine(self) -> list[dict]:
        due = [c for c in self.coordinator.data.chores if c["status"] in ("overdue", "due_today")]
        if self._person_id == CHORES_EVERYONE:
            return [c for c in due if not c.get("next_assignee")]
        return [c for c in due if c.get("next_assignee") == self._person_id]

    @property
    def todo_items(self) -> list[TodoItem]:
        return [
            TodoItem(
                uid=str(chore["id"]),
                summary=chore["name"],
                due=dt_util.as_local(dt_util.parse_datetime(chore["next_due"])).date() if chore["next_due"] else None,
                status=TodoItemStatus.NEEDS_ACTION,
            )
            for chore in self._mine()
        ]

    async def async_update_todo_item(self, item: TodoItem) -> None:
        if item.status == TodoItemStatus.COMPLETED:
            person = None if self._person_id == CHORES_EVERYONE else self._person_id
            await self.client.post(f"api/chores/{item.uid}/execute", {"person_id": person})
            await self.coordinator.async_request_refresh()
