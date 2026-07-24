"""iOS Simulator automation tools — device control via simctl + idb.

Lifecycle management (boot, install, launch, screenshot) uses Apple's
``xcrun simctl``, which ships with Xcode Command Line Tools. UI
interaction (tap, swipe, text input, accessibility tree) uses Meta's
``idb`` (https://fbidb.io), installed separately with::

    brew tap facebook/fb && brew install idb-companion && pip install fb-idb

Only available on macOS with Xcode installed; every tool here returns a
clear ``success=False`` result with an install/setup hint on any other
platform or when a required binary is missing.
"""

from __future__ import annotations

import base64
import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, List, Optional, Tuple

from openjarvis.core.registry import ToolRegistry
from openjarvis.core.types import ToolResult
from openjarvis.security.capabilities import Capability
from openjarvis.tools._stubs import BaseTool, ToolSpec

_DEFAULT_TIMEOUT = 30.0
_IDB_INSTALL_HINT = (
    "idb not installed. Install with:"
    " brew tap facebook/fb && brew install idb-companion && pip install fb-idb"
)


class _SimulatorSession:
    """Tracks the currently targeted simulator UDID across tool calls."""

    def __init__(self) -> None:
        self.udid: Optional[str] = None


_session = _SimulatorSession()


def _is_macos() -> bool:
    return platform.system() == "Darwin"


def _not_macos_result(tool_name: str) -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        content=(
            "iOS Simulator control requires macOS with Xcode installed."
            f" Current platform: {platform.system()}."
        ),
        success=False,
    )


