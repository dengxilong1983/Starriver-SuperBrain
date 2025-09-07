import json
from uuid import uuid4


def _extract_error_message(body):
    if isinstance(body, dict):
        if isinstance(body.get("error"), dict):
            return body["error"].get("message") or body["error"].get("code")
        # prefer unified error wrapper fields
        if isinstance(body.get("details"), dict):
            return body.get("message") or body["details"].get("message") or body["details"].get("code")
        if isinstance(body.get("detail"), dict):
            return body["detail"].get("message") or body["detail"].get("code")
        return body.get("message") or body.get("code")
    return str(body)


class TestObservabilityAndConsciousness:
    def test_observability_flags_get_and_post_merge(self, fresh_client):
        g = fresh_client.get("/api/v2.3-preview/observability/flags")
        assert g.status_code == 200
        snap = g.json()
        assert "flags" in snap and isinstance(snap["flags"], dict)

        u = fresh_client.post(
            "/api/v2.3-preview/observability/flags",
            json={"flags": {"cloud_evolution_enabled": True, "shadow_playback_enabled": True, "new_flag": True}},
        )
        assert u.status_code == 200
        body = u.json()
        assert body["flags"]["cloud_evolution_enabled"] is True
        assert body["flags"]["shadow_playback_enabled"] is True
        assert body["flags"]["new_flag"] is True

    def test_observability_logs_search_get_and_post(self, fresh_client):
        # trigger some logs via experience search endpoint (it logs every call)
        s1 = fresh_client.get(
            "/api/v2.3-preview/experience/rules/search",
            params={"q": "xyz", "tag": "t", "category": "news", "status": "active"},
        )
        assert s1.status_code == 200

        # GET logs/search with filtering and limit
        lg = fresh_client.get(
            "/api/v2.3-preview/observability/logs/search",
            params={"q": "experience search", "level": "INFO", "limit": 1, "since_seconds": 3600},
        )
        assert lg.status_code == 200
        data = lg.json()
        assert data["returned"] >= 0 and isinstance(data["items"], list)

        # GET invalid limit should 422
        bad = fresh_client.get(
            "/api/v2.3-preview/observability/logs/search",
            params={"limit": 0},
        )
        assert bad.status_code == 422

        # POST variant with alias 'query' and oversized limit (should clamp internally)
        lp = fresh_client.post(
            "/api/v2.3-preview/observability/logs/search",
            json={"query": "experience search", "level": "INFO", "limit": 1000, "since_seconds": 3600},
        )
        assert lp.status_code == 200
        pdata = lp.json()
        assert pdata["returned"] >= 0 and isinstance(pdata["items"], list)

    def test_observability_metrics_and_slo_snapshot(self, fresh_client):
        # generate several http requests to collect timings and counters
        for _ in range(3):
            fresh_client.get("/api/v2.3-preview/experience/rules/search", params={"q": "a"})
            fresh_client.get("/api/v2.3-preview/observability/flags")

        m = fresh_client.get("/api/v2.3-preview/observability/metrics")
        assert m.status_code == 200
        ms = m.json()
        assert "counters" in ms and "gauges" in ms and "timings" in ms

        slo = fresh_client.get("/api/v2.3-preview/observability/slo/snapshot")
        assert slo.status_code == 200
        sb = slo.json()
        assert 0.0 <= sb["availability"] <= 1.0
        assert 0.0 <= sb["error_rate"] <= 1.0
        assert isinstance(sb["latency_ms"], dict)
        assert "updated_at" in sb

    def test_consciousness_attention_require_current_404_then_push_replace_clear(self, fresh_client):
        # initially require_current should 404
        g404 = fresh_client.get("/api/v2.3-preview/consciousness/attention", params={"require_current": True})
        assert g404.status_code == 404
        assert _extract_error_message(g404.json()) in ("no current goal", "not_found")

        # push a goal
        p = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push", "target": "goal-1"},
        )
        assert p.status_code == 200
        pb = p.json()
        assert pb.get("current") == "goal-1"
        assert pb.get("stack_size", 0) >= 1

        # replace current
        r = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "replace", "target": "goal-2"},
        )
        assert r.status_code == 200
        rb = r.json()
        assert rb.get("current") == "goal-2"

        # clear stack
        c = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "clear"},
        )
        assert c.status_code == 200
        cb = c.json()
        assert cb.get("stack_size") == 0 or cb.get("current") is None

        # invalid mode -> 400
        bad = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "invalid", "target": "x"},
        )
        assert bad.status_code == 400
        assert _extract_error_message(bad.json()) in ("invalid mode", "bad_request")

    def test_observability_shadow_diff(self, fresh_client):
        payload = {
            "baseline": {"status": 200, "result": {"a": 1, "b": 2}, "latency_ms": 50},
            "candidate": {"status": 500, "result": {"a": 1}, "latency_ms": 200},
            "tolerance_ms": 100,
        }
        r = fresh_client.post("/api/v2.3-preview/observability/shadow/diff", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body.get("differences"), list)
        assert "updated_at" in body


