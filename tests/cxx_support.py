from __future__ import annotations

from tests.support import WorkspaceTestCase


class CxxAnalysisTestCase(WorkspaceTestCase):
    def source_result(
        self,
        script: str,
        *arguments: str,
        source=None,
        expected_code: int = 0,
    ) -> dict:
        return self.cli(
            script,
            "--source",
            str(source or self.fixture.source_file),
            *arguments,
            expected_code=expected_code,
        )
