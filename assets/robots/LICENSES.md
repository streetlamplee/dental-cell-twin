# Robot descriptions — attribution and licenses

## Seeed Studio reBot Arm B601-DM

| | |
|---|---|
| Source | [Seeed-Projects/reBot-DevArm](https://github.com/Seeed-Projects/reBot-DevArm), `Rebot_Arm_description/DM/urdf/ReBot_Arm_DM.urdf` and its meshes |
| Commit | `6c2bb32b3f7f430c58a37cf93d459d07ee99d736` (pinned in `sources.json`, files checked by SHA256) |
| License | **CERN Open Hardware Licence Version 2 – Weakly Reciprocal (CERN-OHL-W-2.0)**, see the repository's `LICENSE` (downloaded with the files) |

**What this repository contains:** only `usd/rebot_b601_dm.kinematics.json` — the joint description (names, types, axes, origins, limits) taken from the URDF by `scripts/urdf_mesh_to_usd.py`, unmodified in content.

**What it does not contain:** the URDF, the STL meshes and the converted USD (`.gitignore`). They are downloaded and rebuilt locally:

```powershell
.\scripts\fetch_robot.ps1                 # URDF + meshes + LICENSE at the pinned commit
.\scripts\urdf_mesh_to_usd.ps1 -Urdf assets\robots\rebot_b601_dm\Rebot_Arm_description\DM\urdf\ReBot_Arm_DM.urdf -Out assets\robots\usd\rebot_b601_dm.usd
```

The robot is used as a visual transfer robot in the simulation; this project is not affiliated with or endorsed by Seeed Studio.
