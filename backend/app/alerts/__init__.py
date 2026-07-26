"""Alert evaluation and human-approval workflow.

The system NEVER auto-dispatches. ``evaluate_alerts`` creates draft alerts
from threshold-meeting observations; all alerts require explicit human
approval (admin/emergency_manager) before any action is taken.
"""
