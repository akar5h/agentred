"""AgentDojo integration — `GraftedAttack(BaseAttack)` plugs grafted's
adaptive synthesis into AgentDojo's `BaseAttack.attack(user_task,
injection_task)` contract.

Install: ``pip install -e .[agentdojo]``

Usage:

    from agentdojo.benchmark import benchmark_suite_with_injections
    from grafted.integrations.agentdojo.attack import GraftedAttack
    from grafted.integrations.agentdojo.verdict_harvest import VerdictHarvester

    suite = ...     # AgentDojo TaskSuite
    pipeline = ...  # AgentDojo AgentPipeline
    harvester = VerdictHarvester(logdir, pipeline.name, suite.name)
    attack = GraftedAttack(suite, pipeline, memory_scope="per-suite",
                           verdict_harvester=harvester)
    benchmark_suite_with_injections(pipeline, suite, attack, logdir, force_rerun=False)

Note: GraftedAttack requires the ``agentdojo`` extra installed. The
``verdict_harvest`` module is dep-free and importable directly.
"""
# Don't eager-import attack.py — it depends on agentdojo. Users do:
#   from grafted.integrations.agentdojo.attack import GraftedAttack
# verdict_harvest is dep-free and can be imported directly.
