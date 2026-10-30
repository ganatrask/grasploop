# Robots x tasks: 4 robots, 3 task families, 12 cells, 96 scenarios per condition

| robot | task | object / terrain | reference | one-shot | rerun | physics fb | physics+vision | model | $ |
|---|---|---|---|---|---|---|---|---|---|
| Franka Panda (arm, 2-finger) | pick and place on a target | box_flat | 8/8 | 3/8 | 3/8 | 5/8 | — | Nemotron-3_5-Lightning | 0.07 |
| Franka Panda (arm, 2-finger) | pick and place on a target | box_tall | 8/8 | 0/8 | 0/8 | 1/8 | — | Nemotron-3_5-Lightning | 0.12 |
| Franka Panda (arm, 2-finger) | pick and place on a target | cube | 8/8 | 4/8 | 4/8 | 7/8 | — | Nemotron-3_5-Lightning | 0.06 |
| Franka Panda (arm, 2-finger) | pick up and hold 10 cm | box_flat | 8/8 | 5/8 | 5/8 | 7/8 | 7/8 | Nemotron-3_5-Lightning | 0.14 |
| Franka Panda (arm, 2-finger) | pick up and hold 10 cm | box_tall | 8/8 | 1/8 | 1/8 | 3/8 | 3/8 | Nemotron-3_5-Lightning | 0.22 |
| Franka Panda (arm, 2-finger) | pick up and hold 10 cm | capsule_s | 8/8 | 4/8 | 4/8 | 4/8 | 6/8 | Nemotron-3_5-Lightning | 0.19 |
| Franka Panda (arm, 2-finger) | pick up and hold 10 cm | cube | 8/8 | 4/8 | 4/8 | 8/8 | 8/8 | Nemotron-3_5-Lightning | 0.12 |
| Franka Panda (arm, 2-finger) | pick up and hold 10 cm | sphere_m | 3/8 | 0/8 | 0/8 | 0/8 | 0/8 | Nemotron-3_5-Lightning | 0.27 |
| Franka Panda (arm, 2-finger) | pick up and hold 10 cm | sphere_s | 8/8 | 0/8 | 0/8 | 1/8 | 2/8 | Nemotron-3_5-Lightning | 0.23 |
| Kuka iiwa + Allegro (arm, 4-finger hand) | pick up and hold 10 cm | cube | 7/8 | 0/8 | 0/8 | 0/8 | 0/8 | Nemotron-3_5-Lightning | 0.21 |
| Unitree Go2 (quadruped) | navigate: waypoint then goal | flat ground | 8/8 | 4/8 | 4/8 | 6/8 | — | Nemotron-3_5-Lightning | 0.07 |
| Unitree G1 (humanoid) | navigate: waypoint then goal | flat ground | 8/8 | 2/8 | 2/8 | 6/8 | — | Nemotron-3_5-Lightning | 0.05 |
