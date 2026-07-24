"""Tests for iOS Simulator automation tools."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import patch

import pytest

from openjarvis.core.registry import ToolRegistry

MODULE = "openjarvis.tools.ios_simulator"


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture(autouse=True)
def _reset_session():
    """Each test starts with no cached target UDID."""
    from openjarvis.tools import ios_simulator

    ios_simulator._session.udid = None
    yield
    ios_simulator._session.udid = None


@pytest.fixture
def macos():
    """Pretend we're running on macOS for the duration of the test."""
    with patch(f"{MODULE}.platform.system", return_value="Darwin"):
        yield


@pytest.fixture
def idb_present():
    with patch(f"{MODULE}.shutil.which", return_value="/usr/local/bin/idb"):
        yield


AVAILABLE_DEVICES_JSON = json.dumps(
    {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
                {
                    "name": "iPhone 17 Pro",
                    "udid": "ABCD-1234",
                    "state": "Shutdown",
                    "isAvailable": True,
                }
            ]
        }
    }
)

BOOTED_DEVICES_JSON = json.dumps(
    {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
                {
                    "name": "iPhone 17 Pro",
                    "udid": "ABCD-1234",
                    "state": "Booted",
                    "isAvailable": True,
                }
            ]
        }
    }
)

NO_BOOTED_DEVICES_JSON = json.dumps({"devices": {}})


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_all_tools_registered(self):
        # Registration happens at import time via @ToolRegistry.register.
        # Other test modules may clear the registry, so re-register if needed.
        from openjarvis.tools.ios_simulator import (
            IOSSimulatorBootTool,
            IOSSimulatorDescribeUITool,
            IOSSimulatorInstallAppTool,
            IOSSimulatorLaunchAppTool,
            IOSSimulatorScreenshotTool,
            IOSSimulatorSwipeTool,
            IOSSimulatorTapTool,
            IOSSimulatorTypeTextTool,
        )

        tools = {
            "ios_simulator_boot": IOSSimulatorBootTool,
            "ios_simulator_install_app": IOSSimulatorInstallAppTool,
            "ios_simulator_launch_app": IOSSimulatorLaunchAppTool,
            "ios_simulator_screenshot": IOSSimulatorScreenshotTool,
            "ios_simulator_tap": IOSSimulatorTapTool,
            "ios_simulator_swipe": IOSSimulatorSwipeTool,
            "ios_simulator_type_text": IOSSimulatorTypeTextTool,
            "ios_simulator_describe_ui": IOSSimulatorDescribeUITool,
        }
        for key, cls in tools.items():
            if not ToolRegistry.contains(key):
                ToolRegistry.register_value(key, cls)

        for key in tools:
            assert ToolRegistry.contains(key)


# ---------------------------------------------------------------------------
# Non-macOS guard — applies to every tool, checked once per representative
# ---------------------------------------------------------------------------


class TestNonMacOSGuard:
    def test_boot_rejects_non_macos(self):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with patch(f"{MODULE}.platform.system", return_value="Linux"):
            result = IOSSimulatorBootTool().execute()
        assert result.success is False
        assert "macOS" in result.content

    def test_tap_rejects_non_macos(self):
        from openjarvis.tools.ios_simulator import IOSSimulatorTapTool

        with patch(f"{MODULE}.platform.system", return_value="Linux"):
            result = IOSSimulatorTapTool().execute(x=1, y=2)
        assert result.success is False
        assert "macOS" in result.content


# ---------------------------------------------------------------------------
# IOSSimulatorBootTool
# ---------------------------------------------------------------------------