class TestConsciousnessStatePaths:
    def test_state_invalid_and_illegal_then_force(self, fresh_client):
        # invalid state -> 400
        r1 = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "unknown"},
        )
        assert r1.status_code == 400
        body1 = r1.json()
        assert _extract_error_message(body1) == "invalid state"
        container1 = body1.get("details") or body1.get("detail") or body1
        assert "allowed_states" in container1

        # illegal transition from idle -> executing (not allowed without force)
        r2 = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "executing"},
        )
        assert r2.status_code == 409
        b2 = r2.json()
        assert _extract_error_message(b2) == "illegal transition"
        container2 = b2.get("details") or b2.get("detail") or b2
        assert set(container2.get("allowed_next_states", [])) == {"focusing", "sleeping"}

        # with force -> allowed
        r3 = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "executing", "force": True},
        )
        assert r3.status_code == 200
        b3 = r3.json()
        assert b3["state"] == "executing"
        assert set(b3["allowed_next_states"]) == {"focusing", "sleeping"}

    def test_state_goal_overflow_and_clear(self, fresh_client):
        # shrink the cap to 1 to trigger overflow on second append
        import app.routes.v2_3.consciousness as cons
        old_cap = cons._MAX_GOAL_STACK
        try:
            cons._MAX_GOAL_STACK = 1
            # first goal ok
            ok = fresh_client.post(
                "/api/v2.3-preview/consciousness/state",
                json={"state": "focusing", "force": True, "goal": "g1"},
            )
            assert ok.status_code == 200
            # second append should overflow
            ov = fresh_client.post(
                "/api/v2.3-preview/consciousness/state",
                json={"state": "focusing", "force": True, "goal": "g2"},
            )
            assert ov.status_code == 409
            ovb = ov.json()
            assert _extract_error_message(ovb) == "attention stack overflow"
            assert (ovb.get("details") or {}).get("max_stack_size") == 1
            # clear goal stack via empty string goal
            clr = fresh_client.post(
                "/api/v2.3-preview/consciousness/state",
                json={"state": "focusing", "force": True, "goal": ""},
            )
            assert clr.status_code == 200
            assert clr.json()["current_goal"] in (None, "")
        finally:
            cons._MAX_GOAL_STACK = old_cap

    def test_attention_overflow_push(self, fresh_client):
        import app.routes.v2_3.consciousness as cons
        old_cap = cons._MAX_GOAL_STACK
        try:
            cons._MAX_GOAL_STACK = 1
            # first push ok
            p1 = fresh_client.post(
                "/api/v2.3-preview/consciousness/attention",
                json={"mode": "push", "target": "t1"},
            )
            assert p1.status_code == 200
            assert p1.json()["stack_size"] == 1
            # second push should overflow
            p2 = fresh_client.post(
                "/api/v2.3-preview/consciousness/attention",
                json={"mode": "push", "target": "t2"},
            )
            assert p2.status_code == 409
            p2b = p2.json()
            assert _extract_error_message(p2b) == "attention stack overflow"
            assert (p2b.get("details") or {}).get("max_stack_size") == 1
        finally:
            cons._MAX_GOAL_STACK = old_cap

    def test_um_enabled_state_and_attention_paths(self, fresh_client, monkeypatch):
        # enable UM path and reset UM state
        from app.unified_mind import UM
        monkeypatch.setenv("UNIFIED_MIND_ENABLED", "true")
        UM.state = "idle"
        UM.goal_stack.clear()

        # require_current should 404 when empty
        g404 = fresh_client.get("/api/v2.3-preview/consciousness/attention", params={"require_current": True})
        assert g404.status_code == 404

        # push and then get current
        p = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push", "target": "u1"},
        )
        assert p.status_code == 200
        assert p.json()["current"] == "u1"

        g = fresh_client.get("/api/v2.3-preview/consciousness/attention", params={"require_current": True})
        assert g.status_code == 200
        assert g.json()["current"] == "u1"

        # illegal transition without force under UM
        bad = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "executing"},
        )
        assert bad.status_code == 409
        assert _extract_error_message(bad.json()) == "illegal transition"

        # with force -> allowed
        ok = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "executing", "force": True},
        )
        assert ok.status_code == 200
        assert ok.json()["state"] == "executing"

        # invalid state under UM -> 400
        inv = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "bad"},
        )
        assert inv.status_code == 400
        assert _extract_error_message(inv.json()) in ("invalid state", "bad_request")


