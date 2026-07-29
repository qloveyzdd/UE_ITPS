from __future__ import annotations

from tests.fixture import FixtureTestCase


class SourceLayerTestCase(FixtureTestCase):
    def source_result(self, script: str, *extra: str) -> dict:
        return self.selected_source_result(
            script,
            self.fixture.source_file,
            *extra,
        )

    def selected_source_result(
        self,
        script: str,
        source,
        *extra: str,
        expected_code: int = 0,
    ) -> dict:
        return self.cli(
            script,
            "--source",
            str(source),
            *extra,
            expected_code=expected_code,
        )
