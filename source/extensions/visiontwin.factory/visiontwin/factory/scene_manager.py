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


BELT, CELL = "belt", "cell"


def build_factory_scene(stage: Usd.Stage, camera_height: float = L.CAMERA_HEIGHT_ABOVE_BELT,
                        camera_focal_mm: float = L.CAMERA_FOCAL_MM, light_factor: float = 1.0,
                        layout: str = BELT) -> None:
    """Create (or recreate) the factory prims under FACTORY_PATH.

    layout "belt": one conveyor, fixed top-down inspection camera over the inspection line
    (height/focal length per product). layout "cell": two conveyor sections with a gap at
    CELL_X for the inspection cell (machine + spindle camera, added by InspectionCell)."""
    configure_stage(stage)
    if stage.GetPrimAtPath(L.FACTORY_PATH):
        stage.RemovePrim(L.FACTORY_PATH)
    UsdGeom.Xform.Define(stage, L.FACTORY_PATH)
    UsdGeom.Xform.Define(stage, L.PRODUCTS_PATH)

    f = L.FACTORY_PATH
    _box(stage, f"{f}/Floor", (0.0, 0.0, -0.01), (12.0, 8.0, 0.02), (0.35, 0.35, 0.38))

    start, end = -L.CONVEYOR_LENGTH / 2.0, L.CONVEYOR_LENGTH / 2.0
    sections = ([(start, end)] if layout == BELT else
                [(start, L.CELL_X - L.CELL_GAP_HALF), (L.CELL_X + L.CELL_GAP_HALF, end)])
    for k, (x0, x1) in enumerate(sections):
        _belt_section(stage, f"{f}/Conveyor/Section_{k}", x0, x1)

    # Posts beside the belt showing where inspection and rejection happen. They stand
    # outside the belt lane so the inspection camera's ROI never contains them.
    post_h = 0.25
    zones = [("RejectZone", L.REJECT_X, (1.0, 0.4, 0.1))]
    if layout == BELT:
        zones.insert(0, ("InspectionZone", L.INSPECTION_X, (0.1, 0.6, 1.0)))
    for name, x, color in zones:
        UsdGeom.Xform.Define(stage, f"{f}/{name}")
        for side, y in (("L", L.MARKER_OFFSET_Y), ("R", -L.MARKER_OFFSET_Y)):
            _box(stage, f"{f}/{name}/Post_{side}", (x, y, L.CONVEYOR_TOP_Z + post_h / 2.0 - 0.05),
                 (0.03, 0.03, post_h), color)
    # Pusher on the +Y side of the reject line (retracted), sweeps rejects to the -Y bin.
    _box(stage, f"{f}/Pusher", (L.REJECT_X, L.CONVEYOR_WIDTH / 2 + 0.12, L.CONVEYOR_TOP_Z + 0.09),
         (0.12, 0.04, 0.16), (0.85, 0.75, 0.2))
    # Reject bin beside the belt (-Y side).
    _box(stage, f"{f}/RejectBin", (L.REJECT_X, -L.CONVEYOR_WIDTH / 2 - 0.4, 0.2),
         (0.6, 0.5, 0.4), (0.6, 0.15, 0.1))

    if layout == BELT:
        _define_inspection_camera(stage, camera_height, camera_focal_mm)
    else:
        _define_cell_overview_camera(stage)
    _define_overview_camera(stage)
    _define_light(stage, light_factor)


def _belt_section(stage: Usd.Stage, path: str, x0: float, x1: float) -> None:
    belt_z = L.CONVEYOR_TOP_Z - L.CONVEYOR_THICKNESS / 2.0
    _box(stage, f"{path}/Belt", ((x0 + x1) / 2.0, 0.0, belt_z),
         (x1 - x0, L.CONVEYOR_WIDTH, L.CONVEYOR_THICKNESS), (0.12, 0.12, 0.12))
    leg_h = L.CONVEYOR_TOP_Z - L.CONVEYOR_THICKNESS
    xs = (x0 + 0.2, (x0 + x1) / 2.0, x1 - 0.2) if x1 - x0 > 1.0 else (x0 + 0.1, x1 - 0.1)
    for i, x in enumerate(xs):
        for j, y in enumerate((-L.CONVEYOR_WIDTH / 2 + 0.05, L.CONVEYOR_WIDTH / 2 - 0.05)):
            _box(stage, f"{path}/Leg_{i}_{j}", (x, y, leg_h / 2.0), (0.08, 0.08, leg_h), (0.5, 0.5, 0.55))