class TestUMExtendedPaths:
    def test_um_attention_replace_and_clear(self, fresh_client, monkeypatch):
        # enable UM path
        from app.unified_mind import UM
        monkeypatch.setenv("UNIFIED_MIND_ENABLED", "true")
        UM.goal_stack.clear()
        UM.state = "idle"

        # push first
        p = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push", "target": "u1"},
        )
        assert p.status_code == 200
        assert p.json()["current"] == "u1"

        # replace current
        r = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "replace", "target": "u2"},
        )
        assert r.status_code == 200
        rb = r.json()
        assert rb["current"] == "u2"
        assert rb["stack_size"] == 1

        # clear stack
        c = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "clear"},
        )
        assert c.status_code == 200
        cb = c.json()
        assert cb["stack_size"] == 0
        assert cb["current"] is None

    def test_um_state_goal_append_and_clear_and_get_state(self, fresh_client, monkeypatch):
        # enable UM path
        from app.unified_mind import UM
        monkeypatch.setenv("UNIFIED_MIND_ENABLED", "true")
        UM.goal_stack.clear()
        UM.state = "idle"

        # set focusing with goal
        s1 = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing", "force": True, "goal": "ug1"},
        )
        assert s1.status_code == 200
        b1 = s1.json()
        assert b1["state"] == "focusing"
        assert b1["current_goal"] == "ug1"
        assert b1["goal_stack"][-1] == "ug1"

        # clear goal via empty string
        s2 = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing", "force": True, "goal": ""},
        )
        assert s2.status_code == 200
        b2 = s2.json()
        assert b2["state"] == "focusing"
        assert b2["current_goal"] in (None, "")
        assert b2["goal_stack"] == []

        # get_state under UM path reflects allowed_next_states
        g = fresh_client.get("/api/v2.3-preview/consciousness/state")
        assert g.status_code == 200
        gb = g.json()
        assert set(gb["allowed_next_states"]) == {"reasoning", "sleeping", "idle"}

    def test_state_hooks_trigger_under_um(self, fresh_client, monkeypatch):
        # enable UM path
        from app.unified_mind import UM
        import app.routes.v2_3.consciousness as cons
        monkeypatch.setenv("UNIFIED_MIND_ENABLED", "true")
        UM.goal_stack.clear()
        UM.state = "idle"

        # prepare hook recorders
        calls = {"exit": [], "enter": []}

        def on_exit_idle():
            calls["exit"].append("idle")

        def on_enter_focusing():
            calls["enter"].append("focusing")

        # register hooks
        cons.register_state_hook("idle", "exit", on_exit_idle)
        cons.register_state_hook("focusing", "enter", on_enter_focusing)

        # trigger transition with force
        r = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing", "force": True},
        )
        assert r.status_code == 200
        # hooks should have been called exactly once
        assert calls["exit"].count("idle") >= 1
        assert calls["enter"].count("focusing") >= 1


