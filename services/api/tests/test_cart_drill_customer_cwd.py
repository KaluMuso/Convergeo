from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def launch(tmp_path: Path, *, customer_context: bool) -> tuple[int, dict[str, object]]:
    shell = (ROOT / "scripts/qa/run-cart-response-drill.sh").read_text()
    function = (
        "drill_as_user() {" + shell.split("drill_as_user() {", 1)[1].split("\n}\n", 1)[0] + "\n}"
    )
    line = next(
        line
        for line in shell.splitlines()
        if line.startswith("drill_as_user ") and "node_modules/next/dist/bin/next" in line
    )
    if not customer_context:
        line = line.replace(" --customer-project", "")
    stage = tmp_path / "stage"
    customer = stage / "apps/customer"
    (customer / "lib").mkdir(parents=True)
    (customer / "lib/api-base-url.js").write_text('module.exports = "fixture-origin";')
    cli = customer / "node_modules/next/dist/bin/next"
    cli.parent.mkdir(parents=True)
    # Match Next 15.5.27's requireFromString: a virtual Module, .paths and
    # _compile, with a relative config import. No framework, server or network.
    cli.write_text(
        "const Module = require('node:module');\n"
        "const path = require('node:path');\n"
        "const customer = process.argv[3];\n"
        "const filename = path.join(customer, 'next.config.compiled.js');\n"
        "const config = new Module(filename, module.parent);\n"
        "config.paths = Module._nodeModulePaths(customer);\n"
        "const result = {cwd: process.cwd() === customer ? 'customer' : 'stage_root',\n"
        "private_env_present: process.env.PRIVATE_TEST_ENV !== undefined,\n"
        "test_uid: process.env.CART_DRILL_UID};\n"
        "try { config._compile(\"module.exports = require('./lib/api-base-url');\", filename);\n"
        "result.origin = config.exports; } catch (error) {\n"
        "result.error_code = error.code === 'MODULE_NOT_FOUND' ? error.code : 'other';\n"
        "process.exitCode = 1; }\n"
        "console.log(JSON.stringify(result));\n"
    )
    output = stage / "e2e/results/cart-response-drill"
    output.mkdir(parents=True)
    node = shutil.which("node")
    assert node is not None
    script = "\n".join(
        [
            "set -euo pipefail",
            f"drill_root={shlex.quote(str(stage))}",
            f"drill_package_root={shlex.quote(str(stage))}",
            f"drill_output={shlex.quote(str(output))}",
            f"drill_node={shlex.quote(node)}",
            "drill_uid=999",
            "drill_python_library=/public-sdk/lib",
            "drill_browser_path=/public-browser",
            "SUPABASE_ANON_KEY=local-dummy",
            "SUPABASE_SERVICE_ROLE_KEY=local-dummy",
            "sudo() {",
            '  [[ "$1" = -u && "$2" = cartdrill && "$3" = env && "$4" = -i ]]',
            "  shift 2",
            '  "$@"',
            "}",
            function,
            line,
            'wait "$!"',
        ]
    )
    result = subprocess.run(
        ["bash", "-c", script],
        env={"PATH": os.environ["PATH"], "PRIVATE_TEST_ENV": "must-not-be-forwarded"},
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.stdout == result.stderr == ""
    data: dict[str, object] = json.loads((output / "private-customer.log").read_text())
    return result.returncode, data


def test_customer_launcher_resolves_relative_next_config_import_from_project(
    tmp_path: Path,
) -> None:
    code, data = launch(tmp_path, customer_context=True)
    assert code == 0
    assert data == {
        "cwd": "customer",
        "private_env_present": False,
        "test_uid": "999",
        "origin": "fixture-origin",
    }


def test_default_drill_context_stays_at_root_and_exposes_the_original_failure(
    tmp_path: Path,
) -> None:
    code, data = launch(tmp_path, customer_context=False)
    assert code == 1
    assert data == {
        "cwd": "stage_root",
        "private_env_present": False,
        "test_uid": "999",
        "error_code": "MODULE_NOT_FOUND",
    }
