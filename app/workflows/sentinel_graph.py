from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from app.workflows.nodes import SentinelWorkflowNodes
from app.workflows.state import SentinelWorkflowState


def _route_after_remediation(state: SentinelWorkflowState) -> str:
    if state.get("approval_required", False):
        return "approval_node"
    return "final_report_node"


def build_sentinel_workflow(
    *,
    nodes: SentinelWorkflowNodes,
    checkpointer: Any,
):
    workflow = StateGraph(SentinelWorkflowState)
    workflow.add_node("intake_node", nodes.intake_node)
    workflow.add_node("incident_classifier_node", nodes.incident_classifier_node)
    workflow.add_node("tool_evidence_node", nodes.tool_evidence_node)
    workflow.add_node("retrieval_node", nodes.retrieval_node)
    workflow.add_node("hypothesis_node", nodes.hypothesis_node)
    workflow.add_node("remediation_node", nodes.remediation_node)
    workflow.add_node("approval_node", nodes.approval_node)
    workflow.add_node("final_report_node", nodes.final_report_node)

    workflow.add_edge(START, "intake_node")
    workflow.add_edge("intake_node", "incident_classifier_node")
    workflow.add_edge("incident_classifier_node", "tool_evidence_node")
    workflow.add_edge("tool_evidence_node", "retrieval_node")
    workflow.add_edge("retrieval_node", "hypothesis_node")
    workflow.add_edge("hypothesis_node", "remediation_node")
    workflow.add_conditional_edges(
        "remediation_node",
        _route_after_remediation,
        {
            "approval_node": "approval_node",
            "final_report_node": "final_report_node",
        },
    )
    workflow.add_edge("approval_node", "final_report_node")
    workflow.add_edge("final_report_node", END)

    return workflow.compile(checkpointer=checkpointer)
