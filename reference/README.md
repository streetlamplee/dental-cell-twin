# teeth_mill URDF → Omniverse (Isaac Sim)

`teeth_mill.urdf` is `teeth_description/urdf/teeth.urdf.xacro` expanded to a plain URDF.
It only uses boxes and cylinders (no mesh files, no `package://` paths), so this one file is all that is needed.

## Open in Isaac Sim (other PC: NVIDIA RTX GPU, Windows or Linux)

1. Install Isaac Sim (download from NVIDIA; the URDF importer extension is included).
2. `File > Import` → choose `teeth_mill.urdf`
   (older Isaac Sim: `Isaac Utils > Workflows > URDF Importer`).
3. Importer options:
   - **Fix Base Link: on** (root link is `world`, the machine does not move)
   - Joint drive: Position
   - Collision: none in the model, so the "convex decomposition" setting does not matter
4. Save the stage as `.usd`. After that the USD can be opened in any Omniverse app without the URDF.

Joints: `x_joint`, `y_joint`, `z_joint` (prismatic, m), `b_joint`, `c_joint` (continuous, rad).
Units are meters, z up, same as the URDF.

## Limits of this model

- No `<inertial>` and no `<collision>`: the importer gives default mass and warns. Fine for viewing and moving
  joints; not for physics / contact simulation.
- Lead (5 mm), B/C gear ratios and part sizes are placeholders (see the xacro header).

## Editing

The URDF is only the starting model. After import, edit the USD in Omniverse; those edits are not written back
to the URDF / xacro here.

## Regenerate after changing the xacro

On this PC (WSL ROS 2):
```powershell
wsl -d Ubuntu-24.04 -- bash -c ". /opt/ros/jazzy/setup.bash && xacro ros2_sim/teeth_description/urdf/teeth.urdf.xacro -o ros2_sim/omniverse/teeth_mill.urdf && check_urdf ros2_sim/omniverse/teeth_mill.urdf"
```
Without ROS: `pip install xacro`, then `xacro teeth.urdf.xacro -o teeth_mill.urdf`.
