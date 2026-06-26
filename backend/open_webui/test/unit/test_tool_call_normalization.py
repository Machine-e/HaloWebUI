import json


def _merge_fragment(existing: str, incoming: str) -> str:
    if not isinstance(existing, str):
        existing = str(existing or "")
    if not isinstance(incoming, str):
        incoming = str(incoming or "")

    if not incoming:
        return existing
    if not existing:
        return incoming

    if incoming == existing or incoming in existing:
        return existing

    if existing in incoming:
        repeat_count = len(incoming) // len(existing) if existing else 0
        if repeat_count >= 2 and existing * repeat_count == incoming:
            return existing
        return incoming

    if existing.startswith(incoming) or existing.endswith(incoming):
        return existing

    max_overlap = min(len(existing), len(incoming))
    for overlap in range(max_overlap, 0, -1):
        if existing.endswith(incoming[:overlap]):
            return existing + incoming[overlap:]

    return existing + incoming


def _aggregate_stream_tool_calls(
    delta_tool_calls: list[dict],
) -> tuple[list[dict], list[dict]]:
    response_tool_calls = []
    lookup = {}
    repairs = []
    recovered = set()

    for pos, delta_tool_call in enumerate(delta_tool_calls or []):
        if not isinstance(delta_tool_call, dict):
            continue

        incoming_index = delta_tool_call.get("index")
        incoming_id = delta_tool_call.get("id")

        keys = []
        if incoming_index is not None:
            keys.append(("index", str(incoming_index)))
        if incoming_id:
            keys.append(("id", str(incoming_id)))
        if not keys:
            keys.append(("pos", str(pos)))

        idx = None
        for key in keys:
            if key in lookup:
                idx = lookup[key]
                break

        if idx is None:
            tc = dict(delta_tool_call)
            tc["function"] = dict(delta_tool_call.get("function", {}) or {})
            tc["function"].setdefault("name", "")
            tc["function"].setdefault("arguments", "")

            if tc.get("index") is None:
                tc["index"] = len(response_tool_calls)
                marker = f"id:{incoming_id}" if incoming_id else f"pos:{pos}"
                if marker not in recovered:
                    recovered.add(marker)
                    repairs.append(
                        {
                            "action": "recover_missing_index",
                            "from": {"id": incoming_id or "", "index": "(missing)"},
                            "to": {"index": tc["index"]},
                        }
                    )

            response_tool_calls.append(tc)
            idx = len(response_tool_calls) - 1
        else:
            tc = response_tool_calls[idx]
            tc.setdefault("function", {})
            tc["function"].setdefault("name", "")
            tc["function"].setdefault("arguments", "")

            if incoming_id and not tc.get("id"):
                tc["id"] = incoming_id

            if incoming_index is not None and tc.get("index") is None:
                tc["index"] = incoming_index

            delta_name = (delta_tool_call.get("function", {}) or {}).get("name")
            delta_arguments = (delta_tool_call.get("function", {}) or {}).get(
                "arguments"
            )
            if delta_name:
                tc["function"]["name"] = _merge_fragment(
                    tc["function"].get("name", ""), delta_name
                )
            if delta_arguments:
                tc["function"]["arguments"] = _merge_fragment(
                    tc["function"].get("arguments", ""), delta_arguments
                )

        tc = response_tool_calls[idx]
        if tc.get("index") is not None:
            lookup[("index", str(tc.get("index")))] = idx
        if tc.get("id"):
            lookup[("id", str(tc.get("id")))] = idx
        for key in keys:
            lookup[key] = idx

    return response_tool_calls, repairs


def _parse_args(arg_str: str) -> dict:
    try:
        out = json.loads(arg_str)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _map_aliases(args_dict: dict, allowed: set[str]) -> tuple[dict, list[dict]]:
    mapped = {}
    repairs = []
    for key, value in args_dict.items():
        if key in allowed:
            mapped[key] = value
            continue
        if key.endswith("s") and key[:-1] in allowed:
            target = key[:-1]
            mapped[target] = (
                value[0] if isinstance(value, list) and len(value) == 1 else value
            )
            repairs.append({"action": "param_alias_mapping", "from": key, "to": target})
            continue
        plural = f"{key}s"
        if plural in allowed:
            mapped[plural] = value if isinstance(value, list) else [value]
            repairs.append({"action": "param_alias_mapping", "from": key, "to": plural})
    return mapped, repairs


