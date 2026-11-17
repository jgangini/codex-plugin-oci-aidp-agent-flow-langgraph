import asyncio
import importlib.util
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from aidp_agent_flow.model import OCIModel
from aidp_agent_flow.model_boundary import final_text, final_text_scope, run_blocking
from aidp_agent_flow.project import FlowError, initialize
try:
    from .support import TemporaryDirectory
except ImportError:
    from support import TemporaryDirectory


def response(reason="stop", *, tools=None):
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason,
        message=SimpleNamespace(role="ASSISTANT", tool_calls=tools,
            content=[SimpleNamespace(type="TEXT", text='{"answer":"plausible"}')]))])


class NativeParityTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_native_and_local_adapters_reject_same_terminal_failures(self):
        base = Path(__file__).resolve().parents[3] / "validation-work"
        base.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=base) as temporary:
            root = Path(temporary) / "project"
            initialize(root, "Adapter parity", sync=False)
            namespace = {"__name__": "synthetic_native", "__file__": str(root / "agent/core/native.py")}
            code = (root / "agent/core/native.py").read_text().replace(
                "from .model_boundary import final_text, run_blocking", "")
            namespace.update(final_text=final_text, run_blocking=run_blocking)
            exec(compile(code, str(root / "agent/core/native.py"), "exec"), namespace)
            settings = {"region": "us-chicago-1", "model_id": "synthetic",
                        "compartment_id": "synthetic", "max_tokens": 20}
            for reason, tools, accepted in (("stop", None, True), ("length", None, False),
                    ("content_filter", None, False), (None, None, False), ("stop", [object()], False)):
                with self.subTest(reason=reason, tools=bool(tools)):
                    client = Mock()
                    client.chat.return_value = SimpleNamespace(data=SimpleNamespace(chat_response=response(reason, tools=tools)))
                    native = namespace["NativeModel"](client, settings)
                    local = OCIModel("never-read", "DEFAULT", settings)
                    local.client = client
                    if accepted:
                        self.assertEqual(await native.complete("s", "q"), await local.complete("s", "q"))
                    else:
                        with self.assertRaises(ValueError):
                            await native.complete("s", "q")
                        with self.assertRaises(FlowError):
                            await local.complete("s", "q")
            canonical = Path(__file__).resolve().parents[1] / "aidp_agent_flow/model_boundary.py"
            self.assertEqual((root / "agent/core/model_boundary.py").read_bytes(), canonical.read_bytes())

    async def test_generated_boundary_imports_without_plugin_on_remote_python_path(self):
        source = Path(__file__).resolve().parents[1] / "aidp_agent_flow/model_boundary.py"
        spec = importlib.util.spec_from_file_location("standalone_boundary", source)
        standalone = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(standalone)
        self.assertEqual(standalone.final_text(response()), '{"answer":"plausible"}')

    async def test_recovered_truncation_cannot_pass_scope_and_does_not_poison_concurrent_or_next_calls(self):
        async def graph_child(reason):
            try:
                final_text(response(reason))
            except ValueError:
                return "plausible fallback"
            return "complete"

        async def invocation(reason):
            with final_text_scope():
                return await asyncio.create_task(graph_child(reason))

        bad, good = await asyncio.gather(invocation("length"), invocation("stop"), return_exceptions=True)
        self.assertIsInstance(bad, ValueError)
        self.assertEqual(good, "complete")
        self.assertEqual(await invocation("stop"), "complete")


class CancellationTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_cancellation_drains_sdk_worker_before_owner_cleanup(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        cleanup = []

        def blocking():
            started.set()
            release.wait(3)
            finished.set()
            return "late reply"

        async def owner():
            try:
                await run_blocking(blocking)
            finally:
                cleanup.append(finished.is_set())

        task = asyncio.create_task(owner())
        try:
            while not started.is_set():
                await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.sleep(0.01)
            self.assertFalse(task.done())
            self.assertEqual(cleanup, [])
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(cleanup, [True])

    async def test_worker_exception_remains_exception_and_cancel_remains_cancel(self):
        def fail():
            raise RuntimeError("synthetic")

        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            await run_blocking(fail)

    async def test_local_sdk_client_is_closed_explicitly(self):
        model = OCIModel("never-read", "DEFAULT", {"region": "us-chicago-1",
                         "model_id": "synthetic", "compartment_id": "synthetic"})
        model.client = Mock()
        model.close()
        model.client.base_client.session.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
