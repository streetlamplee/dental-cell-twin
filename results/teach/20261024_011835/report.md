# Surface teaching: origin + 5 faces, standoff 20 mm

X/Y/Z in mm, B/C in deg; angle = tool axis vs face normal; offset = tool tip from the face centre line.

| point | x_joint | y_joint | z_joint | b_joint | c_joint | angle_deg | offset_mm | standoff_mm | limits |
|---|---|---|---|---|---|---|---|---|---|
| origin | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |  |  |  | True |
| top | -119.95 | 50.98 | -34.1 | 0.0 | 0.0 | 0.0 | 0.0 | 20.0 | True |
| side_+x | -119.95 | 68.48 | -44.1 | -90.0 | 90.0 | 0.0 | 0.0 | 20.0 | True |
| side_-x | -119.95 | 68.48 | -44.1 | -90.0 | 270.0 | 0.0 | 0.0 | 20.0 | True |
| side_+y | -119.95 | 68.48 | -44.1 | -90.0 | 0.0 | 0.0 | 0.0 | 20.0 | True |
| side_-y | -119.95 | 68.48 | -44.1 | -90.0 | 180.0 | 0.0 | 0.0 | 20.0 | True |

Closer standoff: standoff 10 mm: out of reach: side_+x (needs {'z_joint': -54.1} mm), side_-x (needs {'z_joint': -54.1} mm), side_+y (needs {'z_joint': -54.1} mm), side_-y (needs {'z_joint': -54.1} mm)

Program: teach_program_20261024_011912.json
