"""CBRN (Chemical, Biological, Radiological, Nuclear) Domain — Phase 18.

Models CBRN weapon effects as terrain modifiers, casualty generators, and
performance degraders.  Contamination zones overlay the terrain grid; units in
contaminated cells take casualties based on protection level; MOPP posture
degrades movement/detection/fatigue through existing parameter interfaces.
All effects gated behind ``enable_cbrn`` configuration flag.
"""