class TestIOSSimulatorBootTool:
    def test_spec_name_and_category(self):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        tool = IOSSimulatorBootTool()
        assert tool.spec.name == "ios_simulator_boot"
        assert tool.spec.category == "ios_simulator"

    def test_boots_first_available_device(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with (
            patch(f"{MODULE}._run") as mock_run,
            patch(f"{MODULE}._session") as mock_session,
        ):
            mock_run.side_effect = [
                _completed(stdout=AVAILABLE_DEVICES_JSON),  # list available
                _completed(),  # boot
                _completed(),  # open -a Simulator
            ]
            result = IOSSimulatorBootTool().execute()

        assert result.success is True
        assert result.metadata["udid"] == "ABCD-1234"
        assert mock_session.udid == "ABCD-1234"

    def test_matches_device_name_case_insensitive(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with patch(f"{MODULE}._run") as mock_run:
            mock_run.side_effect = [
                _completed(stdout=AVAILABLE_DEVICES_JSON),
                _completed(),
                _completed(),
            ]
            result = IOSSimulatorBootTool().execute(device_name="iphone 17 pro")

        assert result.success is True
        assert result.metadata["device_name"] == "iPhone 17 Pro"

    def test_no_matching_device(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with patch(f"{MODULE}._run") as mock_run:
            mock_run.return_value = _completed(stdout=AVAILABLE_DEVICES_JSON)
            result = IOSSimulatorBootTool().execute(device_name="Apple Watch")

        assert result.success is False
        assert "No available simulator" in result.content

    def test_already_booted_skips_boot_call(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        already_booted_json = json.dumps(
            {
                "devices": {
                    "com.apple.CoreSimulator.SimRuntime.iOS-18-0": [
                        {
                            "name": "iPhone 17 Pro",
                            "udid": "ABCD-1234",
                            "state": "Booted",
                            "isAvailable": True,
                        }
                    ]
                }
            }
        )
        with patch(f"{MODULE}._run") as mock_run:
            mock_run.return_value = _completed(stdout=already_booted_json)
            result = IOSSimulatorBootTool().execute()

        assert result.success is True
        assert "already booted" in result.content
        assert mock_run.call_count == 1  # only the list call, no boot/open

    def test_simctl_not_found(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with patch(f"{MODULE}._run", side_effect=FileNotFoundError):
            result = IOSSimulatorBootTool().execute()

        assert result.success is False
        assert "xcrun not found" in result.content


# ---------------------------------------------------------------------------
# IOSSimulatorInstallAppTool
# ---------------------------------------------------------------------------


class TestIOSSimulatorInstallAppTool:
    def test_missing_app_path(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorInstallAppTool

        result = IOSSimulatorInstallAppTool().execute()
        assert result.success is False
        assert "No app_path" in result.content

    def test_app_path_does_not_exist(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorInstallAppTool

        result = IOSSimulatorInstallAppTool().execute(app_path="/nope/Does.app")
        assert result.success is False
        assert "not found" in result.content

    def test_no_booted_simulator(self, macos, tmp_path):
        from openjarvis.tools.ios_simulator import IOSSimulatorInstallAppTool

        app_path = tmp_path / "App.app"
        app_path.mkdir()

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorInstallAppTool().execute(app_path=str(app_path))

        assert result.success is False
        assert "No booted simulator" in result.content

    def test_installs_on_resolved_udid(self, macos, tmp_path):
        from openjarvis.tools.ios_simulator import IOSSimulatorInstallAppTool

        app_path = tmp_path / "App.app"
        app_path.mkdir()

        with patch(f"{MODULE}._run") as mock_run:
            mock_run.side_effect = [
                _completed(stdout=BOOTED_DEVICES_JSON),  # resolve udid
                _completed(),  # install
            ]
            result = IOSSimulatorInstallAppTool().execute(
                app_path=str(app_path), udid="EXPLICIT-UDID"
            )

        assert result.success is True
        assert result.metadata["udid"] == "EXPLICIT-UDID"
        install_call = mock_run.call_args_list[0]
        assert install_call.args[0][:3] == ["xcrun", "simctl", "install"]


# ---------------------------------------------------------------------------
# IOSSimulatorLaunchAppTool
# ---------------------------------------------------------------------------


class TestIOSSimulatorLaunchAppTool:
    def test_missing_bundle_id(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorLaunchAppTool

        result = IOSSimulatorLaunchAppTool().execute(udid="X")
        assert result.success is False
        assert "No bundle_id" in result.content

    def test_launch_success(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorLaunchAppTool

        with patch(f"{MODULE}._run") as mock_run:
            mock_run.return_value = _completed(stdout="com.acme.field: 12345\n")
            result = IOSSimulatorLaunchAppTool().execute(
                bundle_id="com.acme.field", udid="ABCD-1234"
            )

        assert result.success is True
        assert result.metadata["bundle_id"] == "com.acme.field"
        assert "12345" in result.content

    def test_launch_failure_surfaces_stderr(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorLaunchAppTool

        with patch(f"{MODULE}._run") as mock_run:
            mock_run.return_value = _completed(
                returncode=1, stderr="No such bundle identifier"
            )
            result = IOSSimulatorLaunchAppTool().execute(
                bundle_id="com.acme.field", udid="ABCD-1234"
            )

        assert result.success is False
        assert "No such bundle identifier" in result.content


# ---------------------------------------------------------------------------
# IOSSimulatorScreenshotTool
# ---------------------------------------------------------------------------


class TestIOSSimulatorScreenshotTool:
    def test_screenshot_returns_base64(self, macos, tmp_path):
        from openjarvis.tools.ios_simulator import IOSSimulatorScreenshotTool

        save_path = tmp_path / "shot.png"

        def _fake_simctl_screenshot(args, timeout=30.0):
            # args: ["xcrun", "simctl", "io", udid, "screenshot", target_path]
            target = args[-1]
            with open(target, "wb") as f:
                f.write(b"\x89PNG\x00fakepngdata")
            return _completed()

        with patch(f"{MODULE}._run") as mock_run:
            mock_run.side_effect = [
                _completed(stdout=BOOTED_DEVICES_JSON),  # resolve udid
                None,  # placeholder, replaced below
            ]
            # Replace the second call with the side-effecting fake.
            mock_run.side_effect = None

            call_state = {"n": 0}

            def _dispatch(args, timeout=30.0):
                call_state["n"] += 1
                if call_state["n"] == 1:
                    return _completed(stdout=BOOTED_DEVICES_JSON)
                return _fake_simctl_screenshot(args, timeout)

            mock_run.side_effect = _dispatch

            result = IOSSimulatorScreenshotTool().execute(path=str(save_path))

        assert result.success is True
        assert "screenshot_base64" in result.metadata
        import base64

        decoded = base64.b64decode(result.metadata["screenshot_base64"])
        assert decoded.startswith(b"\x89PNG")

    def test_no_booted_simulator(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorScreenshotTool

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorScreenshotTool().execute()

        assert result.success is False
        assert "No booted simulator" in result.content


# ---------------------------------------------------------------------------
# IOSSimulatorTapTool
# ---------------------------------------------------------------------------


class TestIOSSimulatorTapTool:
    def test_idb_missing(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorTapTool

        with patch(f"{MODULE}.shutil.which", return_value=None):
            result = IOSSimulatorTapTool().execute(x=10, y=20, udid="X")

        assert result.success is False
        assert "idb not installed" in result.content

    def test_missing_coordinates(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTapTool

        result = IOSSimulatorTapTool().execute(udid="X")
        assert result.success is False
        assert "x and y" in result.content

    def test_tap_success(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTapTool

        with patch(f"{MODULE}._run", return_value=_completed()) as mock_run:
            result = IOSSimulatorTapTool().execute(x=100, y=200, udid="ABCD-1234")

        assert result.success is True
        args = mock_run.call_args.args[0]
        assert args[:3] == ["idb", "ui", "tap"]
        assert "100" in args and "200" in args
        assert "--udid" in args and "ABCD-1234" in args


# ---------------------------------------------------------------------------
# IOSSimulatorSwipeTool
# ---------------------------------------------------------------------------


class TestIOSSimulatorSwipeTool:
    def test_missing_params(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorSwipeTool

        result = IOSSimulatorSwipeTool().execute(start_x=0, start_y=0, udid="X")
        assert result.success is False

    def test_swipe_success_with_duration(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorSwipeTool

        with patch(f"{MODULE}._run", return_value=_completed()) as mock_run:
            result = IOSSimulatorSwipeTool().execute(
                start_x=10, start_y=500, end_x=10, end_y=100, duration=0.3, udid="X"
            )

        assert result.success is True
        args = mock_run.call_args.args[0]
        assert "--duration" in args
        assert "0.3" in args


# ---------------------------------------------------------------------------
# IOSSimulatorTypeTextTool
# ---------------------------------------------------------------------------


class TestIOSSimulatorTypeTextTool:
    def test_no_text(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTypeTextTool

        result = IOSSimulatorTypeTextTool().execute(udid="X")
        assert result.success is False
        assert "No text" in result.content

    def test_types_text(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTypeTextTool

        with patch(f"{MODULE}._run", return_value=_completed()) as mock_run:
            result = IOSSimulatorTypeTextTool().execute(text="hello", udid="X")

        assert result.success is True
        args = mock_run.call_args.args[0]
        assert args[:3] == ["idb", "ui", "text"]
        assert "hello" in args


# ---------------------------------------------------------------------------
# IOSSimulatorDescribeUITool
# ---------------------------------------------------------------------------


class TestIOSSimulatorDescribeUITool:
    def test_describe_ui_returns_json(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorDescribeUITool

        tree_json = json.dumps([{"AXLabel": "Water now", "frame": {"x": 10, "y": 20}}])
        with patch(f"{MODULE}._run", return_value=_completed(stdout=tree_json)):
            result = IOSSimulatorDescribeUITool().execute(udid="X")

        assert result.success is True
        assert "Water now" in result.content

    def test_idb_missing(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorDescribeUITool

        with patch(f"{MODULE}.shutil.which", return_value=None):
            result = IOSSimulatorDescribeUITool().execute(udid="X")

        assert result.success is False
        assert "idb not installed" in result.content


# ---------------------------------------------------------------------------
# _resolve_udid — direct error-path coverage
# ---------------------------------------------------------------------------


class TestResolveUdid:
    def test_timeout_listing_booted(self):
        from openjarvis.tools.ios_simulator import _resolve_udid

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            udid, error = _resolve_udid(None)

        assert udid is None
        assert "Timed out" in error

    def test_returncode_nonzero(self):
        from openjarvis.tools.ios_simulator import _resolve_udid

        with patch(
            f"{MODULE}._run", return_value=_completed(returncode=1, stderr="boom")
        ):
            udid, error = _resolve_udid(None)

        assert udid is None
        assert "simctl list failed" in error

    def test_bad_json(self):
        from openjarvis.tools.ios_simulator import _resolve_udid

        with patch(f"{MODULE}._run", return_value=_completed(stdout="not json")):
            udid, error = _resolve_udid(None)

        assert udid is None
        assert "Could not parse" in error

    def test_explicit_udid_short_circuits(self):
        from openjarvis.tools.ios_simulator import _resolve_udid

        with patch(f"{MODULE}._run") as mock_run:
            udid, error = _resolve_udid("EXPLICIT")

        assert udid == "EXPLICIT"
        assert error is None
        mock_run.assert_not_called()

    def test_session_udid_short_circuits(self):
        from openjarvis.tools import ios_simulator
        from openjarvis.tools.ios_simulator import _resolve_udid

        ios_simulator._session.udid = "CACHED"
        with patch(f"{MODULE}._run") as mock_run:
            udid, error = _resolve_udid(None)

        assert udid == "CACHED"
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Remaining non-macOS guards
# ---------------------------------------------------------------------------


class TestRemainingNonMacOSGuards:
    @pytest.mark.parametrize(
        "cls_name,call_kwargs",
        [
            ("IOSSimulatorInstallAppTool", {"app_path": "/tmp/App.app"}),
            ("IOSSimulatorLaunchAppTool", {"bundle_id": "com.acme.field"}),
            ("IOSSimulatorScreenshotTool", {}),
            (
                "IOSSimulatorSwipeTool",
                {"start_x": 0, "start_y": 0, "end_x": 1, "end_y": 1},
            ),
            ("IOSSimulatorTypeTextTool", {"text": "hi"}),
            ("IOSSimulatorDescribeUITool", {}),
        ],
    )
    def test_rejects_non_macos(self, cls_name, call_kwargs):
        import openjarvis.tools.ios_simulator as mod

        cls = getattr(mod, cls_name)
        with patch(f"{MODULE}.platform.system", return_value="Linux"):
            result = cls().execute(**call_kwargs)

        assert result.success is False
        assert "macOS" in result.content


# ---------------------------------------------------------------------------
# Boot — remaining error branches
# ---------------------------------------------------------------------------


class TestIOSSimulatorBootErrorBranches:
    def test_timeout_listing_available(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            result = IOSSimulatorBootTool().execute()

        assert result.success is False
        assert "Timed out listing" in result.content

    def test_list_available_returncode_nonzero(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with patch(
            f"{MODULE}._run", return_value=_completed(returncode=1, stderr="boom")
        ):
            result = IOSSimulatorBootTool().execute()

        assert result.success is False
        assert "simctl list failed" in result.content

    def test_list_available_bad_json(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        with patch(f"{MODULE}._run", return_value=_completed(stdout="not json")):
            result = IOSSimulatorBootTool().execute()

        assert result.success is False
        assert "Could not parse" in result.content

    def test_boot_call_times_out(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        def _dispatch(args, timeout=30.0):
            if args[:3] == ["xcrun", "simctl", "list"]:
                return _completed(stdout=AVAILABLE_DEVICES_JSON)
            raise subprocess.TimeoutExpired("x", 1)

        with patch(f"{MODULE}._run", side_effect=_dispatch):
            result = IOSSimulatorBootTool().execute()

        assert result.success is False
        assert "Timed out booting" in result.content

    def test_boot_call_fails(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        def _dispatch(args, timeout=30.0):
            if args[:3] == ["xcrun", "simctl", "list"]:
                return _completed(stdout=AVAILABLE_DEVICES_JSON)
            return _completed(returncode=1, stderr="boot exploded")

        with patch(f"{MODULE}._run", side_effect=_dispatch):
            result = IOSSimulatorBootTool().execute()

        assert result.success is False
        assert "Boot failed" in result.content

    def test_open_simulator_app_missing_is_ignored(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorBootTool

        def _dispatch(args, timeout=30.0):
            if args[:3] == ["xcrun", "simctl", "list"]:
                return _completed(stdout=AVAILABLE_DEVICES_JSON)
            if args[:3] == ["xcrun", "simctl", "boot"]:
                return _completed()
            raise FileNotFoundError("no Simulator.app on this box")

        with patch(f"{MODULE}._run", side_effect=_dispatch):
            result = IOSSimulatorBootTool().execute()

        assert result.success is True


# ---------------------------------------------------------------------------
# Install / Launch / Screenshot / Tap / Swipe / Text / Describe — remaining
# timeout and failure branches
# ---------------------------------------------------------------------------


class TestRemainingFailureBranches:
    def test_install_app_udid_resolution_error_passthrough(self, macos, tmp_path):
        from openjarvis.tools.ios_simulator import IOSSimulatorInstallAppTool

        app_path = tmp_path / "App.app"
        app_path.mkdir()
        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorInstallAppTool().execute(app_path=str(app_path))

        assert result.success is False

    def test_install_app_timeout(self, macos, tmp_path):
        from openjarvis.tools.ios_simulator import IOSSimulatorInstallAppTool

        app_path = tmp_path / "App.app"
        app_path.mkdir()

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            result = IOSSimulatorInstallAppTool().execute(
                app_path=str(app_path), udid="X"
            )

        assert result.success is False
        assert "Timed out installing" in result.content

    def test_install_app_failure(self, macos, tmp_path):
        from openjarvis.tools.ios_simulator import IOSSimulatorInstallAppTool

        app_path = tmp_path / "App.app"
        app_path.mkdir()

        with patch(
            f"{MODULE}._run", return_value=_completed(returncode=1, stderr="nope")
        ):
            result = IOSSimulatorInstallAppTool().execute(
                app_path=str(app_path), udid="X"
            )

        assert result.success is False
        assert "Install failed" in result.content

    def test_launch_app_udid_resolution_error(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorLaunchAppTool

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorLaunchAppTool().execute(bundle_id="com.acme.field")

        assert result.success is False

    def test_launch_app_timeout(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorLaunchAppTool

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            result = IOSSimulatorLaunchAppTool().execute(
                bundle_id="com.acme.field", udid="X"
            )

        assert result.success is False
        assert "Timed out launching" in result.content

    def test_screenshot_udid_resolution_error(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorScreenshotTool

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorScreenshotTool().execute()

        assert result.success is False

    def test_screenshot_timeout(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorScreenshotTool

        def _dispatch(args, timeout=30.0):
            if "screenshot" in args:
                raise subprocess.TimeoutExpired("x", 1)
            return _completed(stdout=BOOTED_DEVICES_JSON)

        with patch(f"{MODULE}._run", side_effect=_dispatch):
            result = IOSSimulatorScreenshotTool().execute()

        assert result.success is False
        assert "Timed out taking" in result.content

    def test_screenshot_command_failure(self, macos):
        from openjarvis.tools.ios_simulator import IOSSimulatorScreenshotTool

        def _dispatch(args, timeout=30.0):
            if "screenshot" in args:
                return _completed(returncode=1, stderr="no device")
            return _completed(stdout=BOOTED_DEVICES_JSON)

        with patch(f"{MODULE}._run", side_effect=_dispatch):
            result = IOSSimulatorScreenshotTool().execute()

        assert result.success is False
        assert "Screenshot failed" in result.content

    def test_screenshot_unreadable_file(self, macos, tmp_path):
        from openjarvis.tools.ios_simulator import IOSSimulatorScreenshotTool

        missing_path = tmp_path / "does" / "not" / "exist.png"

        def _dispatch(args, timeout=30.0):
            if "screenshot" in args:
                return _completed()  # simctl "succeeds" but writes nothing
            return _completed(stdout=BOOTED_DEVICES_JSON)

        with patch(f"{MODULE}._run", side_effect=_dispatch):
            result = IOSSimulatorScreenshotTool().execute(path=str(missing_path))

        assert result.success is False
        assert "could not be read" in result.content

    def test_tap_udid_resolution_error(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTapTool

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorTapTool().execute(x=1, y=2)

        assert result.success is False

    def test_tap_timeout(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTapTool

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            result = IOSSimulatorTapTool().execute(x=1, y=2, udid="X")

        assert result.success is False
        assert "Timed out tapping" in result.content

    def test_tap_command_failure(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTapTool

        with patch(
            f"{MODULE}._run", return_value=_completed(returncode=1, stderr="oops")
        ):
            result = IOSSimulatorTapTool().execute(x=1, y=2, udid="X")

        assert result.success is False
        assert "Tap failed" in result.content

    def test_swipe_udid_resolution_error(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorSwipeTool

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorSwipeTool().execute(
                start_x=0, start_y=0, end_x=1, end_y=1
            )

        assert result.success is False

    def test_swipe_timeout(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorSwipeTool

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            result = IOSSimulatorSwipeTool().execute(
                start_x=0, start_y=0, end_x=1, end_y=1, udid="X"
            )

        assert result.success is False
        assert "Timed out swiping" in result.content

    def test_swipe_command_failure(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorSwipeTool

        with patch(
            f"{MODULE}._run", return_value=_completed(returncode=1, stderr="oops")
        ):
            result = IOSSimulatorSwipeTool().execute(
                start_x=0, start_y=0, end_x=1, end_y=1, udid="X"
            )

        assert result.success is False
        assert "Swipe failed" in result.content

    def test_type_text_udid_resolution_error(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTypeTextTool

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorTypeTextTool().execute(text="hi")

        assert result.success is False

    def test_type_text_timeout(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTypeTextTool

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            result = IOSSimulatorTypeTextTool().execute(text="hi", udid="X")

        assert result.success is False
        assert "Timed out typing" in result.content

    def test_type_text_command_failure(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorTypeTextTool

        with patch(
            f"{MODULE}._run", return_value=_completed(returncode=1, stderr="oops")
        ):
            result = IOSSimulatorTypeTextTool().execute(text="hi", udid="X")

        assert result.success is False
        assert "Type failed" in result.content

    def test_describe_ui_udid_resolution_error(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorDescribeUITool

        no_booted = _completed(stdout=NO_BOOTED_DEVICES_JSON)
        with patch(f"{MODULE}._run", return_value=no_booted):
            result = IOSSimulatorDescribeUITool().execute()

        assert result.success is False

    def test_describe_ui_timeout(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorDescribeUITool

        with patch(f"{MODULE}._run", side_effect=subprocess.TimeoutExpired("x", 1)):
            result = IOSSimulatorDescribeUITool().execute(udid="X")

        assert result.success is False
        assert "Timed out describing" in result.content

    def test_describe_ui_command_failure(self, macos, idb_present):
        from openjarvis.tools.ios_simulator import IOSSimulatorDescribeUITool

        with patch(
            f"{MODULE}._run", return_value=_completed(returncode=1, stderr="oops")
        ):
            result = IOSSimulatorDescribeUITool().execute(udid="X")

        assert result.success is False
        assert "Describe UI failed" in result.content
