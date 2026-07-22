"""Aero & trim — MODEL_DETAILS.md section 3.

Contract: (geometry, mass/CG, operating point incl. control deflections) ->
lift, drag buildup, pitching moment, stability derivatives; smooth throughout.
VLM + NeuralFoil strip theory + parasite buildup; explicit ruddervator deflection
as the trim variable; dual smooth/tripped polar evaluation. Arrives at M1 (fixed
design) / M3 (trim constraints).
"""
