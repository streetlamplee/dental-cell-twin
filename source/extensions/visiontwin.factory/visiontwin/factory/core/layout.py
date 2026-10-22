"""Factory line layout constants (meters, Z-up).

Pure Python: no omni/pxr imports, so simulation logic and tests can share it
without a running Kit app.
"""

# Conveyor runs along +X. Products spawn at SPAWN_X and leave at EXIT_X.
CONVEYOR_LENGTH = 6.0
CONVEYOR_WIDTH = 0.6
CONVEYOR_TOP_Z = 0.8  # belt surface height
CONVEYOR_THICKNESS = 0.1

SPAWN_X = -CONVEYOR_LENGTH / 2.0 + 0.2
INSPECTION_X = -0.5  # products are photographed when crossing this line
REJECT_X = 1.5  # rejected products are pushed off when crossing this line
EXIT_X = CONVEYOR_LENGTH / 2.0

PRODUCT_SIZE = 0.2  # cube edge length

# Inspection camera: straight above the inspection line, looking down (-Z).
# Apertures are set explicitly so the pixel footprint is known (see camera_model.py).
CAMERA_HEIGHT_ABOVE_BELT = 1.2
CAMERA_RESOLUTION = (640, 480)
CAMERA_FOCAL_MM = 18.0
CAMERA_H_APERTURE_MM = 20.955
CAMERA_V_APERTURE_MM = CAMERA_H_APERTURE_MM * CAMERA_RESOLUTION[1] / CAMERA_RESOLUTION[0]

# Zone markers sit beside the belt (|y| > belt half width) so they stay out of the
# inspection ROI, which only covers the belt lane.
MARKER_OFFSET_Y = CONVEYOR_WIDTH / 2.0 + 0.06

# Inspection window along the belt (half length, m). Must exceed PRODUCT_SIZE/2 plus the
# distance a product travels between line crossing and capture, and stay below the
# spawn gap so a neighbour never enters it.
INSPECTION_HALF_LENGTH = 0.25

# Mill station (CAD asset from reference/teeth_mill.urdf): behind the belt (+Y), upstream
# of the inspection line and outside the inspection camera's view (|y| > ~0.5 m there).
MILL_X = -1.8  # station line: products crossing it trigger a machining cycle
MILL_Y = 0.85
MILL_STAND_HEIGHT = 0.6
MILL_PATH = "/World/Factory/MillStation"
# Dental line: the mill is a processing station; products stop at the entry, are loaded onto
# the C platter, machined and unloaded at the exit. Entry/exit are > min_gap apart.
MILL_ENTRY_X = MILL_X - 0.2
MILL_EXIT_X = MILL_X + 0.2
# Fractions of the processing cycle: load (belt -> platter), machining, unload (platter -> belt).
MILL_LOAD_FRACTION = 0.15
MILL_UNLOAD_FRACTION = 0.15
MILL_CAMERA_PATH = "/World/Factory/MillCamera"
MILL_CAMERA_EYE = (MILL_X + 0.55, -0.55, 1.35)  # front-right, above the belt: entry, mill and exit
MILL_CAMERA_TARGET = (MILL_X, 0.45, 0.8)

# Root prim paths
ROOT_PATH = "/World"
FACTORY_PATH = "/World/Factory"
PRODUCTS_PATH = "/World/Products"
CAMERA_PATH = "/World/Factory/InspectionCamera"

# Overview camera used by the main viewport (front-left, above the line).
OVERVIEW_CAMERA_PATH = "/World/Factory/OverviewCamera"
OVERVIEW_CAMERA_EYE = (-2.0, -6.5, 3.5)
OVERVIEW_CAMERA_TARGET = (0.3, 0.0, 0.8)
