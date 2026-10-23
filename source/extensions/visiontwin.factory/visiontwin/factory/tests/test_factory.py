"""In-Kit smoke tests: the panel loads, Build Scene creates the factory, Start spawns products."""

import carb.settings
import omni.kit.app
import omni.kit.test
import omni.kit.ui_test as ui_test
import omni.usd

from visiontwin.factory.core import layout as L

WINDOW = "VisionTwin Factory"
BELT = f"{L.FACTORY_PATH}/Conveyor/Section_0/Belt"  # first (or only) conveyor section


def _use_belt_layout():
    """The box line: one conveyor + fixed top camera (the crown's inspection cell needs the CAD
    machine asset, which the app's settings point to; it is covered by scripts/render_smoke)."""
    carb.settings.get_settings().set("/exts/visiontwin.factory/part", "box")


def _button(text):
    return ui_test.find(f"{WINDOW}//Frame/**/Button[*].text=='{text}'")


async def _wait_until(cond, max_frames=600):
    app = omni.kit.app.get_app()
    for _ in range(max_frames):
        if cond():
            return True
        await app.next_update_async()
    return cond()


class TestDashboard(omni.kit.test.AsyncTestCase):
    async def test_line_setup_controls_exist(self):
        combos = ui_test.find_all(f"{WINDOW}//Frame/**/ComboBox[*]")
        self.assertGreaterEqual(len(combos), 2, "product and view selectors")
        for label in ("Product", "Seed", "Products", "Defect rate", "View"):
            self.assertIsNotNone(ui_test.find(f"{WINDOW}//Frame/**/Label[*].text=='{label}'"), label)

    async def test_set_view_without_viewport_is_safe(self):
        import visiontwin.factory.extension as vt

        vt.get_instance().set_view(1)  # headless test app: no main viewport, must not raise


class TestFactory(omni.kit.test.AsyncTestCase):
    async def test_build_scene_creates_factory_prims(self):
        _use_belt_layout()
        await _button("Build Scene").click()
        ok = await _wait_until(lambda: bool(
            omni.usd.get_context().get_stage()
            and omni.usd.get_context().get_stage().GetPrimAtPath(BELT)))
        self.assertTrue(ok, "conveyor belt prim was not created")
        stage = omni.usd.get_context().get_stage()
        for path in (L.CAMERA_PATH, f"{L.FACTORY_PATH}/InspectionZone", f"{L.FACTORY_PATH}/RejectZone"):
            self.assertTrue(stage.GetPrimAtPath(path).IsValid(), path)

    async def test_start_spawns_products_and_stop_halts(self):
        _use_belt_layout()
        await _button("Build Scene").click()
        await _wait_until(lambda: bool(
            omni.usd.get_context().get_stage()
            and omni.usd.get_context().get_stage().GetPrimAtPath(BELT)))

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