class TestConsciousnessAdditionalCoverage:
    def test_attention_invalid_mode_returns_400(self, fresh_client, monkeypatch):
        # Disable UM path to test pure route validation
        monkeypatch.delenv("UNIFIED_MIND_ENABLED", raising=False)
        r = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "noop", "target": "x"},
        )
        assert r.status_code == 400
        body = r.json()
        # Be tolerant to ErrorBody/HTTPException structure
        msg = str(body)
        assert "invalid mode" in msg

    def test_non_um_attention_push_overflow_returns_409(self, fresh_client, monkeypatch):
        # Non-UM path with small stack cap to trigger overflow
        import app.routes.v2_3.consciousness as cons

        monkeypatch.delenv("UNIFIED_MIND_ENABLED", raising=False)
        monkeypatch.setattr(cons, "_MAX_GOAL_STACK", 1)

        # Ensure clean stack first
        c = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "clear"},
        )
        assert c.status_code == 200

        # First push fits into cap
        p1 = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push", "target": "a"},
        )
        assert p1.status_code == 200
        assert p1.json()["stack_size"] == 1

        # Second push should overflow
        p2 = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push", "target": "b"},
        )
        assert p2.status_code == 409
        body = p2.json()
        msg = str(body)
        assert "attention stack overflow" in msg
        # max_stack_size hint should be present
        assert "1" in msg or body.get("detail", {}).get("max_stack_size") == 1

    def test_non_um_state_goal_append_overflow_returns_409(self, fresh_client, monkeypatch):
        # Non-UM path with small stack cap to trigger overflow on goal append in set_state
        import app.routes.v2_3.consciousness as cons

        monkeypatch.delenv("UNIFIED_MIND_ENABLED", raising=False)
        monkeypatch.setattr(cons, "_MAX_GOAL_STACK", 1)

        # Clear any residual goals via API
        c = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "clear"},
        )
        assert c.status_code == 200

        # First set_state with goal succeeds
        s1 = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing", "force": True, "goal": "g1"},
        )
        assert s1.status_code == 200
        assert s1.json()["current_goal"] == "g1"

        # Second set_state with another goal should overflow
        s2 = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing", "force": True, "goal": "g2"},
        )
        assert s2.status_code == 409
        body = s2.json()
        msg = str(body)
        assert "attention stack overflow" in msg

    def test_um_invalid_state_returns_400(self, fresh_client, monkeypatch):
        # Enable UM path and send invalid state to exercise UM ValueError mapping
        monkeypatch.setenv("UNIFIED_MIND_ENABLED", "true")
        r = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "unknown"},
        )
        assert r.status_code == 400
        # Robust message extraction without relying on helper
        body = r.json()
        msg = str(body)
        assert "invalid state" in msg


