import csv
import io
from pathlib import Path
from types import SimpleNamespace

import ga4_definitions


def test_csv_file_preserves_rows_and_embedded_newlines_on_windows(monkeypatch, tmp_path):
    target = tmp_path / "report.csv"
    data = []
    original = Path.open

    class Buffer(io.BytesIO):
        def close(self):
            data.append(self.getvalue())
            super().close()

    def windows_open(path, mode="r", buffering=-1, encoding=None, errors=None, newline=None):
        if path == target and mode == "w":
            return io.TextIOWrapper(
                Buffer(), encoding="utf-8", newline="\r\n" if newline is None else newline
            )
        return original(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", windows_open)
    rendered = ga4_definitions._to_csv({"rows": [{"label": "two\r\nlines", "sessions": "3"}]})
    ga4_definitions._write_output(rendered, SimpleNamespace(output=str(target)))
    assert b"\r\r\n" not in data[0]
    assert list(csv.reader(io.StringIO(data[0].decode(), newline=""))) == [
        ["label", "sessions"],
        ["two\r\nlines", "3"],
    ]
