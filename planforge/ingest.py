"""Read a message file exactly as given and cut it into numbered blocks.

The model later groups blocks into messages by block number, so the original text is never
retyped or paraphrased: evidence shown in the trace/UI is always the exact source text.
"""
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RawInput:
    path: str
    sha256: str
    text: str
    blocks: list  # list[str], exact text of each block


def decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def split_blocks(text: str) -> list:
    """Blank-line separated groups; if the file has no blank lines, one line per block."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    groups, cur = [], []
    for ln in lines:
        if ln.strip():
            cur.append(ln.rstrip())
        elif cur:
            groups.append("\n".join(cur))
            cur = []
    if cur:
        groups.append("\n".join(cur))
    if len(groups) == 1 and groups[0].count("\n") >= 2:
        groups = [ln for ln in groups[0].split("\n") if ln.strip()]
    return groups


def read_input(path) -> RawInput:
    data = Path(path).read_bytes()
    text = decode(data)
    return RawInput(path=str(path), sha256=hashlib.sha256(data).hexdigest(), text=text,
                    blocks=split_blocks(text))


def from_text(text: str, name: str = "pasted.txt") -> RawInput:
    data = text.encode("utf-8")
    return RawInput(path=name, sha256=hashlib.sha256(data).hexdigest(), text=text, blocks=split_blocks(text))