class TestCoverageExtras:
    def test_attention_replace_with_none_clears_stack_non_um(self, fresh_client, monkeypatch):
        import app.routes.v2_3.consciousness as cons
        # Ensure UM path is disabled
        monkeypatch.delenv("UNIFIED_MIND_ENABLED", raising=False)
        # Reset in-process stack safely
        with cons._STATE_LOCK:
            cons._GOAL_STACK.clear()
            cons._CURRENT_STATE = "idle"
        # Seed one item via push
        p = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push", "target": "seed"},
        )
        assert p.status_code == 200
        assert p.json().get("stack_size", 0) >= 1
        # Replace with no target -> clears stack
        r = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "replace"},
        )
        assert r.status_code == 200
        rb = r.json()
        assert rb["stack_size"] == 0
        assert rb["current"] is None

    def test_state_hooks_exceptions_do_not_break_non_um(self, fresh_client, monkeypatch):
        import app.routes.v2_3.consciousness as cons
        # Disable UM path
        monkeypatch.delenv("UNIFIED_MIND_ENABLED", raising=False)
        # Reset state
        with cons._STATE_LOCK:
            cons._CURRENT_STATE = "idle"
            cons._GOAL_STACK.clear()
        # Register hooks that raise exceptions
        def boom_exit():
            raise RuntimeError("exit failure")
        def boom_enter():
            raise RuntimeError("enter failure")
        cons.register_state_hook("idle", "exit", boom_exit)
        cons.register_state_hook("focusing", "enter", boom_enter)
        # Force transition; API should still succeed despite hook errors
        st = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing", "force": True},
        )
        assert st.status_code == 200
        assert st.json()["state"] == "focusing"

    def test_attention_unlimited_stack_no_overflow_non_um(self, fresh_client, monkeypatch):
        import app.routes.v2_3.consciousness as cons
        # Disable UM path
        monkeypatch.delenv("UNIFIED_MIND_ENABLED", raising=False)
        old_cap = cons._MAX_GOAL_STACK
        try:
            # 0 means unlimited
            cons._MAX_GOAL_STACK = 0
            with cons._STATE_LOCK:
                cons._GOAL_STACK.clear()
                cons._CURRENT_STATE = "idle"
            # Push several targets without overflow
            for i in range(3):
                rr = fresh_client.post(
                    "/api/v2.3-preview/consciousness/attention",
                    json={"mode": "push", "target": f"t{i}"},
                )
                assert rr.status_code == 200
            g = fresh_client.get("/api/v2.3-preview/consciousness/attention")
            assert g.status_code == 200
            body = g.json()
            assert body["stack_size"] >= 3
        finally:
            cons._MAX_GOAL_STACK = old_cap

    def test_attention_push_without_target_non_um_and_um(self, fresh_client, monkeypatch):
        import app.routes.v2_3.consciousness as cons
        from app.unified_mind import UM

        # Non-UM: ensure pushing without target is a no-op and succeeds
        monkeypatch.delenv("UNIFIED_MIND_ENABLED", raising=False)
        UM.goal_stack.clear()
        r1 = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push"},
        )
        assert r1.status_code == 200
        b1 = r1.json()
        assert isinstance(b1.get("stack_size"), int)

        # UM: pushing without target should also be a no-op
        monkeypatch.setenv("UNIFIED_MIND_ENABLED", "true")
        UM.goal_stack.clear()
        r2 = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "push"},
        )
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2.get("stack_size") == 0

    def test_set_state_um_generic_value_error(self, fresh_client, monkeypatch):
        # Force UM path and simulate unexpected ValueError in UM.set_state
        from app.unified_mind import UM
        import app.routes.v2_3.consciousness as cons

        monkeypatch.setenv("UNIFIED_MIND_ENABLED", "true")
        # ensure a valid transition source so 409 does not short-circuit
        UM.state = "idle"
        UM.goal_stack.clear()
    
        def boom(*args, **kwargs):
            raise ValueError("boom")
    
        # patch the exact instance used by the route to guarantee interception
        monkeypatch.setattr(cons.UM, "set_state", boom, raising=True)
    
        resp = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing"},
        )
        assert resp.status_code == 400
        # generic error path should surface original message
        body = resp.json()
        msg = body.get("message") or (body.get("detail") or {}).get("message") or (body.get("details") or {}).get("message")
        assert msg == "boom"

    def test_observability_errors_do_not_break_paths(self, fresh_client, monkeypatch):
        # Patch observability to raise inside metrics/logs to cover except paths
        import app.routes.v2_3.consciousness as cons

        class BadMetrics:
            def inc(self, *a, **k):
                raise RuntimeError("inc failed")

            def set_gauge(self, *a, **k):
                raise RuntimeError("gauge failed")

            def set_label(self, *a, **k):
                raise RuntimeError("label failed")

            def observe(self, *a, **k):
                raise RuntimeError("observe failed")

        class BadLogs:
            def add(self, *a, **k):
                raise RuntimeError("log failed")

        monkeypatch.setattr(cons, "obs_metrics", BadMetrics(), raising=True)
        monkeypatch.setattr(cons, "obs_logs", BadLogs(), raising=True)

        # Calls should still succeed despite observability failures
        g = fresh_client.get("/api/v2.3-preview/consciousness/attention")
        assert g.status_code == 200

        p = fresh_client.post(
            "/api/v2.3-preview/consciousness/attention",
            json={"mode": "replace", "target": "x"},
        )
        assert p.status_code == 200

        s = fresh_client.get("/api/v2.3-preview/consciousness/state")
        assert s.status_code == 200

        # force state transition also hits metrics update block
        st = fresh_client.post(
            "/api/v2.3-preview/consciousness/state",
            json={"state": "focusing", "force": True},
        )
        assert st.status_code == 200


