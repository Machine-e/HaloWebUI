import asyncio
from types import SimpleNamespace

from pydantic import BaseModel

from open_webui.routers import functions as functions_router


def test_updating_function_valves_invalidates_model_list_cache(monkeypatch):
    class Valves(BaseModel):
        MODEL_ID: str = ""

    function_module = SimpleNamespace(Valves=Valves)
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(FUNCTIONS={"pipe_a": function_module})
        )
    )
    invalidated = []
    saved_valves = []

    monkeypatch.setattr(
        functions_router.Functions,
        "get_function_by_id",
        lambda function_id: SimpleNamespace(id=function_id, type="pipe"),
    )
    monkeypatch.setattr(
        functions_router.Functions,
        "update_function_valves_by_id",
        lambda function_id, valves: saved_valves.append((function_id, valves)),
    )
    monkeypatch.setattr(
        functions_router,
        "_invalidate_model_list_cache",
        lambda request: invalidated.append(request),
    )

    result = asyncio.run(
        functions_router.update_function_valves_by_id(
            request,
            "pipe_a",
            {"MODEL_ID": "model_id_1", "ignored_none": None},
            user=SimpleNamespace(id="admin"),
        )
    )

    assert result == {"MODEL_ID": "model_id_1"}
    assert saved_valves == [("pipe_a", {"MODEL_ID": "model_id_1"})]
    assert invalidated == [request]
