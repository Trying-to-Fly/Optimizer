"""Propulsion chain — MODEL_DETAILS.md section 2.

Contract: (V, required thrust T, PowertrainConfig) -> P_elec + diagnostics
(RPM, advance ratio J, per-stage efficiencies). Objective-agnostic; mission
evaluators compose it.

M0 status: stub. M1 brings the APC proxy-table fits (data/props/, built by
tools/ingest_props.py), the motor equivalent circuit
(asb motor_electric_performance), and the thrust-match coupling.
"""
