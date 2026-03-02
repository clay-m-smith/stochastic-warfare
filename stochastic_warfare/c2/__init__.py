"""Command & Control Infrastructure — Phase 5 of the stochastic warfare simulation.

Provides order types and propagation, command authority with succession,
communications with stochastic reliability, ROE enforcement, fire support
coordination, and mission command / subordinate initiative. Naval C2
(task force hierarchy, data links, submarine comms) is fully integrated.

No AI decision-making — this phase is the C2 *plumbing*. Commanders decide
what to do (Phase 8); this module moves those decisions through the chain
of command with realistic friction, delay, and degradation.
"""
