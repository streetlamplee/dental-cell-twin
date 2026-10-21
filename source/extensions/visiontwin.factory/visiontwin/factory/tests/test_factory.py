"""In-Kit smoke tests: the panel loads, Build Scene creates the factory, Start spawns products."""

import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.usd

from visiontwin.factory.core import layout as L

WINDOW = "VisionTwin Factory"


def _button(text):
    return ui_test.find(f"{WINDOW}//Frame/**/Button[*].text=='{text}'")


async def _wait_until(cond, max_frames=600):
    app = omni.kit.app.get_app()
    for _ in range(max_frames):
        if cond():
            return True
        await app.next_update_async()
    return cond()


class TestFactory(omni.kit.test.AsyncTestCase):
    async def test_build_scene_creates_factory_prims(self):
        await _button("Build Scene").click()
        ok = await _wait_until(lambda: bool(
            omni.usd.get_context().get_stage()
            and omni.usd.get_context().get_stage().GetPrimAtPath(f"{L.FACTORY_PATH}/Conveyor/Belt")))
        self.assertTrue(ok, "conveyor belt prim was not created")
        stage = omni.usd.get_context().get_stage()
        for path in (L.CAMERA_PATH, f"{L.FACTORY_PATH}/InspectionZone", f"{L.FACTORY_PATH}/RejectZone"):
            self.assertTrue(stage.GetPrimAtPath(path).IsValid(), path)

    async def test_start_spawns_products_and_stop_halts(self):
        await _button("Build Scene").click()
        await _wait_until(lambda: bool(
            omni.usd.get_context().get_stage()
            and omni.usd.get_context().get_stage().GetPrimAtPath(f"{L.FACTORY_PATH}/Conveyor/Belt")))

        await _button("Start").click()

        def product_count():
            products = omni.usd.get_context().get_stage().GetPrimAtPath(L.PRODUCTS_PATH)
            return len(products.GetChildren()) if products else 0

        ok = await _wait_until(lambda: product_count() >= 1)
        self.assertTrue(ok, "no product prim spawned after Start")

        await _button("Stop").click()
        await omni.kit.app.get_app().next_update_async()
        n = product_count()
        for _ in range(30):
            await omni.kit.app.get_app().next_update_async()
        self.assertEqual(product_count(), n, "products changed after Stop")

        await _button("Reset").click()
        await omni.kit.app.get_app().next_update_async()
        self.assertEqual(product_count(), 0)
