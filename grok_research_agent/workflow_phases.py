from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
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

    def run(self, session_id: str, command: str | None = None) -> None:
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
        preview = "\n".join(lines[:20])
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

    def _fetch_readable_text(self, url: str, timeout_s: int = 20) -> str:
        resp = self._http_get(url, timeout=timeout_s, headers={"User-Agent": "grok-research-agent/0.1"})
        resp.raise_for_status()
        if "text/html" in resp.headers.get("content-type", ""):
            doc = Document(resp.text)
            return doc.summary(html_partial=True)
        return resp.text

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
                raw = self._fetch_readable_text(url)
            except Exception as e:  # noqa: BLE001
                self.console.print(f"[yellow]Fetch failed:[/yellow] {url} ({e})")
                continue
            user_prompt = client.render_template(
                template,
                {"topic": ctx.state.topic, "title": title, "url": url, "content": raw[:200000]},
            )
            extracted_md = client.chat_text(system="You are Grok.", user=user_prompt)
            out_path = extracted_dir / f"{i:03d}.md"
            self._write(out_path, extracted_md)
            self._write(session_extracted_dir / f"{i:03d}.md", extracted_md)
        self._write(ctx.session_dir / "03_extracted_index.txt", "Generated in latest run")

    def _phase4_notebook(self, ctx: WorkflowContext) -> None:
        client = self._client(ctx)
        extracted_dir = ctx.session_dir / "03_extracted"
        if not extracted_dir.exists():
            self.console.print("No extracted sources found in this run. Resume from Phase 3.")
            return
        extracted_parts = []
        for p in sorted(extracted_dir.glob("*.md")):
            extracted_parts.append(p.read_text(encoding="utf-8"))
        merged = "\n\n---\n\n".join(extracted_parts)

        template = client.prompt_from_file(ctx.prompts_dir / "notebook_prompt.txt")
        user_prompt = client.render_template(
            template,
            {"topic": ctx.state.topic, "extractions": merged[:220000]},
        )
        notebook = client.chat_text(system="You are Grok.", user=user_prompt)
        self._write(ctx.run_dir / "04_master_notebook.md", notebook)
        self._write(ctx.session_dir / "04_master_notebook.md", notebook)

    def _phase5_synthesis(self, ctx: WorkflowContext, force: bool = False) -> None:
        client = self._client(ctx)
        notebook_path = ctx.session_dir / "04_master_notebook.md"
        if not notebook_path.exists():
            self.console.print("Missing notebook. Resume from Phase 4.")
            return

        template = client.prompt_from_file(ctx.prompts_dir / "synthesis_prompt.txt")
        user_prompt = client.render_template(
            template,
            {"topic": ctx.state.topic, "notebook": notebook_path.read_text(encoding="utf-8")[:240000]},
        )
        draft = client.chat_text(system="You are Grok.", user=user_prompt)
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
        curated_path = ctx.session_dir / "02_curated_sources.json"
        if not curated_path.exists():
            self.console.print("Missing curated sources.")
            return
        try:
            sources = self.session_manager.read_json(curated_path)
        except Exception:
            self.console.print("Curated sources JSON invalid.")
            return
        if not isinstance(sources, list):
            self.console.print("Curated sources JSON is not a list.")
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
                content = self._fetch_readable_text(url)
            except Exception:
                continue
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
        latest_draft = drafts[-1].read_text(encoding="utf-8")
        template = client.prompt_from_file(ctx.prompts_dir / "final_polish_prompt.txt")
        user_prompt = client.render_template(
            template,
            {
                "topic": ctx.state.topic,
                "notebook": notebook_path.read_text(encoding="utf-8")[:180000],
                "draft": latest_draft[:180000],
            },
        )
        final_md = client.chat_text(system="You are Grok.", user=user_prompt)
        self._write(ctx.run_dir / "FINAL_REPORT.md", final_md)
        self._write(ctx.session_dir / "FINAL_REPORT.md", final_md)

        image_template = client.prompt_from_file(ctx.prompts_dir / "images_prompt.txt")
        image_prompts = client.chat_text(
            system="You are Grok.",
            user=client.render_template(image_template, {"report": final_md[:200000]}),
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
            user=client.render_template(image_template, {"report": report.read_text(encoding='utf-8')[:200000]}),
        )
        self._write(ctx.run_dir / "images_to_generate.md", image_prompts)
        self._write(ctx.session_dir / "images_to_generate.md", image_prompts)
        self.console.print(f"Saved {ctx.session_dir / 'images_to_generate.md'}")