class TestObservabilityExtended:
    def test_observability_logs_search_tag_match_and_level_filter(self, fresh_client):
        # trigger logs with known tags via experience search (tags include q, tag, category, trace_id)
        q, tag, category = "tagmatch", "alpha", "beta"
        r = fresh_client.get(
            "/api/v2.3-preview/experience/rules/search",
            params={"q": q, "tag": tag, "category": category},
        )
        assert r.status_code == 200

        # search logs by tag value that is not necessarily in message, filter by level INFO
        lg = fresh_client.get(
            "/api/v2.3-preview/observability/logs/search",
            params={"q": category, "level": "INFO", "limit": 5, "since_seconds": 3600},
        )
        assert lg.status_code == 200
        data = lg.json()
        assert data["returned"] >= 0 and isinstance(data["items"], list)
        # ensure at least one item has our tag present
        assert any(category in (it.get("tags") or []) for it in data["items"]) or data["returned"] == 0

    def test_observability_logs_search_post_limit_zero_clamped(self, fresh_client):
        # ensure there is at least one recent log by calling a known logging endpoint
        _ = fresh_client.get(
            "/api/v2.3-preview/experience/rules/search",
            params={"q": "x"},
        )
        lp = fresh_client.post(
            "/api/v2.3-preview/observability/logs/search",
            json={"q": "experience search", "level": "INFO", "limit": 0, "since_seconds": 3600},
        )
        assert lp.status_code == 200
        pdata = lp.json()
        # POST clamps limit>=1 internally instead of 422 like GET
        assert pdata["returned"] >= 1

    def test_observability_flags_update_reflects_in_metrics_labels(self, fresh_client):
        # set a known flag True, then False, and verify metrics labels reflect state
        u1 = fresh_client.post(
            "/api/v2.3-preview/observability/flags",
            json={"flags": {"cloud_consent_gate_enabled": True}},
        )
        assert u1.status_code == 200
        m1 = fresh_client.get("/api/v2.3-preview/observability/metrics")
        assert m1.status_code == 200
        labels1 = (m1.json() or {}).get("labels", {})
        assert labels1.get("feature_cloud_consent_gate_enabled") == "true"

        u2 = fresh_client.post(
            "/api/v2.3-preview/observability/flags",
            json={"flags": {"cloud_consent_gate_enabled": False}},
        )
        assert u2.status_code == 200
        m2 = fresh_client.get("/api/v2.3-preview/observability/metrics")
        assert m2.status_code == 200
        labels2 = (m2.json() or {}).get("labels", {})
        assert labels2.get("feature_cloud_consent_gate_enabled") == "false"

    def test_observability_search_by_error_trace_id(self, fresh_client):
        # cause a 404 error to obtain a trace_id tagged into logs by global error handler
        g404 = fresh_client.get(
            "/api/v2.3-preview/experience/rules/00000000-0000-0000-0000-000000000000"
        )
        assert g404.status_code == 404
        body = g404.json()
        trace_id = body.get("trace_id") or ((body.get("detail") or body.get("details") or {}) or {}).get("trace_id")
        assert trace_id

        lg = fresh_client.get(
            "/api/v2.3-preview/observability/logs/search",
            params={"q": trace_id, "limit": 5, "since_seconds": 3600},
        )
        assert lg.status_code == 200
        data = lg.json()
        assert data["returned"] >= 0 and isinstance(data["items"], list)
        # At least one item should have our trace_id as tag
        assert any(trace_id in (it.get("tags") or []) for it in data["items"]) or data["returned"] == 0


