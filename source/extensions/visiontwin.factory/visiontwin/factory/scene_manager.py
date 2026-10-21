"""Builds the static factory scene (floor, conveyor, zones, camera, light) with plain USD."""

from pxr import Gf, Usd, UsdGeom, UsdLux

from .core import layout as L


def _box(stage: Usd.Stage, path: str, center, size, color) -> UsdGeom.Cube:
    """Axis-aligned box from a unit cube scaled to `size` (x, y, z)."""
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    xf = UsdGeom.XformCommonAPI(cube)
    xf.SetTranslate(Gf.Vec3d(*center))
    xf.SetScale(Gf.Vec3f(*size))
    return cube


def configure_stage(stage: Usd.Stage) -> None:
    """Z-up, meters. All layout constants assume this."""
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, L.ROOT_PATH)
    stage.SetDefaultPrim(world.GetPrim())


def build_factory_scene(stage: Usd.Stage) -> None:
    """Create (or recreate) the factory prims under FACTORY_PATH."""
    configure_stage(stage)
    if stage.GetPrimAtPath(L.FACTORY_PATH):
        stage.RemovePrim(L.FACTORY_PATH)
    UsdGeom.Xform.Define(stage, L.FACTORY_PATH)
    UsdGeom.Xform.Define(stage, L.PRODUCTS_PATH)

    f = L.FACTORY_PATH
    _box(stage, f"{f}/Floor", (0.0, 0.0, -0.01), (12.0, 8.0, 0.02), (0.35, 0.35, 0.38))

    belt_z = L.CONVEYOR_TOP_Z - L.CONVEYOR_THICKNESS / 2.0
    _box(stage, f"{f}/Conveyor/Belt", (0.0, 0.0, belt_z),
         (L.CONVEYOR_LENGTH, L.CONVEYOR_WIDTH, L.CONVEYOR_THICKNESS), (0.12, 0.12, 0.12))
    leg_h = L.CONVEYOR_TOP_Z - L.CONVEYOR_THICKNESS
    for i, x in enumerate((-L.CONVEYOR_LENGTH / 2 + 0.2, 0.0, L.CONVEYOR_LENGTH / 2 - 0.2)):
        for j, y in enumerate((-L.CONVEYOR_WIDTH / 2 + 0.05, L.CONVEYOR_WIDTH / 2 - 0.05)):
            _box(stage, f"{f}/Conveyor/Leg_{i}_{j}", (x, y, leg_h / 2.0),
                 (0.08, 0.08, leg_h), (0.5, 0.5, 0.55))

    # Posts beside the belt showing where inspection and rejection happen. They stand
    # outside the belt lane so the inspection camera's ROI never contains them.
    post_h = 0.25
    for name, x, color in (("InspectionZone", L.INSPECTION_X, (0.1, 0.6, 1.0)),
                           ("RejectZone", L.REJECT_X, (1.0, 0.4, 0.1))):
        UsdGeom.Xform.Define(stage, f"{f}/{name}")
        for side, y in (("L", L.MARKER_OFFSET_Y), ("R", -L.MARKER_OFFSET_Y)):
            _box(stage, f"{f}/{name}/Post_{side}", (x, y, L.CONVEYOR_TOP_Z + post_h / 2.0 - 0.05),
                 (0.03, 0.03, post_h), color)
    # Reject bin beside the belt (-Y side).
    _box(stage, f"{f}/RejectBin", (L.REJECT_X, -L.CONVEYOR_WIDTH / 2 - 0.4, 0.2),
         (0.6, 0.5, 0.4), (0.6, 0.15, 0.1))

    _define_inspection_camera(stage)
    _define_overview_camera(stage)
    _define_light(stage)


def _define_overview_camera(stage: Usd.Stage) -> None:
    """Fixed camera for the main viewport and demo recordings (deterministic framing)."""
    cam = UsdGeom.Camera.Define(stage, L.OVERVIEW_CAMERA_PATH)
    eye = Gf.Vec3d(*L.OVERVIEW_CAMERA_EYE)
    target = Gf.Vec3d(*L.OVERVIEW_CAMERA_TARGET)
    # SetLookAt builds a view matrix (world->camera); the prim needs camera->world.
    cam_to_world = Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0, 0, 1)).GetInverse()
    cam.AddTransformOp().Set(cam_to_world)
    cam.CreateFocalLengthAttr(24.0)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.05, 1000.0))


def _define_inspection_camera(stage: Usd.Stage) -> None:
    # A USD camera looks down its local -Z axis, so no rotation = looking straight down.
    cam = UsdGeom.Camera.Define(stage, L.CAMERA_PATH)
    UsdGeom.XformCommonAPI(cam).SetTranslate(
        Gf.Vec3d(L.INSPECTION_X, 0.0, L.CONVEYOR_TOP_Z + L.CAMERA_HEIGHT_ABOVE_BELT))
    cam.CreateFocalLengthAttr(L.CAMERA_FOCAL_MM)
    cam.CreateHorizontalApertureAttr(L.CAMERA_H_APERTURE_MM)
    cam.CreateVerticalApertureAttr(L.CAMERA_V_APERTURE_MM)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))


# Product colors. A "color" defect is rendered with a different hue; the vision
# inspector must detect it from pixels, never from these constants.
GOOD_COLOR = (0.15, 0.45, 0.85)
DEFECT_COLORS = {"color": (0.85, 0.25, 0.15)}


def product_path(product_id: int) -> str:
    return f"{L.PRODUCTS_PATH}/P_{product_id:04d}"


def spawn_product_prim(stage: Usd.Stage, product_id: int, defect_kind, x: float) -> None:
    color = DEFECT_COLORS.get(defect_kind, GOOD_COLOR)
    s = L.PRODUCT_SIZE
    _box(stage, product_path(product_id), (x, 0.0, L.CONVEYOR_TOP_Z + s / 2.0), (s, s, s), color)


def move_product_prim(stage: Usd.Stage, product_id: int, x: float, y: float = 0.0, z: float = None) -> None:
    prim = stage.GetPrimAtPath(product_path(product_id))
    if not prim:
        return
    if z is None:
        z = L.CONVEYOR_TOP_Z + L.PRODUCT_SIZE / 2.0
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(x, y, z))


def move_product_to_reject_bin(stage: Usd.Stage, product_id: int) -> None:
    move_product_prim(stage, product_id, L.REJECT_X, -L.CONVEYOR_WIDTH / 2 - 0.4, 0.4 + L.PRODUCT_SIZE / 2.0)


def remove_product_prim(stage: Usd.Stage, product_id: int) -> None:
    stage.RemovePrim(product_path(product_id))


def clear_products(stage: Usd.Stage) -> None:
    if stage.GetPrimAtPath(L.PRODUCTS_PATH):
        stage.RemovePrim(L.PRODUCTS_PATH)
    UsdGeom.Xform.Define(stage, L.PRODUCTS_PATH)


def _define_light(stage: Usd.Stage) -> None:
    # Kit's "Default" rig is distant 2^10 + dome 2^9; at that level the top-down inspection
    # frames were washed out (product saturation below threshold), so use 1/4 of it.
    light = UsdLux.DistantLight.Define(stage, f"{L.FACTORY_PATH}/KeyLight")
    light.CreateIntensityAttr(250.0)
    light.CreateAngleAttr(0.53)
    UsdGeom.XformCommonAPI(light).SetRotate(Gf.Vec3f(-30.0, 20.0, 0.0))
    dome = UsdLux.DomeLight.Define(stage, f"{L.FACTORY_PATH}/Ambient")
    dome.CreateIntensityAttr(125.0)
