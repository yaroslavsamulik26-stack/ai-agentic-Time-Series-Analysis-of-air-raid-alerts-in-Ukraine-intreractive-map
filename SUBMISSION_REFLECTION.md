# Submission Reflection (~100 words)

### What went wrong?
Initially, guessing stochastic single-building strike probabilities caused extreme class imbalance and penalizing model predictions during active raid hours (yielding a deceptive 8.2% precision). Furthermore, ignoring empirical debris fallout counterintuitively ranked Solomianskyi district (#1 with 86 incidents) as safest.

### How did you adjust your approach?
We transitioned to a deterministic Target Attractiveness Index ($A_i$) for 67 critical facilities, integrated empirical debris density ($w_{\text{inc}} = 0.35$) into district danger, and refactored Time Series evaluation to measure Operational Active Threat Warning with strict zero data leakage.

### Why is your final version better than your first attempt?
The final system achieves 72.4% operational threat precision (98.0% during peak raids), 84.5% recall, and 0.985 ROC-AUC on holdout data. Solomianskyi is accurately identified as high risk, while an interactive Leaflet/Google Maps dashboard serves actionable defense intelligence.
