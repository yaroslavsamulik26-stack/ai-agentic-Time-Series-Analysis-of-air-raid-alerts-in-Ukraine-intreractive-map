# Submission Reflection (~100 words)

### What went wrong?
Initially, I attempted to calculate exact hit probabilities for individual facilities. However, predicting single-building strikes was far too stochastic and noisy, resulting in extreme class imbalance and deceptive 8.2% precision. Furthermore, omitting empirical debris fallout counterintuitively ranked Solomianskyi district as safest.

### How did you adjust your approach?
Recognizing that hit probability was essentially random guessing, I transitioned to a deterministic Target Attractiveness Index across 67 critical facilities. We incorporated empirical interception debris density (weight 0.35) into district risk scoring and evaluated time-series threat windows without data leakage.

### Why is your final version better than your first attempt?
The final pipeline replaces speculative guessing with actionable defense intelligence, achieving 72.4% operational threat precision (98.0% during peak raids), 84.5% recall, and 0.985 ROC-AUC, fully integrated into an interactive Python defense dashboard.
