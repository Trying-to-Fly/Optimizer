"""Constraint assembly — MODEL_DETAILS.md section 4.

Contract: attach every equality/inequality to an asb.Opti instance, given the
modules' outputs and MissionSpec values. Smoothness rule: no `if`, no `ceil`,
no interpolation kinks inside the loop (smooth-max via log-sum-exp).
Arrives at M2/M3.
"""