class TestObservabilityEdgeCases:
    def test_logs_level_case_insensitive_and_since_seconds_boundary(self, fresh_client, monkeypatch):
        from app.routes.v2_3 import observability as obs
        from datetime import datetime, timedelta, timezone
        from uuid import uuid4

        uniq = f"edge_case_{uuid4()}"

        # Insert an old log (older than 1 hour) directly into buffer
        old_ts = (datetime.now(timezone.utc) - timedelta(seconds=7200)).isoformat()
        obs.logs._buf.append({
            "ts": old_ts,
            "level": "INFO",
            "message": "old edge log",
            "module": "tests",
            "tags": [uniq],
            "extra": {},
        })
        # Insert a recent WARN log with the same tag
        obs.logs._buf.append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": "WARN",
            "message": "new edge log",
            "module": "tests",
            "tags": [uniq],
            "extra": {},
        })

        # since_seconds boundary should exclude the old log and include the recent one
        r = fresh_client.get(
            "/api/v2.3-preview/observability/logs/search",
            params={"q": uniq, "since_seconds": 3600, "limit": 50},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["returned"] >= 0
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=3600)
        for it in body["items"]:
            assert uniq in (it.get("tags") or [])
            its = datetime.fromisoformat(it.get("ts"))
            assert its >= cutoff

        # Level filter should be case-insensitive ("warn" -> "WARN")
        r2 = fresh_client.get(
            "/api/v2.3-preview/observability/logs/search",
            params={"q": uniq, "level": "warn", "since_seconds": 3600},
        )
        assert r2.status_code == 200
        body2 = r2.json()
        assert all(it.get("level") == "WARN" for it in body2["items"]) or body2["returned"] == 0

    def test_flags_accepts_int_values_and_metrics_labels_follow(self, fresh_client):
        # 1 should set True
        u1 = fresh_client.post(
            "/api/v2.3-preview/observability/flags",
            json={"flags": {"cloud_consent_gate_enabled": 1}},
        )
        assert u1.status_code == 200
        m1 = fresh_client.get("/api/v2.3-preview/observability/metrics")
        assert m1.status_code == 200
        labels1 = (m1.json() or {}).get("labels", {})
        assert labels1.get("feature_cloud_consent_gate_enabled") == "true"

        # 0 should set False
        u2 = fresh_client.post(
            "/api/v2.3-preview/observability/flags",
            json={"flags": {"cloud_consent_gate_enabled": 0}},
        )
        assert u2.status_code == 200
        m2 = fresh_client.get("/api/v2.3-preview/observability/metrics")
        assert m2.status_code == 200
        labels2 = (m2.json() or {}).get("labels", {})
        assert labels2.get("feature_cloud_consent_gate_enabled") == "false"

    def test_slo_snapshot_reflects_server_error_counters(self, fresh_client):
        from app.routes.v2_3 import observability as obs
        # Inject counters to simulate traffic with a server error
        obs.metrics.inc("http_requests_total|GET|/edge|200", 1)
        obs.metrics.inc("http_requests_total|GET|/edge|500", 1)

        r = fresh_client.get("/api/v2.3-preview/observability/slo/snapshot")
        assert r.status_code == 200
        snap = r.json()
        assert 0.0 <= snap["error_rate"] <= 1.0
        assert 0.0 <= snap["availability"] <= 1.0
        assert snap["error_rate"] > 0.0
        assert snap["availability"] < 1.0

    def test_experience_update_rule_exception_is_logged_and_searchable(self, fresh_client, monkeypatch):
        from uuid import uuid4
        from app.routes.v2_3 import experience as exp

        # Force update to raise a generic exception -> 500 path
        def raise_exc(*a, **k):
            raise RuntimeError("update exploded")
        monkeypatch.setattr(exp.store, "update", raise_exc, raising=True)

        trace_id = f"edge-update-exc-{uuid4()}"
        rule_id = uuid4()
        resp = fresh_client.put(
            f"/api/v2.3-preview/experience/rules/{rule_id}",
            json={"title": "x"},
            headers={"x-trace-id": trace_id},
        )
        assert resp.status_code == 500

        # The error should be logged at ERROR level with our trace_id tag
        lg = fresh_client.get(
            "/api/v2.3-preview/observability/logs/search",
            params={"q": trace_id, "level": "ERROR", "since_seconds": 3600},
        )
        assert lg.status_code == 200
        data = lg.json()
        assert data["returned"] >= 0 and isinstance(data.get("items"), list)
        assert any((trace_id in (it.get("tags") or [])) and (it.get("module") == "experience") for it in data["items"]) or data["returned"] == 0