def _run(
    args: List[str], timeout: float = _DEFAULT_TIMEOUT
) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _resolve_udid(explicit: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Resolve which simulator UDID to target.

    Returns ``(udid, error)`` — exactly one of the two is non-``None``.
    """
    if explicit:
        return explicit, None
    if _session.udid:
        return _session.udid, None
    try:
        proc = _run(["xcrun", "simctl", "list", "devices", "booted", "-j"])
    except FileNotFoundError:
        return None, "xcrun not found. Install Xcode Command Line Tools."
    except subprocess.TimeoutExpired:
        return None, "Timed out listing booted simulators."
    if proc.returncode != 0:
        return None, f"simctl list failed: {proc.stderr.strip()}"
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None, "Could not parse simctl output."
    for devices in data.get("devices", {}).values():
        for device in devices:
            if device.get("state") == "Booted":
                return device["udid"], None
    return None, "No booted simulator found. Call ios_simulator_boot first."


def _idb_available() -> bool:
    return shutil.which("idb") is not None


# ---------------------------------------------------------------------------
# Tool 1: IOSSimulatorBootTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_boot")
class IOSSimulatorBootTool(BaseTool):
    """Boot an iOS Simulator device, becoming the default target for other tools."""

    tool_id = "ios_simulator_boot"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_boot",
            description=(
                "Boot an iOS Simulator device. If already booted, becomes the"
                " default target for subsequent ios_simulator_* calls."
                " Returns the device name and UDID."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "device_name": {
                        "type": "string",
                        "description": (
                            "Device name or substring to match, e.g. 'iPhone 17"
                            " Pro'. If omitted, boots the first available device."
                        ),
                    },
                },
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_boot")

        device_name = params.get("device_name")

        try:
            proc = _run(["xcrun", "simctl", "list", "devices", "available", "-j"])
        except FileNotFoundError:
            return ToolResult(
                tool_name="ios_simulator_boot",
                content="xcrun not found. Install Xcode Command Line Tools.",
                success=False,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_boot",
                content="Timed out listing available simulators.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_boot",
                content=f"simctl list failed: {proc.stderr.strip()}",
                success=False,
            )

        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return ToolResult(
                tool_name="ios_simulator_boot",
                content="Could not parse simctl output.",
                success=False,
            )

        candidate = None
        for devices in data.get("devices", {}).values():
            for device in devices:
                if not device.get("isAvailable", True):
                    continue
                if device_name and device_name.lower() not in device["name"].lower():
                    continue
                candidate = device
                break
            if candidate:
                break

        if candidate is None:
            hint = f" matching '{device_name}'" if device_name else ""
            return ToolResult(
                tool_name="ios_simulator_boot",
                content=f"No available simulator device found{hint}.",
                success=False,
            )

        udid = candidate["udid"]
        already_booted = candidate.get("state") == "Booted"

        if not already_booted:
            try:
                boot_proc = _run(["xcrun", "simctl", "boot", udid], timeout=60.0)
            except subprocess.TimeoutExpired:
                return ToolResult(
                    tool_name="ios_simulator_boot",
                    content=f"Timed out booting device '{candidate['name']}'.",
                    success=False,
                )
            if boot_proc.returncode != 0:
                return ToolResult(
                    tool_name="ios_simulator_boot",
                    content=f"Boot failed: {boot_proc.stderr.strip()}",
                    success=False,
                )
            # Best-effort: bring the Simulator app UI to the foreground.
            try:
                _run(["open", "-a", "Simulator"], timeout=10.0)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

        _session.udid = udid

        status = "already booted" if already_booted else "booted"
        return ToolResult(
            tool_name="ios_simulator_boot",
            content=f"Device '{candidate['name']}' ({udid}) {status}.",
            success=True,
            metadata={"udid": udid, "device_name": candidate["name"]},
        )


# ---------------------------------------------------------------------------
# Tool 2: IOSSimulatorInstallAppTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_install_app")
class IOSSimulatorInstallAppTool(BaseTool):
    """Install a built .app bundle onto the simulator."""

    tool_id = "ios_simulator_install_app"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_install_app",
            description=("Install a built .app bundle onto the target iOS Simulator."),
            parameters={
                "type": "object",
                "properties": {
                    "app_path": {
                        "type": "string",
                        "description": "Path to the built .app bundle.",
                    },
                    "udid": {
                        "type": "string",
                        "description": (
                            "Target simulator UDID. Defaults to the last-booted"
                            " device, or the first currently-booted simulator."
                        ),
                    },
                },
                "required": ["app_path"],
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_install_app")

        app_path = params.get("app_path", "")
        if not app_path:
            return ToolResult(
                tool_name="ios_simulator_install_app",
                content="No app_path provided.",
                success=False,
            )
        if not Path(app_path).exists():
            return ToolResult(
                tool_name="ios_simulator_install_app",
                content=f"App bundle not found: {app_path}",
                success=False,
            )

        udid, error = _resolve_udid(params.get("udid"))
        if error:
            return ToolResult(
                tool_name="ios_simulator_install_app", content=error, success=False
            )

        try:
            proc = _run(["xcrun", "simctl", "install", udid, app_path], timeout=60.0)
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_install_app",
                content="Timed out installing app.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_install_app",
                content=f"Install failed: {proc.stderr.strip()}",
                success=False,
            )

        return ToolResult(
            tool_name="ios_simulator_install_app",
            content=f"Installed {app_path} on {udid}.",
            success=True,
            metadata={"udid": udid, "app_path": app_path},
        )


# ---------------------------------------------------------------------------
# Tool 3: IOSSimulatorLaunchAppTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_launch_app")
class IOSSimulatorLaunchAppTool(BaseTool):
    """Launch an installed app by bundle identifier."""

    tool_id = "ios_simulator_launch_app"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_launch_app",
            description="Launch an installed app on the target iOS Simulator.",
            parameters={
                "type": "object",
                "properties": {
                    "bundle_id": {
                        "type": "string",
                        "description": (
                            "App bundle identifier, e.g. 'com.acme.field'."
                        ),
                    },
                    "udid": {
                        "type": "string",
                        "description": (
                            "Target simulator UDID. Defaults to the last-booted"
                            " device, or the first currently-booted simulator."
                        ),
                    },
                },
                "required": ["bundle_id"],
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_launch_app")

        bundle_id = params.get("bundle_id", "")
        if not bundle_id:
            return ToolResult(
                tool_name="ios_simulator_launch_app",
                content="No bundle_id provided.",
                success=False,
            )

        udid, error = _resolve_udid(params.get("udid"))
        if error:
            return ToolResult(
                tool_name="ios_simulator_launch_app", content=error, success=False
            )

        try:
            proc = _run(["xcrun", "simctl", "launch", udid, bundle_id], timeout=30.0)
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_launch_app",
                content="Timed out launching app.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_launch_app",
                content=f"Launch failed: {proc.stderr.strip()}",
                success=False,
            )

        return ToolResult(
            tool_name="ios_simulator_launch_app",
            content=proc.stdout.strip() or f"Launched {bundle_id} on {udid}.",
            success=True,
            metadata={"udid": udid, "bundle_id": bundle_id},
        )


# ---------------------------------------------------------------------------
# Tool 4: IOSSimulatorScreenshotTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_screenshot")
class IOSSimulatorScreenshotTool(BaseTool):
    """Take a screenshot of the target iOS Simulator."""

    tool_id = "ios_simulator_screenshot"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_screenshot",
            description=(
                "Take a screenshot of the target iOS Simulator."
                " Returns the screenshot as base64-encoded PNG data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Optional file path to save the screenshot.",
                    },
                    "udid": {
                        "type": "string",
                        "description": (
                            "Target simulator UDID. Defaults to the last-booted"
                            " device, or the first currently-booted simulator."
                        ),
                    },
                },
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_screenshot")

        udid, error = _resolve_udid(params.get("udid"))
        if error:
            return ToolResult(
                tool_name="ios_simulator_screenshot", content=error, success=False
            )

        path = params.get("path")
        target_path = path or tempfile.mktemp(suffix=".png")

        try:
            proc = _run(
                ["xcrun", "simctl", "io", udid, "screenshot", target_path],
                timeout=30.0,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_screenshot",
                content="Timed out taking screenshot.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_screenshot",
                content=f"Screenshot failed: {proc.stderr.strip()}",
                success=False,
            )

        try:
            screenshot_bytes = Path(target_path).read_bytes()
        except OSError as exc:
            return ToolResult(
                tool_name="ios_simulator_screenshot",
                content=f"Screenshot taken but could not be read: {exc}",
                success=False,
            )
        finally:
            if not path:
                Path(target_path).unlink(missing_ok=True)

        b64_data = base64.b64encode(screenshot_bytes).decode("utf-8")
        description = "Screenshot taken"
        if path:
            description += f", saved to {path}"

        return ToolResult(
            tool_name="ios_simulator_screenshot",
            content=description,
            success=True,
            metadata={"udid": udid, "screenshot_base64": b64_data},
        )


# ---------------------------------------------------------------------------
# Tool 5: IOSSimulatorTapTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_tap")
class IOSSimulatorTapTool(BaseTool):
    """Tap a point on the simulator screen (requires idb)."""

    tool_id = "ios_simulator_tap"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_tap",
            description=(
                "Tap a point on the iOS Simulator screen, in points (not"
                " pixels), matching the coordinates seen in a screenshot"
                " taken at the simulator's logical resolution."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "number", "description": "X coordinate, in points."},
                    "y": {"type": "number", "description": "Y coordinate, in points."},
                    "udid": {
                        "type": "string",
                        "description": (
                            "Target simulator UDID. Defaults to the last-booted"
                            " device, or the first currently-booted simulator."
                        ),
                    },
                },
                "required": ["x", "y"],
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_tap")
        if not _idb_available():
            return ToolResult(
                tool_name="ios_simulator_tap", content=_IDB_INSTALL_HINT, success=False
            )

        if "x" not in params or "y" not in params:
            return ToolResult(
                tool_name="ios_simulator_tap",
                content="Both x and y coordinates are required.",
                success=False,
            )

        udid, error = _resolve_udid(params.get("udid"))
        if error:
            return ToolResult(
                tool_name="ios_simulator_tap", content=error, success=False
            )

        x, y = params["x"], params["y"]
        try:
            proc = _run(
                ["idb", "ui", "tap", str(x), str(y), "--udid", udid], timeout=15.0
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_tap",
                content="Timed out tapping.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_tap",
                content=f"Tap failed: {proc.stderr.strip()}",
                success=False,
            )

        return ToolResult(
            tool_name="ios_simulator_tap",
            content=f"Tapped ({x}, {y}).",
            success=True,
            metadata={"udid": udid, "x": x, "y": y},
        )


# ---------------------------------------------------------------------------
# Tool 6: IOSSimulatorSwipeTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_swipe")
class IOSSimulatorSwipeTool(BaseTool):
    """Swipe from one point to another on the simulator screen (requires idb)."""

    tool_id = "ios_simulator_swipe"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_swipe",
            description=(
                "Swipe from one point to another on the iOS Simulator screen,"
                " in points (not pixels)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "start_x": {"type": "number", "description": "Start X, in points."},
                    "start_y": {"type": "number", "description": "Start Y, in points."},
                    "end_x": {"type": "number", "description": "End X, in points."},
                    "end_y": {"type": "number", "description": "End Y, in points."},
                    "duration": {
                        "type": "number",
                        "description": (
                            "Swipe duration in seconds. Default: idb's default."
                        ),
                    },
                    "udid": {
                        "type": "string",
                        "description": (
                            "Target simulator UDID. Defaults to the last-booted"
                            " device, or the first currently-booted simulator."
                        ),
                    },
                },
                "required": ["start_x", "start_y", "end_x", "end_y"],
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_swipe")
        if not _idb_available():
            return ToolResult(
                tool_name="ios_simulator_swipe",
                content=_IDB_INSTALL_HINT,
                success=False,
            )

        required = ("start_x", "start_y", "end_x", "end_y")
        if any(k not in params for k in required):
            return ToolResult(
                tool_name="ios_simulator_swipe",
                content="start_x, start_y, end_x, and end_y are all required.",
                success=False,
            )

        udid, error = _resolve_udid(params.get("udid"))
        if error:
            return ToolResult(
                tool_name="ios_simulator_swipe", content=error, success=False
            )

        args = [
            "idb",
            "ui",
            "swipe",
            str(params["start_x"]),
            str(params["start_y"]),
            str(params["end_x"]),
            str(params["end_y"]),
            "--udid",
            udid,
        ]
        duration = params.get("duration")
        if duration is not None:
            args.extend(["--duration", str(duration)])

        try:
            proc = _run(args, timeout=15.0)
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_swipe",
                content="Timed out swiping.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_swipe",
                content=f"Swipe failed: {proc.stderr.strip()}",
                success=False,
            )

        return ToolResult(
            tool_name="ios_simulator_swipe",
            content=(
                f"Swiped ({params['start_x']}, {params['start_y']}) ->"
                f" ({params['end_x']}, {params['end_y']})."
            ),
            success=True,
            metadata={"udid": udid},
        )


# ---------------------------------------------------------------------------
# Tool 7: IOSSimulatorTypeTextTool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_type_text")
class IOSSimulatorTypeTextTool(BaseTool):
    """Type text into the currently focused field (requires idb)."""

    tool_id = "ios_simulator_type_text"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_type_text",
            description=(
                "Type text into whichever field is currently focused on the"
                " iOS Simulator. Tap the field first with ios_simulator_tap."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type."},
                    "udid": {
                        "type": "string",
                        "description": (
                            "Target simulator UDID. Defaults to the last-booted"
                            " device, or the first currently-booted simulator."
                        ),
                    },
                },
                "required": ["text"],
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_type_text")
        if not _idb_available():
            return ToolResult(
                tool_name="ios_simulator_type_text",
                content=_IDB_INSTALL_HINT,
                success=False,
            )

        text = params.get("text", "")
        if not text:
            return ToolResult(
                tool_name="ios_simulator_type_text",
                content="No text provided.",
                success=False,
            )

        udid, error = _resolve_udid(params.get("udid"))
        if error:
            return ToolResult(
                tool_name="ios_simulator_type_text", content=error, success=False
            )

        try:
            proc = _run(["idb", "ui", "text", text, "--udid", udid], timeout=15.0)
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_type_text",
                content="Timed out typing text.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_type_text",
                content=f"Type failed: {proc.stderr.strip()}",
                success=False,
            )

        return ToolResult(
            tool_name="ios_simulator_type_text",
            content=f"Typed {len(text)} characters.",
            success=True,
            metadata={"udid": udid},
        )


# ---------------------------------------------------------------------------
# Tool 8: IOSSimulatorDescribeUITool
# ---------------------------------------------------------------------------


@ToolRegistry.register("ios_simulator_describe_ui")
class IOSSimulatorDescribeUITool(BaseTool):
    """Return the accessibility tree of the current screen (requires idb)."""

    tool_id = "ios_simulator_describe_ui"

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="ios_simulator_describe_ui",
            description=(
                "Return the accessibility tree of the current iOS Simulator"
                " screen as JSON — element labels, types, and frames (in"
                " points). Use this to find tap targets without relying on"
                " pixel-guessing from a screenshot."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "udid": {
                        "type": "string",
                        "description": (
                            "Target simulator UDID. Defaults to the last-booted"
                            " device, or the first currently-booted simulator."
                        ),
                    },
                },
            },
            category="ios_simulator",
            required_capabilities=[Capability.CODE_EXECUTE],
        )

    def execute(self, **params: Any) -> ToolResult:
        if not _is_macos():
            return _not_macos_result("ios_simulator_describe_ui")
        if not _idb_available():
            return ToolResult(
                tool_name="ios_simulator_describe_ui",
                content=_IDB_INSTALL_HINT,
                success=False,
            )

        udid, error = _resolve_udid(params.get("udid"))
        if error:
            return ToolResult(
                tool_name="ios_simulator_describe_ui", content=error, success=False
            )

        try:
            proc = _run(["idb", "ui", "describe-all", "--udid", udid], timeout=15.0)
        except subprocess.TimeoutExpired:
            return ToolResult(
                tool_name="ios_simulator_describe_ui",
                content="Timed out describing UI.",
                success=False,
            )
        if proc.returncode != 0:
            return ToolResult(
                tool_name="ios_simulator_describe_ui",
                content=f"Describe UI failed: {proc.stderr.strip()}",
                success=False,
            )

        content = proc.stdout.strip() or "[]"
        if len(content) > 10000:
            content = content[:10000] + "\n\n[Content truncated]"

        return ToolResult(
            tool_name="ios_simulator_describe_ui",
            content=content,
            success=True,
            metadata={"udid": udid},
        )


__all__ = [
    "IOSSimulatorBootTool",
    "IOSSimulatorInstallAppTool",
    "IOSSimulatorLaunchAppTool",
    "IOSSimulatorScreenshotTool",
    "IOSSimulatorTapTool",
    "IOSSimulatorSwipeTool",
    "IOSSimulatorTypeTextTool",
    "IOSSimulatorDescribeUITool",
]