def _infer_empty_name(args_dict: dict, rules: dict) -> str | None:
    arg_keys = set(args_dict.keys())
    candidates = []
    for tool_name, rule in rules.items():
        allowed = set(rule.get("allowed", []))
        required = set(rule.get("required", []))
        if required and not required.issubset(arg_keys):
            continue
        if arg_keys - allowed:
            continue
        if len(arg_keys & allowed) <= 0:
            continue
        candidates.append(
            (len(required), len(arg_keys & allowed), -len(allowed), tool_name)
        )

    if not candidates:
        return None
    candidates.sort(reverse=True)
    if len(candidates) > 1 and candidates[0][:3] == candidates[1][:3]:
        return None
    return candidates[0][3]


def _normalize_calls(
    calls: list[dict], rules: dict
) -> tuple[list[dict], list[dict], list[dict]]:
    repaired = []
    invalid = []
    normalized = []

    filtered = []
    for tc in calls:
        fn = tc.get("function", {}) or {}
        name = (fn.get("name") or "").strip()
        args = _parse_args(fn.get("arguments", "") or "")
        if not name and not args:
            repaired.append({"action": "drop_placeholder"})
            continue
        filtered.append(tc)

    idx = 0
    compact = []
    while idx < len(filtered):
        tc = filtered[idx]
        fn = tc.get("function", {}) or {}
        name = (fn.get("name") or "").strip()
        args = _parse_args(fn.get("arguments", "") or "")
        if name and not args:
            look = idx + 1
            merged = False
            while look < len(filtered):
                next_tc = filtered[look]
                next_fn = next_tc.get("function", {}) or {}
                next_name = (next_fn.get("name") or "").strip()
                next_args = _parse_args(next_fn.get("arguments", "") or "")
                if next_name:
                    break
                if next_args:
                    new_tc = dict(tc)
                    new_fn = dict(fn)
                    new_fn["arguments"] = json.dumps(next_args, ensure_ascii=False)
                    new_tc["function"] = new_fn
                    compact.append(new_tc)
                    repaired.append({"action": "merge_split_call", "to": [name]})
                    idx = look + 1
                    merged = True
                    break
                look += 1
            if merged:
                continue

        compact.append(tc)
        idx += 1

    for tc in compact:
        fn = tc.get("function", {}) or {}
        name = (fn.get("name") or "").strip()
        args = _parse_args(fn.get("arguments", "") or "")

        if not name:
            inferred = _infer_empty_name(args, rules)
            if inferred:
                name = inferred
                repaired.append({"action": "infer_empty_name", "to": [name]})

        if not name:
            invalid.append({"name": "(empty)", "arg_keys": sorted(list(args.keys()))})
            continue

        if len(name) % 2 == 0:
            half = len(name) // 2
            if name[:half] == name[half:] and name[:half] in rules:
                repaired.append({"action": "dedupe_repeated_name", "to": [name[:half]]})
                name = name[:half]

        if name not in rules:
            invalid.append({"name": name, "arg_keys": sorted(list(args.keys()))})
            continue

        allowed = set(rules[name].get("allowed", []))
        required = set(rules[name].get("required", []))

        mapped_args, alias_repairs = _map_aliases(args, allowed)
        repaired.extend(alias_repairs)
        mapped_args = {k: v for k, v in mapped_args.items() if k in allowed}
        if required and not required.issubset(set(mapped_args.keys())):
            invalid.append({"name": name, "arg_keys": sorted(list(args.keys()))})
            continue

        new_tc = dict(tc)
        new_fn = dict(fn)
        new_fn["name"] = name
        new_fn["arguments"] = json.dumps(mapped_args or {}, ensure_ascii=False)
        new_tc["function"] = new_fn
        normalized.append(new_tc)

    return normalized, repaired, invalid


