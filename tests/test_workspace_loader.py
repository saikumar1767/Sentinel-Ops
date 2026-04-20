from pathlib import Path

from app.rag.loader import KnowledgeDocumentLoader
from app.settings import Settings


def test_loader_indexes_workspace_docs_and_deployment_files(tmp_path) -> None:
    workspace_root = tmp_path / "checkout-service"
    (workspace_root / "docs").mkdir(parents=True, exist_ok=True)
    (workspace_root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (workspace_root / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
    (workspace_root / "README.md").write_text("# Checkout Service\n", encoding="utf-8")
    (workspace_root / "docs" / "runbook.md").write_text(
        "---\n"
        "title: Checkout Runbook\n"
        "incident_type: deployment\n"
        "tags: payments, rollout\n"
        "---\n"
        "# Steps\n",
        encoding="utf-8",
    )
    (workspace_root / ".github" / "workflows" / "deploy.yml").write_text("name: Deploy\n", encoding="utf-8")
    (workspace_root / "node_modules" / "pkg" / "README.md").write_text("ignore me\n", encoding="utf-8")

    settings = Settings(
        workspace_root=workspace_root,
        workspace_name="Checkout Service",
        knowledge_base_dir=tmp_path / "knowledge",
        incident_templates_dir=tmp_path / "incident_templates",
        incident_history_dir=tmp_path / "history",
    )
    loader = KnowledgeDocumentLoader(settings)

    documents = loader.load_documents()
    source_paths = {document.source_path for document in documents}

    assert "README.md" in source_paths
    assert "docs/runbook.md" in source_paths
    assert ".github/workflows/deploy.yml" in source_paths
    assert "node_modules/pkg/README.md" not in source_paths

    runbook = next(document for document in documents if document.source_path == "docs/runbook.md")
    assert runbook.title == "Checkout Runbook"
    assert runbook.incident_type == "deployment"
    assert runbook.tags == ["payments", "rollout"]


def test_loader_respects_configured_workspace_doc_roots(tmp_path) -> None:
    workspace_root = tmp_path / "billing-service"
    (workspace_root / "docs").mkdir(parents=True, exist_ok=True)
    (workspace_root / "runbooks").mkdir(parents=True, exist_ok=True)
    (workspace_root / "ops").mkdir(parents=True, exist_ok=True)
    (workspace_root / "README.md").write_text("# Billing Service\n", encoding="utf-8")
    (workspace_root / "docs" / "overview.md").write_text("# Docs\n", encoding="utf-8")
    (workspace_root / "runbooks" / "recovery.md").write_text("# Recovery\n", encoding="utf-8")
    (workspace_root / "ops" / "internal.md").write_text("# Internal ops\n", encoding="utf-8")

    settings = Settings(
        workspace_root=workspace_root,
        workspace_name="Billing Service",
        workspace_doc_roots=["README.md", "runbooks"],
        knowledge_base_dir=tmp_path / "knowledge",
        incident_templates_dir=tmp_path / "incident_templates",
        incident_history_dir=tmp_path / "history",
    )
    loader = KnowledgeDocumentLoader(settings)

    documents = loader.load_documents()
    source_paths = {document.source_path for document in documents}

    assert "README.md" in source_paths
    assert "runbooks/recovery.md" in source_paths
    assert "docs/overview.md" not in source_paths
    assert "ops/internal.md" not in source_paths
