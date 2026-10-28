"""Recipe and meal plan routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile

from ..api import Actor, Files, Hub, Session, require_auth
from ..schemas import (
    CookIn,
    Fulfillment,
    MealPlanIn,
    MealPlanOut,
    MealPlanPatch,
    RecipeImportIn,
    RecipeIn,
    RecipeOut,
    RecipePatch,
    RecipeSuggestion,
)
from ..services import recipes
from ..timeutil import today

router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])


@router.get("/recipes", response_model=list[RecipeOut])
async def list_recipes(session: Session):
    return await recipes.list_recipes(session)


@router.post("/recipes", response_model=RecipeOut)
async def create_recipe(session: Session, hub: Hub, body: RecipeIn):
    return await recipes.create_recipe(session, hub, body)


@router.post("/recipes/import", response_model=RecipeOut)
async def import_recipe(session: Session, hub: Hub, files: Files, body: RecipeImportIn):
    return await recipes.import_url(session, hub, files, body.url)


@router.get("/recipes/suggestions", response_model=list[RecipeSuggestion])
async def suggestions(session: Session, limit: int = 10):
    return await recipes.suggestions(session, limit)


@router.post("/recipes/parse-ingredient")
async def parse_ingredient(body: dict) -> dict:
    return recipes.parse_ingredient(str(body.get("text", "")))


@router.get("/recipes/{recipe_id}", response_model=RecipeOut)
async def get_recipe(session: Session, recipe_id: int):
    return await recipes.get_recipe(session, recipe_id)


@router.patch("/recipes/{recipe_id}", response_model=RecipeOut)
async def update_recipe(session: Session, hub: Hub, recipe_id: int, body: RecipePatch):
    return await recipes.update_recipe(session, hub, recipe_id, body)


@router.delete("/recipes/{recipe_id}", status_code=204)
async def delete_recipe(session: Session, hub: Hub, files: Files, recipe_id: int) -> None:
    await recipes.delete_recipe(session, hub, files, recipe_id)


@router.put("/recipes/{recipe_id}/photo", response_model=RecipeOut)
async def set_photo(session: Session, hub: Hub, files: Files, recipe_id: int, file: UploadFile = File(...)):
    return await recipes.set_photo(session, hub, files, recipe_id, await file.read(), file.filename)


@router.delete("/recipes/{recipe_id}/photo", response_model=RecipeOut)
async def remove_photo(session: Session, hub: Hub, files: Files, recipe_id: int):
    return await recipes.remove_photo(session, hub, files, recipe_id)


@router.get("/recipes/{recipe_id}/fulfillment", response_model=Fulfillment)
async def fulfillment(session: Session, recipe_id: int, servings: int | None = None):
    return await recipes.get_fulfillment(session, recipe_id, servings)


@router.post("/recipes/{recipe_id}/cook")
async def cook(session: Session, hub: Hub, actor: Actor, recipe_id: int, body: CookIn | None = None) -> dict:
    return {"used": await recipes.cook(session, hub, recipe_id, body.servings if body else None, actor)}


@router.post("/recipes/{recipe_id}/shopping")
async def to_shopping_list(session: Session, hub: Hub, recipe_id: int, body: CookIn | None = None) -> dict:
    return {"added": await recipes.recipe_to_list(session, hub, recipe_id, body.servings if body else None)}


@router.get("/mealplan", response_model=list[MealPlanOut])
async def meal_plan(session: Session, start: date | None = None, end: date | None = None):
    week_start, week_end = recipes.week_of(today())
    return await recipes.meal_plan(session, start or week_start, end or week_end)


@router.post("/mealplan", response_model=MealPlanOut)
async def add_meal(session: Session, hub: Hub, body: MealPlanIn):
    return await recipes.add_meal(session, hub, body)


@router.post("/mealplan/shopping")
async def plan_to_list(session: Session, hub: Hub, start: date | None = None, end: date | None = None) -> dict:
    _, week_end = recipes.week_of(today())
    return {"added": await recipes.plan_to_list(session, hub, start or today(), end or week_end)}


@router.patch("/mealplan/{entry_id}", response_model=MealPlanOut)
async def update_meal(session: Session, hub: Hub, entry_id: int, body: MealPlanPatch):
    return await recipes.update_meal(session, hub, entry_id, body)


@router.delete("/mealplan/{entry_id}", status_code=204)
async def delete_meal(session: Session, hub: Hub, entry_id: int) -> None:
    await recipes.delete_meal(session, hub, entry_id)


@router.post("/mealplan/{entry_id}/done", response_model=MealPlanOut)
async def complete_meal(session: Session, hub: Hub, actor: Actor, entry_id: int, cook: bool = True):
    return await recipes.complete_meal(session, hub, entry_id, cook, actor)
