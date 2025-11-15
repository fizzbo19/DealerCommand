# backend/plan_utils.py
def has_feature(plan, feature, trial_active=False):
    """
    Simple permission matrix.
    plan: string ('free','premium','pro','platinum')
    feature: 'analytics.pro' or 'analytics.platinum' etc
    trial_active: bool - if trial active, treat user as platinum
    """
    plan = (plan or "free").lower()
    if trial_active:
        plan = "platinum"
    matrix = {
        "free": [],
        "premium": [],
        "pro": ["analytics.pro"],
        "platinum": ["analytics.pro","analytics.platinum"]
    }
    return feature in matrix.get(plan, [])
