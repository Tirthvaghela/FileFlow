import json
import logging
import subprocess
from pathlib import Path

from config.settings import settings

logger = logging.getLogger("fileflow.uipath")


def execute_move_via_uipath(source: Path, dest_folder: Path, final_name: str) -> Path | None:
    """Ask UiPath Robot to physically execute the move (uipath/FileFlowMove/
    MoveFile.xaml), instead of doing it in Python. Best-effort: any failure
    -- Robot missing, package not published, timeout, unexpected output --
    is logged and swallowed, returning None so the caller falls back to a
    plain shutil.move. This must never be the reason a file fails to
    organize."""
    if not settings.UIPATH_ENABLED:
        return None
    if not settings.UIPATH_ROBOT_EXE or not settings.UIPATH_PACKAGE_PATH:
        logger.warning(
            "UIPATH_ENABLED is true but UIPATH_ROBOT_EXE/UIPATH_PACKAGE_PATH "
            "aren't both set -- skipping UiPath and using the Python move."
        )
        return None

    payload = json.dumps(
        {
            "in_SourceFilePath": str(source),
            "in_DestFolderPath": str(dest_folder),
            "in_FinalFileName": final_name,
        }
    )

    try:
        result = subprocess.run(
            [
                str(settings.UIPATH_ROBOT_EXE),
                "execute",
                "--file",
                str(settings.UIPATH_PACKAGE_PATH),
                "--entry",
                settings.UIPATH_ENTRY_POINT,
                "--input",
                payload,
            ],
            capture_output=True,
            text=True,
            timeout=settings.UIPATH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("UiPath Robot invocation failed to start: %s", exc)
        return None

    if result.returncode != 0:
        logger.warning(
            "UiPath Robot exited %s for %s: %s",
            result.returncode,
            source.name,
            result.stderr.strip() or result.stdout.strip(),
        )
        return None

    try:
        output = json.loads(result.stdout.strip())
        dest_path = Path(output["out_DestinationPath"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning("Could not parse UiPath Robot output for %s: %s", source.name, exc)
        return None

    # The real, unmodified MoveFile.xaml always computes out_DestinationPath
    # as exactly Combine(in_DestFolderPath, in_FinalFileName), so this never
    # fires in normal operation -- but nothing previously verified it, and
    # the caller (organizer.py::process_file) discards this function's
    # return value once it's non-None, unconditionally logging its OWN
    # pre-computed destination as though it were confirmed. A reported path
    # that merely happens to exist somewhere else entirely (a differently
    # built package, a tampered workflow, a corrupted response) was
    # previously trusted completely instead of being caught here and
    # falling back to Python's own, independently-verified move.
    expected_dest_path = dest_folder / final_name
    if dest_path.resolve() != expected_dest_path.resolve():
        logger.warning(
            "UiPath Robot reported an unexpected destination for %s (expected %s, got %s) "
            "-- falling back.",
            source.name, expected_dest_path, dest_path,
        )
        return None

    if not dest_path.exists():
        logger.warning(
            "UiPath Robot reported success but %s does not exist -- falling back.",
            dest_path,
        )
        return None

    return dest_path
