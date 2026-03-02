"""Morale & Human Factors — Phase 4 of the stochastic warfare simulation.

Provides Markov-chain morale state transitions, unit cohesion modeling,
combat stress accumulation, experience progression, psychological operations,
and rout/rally/surrender mechanics.  Subscribes to combat events via EventBus;
never imports combat modules directly.
"""
