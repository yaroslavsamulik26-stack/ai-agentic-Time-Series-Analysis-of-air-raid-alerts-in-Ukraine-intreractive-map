# Submission Reflection (~100 words)

### What went wrong?
Initially, we treated air raid alerts as a static geospatial mapping problem, which risked data leakage by using retrospective full-period aggregations and failed to capture the distinct tactical differences between nighttime Shahed swarms and morning missile salvos.

### How did you adjust your approach?
We refactored the pipeline into a spatio-temporal architecture with a strict chronological train/test split (training before September, testing on the latest period). We engineered causal lag features without look-ahead bias and decoupled threats into Yellow (drones/energy) and Red (missiles/infrastructure).

### Why is your final version better than your first attempt?
The final model achieves a leak-free 0.681 ROC-AUC on the holdout test set, outperforming baseline empirical priors while powering an interactive, standalone defense intelligence dashboard with Google Maps tiles.
