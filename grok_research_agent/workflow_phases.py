from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from readability import Document
from rich.console import Console
from rich.table import Table

from grok_research_agent.grok_client import GrokClient, GrokError
from grok_research_agent.session_manager import SessionManager, SessionState


@dataclass(frozen=True)
class WorkflowContext:
    state: SessionState
    session_dir: Path
    run_dir: Path
    prompts_dir: Path


class WorkflowRunner:
    AUTO_TYPES: tuple[str, ...] = (
        "auto-model",
        "auto-list",
        "auto-set",
        "auto-graph",
        "auto-hypergraph",
        "auto-temporal-graph",
        "auto-spatial-graph",
        "auto-spatiotemporal-graph",
    )
    SOURCE_CHUNK_CHARS = 45000
    SOURCE_CHUNK_OVERLAP = 5000
    NOTEBOOK_CHUNK_CHARS = 70000
    REPORT_SECTIONS: tuple[str, ...] = (
        "Core Definitions and Scope",
        "Architecture and Technical Mechanisms",
        "Workflows, Processes, and Operational Patterns",
        "Evidence, Examples, and Case Studies",
        "Limitations, Trade-offs, and Failure Modes",
        "Open Questions and Future Directions",
    )

    def __init__(
        self,
        session_manager: SessionManager,
        console: Console,
        *,
        client_factory: Callable[[WorkflowContext], GrokClient] | None = None,
        http_get: Callable[..., requests.Response] | None = None,
    ):
        self.session_manager = session_manager
        self.console = console
        self._client_factory = client_factory
        self._http_get = http_get or requests.get

    def run(self, session_id: str, command: str | None = None, **options: object) -> None:
        state = self.session_manager.load_state(session_id)
        paths = self.session_manager.session_paths(session_id)
        run_dir = self.session_manager.create_run_dir(session_id)
        prompts_dir = Path(__file__).parent / "prompts"

        ctx = WorkflowContext(
            state=state,
            session_dir=paths.session_dir,
            run_dir=run_dir,
            prompts_dir=prompts_dir,
        )

        if command in {"generate-images"}:
            self._generate_images(ctx)
            return

        if command in {"synthesize"}:
            self._phase5_synthesis(ctx, force=True)
            return

        if command in {"update"}:
            self._phase1_discovery(ctx, since_last_run=True)
            ctx.state.current_phase = 2
            self.session_manager.save_state(ctx.state)
            self.console.print("Update discovery completed. Resume to curate sources (H1).")
            return

        if command == "compile":
            compile_type = str(options.get("compile_type") or "auto-hypergraph")
            self._compile(ctx, compile_type=compile_type)
            return

        if command == "drill":
            drill_mode = str(options.get("drill_mode") or "backward")
            self._drill(ctx, drill_mode=drill_mode)
            return

        if command == "feed":
            new_doc = options.get("new_doc")
            if not new_doc:
                self.console.print("Missing --new-doc")
                return
            self._feed(ctx, Path(str(new_doc)))
            return

        if command == "show":
            self._show(ctx)
            return

        self._run_until_human_step(ctx)

    def _run_until_human_step(self, ctx: WorkflowContext) -> None:
        phase = ctx.state.current_phase

        if phase == 0:
            self._phase0_scope(ctx)
            return
        if phase == 1:
            self._phase1_discovery(ctx)
            ctx.state.current_phase = 2
            self.session_manager.save_state(ctx.state)
            self.console.print("Discovery completed. Resume to curate sources (H1).")
            return
        if phase == 2:
            self._phase2_curation(ctx)
            return
        if phase == 3:
            self._phase3_extraction(ctx)
            ctx.state.current_phase = 4
            self.session_manager.save_state(ctx.state)
            self.console.print("Extraction completed. Resume to build notebook.")
            return
        if phase == 4:
            self._phase4_notebook(ctx)
            ctx.state.current_phase = 5
            self.session_manager.save_state(ctx.state)
            self.console.print("Notebook updated. Resume to synthesize draft (H2).")
            return
        if phase == 5:
            self._phase5_synthesis(ctx)
            return
        if phase == 6:
            self._phase6_full_collection(ctx)
            return
        if phase == 7:
            self._phase7_final_polish(ctx)
            ctx.state.current_phase = 8
            self.session_manager.save_state(ctx.state)
            self.console.print(f"Final report ready at {ctx.session_dir / 'FINAL_REPORT.md'}")
            return

        self.console.print("Session is complete.")

    def _client(self, ctx: WorkflowContext) -> GrokClient:
        if self._client_factory is not None:
            return self._client_factory(ctx)
        env_path = ctx.session_dir.parent.parent / ".env"
        if not env_path.exists():
            env_path = None
        return GrokClient(env_path=env_path)

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _strip_code_fences(self, text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            lines = t.splitlines()
            if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
                return "\n".join(lines[1:-1]).strip()
        return t

    def _safe_json(self, text: str) -> dict[str, object]:
        cleaned = self._strip_code_fences(text)
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
            return {"data": obj}
        except Exception:  # noqa: BLE001
            return {"raw": cleaned}

    def _slug(self, text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
        return slug or "section"

    def _html_to_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = soup.get_text("\n")
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in text.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if line in seen:
                continue
            lines.append(line)
            seen.add(line)
        return "\n".join(lines)

    def _merge_text_variants(self, main_text: str, full_text: str) -> str:
        sections: list[str] = []
        if main_text.strip():
            sections.append("## Main Article Text\n" + main_text.strip())
        if full_text.strip():
            if main_text.strip() and full_text.strip() == main_text.strip():
                return "\n\n".join(sections)
            sections.append("## Full Page Text\n" + full_text.strip())
        return "\n\n".join(sections).strip()

    def _fetch_source_bundle(self, url: str, timeout_s: int = 20) -> dict[str, str]:
        resp = self._http_get(url, timeout=timeout_s, headers={"User-Agent": "grok-research-agent/0.1"})
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "")
        raw = resp.text
        if "text/html" not in content_type:
            text = raw.replace("\r\n", "\n")
            return {
                "content_type": content_type,
                "raw": raw,
                "main_text": text,
                "full_text": text,
                "analysis_text": text,
            }

        main_html = ""
        try:
            main_html = Document(raw).summary(html_partial=True)
        except Exception:  # noqa: BLE001
            main_html = ""
        main_text = self._html_to_text(main_html) if main_html else ""
        full_text = self._html_to_text(raw)
        analysis_text = self._merge_text_variants(main_text, full_text) or full_text or raw
        return {
            "content_type": content_type,
            "raw": raw,
            "main_text": main_text,
            "full_text": full_text,
            "analysis_text": analysis_text,
        }

    def _fetch_readable_text(self, url: str, timeout_s: int = 20) -> str:
        return self._fetch_source_bundle(url, timeout_s=timeout_s)["analysis_text"]

    def _split_text_into_chunks(self, text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
        normalized = text.replace("\r\n", "\n").strip()
        if not normalized:
            return []
        paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
        if not paragraphs:
            paragraphs = [normalized]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = paragraph if not current else f"{current}\n\n{paragraph}"
            if len(candidate) <= max_chars or not current:
                current = candidate
                continue
            chunks.append(current)
            overlap = current[-overlap_chars:].strip() if overlap_chars > 0 else ""
            current = paragraph if not overlap else f"{overlap}\n\n{paragraph}"
            if len(current) > max_chars:
                for idx in range(0, len(current), max_chars):
                    piece = current[idx : idx + max_chars].strip()
                    if piece:
                        chunks.append(piece)
                current = ""
        if current:
            chunks.append(current)
        return chunks

    def _load_curated_sources(self, ctx: WorkflowContext) -> list[dict[str, object]]:
        curated_path = ctx.session_dir / "02_curated_sources.json"
        if not curated_path.exists():
            return []
        try:
            sources = self.session_manager.read_json(curated_path)
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(sources, list):
            return []
        return [src for src in sources if isinstance(src, dict)]

    def _source_catalog_markdown(self, sources: list[dict[str, object]]) -> str:
        lines = [
            "| Ref | Title | Type | Credibility | Priority | URL |",
            "| - | - | - | - | - | - |",
        ]
        for idx, src in enumerate(sources, start=1):
            title = str(src.get("title", f"Source {idx}")).replace("|", "\\|")
            url = str(src.get("url", "")).replace("|", "\\|")
            source_type = str(src.get("type", "unknown")).replace("|", "\\|")
            credibility = str(src.get("credibility", "")).replace("|", "\\|")
            priority = str(src.get("priority", "")).replace("|", "\\|")
            lines.append(f"| [{idx}] | {title} | {source_type} | {credibility} | {priority} | {url} |")
        return "\n".join(lines)

    def _references_markdown(self, sources: list[dict[str, object]]) -> str:
        refs: list[str] = ["## References"]
        for idx, src in enumerate(sources, start=1):
            title = str(src.get("title", f"Source {idx}")).strip()
            url = str(src.get("url", "")).strip()
            source_type = str(src.get("type", "")).strip()
            why = str(src.get("why_relevant", "")).strip()
            refs.append(f"[{idx}] {title}. {source_type}. {url}")
            if why:
                refs.append(f"    Relevance: {why}")
        return "\n".join(refs)

    def _knowledge_outline_markdown(self, ctx: WorkflowContext) -> str:
        kb = self.session_manager.knowledge_base_paths(ctx.state.session_id)
        sections: list[str] = []
        if kb.core_concepts_path.exists():
            data = self._safe_json(kb.core_concepts_path.read_text(encoding="utf-8"))
            core = data.get("core_concepts")
            if isinstance(core, list) and core:
                lines = ["## Knowledge Base Core Concepts"]
                for item in core[:20]:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    definition = str(item.get("definition", "")).strip()
                    why = str(item.get("why_load_bearing", "")).strip()
                    lines.append(f"- {name}: {definition} Why it matters: {why}".strip())
                sections.append("\n".join(lines))
        if kb.drill_pack_path.exists():
            drill_text = kb.drill_pack_path.read_text(encoding="utf-8").strip()
            if drill_text:
                sections.append("## Drill Pack Snapshot\n" + drill_text)
        return "\n\n".join(sections).strip()

    def _build_toc(self, report_md: str) -> str:
        entries: list[str] = []
        for line in report_md.splitlines():
            if not line.startswith("## "):
                continue
            heading = line[3:].strip()
            if not heading:
                continue
            anchor = re.sub(r"[^a-z0-9 -]", "", heading.lower()).replace(" ", "-")
            entries.append(f"- [{heading}](#{anchor})")
        return "## Table of Contents\n" + ("\n".join(entries) if entries else "- No sections found")

    def _compiler_source(self, ctx: WorkflowContext) -> str | None:
        notebook = ctx.session_dir / "04_master_notebook.md"
        parts: list[str] = []
        if notebook.exists():
            try:
                parts.append(notebook.read_text(encoding="utf-8"))
            except OSError as e:
                self.console.print(f"[yellow]Unable to read notebook:[/yellow] {notebook} ({e})")
        extracted_dir = ctx.session_dir / "03_extracted"
        if extracted_dir.exists():
            try:
                extracted_files = sorted(extracted_dir.glob("*.md"))
            except OSError as e:
                self.console.print(f"[yellow]Unable to list extracted files:[/yellow] {extracted_dir} ({e})")
                return None
            for p in extracted_files:
                try:
                    parts.append(p.read_text(encoding="utf-8"))
                except OSError as e:
                    self.console.print(f"[yellow]Unable to read extracted file:[/yellow] {p} ({e})")
        if parts:
            return "\n\n---\n\n".join(parts)
        return None

    def _compile(self, ctx: WorkflowContext, *, compile_type: str = "auto-hypergraph") -> None:
        if compile_type not in self.AUTO_TYPES:
            if compile_type != "auto-hypergraph":
                self.console.print(f"Unknown type: {compile_type}")
                return
        source = self._compiler_source(ctx)
        if not source:
            self.console.print("Missing notebook or extractions. Resume the session to generate them first.")
            return
        client = self._client(ctx)
        kb = self.session_manager.knowledge_base_paths(ctx.state.session_id)

        hg_template = client.prompt_from_file(ctx.prompts_dir / "compile_auto_hypergraph_prompt.txt")
        hg_prompt = client.render_template(
            hg_template,
            {
                "topic": ctx.state.topic,
                "content": source[:220000],
            },
        )
        hg_text = client.chat_text(system="You are Grok.", user=hg_prompt)
        hg_data = self._safe_json(hg_text)
        self.session_manager.write_json(kb.auto_types_dir / "auto_hypergraph.json", hg_data)
        self.session_manager.write_json(kb.hypergraph_path, hg_data)

        concepts_template = client.prompt_from_file(ctx.prompts_dir / "core_concepts_prompt.txt")
        concepts_prompt = client.render_template(
            concepts_template,
            {
                "topic": ctx.state.topic,
                "content": source[:220000],
                "hypergraph_json": json.dumps(hg_data, ensure_ascii=False)[:120000],
            },
        )
        concepts_text = client.chat_text(system="You are Grok.", user=concepts_prompt)
        concepts_data = self._safe_json(concepts_text)
        self.session_manager.write_json(kb.core_concepts_path, concepts_data)
        self.console.print(f"Saved knowledge base to {kb.base_dir}")

    def _drill(self, ctx: WorkflowContext, *, drill_mode: str = "backward") -> None:
        if drill_mode != "backward":
            self.console.print(f"Unknown drill mode: {drill_mode}")
            return
        kb = self.session_manager.knowledge_base_paths(ctx.state.session_id)
        if not kb.core_concepts_path.exists():
            self._compile(ctx, compile_type="auto-hypergraph")
        if not kb.core_concepts_path.exists():
            self.console.print("Missing core concepts. Run compile first.")
            return
        core = kb.core_concepts_path.read_text(encoding="utf-8")
        client = self._client(ctx)
        template = client.prompt_from_file(ctx.prompts_dir / "drill_pack_prompt.txt")
        prompt = client.render_template(
            template,
            {"topic": ctx.state.topic, "core_concepts_json": core[:200000]},
        )
        text = client.chat_text(system="You are Grok.", user=prompt)
        data = self._safe_json(text)
        drill_md = str(data.get("drill_pack_markdown") or "")
        if not drill_md.strip():
            drill_md = self._strip_code_fences(text)
        self._write(kb.drill_pack_path, drill_md)
        if "drill_questions" in data:
            self.session_manager.write_json(kb.drill_questions_path, data.get("drill_questions"))
        else:
            self.session_manager.write_json(kb.drill_questions_path, data)
        self.console.print(f"Saved drill pack to {kb.drill_pack_path}")

    def _feed(self, ctx: WorkflowContext, new_doc: Path) -> None:
        if not new_doc.exists() or not new_doc.is_file():
            self.console.print(f"File not found: {new_doc}")
            return
        kb = self.session_manager.knowledge_base_paths(ctx.state.session_id)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        dest = kb.feed_docs_dir / f"{stamp}_{new_doc.name}"
        self._write(dest, new_doc.read_text(encoding="utf-8", errors="replace"))
        if not kb.hypergraph_path.exists():
            self._compile(ctx, compile_type="auto-hypergraph")
            return

        existing = kb.hypergraph_path.read_text(encoding="utf-8")
        client = self._client(ctx)
        template = client.prompt_from_file(ctx.prompts_dir / "update_hypergraph_prompt.txt")
        prompt = client.render_template(
            template,
            {
                "topic": ctx.state.topic,
                "existing_hypergraph_json": existing[:160000],
                "new_document": dest.read_text(encoding="utf-8")[:160000],
            },
        )
        updated_text = client.chat_text(system="You are Grok.", user=prompt)
        updated = self._safe_json(updated_text)
        self.session_manager.write_json(kb.hypergraph_path, updated)
        self.session_manager.write_json(kb.auto_types_dir / "auto_hypergraph.json", updated)
        self.console.print(f"Updated hypergraph at {kb.hypergraph_path}")

    def _show(self, ctx: WorkflowContext) -> None:
        kb = self.session_manager.knowledge_base_paths(ctx.state.session_id)
        if not kb.hypergraph_path.exists():
            self.console.print("Missing hypergraph.json. Run compile first.")
            return
        data = self._safe_json(kb.hypergraph_path.read_text(encoding="utf-8"))
        mermaid = self._hypergraph_to_mermaid(data)
        self._write(kb.mermaid_path, mermaid)
        self.console.print(f"Saved Mermaid to {kb.mermaid_path}")

    def _hypergraph_to_mermaid(self, data: dict[str, object]) -> str:
        nodes = data.get("nodes")
        edges = data.get("edges") or data.get("hyperedges")
        lines: list[str] = ["graph TD"]
        if isinstance(nodes, list):
            for n in nodes[:200]:
                if isinstance(n, dict):
                    nid = str(n.get("id") or n.get("name") or "").strip()
                    label = str(n.get("label") or nid).strip()
                    if nid:
                        lines.append(f'  {nid}["{label}"]')
        if isinstance(edges, list):
            for e in edges[:400]:
                if not isinstance(e, dict):
                    continue
                rel = str(e.get("relation") or e.get("label") or "").strip()
                members = e.get("nodes") or e.get("members") or e.get("participants")
                if isinstance(members, list) and len(members) >= 2:
                    a = str(members[0]).strip()
                    b = str(members[1]).strip()
                    if a and b:
                        if rel:
                            lines.append(f"  {a} -->|{rel}| {b}")
                        else:
                            lines.append(f"  {a} --> {b}")
        return "\n".join(lines) + "\n"

    def _phase0_scope(self, ctx: WorkflowContext) -> None:
        try:
            client = self._client(ctx)
        except GrokError as e:
            self.console.print(f"[red]{e}[/red]")
            self.console.print("Create a .env file (see .env.example) and retry.")
            return

        template = client.prompt_from_file(ctx.prompts_dir / "scope_prompt.txt")
        user_prompt = client.render_template(
            template,
            {"topic": ctx.state.topic, "focus": ctx.state.focus or ""},
        )
        scope_md = client.chat_text(system="You are Grok.", user=user_prompt)
        scope_path = ctx.run_dir / "00_scope.md"
        self._write(scope_path, scope_md)

        self.console.print(scope_md)
        while True:
            ans = input("Do you confirm this scope? (yes/edit/cancel) ").strip().lower()
            if ans == "cancel":
                self.console.print("Canceled.")
                return
            if ans == "edit":
                temp = ctx.run_dir / "00_scope_edit.md"
                temp.write_text(scope_md, encoding="utf-8")
                editor = os.environ.get("EDITOR")
                if editor:
                    os.system(f"{editor} {temp}")
                scope_md = temp.read_text(encoding="utf-8")
                self.console.print(scope_md)
                continue
            if ans == "yes":
                self._write(ctx.session_dir / "00_scope_confirmed.md", scope_md)
                ctx.state.current_phase = 1
                self.session_manager.save_state(ctx.state)
                self.console.print("Scope confirmed. Resume to run discovery.")
                return

    def _phase1_discovery(self, ctx: WorkflowContext, since_last_run: bool = False) -> None:
        client = self._client(ctx)
        template = client.prompt_from_file(ctx.prompts_dir / "discovery_prompt.txt")
        user_prompt = client.render_template(
            template,
            {
                "topic": ctx.state.topic,
                "focus": ctx.state.focus or "",
                "since_last_run": "yes" if since_last_run else "no",
            },
        )
        discovery_md = client.chat_text(system="You are Grok.", user=user_prompt)
        self._write(ctx.run_dir / "01_discovery_table.md", discovery_md)
        self._write(ctx.session_dir / "01_discovery_table.md", discovery_md)
        self.console.print("Saved discovery table.")

    def _phase2_curation(self, ctx: WorkflowContext) -> None:
        client = self._client(ctx)
        discovery_path = ctx.session_dir / "01_discovery_table.md"
        if not discovery_path.exists():
            self.console.print("Missing discovery table. Resume from Phase 1.")
            return
        discovery_md = discovery_path.read_text(encoding="utf-8")

        table = Table(title="Discovery Sources")
        table.add_column("Preview")
        lines = [ln for ln in discovery_md.splitlines() if ln.strip()]
        preview = "\n".join(lines[:80])
        table.add_row(preview)
        self.console.print(table)

        self.console.print(
            "Enter numbers to KEEP (comma separated), or 'all', or 'add <url1> <url2>', or 'remove 2,5'. Type 'gap' first to let Grok suggest missing topics."
        )
        selection = input().strip()
        template = client.prompt_from_file(ctx.prompts_dir / "curation_prompt.txt")
        user_prompt = client.render_template(
            template,
            {"discovery_table": discovery_md, "selection": selection, "topic": ctx.state.topic},
        )
        curated_json = client.chat_text(system="You are Grok.", user=user_prompt)
        curated_path = ctx.run_dir / "02_curated_sources.json"
        self._write(curated_path, curated_json)
        self._write(ctx.session_dir / "02_curated_sources.json", curated_json)

        gap_template = client.prompt_from_file(ctx.prompts_dir / "gap_prompt.txt")
        gap_prompt = client.render_template(
            gap_template,
            {"curated_sources_json": curated_json, "topic": ctx.state.topic},
        )
        gap_report = client.chat_text(system="You are Grok.", user=gap_prompt)
        self._write(ctx.run_dir / "02_gap_report.md", gap_report)
        self.console.print(gap_report)

        ans = input("Type 'approve' to continue: ").strip().lower()
        if ans != "approve":
            self.console.print("Not approved. Resume again to repeat curation.")
            return

        ctx.state.current_phase = 3
        self.session_manager.save_state(ctx.state)
        self.console.print("Curated sources approved. Resume to extract.")

    def _phase3_extraction(self, ctx: WorkflowContext) -> None:
        client = self._client(ctx)
        curated_path = ctx.session_dir / "02_curated_sources.json"
        if not curated_path.exists():
            self.console.print("Missing curated sources. Resume from Phase 2.")
            return

        curated_raw = curated_path.read_text(encoding="utf-8")
        template = client.prompt_from_file(ctx.prompts_dir / "extraction_prompt.txt")

        extracted_dir = ctx.run_dir / "03_extracted"
        extracted_dir.mkdir(parents=True, exist_ok=True)
        session_extracted_dir = ctx.session_dir / "03_extracted"
        session_extracted_dir.mkdir(parents=True, exist_ok=True)
        run_snapshot_dir = ctx.run_dir / "03_source_snapshots"
        run_snapshot_dir.mkdir(parents=True, exist_ok=True)
        session_snapshot_dir = ctx.session_dir / "03_source_snapshots"
        session_snapshot_dir.mkdir(parents=True, exist_ok=True)
        run_chunk_dir = ctx.run_dir / "03_extracted_chunks"
        run_chunk_dir.mkdir(parents=True, exist_ok=True)
        session_chunk_dir = ctx.session_dir / "03_extracted_chunks"
        session_chunk_dir.mkdir(parents=True, exist_ok=True)

        extraction_plan = client.chat_text(
            system="You are Grok.",
            user=client.render_template(
                client.prompt_from_file(ctx.prompts_dir / "extraction_plan_prompt.txt"),
                {"curated_sources_json": curated_raw, "topic": ctx.state.topic},
            ),
        )
        self._write(ctx.run_dir / "03_extraction_plan.md", extraction_plan)

        sources = []
        try:
            sources = self.session_manager.read_json(curated_path)
        except Exception:
            pass
        if not isinstance(sources, list):
            self.console.print("Curated sources JSON is not a list. Fix it and resume.")
            return

        for i, src in enumerate(sources, start=1):
            url = str(src.get("url", "")).strip()
            title = str(src.get("title", f"source-{i}")).strip()
            if not url:
                continue
            self.console.print(f"Extracting {i}/{len(sources)}: {title}")
            try:
                bundle = self._fetch_source_bundle(url)
            except Exception as e:  # noqa: BLE001
                self.console.print(f"[yellow]Fetch failed:[/yellow] {url} ({e})")
                continue

            base_name = f"{i:03d}_{self._slug(title)[:50]}"
            parsed = urlparse(url)
            snapshot_header = "\n".join(
                [
                    f"# Source Snapshot [{i}]",
                    f"- Title: {title}",
                    f"- URL: {url}",
                    f"- Host: {parsed.netloc or 'unknown'}",
                    f"- Type: {src.get('type', 'unknown')}",
                    f"- Priority: {src.get('priority', 'unknown')}",
                    f"- Credibility: {src.get('credibility', 'unknown')}",
                ]
            )
            raw_suffix = ".html" if "text/html" in bundle.get("content_type", "") else ".txt"
            self._write(run_snapshot_dir / f"{base_name}_raw{raw_suffix}", bundle["raw"])
            self._write(session_snapshot_dir / f"{base_name}_raw{raw_suffix}", bundle["raw"])
            source_text = "\n\n".join(
                [
                    snapshot_header,
                    "## Why This Source Was Kept",
                    str(src.get("why_relevant", "")).strip() or "No rationale recorded.",
                    "## Preserved Source Text",
                    bundle["analysis_text"].strip(),
                ]
            ).strip()
            self._write(run_snapshot_dir / f"{base_name}_text.md", source_text)
            self._write(session_snapshot_dir / f"{base_name}_text.md", source_text)

            chunks = self._split_text_into_chunks(
                source_text,
                max_chars=self.SOURCE_CHUNK_CHARS,
                overlap_chars=self.SOURCE_CHUNK_OVERLAP,
            )
            chunk_sections: list[str] = []
            for chunk_idx, chunk in enumerate(chunks, start=1):
                user_prompt = client.render_template(
                    template,
                    {
                        "topic": ctx.state.topic,
                        "title": title,
                        "url": url,
                        "source_ref": f"[{i}]",
                        "chunk_number": chunk_idx,
                        "chunk_count": len(chunks),
                        "content": chunk,
                    },
                )
                extracted_chunk = client.chat_text(system="You are Grok.", user=user_prompt)
                chunk_path = run_chunk_dir / f"{base_name}_chunk_{chunk_idx:02d}.md"
                self._write(chunk_path, extracted_chunk)
                self._write(session_chunk_dir / f"{base_name}_chunk_{chunk_idx:02d}.md", extracted_chunk)
                chunk_sections.append(f"## Chunk {chunk_idx} of {len(chunks)}\n\n{extracted_chunk.strip()}")

            extracted_md = "\n\n".join(
                [
                    f"# Source Dossier [{i}] {title}",
                    f"- URL: {url}",
                    f"- Type: {src.get('type', 'unknown')}",
                    f"- Priority: {src.get('priority', 'unknown')}",
                    f"- Credibility: {src.get('credibility', 'unknown')}",
                    "## Retention Notes",
                    "This dossier preserves chunk-level evidence so later report stages can use detailed source material rather than a single summary.",
                    "## Why Relevant",
                    str(src.get("why_relevant", "")).strip() or "No rationale recorded.",
                    "## Chunk Index",
                    "\n".join(f"- Chunk {idx} / {len(chunks)}" for idx in range(1, len(chunks) + 1)),
                    *chunk_sections,
                ]
            ).strip()
            out_path = extracted_dir / f"{i:03d}.md"
            self._write(out_path, extracted_md)
            self._write(session_extracted_dir / f"{i:03d}.md", extracted_md)
        self._write(ctx.session_dir / "03_extracted_index.txt", "Generated in latest run")

    def _phase4_notebook(self, ctx: WorkflowContext) -> None:
        extracted_dir = ctx.session_dir / "03_extracted"
        if not extracted_dir.exists():
            self.console.print("No extracted sources found in this run. Resume from Phase 3.")
            return
        extracted_parts = []
        for p in sorted(extracted_dir.glob("*.md")):
            extracted_parts.append(p.read_text(encoding="utf-8"))
        sources = self._load_curated_sources(ctx)
        notebook_parts = [
            "# Master Notebook",
            f"Topic: {ctx.state.topic}",
            "## Notebook Purpose",
            "This notebook is an evidence-preserving workspace. It keeps detailed source dossiers intact so synthesis can happen section by section without losing technical detail.",
            "## Source Catalog",
            self._source_catalog_markdown(sources) if sources else "No curated source catalog available.",
        ]
        knowledge_outline = self._knowledge_outline_markdown(ctx)
        if knowledge_outline:
            notebook_parts.append(knowledge_outline)
        notebook_parts.append("## Source Dossiers")
        notebook_parts.extend(extracted_parts)
        notebook = "\n\n---\n\n".join(notebook_parts)
        self._write(ctx.run_dir / "04_master_notebook.md", notebook)
        self._write(ctx.session_dir / "04_master_notebook.md", notebook)

    def _phase5_synthesis(self, ctx: WorkflowContext, force: bool = False) -> None:
        client = self._client(ctx)
        notebook_path = ctx.session_dir / "04_master_notebook.md"
        if not notebook_path.exists():
            self.console.print("Missing notebook. Resume from Phase 4.")
            return

        notebook = notebook_path.read_text(encoding="utf-8")
        notebook_chunks = self._split_text_into_chunks(
            notebook,
            max_chars=self.NOTEBOOK_CHUNK_CHARS,
            overlap_chars=self.SOURCE_CHUNK_OVERLAP,
        )
        if not notebook_chunks:
            self.console.print("Notebook is empty. Resume from Phase 4.")
            return
        sources = self._load_curated_sources(ctx)
        source_catalog = self._source_catalog_markdown(sources) if sources else "No curated sources available."
        knowledge_outline = self._knowledge_outline_markdown(ctx) or "No knowledge-base artifacts available yet."
        evidence_template = client.prompt_from_file(ctx.prompts_dir / "section_evidence_prompt.txt")
        section_template = client.prompt_from_file(ctx.prompts_dir / "section_draft_prompt.txt")
        section_evidence_dir = ctx.run_dir / "05_section_evidence"
        section_evidence_dir.mkdir(parents=True, exist_ok=True)
        session_evidence_dir = ctx.session_dir / "05_section_evidence"
        session_evidence_dir.mkdir(parents=True, exist_ok=True)
        section_draft_dir = ctx.run_dir / "05_section_drafts"
        section_draft_dir.mkdir(parents=True, exist_ok=True)
        session_section_draft_dir = ctx.session_dir / "05_section_drafts"
        session_section_draft_dir.mkdir(parents=True, exist_ok=True)

        drafted_sections: list[str] = []
        for section_name in self.REPORT_SECTIONS:
            section_slug = self._slug(section_name)
            evidence_packets: list[str] = []
            for chunk_idx, chunk in enumerate(notebook_chunks, start=1):
                evidence_prompt = client.render_template(
                    evidence_template,
                    {
                        "topic": ctx.state.topic,
                        "section_name": section_name,
                        "source_catalog": source_catalog,
                        "chunk_number": chunk_idx,
                        "chunk_count": len(notebook_chunks),
                        "notebook_chunk": chunk,
                    },
                )
                evidence_md = client.chat_text(system="You are Grok.", user=evidence_prompt)
                evidence_packets.append(f"### Evidence Packet {chunk_idx}\n\n{evidence_md.strip()}")
                packet_name = f"{section_slug}_chunk_{chunk_idx:02d}.md"
                self._write(section_evidence_dir / packet_name, evidence_md)
                self._write(session_evidence_dir / packet_name, evidence_md)

            section_prompt = client.render_template(
                section_template,
                {
                    "topic": ctx.state.topic,
                    "section_name": section_name,
                    "source_catalog": source_catalog,
                    "knowledge_outline": knowledge_outline,
                    "section_evidence": "\n\n".join(evidence_packets),
                },
            )
            section_md = client.chat_text(system="You are Grok.", user=section_prompt).strip()
            drafted_sections.append(section_md)
            section_name_path = f"{section_slug}.md"
            self._write(section_draft_dir / section_name_path, section_md)
            self._write(session_section_draft_dir / section_name_path, section_md)

        draft_parts = [
            f"# Detailed Research Draft: {ctx.state.topic}",
            "## Scope and Coverage",
            "This draft is assembled section by section from detailed source dossiers, chunk-level extraction outputs, and any available structured knowledge-base artifacts.",
            "## Source Catalog",
            source_catalog,
            *drafted_sections,
        ]
        if knowledge_outline and "No knowledge-base artifacts available yet." not in knowledge_outline:
            draft_parts.extend(["## Knowledge Base Alignment", knowledge_outline])
        draft_parts.append(self._references_markdown(sources))
        draft = "\n\n".join(part for part in draft_parts if part.strip())
        v = len(list(ctx.session_dir.glob("05_draft_v*.md"))) + 1
        draft_name = f"05_draft_v{v}.md"
        self._write(ctx.run_dir / draft_name, draft)
        self._write(ctx.session_dir / draft_name, draft)

        self.console.print(f"Saved {draft_name}.")
        self.console.print(
            "Reply with: approve | revise <section> <feedback> | add-section \"Title\" | gap-check"
        )
        feedback = input().strip()
        if feedback.lower() == "approve":
            ctx.state.current_phase = 6
            self.session_manager.save_state(ctx.state)
            self.console.print("Draft approved. Resume to full-collection selection (H3).")
            return

        revise_template = client.prompt_from_file(ctx.prompts_dir / "revise_prompt.txt")
        revised = client.chat_text(
            system="You are Grok.",
            user=client.render_template(
                revise_template,
                {
                    "draft": draft,
                    "feedback": feedback,
                    "topic": ctx.state.topic,
                },
            ),
        )
        v2 = v + 1
        draft_name2 = f"05_draft_v{v2}.md"
        self._write(ctx.run_dir / draft_name2, revised)
        self._write(ctx.session_dir / draft_name2, revised)
        self.console.print(f"Saved {draft_name2}. Resume to review again (H2).")

    def _phase6_full_collection(self, ctx: WorkflowContext) -> None:
        sources = self._load_curated_sources(ctx)
        if not sources:
            self.console.print("Missing curated sources.")
            return

        table = Table(title="Select sources for full offline Markdown copies")
        table.add_column("#")
        table.add_column("Title")
        table.add_column("URL")
        for i, src in enumerate(sources, start=1):
            table.add_row(str(i), str(src.get("title", ""))[:60], str(src.get("url", ""))[:80])
        self.console.print(table)
        ans = input("Which sources do you want FULL offline Markdown copies of? (numbers or 'all' or 'none') ").strip().lower()
        if ans == "none":
            ctx.state.current_phase = 7
            self.session_manager.save_state(ctx.state)
            self.console.print("Skipping full collection. Resume to finalize.")
            return

        picks: set[int] = set()
        if ans == "all":
            picks = set(range(1, len(sources) + 1))
        else:
            for part in ans.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    picks.add(int(part))
                except ValueError:
                    continue

        full_dir = ctx.run_dir / "06_full_sources"
        full_dir.mkdir(parents=True, exist_ok=True)
        session_full_dir = ctx.session_dir / "06_full_sources"
        session_full_dir.mkdir(parents=True, exist_ok=True)
        for i in sorted(picks):
            if i < 1 or i > len(sources):
                continue
            url = str(sources[i - 1].get("url", ""))
            if not url:
                continue
            try:
                bundle = self._fetch_source_bundle(url)
            except Exception:
                continue
            content = "\n\n".join(
                [
                    f"# Full Offline Copy [{i}] {sources[i - 1].get('title', '')}",
                    f"- URL: {url}",
                    "## Preserved Content",
                    bundle["analysis_text"].strip(),
                ]
            )
            self._write(full_dir / f"{i:03d}.md", content)
            self._write(session_full_dir / f"{i:03d}.md", content)
        ctx.state.current_phase = 7
        self.session_manager.save_state(ctx.state)
        self.console.print("Full collection saved. Finalizing now.")
        self._phase7_final_polish(ctx)
        ctx.state.current_phase = 8
        self.session_manager.save_state(ctx.state)
        self.console.print(f"Final report ready at {ctx.session_dir / 'FINAL_REPORT.md'}")

    def _phase7_final_polish(self, ctx: WorkflowContext) -> None:
        client = self._client(ctx)
        notebook_path = ctx.session_dir / "04_master_notebook.md"
        drafts = sorted(ctx.session_dir.glob("05_draft_v*.md"))
        if not notebook_path.exists() or not drafts:
            self.console.print("Missing notebook or draft.")
            return
        latest_draft = drafts[-1].read_text(encoding="utf-8").strip()
        sources = self._load_curated_sources(ctx)
        source_catalog = self._source_catalog_markdown(sources) if sources else "No curated sources available."
        knowledge_outline = self._knowledge_outline_markdown(ctx) or "No knowledge-base artifacts available yet."
        final_template = client.prompt_from_file(ctx.prompts_dir / "final_polish_prompt.txt")
        executive_summary = client.chat_text(
            system="You are Grok.",
            user=client.render_template(
                final_template,
                {
                    "topic": ctx.state.topic,
                    "report_body": latest_draft,
                    "source_catalog": source_catalog,
                    "knowledge_outline": knowledge_outline,
                },
            ),
        ).strip()
        glossary_template = client.prompt_from_file(ctx.prompts_dir / "glossary_prompt.txt")
        glossary = client.chat_text(
            system="You are Grok.",
            user=client.render_template(
                glossary_template,
                {
                    "topic": ctx.state.topic,
                    "report_body": latest_draft,
                    "knowledge_outline": knowledge_outline,
                },
            ),
        ).strip()
        draft_body = latest_draft
        if draft_body.startswith("# "):
            draft_body = "\n".join(draft_body.splitlines()[1:]).strip()
        final_parts = [
            f"# Final Research Report: {ctx.state.topic}",
            self._build_toc(draft_body),
            "## Executive Summary",
            executive_summary,
            draft_body,
            "## Source Catalog",
            source_catalog,
        ]
        if knowledge_outline and "No knowledge-base artifacts available yet." not in knowledge_outline:
            final_parts.extend(["## Knowledge Base Overview", knowledge_outline])
        final_parts.extend(["## Glossary", glossary])
        final_md = "\n\n".join(part for part in final_parts if part.strip())
        self._write(ctx.run_dir / "FINAL_REPORT.md", final_md)
        self._write(ctx.session_dir / "FINAL_REPORT.md", final_md)

        image_template = client.prompt_from_file(ctx.prompts_dir / "images_prompt.txt")
        image_prompts = client.chat_text(
            system="You are Grok.",
            user=client.render_template(image_template, {"report": final_md}),
        )
        self._write(ctx.run_dir / "images_to_generate.md", image_prompts)
        self._write(ctx.session_dir / "images_to_generate.md", image_prompts)

    def _generate_images(self, ctx: WorkflowContext) -> None:
        report = ctx.session_dir / "FINAL_REPORT.md"
        if not report.exists():
            self.console.print("Missing FINAL_REPORT.md")
            return
        client = self._client(ctx)
        image_template = client.prompt_from_file(ctx.prompts_dir / "images_prompt.txt")
        image_prompts = client.chat_text(
            system="You are Grok.",
            user=client.render_template(image_template, {"report": report.read_text(encoding="utf-8")}),
        )
        self._write(ctx.run_dir / "images_to_generate.md", image_prompts)
        self._write(ctx.session_dir / "images_to_generate.md", image_prompts)
        self.console.print(f"Saved {ctx.session_dir / 'images_to_generate.md'}")
