"""
Proof-of-work solver for DeepSeek's chat completion endpoint.

DeepSeek gates `POST /api/v0/chat/completion` behind a proof-of-work header
(`x-ds-pow-response`). The PoW algorithm ("DeepSeekHashV1") is shipped as a
WebAssembly module the website loads from its own CDN
(fe-static.deepseek.com/.../sha3_wasm_bg.wasm). Rather than reimplement its
exact float64 hashing logic, we run DeepSeek's own module — the same code the
browser runs — inside the `wasmtime` sandbox (no file/network access).

Public API:
    solver = DeepSeekPow()                      # loads the wasm once
    header = solver.make_header(challenge_dict)  # -> base64 x-ds-pow-response value

`challenge_dict` is the `biz_data.challenge` object returned by
`POST /api/v0/chat/create_pow_challenge`.
"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path
from typing import Optional

import wasmtime

WASM_PATH = Path(__file__).resolve().parent / "sha3_wasm_bg.wasm"


class DeepSeekPow:
    def __init__(self, wasm_path: Path = WASM_PATH):
        self._store = wasmtime.Store()
        module = wasmtime.Module.from_file(self._store.engine, str(wasm_path))
        self._inst = wasmtime.Instance(self._store, module, [])
        exp = self._inst.exports(self._store)
        self._memory: wasmtime.Memory = exp["memory"]
        self._solve = exp["wasm_solve"]
        self._malloc = exp["__wbindgen_export_0"]            # malloc(size, align)
        self._add_to_stack = exp["__wbindgen_add_to_stack_pointer"]

    def _write_str(self, text: str) -> tuple[int, int]:
        """malloc + copy a UTF-8 string into wasm memory; return (ptr, len)."""
        data = text.encode("utf-8")
        ptr = self._malloc(self._store, len(data), 1)
        base = self._memory.data_ptr(self._store)
        for i, b in enumerate(data):
            base[ptr + i] = b
        return ptr, len(data)

    def solve(self, challenge: str, prefix: str, difficulty: float) -> Optional[int]:
        """Return the integer PoW answer, or None if the module reports failure.

        Mirrors the website's wasm-bindgen call:
            wasm_solve(retptr, challenge_ptr, challenge_len,
                       prefix_ptr, prefix_len, difficulty)
        with a 16-byte return slot reserved on the shadow stack. The slot holds
        an i32 status flag at +0 and an f64 answer at +8.
        """
        retptr = self._add_to_stack(self._store, -16)
        try:
            c_ptr, c_len = self._write_str(challenge)
            p_ptr, p_len = self._write_str(prefix)
            self._solve(self._store, retptr, c_ptr, c_len, p_ptr, p_len, float(difficulty))

            mem = self._memory.data_ptr(self._store)
            status = struct.unpack("<i", bytes(mem[retptr:retptr + 4]))[0]
            value = struct.unpack("<d", bytes(mem[retptr + 8:retptr + 16]))[0]
        finally:
            self._add_to_stack(self._store, 16)

        if status == 0:
            return None
        return int(value)

    def make_header(self, challenge: dict) -> str:
        """Build the base64 `x-ds-pow-response` header value from a challenge dict."""
        prefix = f"{challenge['salt']}_{challenge['expire_at']}_"
        answer = self.solve(challenge["challenge"], prefix, challenge["difficulty"])
        if answer is None:
            raise RuntimeError("PoW solver returned no answer (challenge expired?)")
        payload = {
            "algorithm": challenge["algorithm"],
            "challenge": challenge["challenge"],
            "salt": challenge["salt"],
            "answer": answer,
            "signature": challenge["signature"],
            "target_path": challenge["target_path"],
        }
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return base64.b64encode(raw).decode("utf-8")
