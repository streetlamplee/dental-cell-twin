# Joint velocity and acceleration audit

Status: incomplete

Analytical cubic smoothstep peaks, checked against declared source URDF limits.
Missing limits remain unverified. No runtime timing or configuration was modified.

## arm_load

Duration: 2.000000 s; status: incomplete

| Joint | Units | Segment peak velocity | Velocity limit | Result | Segment peak acceleration | Accel limit | Result |
|---|---|---:|---:|---|---:|---:|---|
| finger_left | m/s, m/s^2 | 0.075000 | 0.080000 | within | 2.000000 | missing | unverified |
| finger_right | m/s, m/s^2 | 0.075000 | 0.080000 | within | 2.000000 | missing | unverified |
| joint1 | rad/s, rad/s^2 | 5.778892 | 50.000000 | within | 95.181757 | missing | unverified |
| joint2 | rad/s, rad/s^2 | 11.548069 | 50.000000 | within | 190.203494 | missing | unverified |
| joint3 | rad/s, rad/s^2 | 7.065643 | 50.000000 | within | 116.375301 | missing | unverified |
| joint4 | rad/s, rad/s^2 | 2.505395 | 200.000000 | within | 41.265333 | missing | unverified |
| joint5 | rad/s, rad/s^2 | 0.000046 | 200.000000 | within | 0.000760 | missing | unverified |
| joint6 | rad/s, rad/s^2 | 15.481433 | 200.000000 | within | 254.988302 | missing | unverified |

### Exceeded segments

| Segment | Time (s) | Joint | Velocity ratio | Acceleration ratio |
|---|---|---|---:|---:|

### Runtime endpoint reset

| Joint | Raw delta | Physical delta | Status |
|---|---:|---:|---|

A real position jump has no finite continuous-time velocity/acceleration bound; segment peaks exclude that jump.

Runtime interpolation crosscheck: True

## arm_unload

Duration: 2.000000 s; status: incomplete

| Joint | Units | Segment peak velocity | Velocity limit | Result | Segment peak acceleration | Accel limit | Result |
|---|---|---:|---:|---|---:|---:|---|
| finger_left | m/s, m/s^2 | 0.075000 | 0.080000 | within | 2.000000 | missing | unverified |
| finger_right | m/s, m/s^2 | 0.075000 | 0.080000 | within | 2.000000 | missing | unverified |
| joint1 | rad/s, rad/s^2 | 5.778873 | 50.000000 | within | 95.181444 | missing | unverified |
| joint2 | rad/s, rad/s^2 | 11.549027 | 50.000000 | within | 190.219273 | missing | unverified |
| joint3 | rad/s, rad/s^2 | 7.068389 | 50.000000 | within | 116.420528 | missing | unverified |
| joint4 | rad/s, rad/s^2 | 2.506874 | 200.000000 | within | 41.289688 | missing | unverified |
| joint5 | rad/s, rad/s^2 | 0.000045 | 200.000000 | within | 0.000735 | missing | unverified |
| joint6 | rad/s, rad/s^2 | 9.702571 | 200.000000 | within | 159.807047 | missing | unverified |

### Exceeded segments

| Segment | Time (s) | Joint | Velocity ratio | Acceleration ratio |
|---|---|---|---:|---:|

### Runtime endpoint reset

| Joint | Raw delta | Physical delta | Status |
|---|---:|---:|---|

A real position jump has no finite continuous-time velocity/acceleration bound; segment peaks exclude that jump.

Runtime interpolation crosscheck: True

## inspection_machine

Duration: 16.024000 s; status: incomplete

| Joint | Units | Segment peak velocity | Velocity limit | Result | Segment peak acceleration | Accel limit | Result |
|---|---|---:|---:|---|---:|---:|---|
| b_joint | rad/s, rad/s^2 | 2.617994 | missing | unverified | 23.271057 | missing | unverified |
| c_joint | rad/s, rad/s^2 | 5.235988 | missing | unverified | 46.542113 | missing | unverified |
| x_joint | m/s, m/s^2 | 0.100000 | 0.100000 | within | 0.183402 | missing | unverified |
| y_joint | m/s, m/s^2 | 0.035058 | 0.100000 | within | 0.282843 | missing | unverified |
| z_joint | m/s, m/s^2 | 0.013180 | 0.100000 | within | 0.117157 | missing | unverified |

### Exceeded segments

| Segment | Time (s) | Joint | Velocity ratio | Acceleration ratio |
|---|---|---|---:|---:|

### Runtime endpoint reset

| Joint | Raw delta | Physical delta | Status |
|---|---:|---:|---|

A real position jump has no finite continuous-time velocity/acceleration bound; segment peaks exclude that jump.

Runtime interpolation crosscheck: True

## Limits of interpretation

- Declared URDF limits are not independently verified hardware specifications
- Missing limits are unverified, not passing
- Cubic smoothstep has acceleration jumps and unbounded ideal jerk at joins
- No payload, torque, tracking error or real controller dynamics considered
- Minimum duration uses known limits only and is not an approved retiming
- Continuous joint cycle boundaries require angle unwrapping before use with a real controller.