def _define_cell_overview_camera(stage: Usd.Stage) -> None:
    """Close-up of the inspection cell: end of section 1, the machine, start of section 2."""
    cam = UsdGeom.Camera.Define(stage, L.CELL_OVERVIEW_CAMERA_PATH)
    eye, target = Gf.Vec3d(*L.CELL_OVERVIEW_EYE), Gf.Vec3d(*L.CELL_OVERVIEW_TARGET)
    cam.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0, 0, 1)).GetInverse())
    cam.CreateFocalLengthAttr(24.0)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))


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


def _define_inspection_camera(stage: Usd.Stage, height: float, focal_mm: float) -> None:
    # A USD camera looks down its local -Z axis, so no rotation = looking straight down.
    cam = UsdGeom.Camera.Define(stage, L.CAMERA_PATH)
    UsdGeom.XformCommonAPI(cam).SetTranslate(Gf.Vec3d(L.INSPECTION_X, 0.0, L.CONVEYOR_TOP_Z + height))
    cam.CreateFocalLengthAttr(focal_mm)
    cam.CreateHorizontalApertureAttr(L.CAMERA_H_APERTURE_MM)
    cam.CreateVerticalApertureAttr(L.CAMERA_V_APERTURE_MM)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))


# Product colors. A "color" defect is rendered with a different hue; the vision
# inspector must detect it from pixels, never from these constants.
GOOD_COLOR = (0.15, 0.45, 0.85)
DEFECT_COLORS = {"color": (0.85, 0.25, 0.15)}


def product_path(product_id: int) -> str:
    return f"{L.PRODUCTS_PATH}/P_{product_id:04d}"


# Height of a product's origin above the belt surface: the procedural box is centred,
# CAD part variants have their origin at the bottom (make_part_variants.py).
BOX_REST_DZ = L.PRODUCT_SIZE / 2.0
PART_REST_DZ = 0.0


def spawn_product_prim(stage: Usd.Stage, product_id: int, defect_kind, x: float,
                       variant_usd: str = None, raw_usd: str = None) -> None:
    """Box (variant_usd None) or a CAD part: P_xxxx (position) / Pose (rotation, follows the
    platter while in the inspection cell) / Part (final shape) and, for processed parts, Raw (shape before
    processing; Part stays hidden until show_final_shape)."""
    if variant_usd is None:
        color = DEFECT_COLORS.get(defect_kind, GOOD_COLOR)
        s = L.PRODUCT_SIZE
        _box(stage, product_path(product_id), (x, 0.0, L.CONVEYOR_TOP_Z + BOX_REST_DZ), (s, s, s), color)
        return
    # The variant's /Part carries its own normalising xform ops (centre, rotate, scale), so it is
    # referenced on a CHILD prim: putting the reference on the product prim itself let our
    # translate replace the variant's centring translate (part sank 1.7 cm into the belt).
    path = product_path(product_id)
    xf = UsdGeom.Xform.Define(stage, path)
    pose = UsdGeom.Xform.Define(stage, f"{path}/Pose")
    pose.AddTransformOp().Set(Gf.Matrix4d(1.0))
    final = UsdGeom.Xform.Define(stage, f"{path}/Pose/Part")
    final.GetPrim().GetReferences().AddReference(variant_usd)
    if raw_usd:
        UsdGeom.Xform.Define(stage, f"{path}/Pose/Raw").GetPrim().GetReferences().AddReference(raw_usd)
        final.MakeInvisible()
    UsdGeom.XformCommonAPI(xf).SetTranslate(Gf.Vec3d(x, 0.0, L.CONVEYOR_TOP_Z + PART_REST_DZ))


def show_final_shape(stage: Usd.Stage, product_id: int) -> None:
    """Processed part: hide the raw shape (blank) and show the final one (crown)."""
    path = product_path(product_id)
    raw, final = stage.GetPrimAtPath(f"{path}/Pose/Raw"), stage.GetPrimAtPath(f"{path}/Pose/Part")
    if raw:
        UsdGeom.Imageable(raw).MakeInvisible()
    if final:
        UsdGeom.Imageable(final).MakeVisible()


