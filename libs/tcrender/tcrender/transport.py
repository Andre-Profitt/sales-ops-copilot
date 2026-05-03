"""Transport layer: abstract `Transport` plus a concrete `SSHTransport`.

The transport is responsible for:
    1. Staging local copies of the .ppttc + (optional) template to a VM-local
       tempdir. ppttc.exe reads paths embedded in the .ppttc verbatim, and
       UNC paths resolved through SSH Session 0 reliably fail with access
       errors. Local staging avoids that entire class of bug.
    2. Patching the .ppttc's `template` field to point at the staged
       (or overridden) Windows path before invoking ppttc.exe.
    3. Running `ppttc.exe <input.ppttc> -o <output.pptx>` over SSH.
    4. Capturing the exit code, stdout, stderr, and the rendered .pptx.
    5. Ferrying the .pptx back to a Mac-side path via scp.

Stdlib-only -- subprocess + ssh + scp. No paramiko, no fabric.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PPTTC_EXE = r"C:\Program Files (x86)\think-cell\ppttc.exe"
DEFAULT_REMOTE_TEMP_ROOT = r"C:\Users\test\AppData\Local\Temp"
TAIL_BYTES = 2048
DEFAULT_TIMEOUT_SECONDS = 240.0


@dataclass(frozen=True)
class TransportRunResult:
    """Internal result returned by Transport.run_render()."""

    exit_code: int
    stdout: str
    stderr: str
    output_size_bytes: int
    elapsed_seconds: float


class Transport(ABC):
    """Abstract transport. Implementations stage, run ppttc.exe, ferry back."""

    @abstractmethod
    def run_render(
        self,
        ppttc_path: Path,
        output_path: Path,
        template_override: Path | None,
        timeout: float,
        keep_stage_files: bool,
    ) -> TransportRunResult:
        """Stage, run ppttc.exe, ferry the .pptx back to `output_path`.

        Args:
            ppttc_path: Mac-side path to source .ppttc.
            output_path: Mac-side destination for the ferried .pptx.
            template_override: Optional Mac-side donor .pptx; when set, the
                .ppttc's `template` entries are rewritten to point at the
                staged copy of this file.
            timeout: Hard wall-clock cap (seconds) for ppttc.exe; raise
                RenderError on timeout.
            keep_stage_files: If True, do not clean up the VM-local stage
                tempdir (useful for forensic inspection).

        Returns:
            TransportRunResult with ppttc.exe's exit code + I/O tails.

        Raises:
            RenderError on ssh/scp failure, timeout, or missing output.
        """


class SSHTransport(Transport):
    """SSH-based transport. Runs commands via `ssh <host> ...` and `scp`.

    Network connectivity is not exercised at construction time; failures
    surface from `run_render`. The host is the SSH config alias (default
    `Windows-VM`) so the user's `~/.ssh/config` controls user/keyfile/port.
    """

    def __init__(
        self,
        host: str = "Windows-VM",
        ppttc_exe: str = DEFAULT_PPTTC_EXE,
        remote_temp_root: str = DEFAULT_REMOTE_TEMP_ROOT,
        ssh_options: tuple[str, ...] = (
            "-o",
            "ConnectTimeout=10",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
        ),
    ) -> None:
        self.host = host
        self.ppttc_exe = ppttc_exe
        self.remote_temp_root = remote_temp_root
        self.ssh_options = ssh_options

    # -- stdlib helpers ---------------------------------------------------

    def _ssh(self, command: str, timeout: float) -> subprocess.CompletedProcess[str]:
        """Run a command on the VM, return the CompletedProcess (text mode)."""
        argv = ["ssh", *self.ssh_options, self.host, command]
        return subprocess.run(  # noqa: S603 -- argv is constructed locally
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _scp_to_vm(self, local: Path, remote: str, timeout: float) -> None:
        """Copy a local file to the VM (remote path uses Windows form).
        scp treats `\\` as escape; forward-slash form is accepted by Win-scp."""
        target = f"{self.host}:{remote.replace(chr(92), '/')}"
        argv = ["scp", *self.ssh_options, str(local), target]
        cp = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if cp.returncode != 0:
            from .models import RenderError  # local import: avoid cycle at import

            raise RenderError(f"scp -> VM failed (rc={cp.returncode}): {cp.stderr.strip()}")

    def _scp_from_vm(self, remote: str, local: Path, timeout: float) -> None:
        """Copy a remote VM file to a local Mac path."""
        source = f"{self.host}:{remote.replace(chr(92), '/')}"
        argv = ["scp", *self.ssh_options, source, str(local)]
        cp = subprocess.run(  # noqa: S603
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if cp.returncode != 0:
            from .models import RenderError

            raise RenderError(f"scp <- VM failed (rc={cp.returncode}): {cp.stderr.strip()}")

    # -- core ---------------------------------------------------------------

    def run_render(
        self,
        ppttc_path: Path,
        output_path: Path,
        template_override: Path | None,
        timeout: float,
        keep_stage_files: bool,
    ) -> TransportRunResult:
        from .models import RenderError

        ppttc_path = ppttc_path.expanduser().resolve()
        output_path = output_path.expanduser().resolve()
        if not ppttc_path.exists():
            raise FileNotFoundError(f"ppttc not found: {ppttc_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build the rewritten .ppttc locally so we ship a single deterministic
        # file to the VM. We need the staged template's *Windows* path before
        # the file is materialized; pre-allocate a stage id and use it on both
        # sides (Windows + Mac stage dirs).
        stage_id = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
        remote_stage_dir = f"{self.remote_temp_root}\\tcrender_{stage_id}"
        remote_input_ppttc = f"{remote_stage_dir}\\{ppttc_path.name}"
        remote_output_pptx = f"{remote_stage_dir}\\{output_path.name}"

        # Determine the path to write into entries[].template. If the caller
        # provided an override, stage it next to the .ppttc and point at it.
        # Otherwise, accept the embedded path as-is (caller's responsibility).
        if template_override is not None:
            tpl = template_override.expanduser().resolve()
            if not tpl.exists():
                raise FileNotFoundError(f"template_override not found: {tpl}")
            remote_template_pptx = f"{remote_stage_dir}\\{tpl.name}"
        else:
            tpl = None
            remote_template_pptx = None

        rewritten_ppttc = self._rewrite_ppttc(ppttc_path, remote_template_pptx)

        local_stage = Path(tempfile.mkdtemp(prefix=f"tcrender_{stage_id}_"))
        try:
            local_ppttc = local_stage / ppttc_path.name
            local_ppttc.write_text(json.dumps(rewritten_ppttc, indent=2), encoding="utf-8")

            # 1. mkdir on VM
            mk = self._ssh(
                f'cmd /c mkdir "{remote_stage_dir}"',
                timeout=min(30.0, timeout),
            )
            if mk.returncode != 0 and "already exists" not in (mk.stderr + mk.stdout):
                raise RenderError(
                    f"mkdir on VM failed (rc={mk.returncode}): {(mk.stderr or mk.stdout).strip()}"
                )

            # 2. scp .ppttc and (optional) template to VM
            self._scp_to_vm(local_ppttc, remote_input_ppttc, timeout=min(60.0, timeout))
            if tpl is not None and remote_template_pptx is not None:
                self._scp_to_vm(tpl, remote_template_pptx, timeout=min(120.0, timeout))

            # 3. invoke ppttc.exe via -EncodedCommand to avoid quoting hazards
            # (cmd.exe + PowerShell + ssh chain can't reliably handle nested
            # POSIX/Windows quoting; base64 sidesteps it entirely).
            quoted_exe = self._winquote(self.ppttc_exe)
            quoted_in = self._winquote(remote_input_ppttc)
            quoted_out = self._winquote(remote_output_pptx)
            cmdline = f"& {quoted_exe} {quoted_in} -o {quoted_out}"
            enc = base64.b64encode(cmdline.encode("utf-16le")).decode("ascii")
            t0 = time.monotonic()
            try:
                cp = self._ssh(
                    f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {enc}",
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RenderError(f"ppttc.exe timeout after {timeout:.0f}s: {exc}") from exc
            elapsed = time.monotonic() - t0

            if cp.returncode != 0:
                raise RenderError(
                    f"ppttc.exe rc={cp.returncode}\n"
                    f"--- stderr (tail) ---\n{cp.stderr[-TAIL_BYTES:]}\n"
                    f"--- stdout (tail) ---\n{cp.stdout[-TAIL_BYTES:]}"
                )

            # 4. ferry rendered .pptx back
            self._scp_from_vm(remote_output_pptx, output_path, timeout=min(120.0, timeout))
            if not output_path.exists():
                raise RenderError(f"ppttc.exe rc=0 but ferried output missing: {output_path}")
            size_bytes = output_path.stat().st_size

            return TransportRunResult(
                exit_code=cp.returncode,
                stdout=cp.stdout[-TAIL_BYTES:],
                stderr=cp.stderr[-TAIL_BYTES:],
                output_size_bytes=size_bytes,
                elapsed_seconds=round(elapsed, 3),
            )
        finally:
            if not keep_stage_files:
                shutil.rmtree(local_stage, ignore_errors=True)
                self._ssh(
                    f'cmd /c rmdir /s /q "{remote_stage_dir}"',
                    timeout=15.0,
                )

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _winquote(p: str) -> str:
        """Quote a Windows path for PowerShell `&` invocation."""
        # Wrap in single quotes; escape any embedded single quotes by doubling.
        return "'" + p.replace("'", "''") + "'"

    @staticmethod
    def _rewrite_ppttc(ppttc_path: Path, remote_template_path: str | None) -> list[dict[str, Any]]:
        """Parse the .ppttc and (optionally) rewrite all entries[].template.

        Returns the parsed (possibly rewritten) list ready to JSON-serialize.
        Raises ValueError if the top-level shape is wrong.
        """
        text = ppttc_path.read_text(encoding="utf-8")
        parsed = json.loads(text)
        if not isinstance(parsed, list) or not parsed:
            raise ValueError(f".ppttc must be a non-empty JSON array: {ppttc_path}")
        if remote_template_path is None:
            return parsed
        rewritten: list[dict[str, Any]] = []
        for entry in parsed:
            if not isinstance(entry, dict):
                raise ValueError(".ppttc entries must be JSON objects {template, data}")
            rewritten.append(dict(entry, template=remote_template_path))
        return rewritten
