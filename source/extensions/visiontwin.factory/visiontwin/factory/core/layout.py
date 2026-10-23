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

# Inspection cell (dental crown line, Day 11): the 5-axis machine from reference/teeth_mill.urdf
# stands IN the line between two conveyor sections and carries the inspection camera on its
# spindle. Products stop at the end of the first section (entry), are loaded onto the C
# platter, viewed from several angles, and unloaded onto the second section (exit).
CELL_X = -1.0  # platter centre at the load pose (on the belt line, y = 0)
CELL_GAP_HALF = 0.32  # belt sections end this far from CELL_X (room for the machine base)
CELL_ENTRY_X = CELL_X - CELL_GAP_HALF - 0.06  # product stop / pick position on section 1
CELL_EXIT_X = CELL_X + CELL_GAP_HALF + 0.06  # place position on section 2
CELL_PATH = "/World/Factory/Cell"
CELL_CAMERA_PATH = "/World/Factory/Cell/CameraRig/Camera"  # moves with the spindle
CELL_OVERVIEW_CAMERA_PATH = "/World/Factory/CellOverviewCamera"
CELL_OVERVIEW_EYE = (CELL_X + 0.3, -0.5, 1.6)  # high in front: section 1 end, machine, section 2 start
CELL_OVERVIEW_TARGET = (CELL_X, 0.05, 0.84)
TRANSFER_LIFT = 0.15  # pick-and-place arc height (clears the B housing and support)

# Root prim paths
ROOT_PATH = "/World"
FACTORY_PATH = "/World/Factory"
PRODUCTS_PATH = "/World/Products"
CAMERA_PATH = "/World/Factory/InspectionCamera"

# Overview camera used by the main viewport (front-left, above the line).
OVERVIEW_CAMERA_PATH = "/World/Factory/OverviewCamera"
OVERVIEW_CAMERA_EYE = (-2.0, -6.5, 3.5)
OVERVIEW_CAMERA_TARGET = (0.3, 0.0, 0.8)