def test_stream_aggregation_recovers_missing_index_and_merges_by_id():
    chunks = [
        {
            "id": "fc_1",
            "function": {"name": "search_", "arguments": '{"query":"NV'},
        },
        {
            "id": "fc_1",
            "function": {"name": "web", "arguments": 'DA","k":5}'},
        },
    ]
    calls, repairs = _aggregate_stream_tool_calls(chunks)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "search_web"
    assert _parse_args(calls[0]["function"]["arguments"]) == {
        "query": "NVDA",
        "k": 5,
    }
    assert any(r.get("action") == "recover_missing_index" for r in repairs)


def test_normalize_empty_name_with_query_k_infers_search_web():
    rules = {
        "search_web": {
            "allowed": {"query", "k"},
            "required": {"query"},
        },
        "search_notes": {
            "allowed": {"query", "count"},
            "required": {"query"},
        },
    }
    calls = [
        {
            "id": "fc_2",
            "function": {
                "name": "",
                "arguments": '{"query":"英伟达 股价 今日 NVDA 今天","k":5}',
            },
        }
    ]
    normalized, repaired, invalid = _normalize_calls(calls, rules)
    assert not invalid
    assert normalized[0]["function"]["name"] == "search_web"
    assert any(r.get("action") == "infer_empty_name" for r in repaired)


def test_normalize_dedupes_repeated_tool_name():
    rules = {
        "search_web": {
            "allowed": {"query", "k"},
            "required": {"query"},
        }
    }
    calls = [
        {
            "id": "fc_3",
            "function": {
                "name": "search_websearch_web",
                "arguments": '{"query":"NVDA"}',
            },
        }
    ]
    normalized, repaired, invalid = _normalize_calls(calls, rules)
    assert not invalid
    assert normalized[0]["function"]["name"] == "search_web"
    assert any(r.get("action") == "dedupe_repeated_name" for r in repaired)


def test_normalize_merges_split_call_name_and_args():
    rules = {
        "search_web": {
            "allowed": {"query", "k"},
            "required": {"query"},
        }
    }
    calls = [
        {"id": "fc_4", "function": {"name": "search_web", "arguments": "{}"}},
        {
            "id": "fc_4a",
            "function": {"name": "", "arguments": '{"query":"NVDA","k":5}'},
        },
    ]
    normalized, repaired, invalid = _normalize_calls(calls, rules)
    assert not invalid
    assert len(normalized) == 1
    assert normalized[0]["function"]["name"] == "search_web"
    assert _parse_args(normalized[0]["function"]["arguments"]) == {
        "query": "NVDA",
        "k": 5,
    }
    assert any(r.get("action") == "merge_split_call" for r in repaired)


def test_param_alias_mapping_queries_to_query():
    rules = {
        "search_web": {
            "allowed": {"query", "k"},
            "required": {"query"},
        }
    }
    calls = [
        {
            "id": "fc_5",
            "function": {
                "name": "search_web",
                "arguments": '{"queries":["NVDA"],"k":5}',
            },
        }
    ]
    normalized, repaired, invalid = _normalize_calls(calls, rules)
    assert not invalid
    args = _parse_args(normalized[0]["function"]["arguments"])
    assert args["query"] == "NVDA"
    assert any(r.get("action") == "param_alias_mapping" for r in repaired)


def test_invalid_for_ambiguous_or_unknown_tool_keeps_arg_keys():
    rules = {
        "search_notes": {
            "allowed": {"query", "count"},
            "required": {"query"},
        },
        "search_chats": {
            "allowed": {"query", "count"},
            "required": {"query"},
        },
    }
    calls = [
        {
            "id": "fc_6",
            "function": {
                "name": "",
                "arguments": '{"query":"hello","count":5}',
            },
        }
    ]
    normalized, repaired, invalid = _normalize_calls(calls, rules)
    assert not normalized
    assert invalid
    assert invalid[0]["name"] == "(empty)"
    assert invalid[0]["arg_keys"] == ["count", "query"]