def set_product_pose(stage: Usd.Stage, product_id: int, world) -> None:
    """Place a CAD part with a full 4x4 world transform (numpy, metres): translation on the
    product prim, rotation on its Pose child (used while it rides the cell's platter)."""
    path = product_path(product_id)
    prim, pose = stage.GetPrimAtPath(path), stage.GetPrimAtPath(f"{path}/Pose")
    if not prim or not pose:
        return
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*(float(v) for v in world[:3, 3])))
    rot = Gf.Matrix4d(1.0)
    rot.SetRotateOnly(Gf.Matrix3d(*(float(v) for v in world[:3, :3].T.flatten())))  # USD: row vectors
    UsdGeom.Xformable(pose).GetOrderedXformOps()[0].Set(rot)


def move_product_prim(stage: Usd.Stage, product_id: int, x: float, y: float = 0.0, z: float = None,
                      rest_dz: float = BOX_REST_DZ) -> None:
    prim = stage.GetPrimAtPath(product_path(product_id))
    if not prim:
        return
    if z is None:
        z = L.CONVEYOR_TOP_Z + rest_dz
    UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(x, y, z))


PUSHER_PATH = f"{L.FACTORY_PATH}/Pusher"
PUSHER_HOME_Y = L.CONVEYOR_WIDTH / 2 + 0.12  # retracted, beside the belt (+Y side)
PUSHER_CONTACT = L.PRODUCT_SIZE / 2 + 0.02  # pusher centre offset from product centre
BIN_Y = -L.CONVEYOR_WIDTH / 2 - 0.4
BIN_DROP_Z = 0.4 + L.PRODUCT_SIZE / 2.0
REJECT_ANIM_S = 0.6


def _lerp(a, b, k):
    return a + (b - a) * k


def reject_motion(u: float, rest_dz: float = BOX_REST_DZ):
    """Visual-only reject motion for progress u in [0, 1] -> (product_xyz, pusher_y).
    approach (pusher reaches the product) -> push (product off the -Y edge) -> drop into
    the bin while the pusher retracts. Simulation state is already final."""
    u = min(max(u, 0.0), 1.0)
    top_z = L.CONVEYOR_TOP_Z + rest_dz
    drop_z = BIN_DROP_Z - BOX_REST_DZ + rest_dz
    edge_y = -L.CONVEYOR_WIDTH / 2 - L.PRODUCT_SIZE / 2
    if u < 0.25:
        k = u / 0.25
        return (L.REJECT_X, 0.0, top_z), _lerp(PUSHER_HOME_Y, PUSHER_CONTACT, k)
    if u < 0.65:
        y = _lerp(0.0, edge_y, (u - 0.25) / 0.4)
        return (L.REJECT_X, y, top_z), y + PUSHER_CONTACT
    k = (u - 0.65) / 0.35
    prod = (L.REJECT_X, _lerp(edge_y, BIN_Y, k), _lerp(top_z, drop_z, k))
    return prod, _lerp(edge_y + PUSHER_CONTACT, PUSHER_HOME_Y, k)


def set_pusher(stage: Usd.Stage, y: float) -> None:
    prim = stage.GetPrimAtPath(PUSHER_PATH)
    if prim:
        UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(L.REJECT_X, y, L.CONVEYOR_TOP_Z + 0.09))


def move_product_to_reject_bin(stage: Usd.Stage, product_id: int) -> None:
    move_product_prim(stage, product_id, L.REJECT_X, BIN_Y, BIN_DROP_Z)


def remove_product_prim(stage: Usd.Stage, product_id: int) -> None:
    stage.RemovePrim(product_path(product_id))


def clear_products(stage: Usd.Stage) -> None:
    if stage.GetPrimAtPath(L.PRODUCTS_PATH):
        stage.RemovePrim(L.PRODUCTS_PATH)
    UsdGeom.Xform.Define(stage, L.PRODUCTS_PATH)


def _define_light(stage: Usd.Stage, factor: float = 1.0) -> None:
    # Kit's "Default" rig is distant 2^10 + dome 2^9; at that level the top-down inspection
    # frames were washed out (product saturation below threshold), so use 1/4 of it.
    light = UsdLux.DistantLight.Define(stage, f"{L.FACTORY_PATH}/KeyLight")
    light.CreateIntensityAttr(250.0 * factor)
    light.CreateAngleAttr(0.53)
    UsdGeom.XformCommonAPI(light).SetRotate(Gf.Vec3f(-30.0, 20.0, 0.0))
    dome = UsdLux.DomeLight.Define(stage, f"{L.FACTORY_PATH}/Ambient")
    dome.CreateIntensityAttr(125.0 * factor)
