"""Comprueba aislamiento de datos y persistencia en contenedores sin usar modelos."""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from agentcraft_forge.generator import generate
from agentcraft_forge.planner import design
from agentcraft_forge.schema import Kind

SENTINEL = "agentcraft-private-synthetic-data"
CHECK = r"""
import json,os
from pathlib import Path
from agent_app.domain import handle
root=Path('/workspace')
assert os.getuid()==10001
assert not Path('/app/journal').exists()
assert not Path('/app/whatsapp').exists()
assert not Path('/app/.env').exists()
assert not Path('/app/open-loops.md').exists()
assert not (root/'journal/private.md').exists()
assert not (root/'whatsapp/private.txt').exists()
assert not (root/'.env').exists()
if os.environ['TEST_KIND']=='expenses':
    request={'action':'record','operation_id':'docker-record-001','currency':'COP','expenses':[{'amount':15000,'description':'Transporte sintético','expense_date':'2026-10-22'}]}
    receipt=handle(root,request)
    assert receipt['persisted']
    assert handle(root,request)['replayed']
    assert handle(root,{'action':'summary'})['total']==15000
else:
    canonical=root/'open-loops.md'
    if not canonical.exists():
        canonical.write_text('# Compromisos\n',encoding='utf-8')
        (root/'journal').mkdir()
        (root/'journal/2026-10-22.md').write_text('Tengo que llamar al proveedor mañana',encoding='utf-8')
    if not list((root/'.agentcraft').glob('audit/receipts/*.json')):
        report=handle(root,{'action':'scan','owner':'Persona sintética','reference_date':'2026-10-22'})
        request={'action':'apply','scan_id':report['scan_id'],'candidate_ids':[report['candidates'][0]['id']],'operation_id':'docker-apply-001'}
        receipt=handle(root,request)
        assert receipt['persisted']
        assert (root/receipt['backup']).read_text(encoding='utf-8')=='# Compromisos\n'
        assert handle(root,request)['replayed']
    assert canonical.read_text(encoding='utf-8').count('- [ ]')==1
print(json.dumps({'status':'ok','kind':os.environ['TEST_KIND']}))
"""


def docker(*args: str) -> str:
    executable = shutil.which("docker")
    if executable is None:
        raise FileNotFoundError("Docker no está instalado.")
    return subprocess.run(  # noqa: S603 - Argumentos separados, sin shell; recursos de prueba creados aquí.
        [executable, *args], check=True, capture_output=True, text=True, timeout=600
    ).stdout.strip()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agentcraft-docker-") as directory:
        for kind in (Kind.expenses, Kind.audit):
            identifier = uuid4().hex
            image = f"agentcraft-smoke-{identifier}"
            volume = f"agentcraft-smoke-{identifier}"
            target = generate(
                design(
                    "docker-" + kind.value, "Pruebas sintéticas de contenedor", kind
                ),
                Path(directory),
            )
            for name in (
                "journal/private.md",
                "whatsapp/private.txt",
                ".env",
                "open-loops.md",
                ".data/private.txt",
                ".agentcraft/private.txt",
            ):
                path = target / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(SENTINEL, encoding="utf-8")
            created_image = False
            created_volume = False
            try:
                docker("build", "--quiet", "--tag", image, str(target))
                created_image = True
                # Ningún archivo personal debe existir tampoco en otras capas finales.
                docker(
                    "run",
                    "--rm",
                    "--entrypoint",
                    "python",
                    image,
                    "-c",
                    "from pathlib import Path; assert not any(b'agentcraft-private-synthetic-data' in p.read_bytes() for p in Path('/app').rglob('*') if p.is_file())",
                )
                docker("volume", "create", volume)
                created_volume = True
                for _ in range(2):
                    result = docker(
                        "run",
                        "--rm",
                        "--mount",
                        f"type=volume,source={volume},target=/workspace",
                        "--env",
                        f"TEST_KIND={kind.value}",
                        "--entrypoint",
                        "python",
                        image,
                        "-c",
                        CHECK,
                    )
                    if json.loads(result)["status"] != "ok":
                        raise RuntimeError(
                            "La prueba del contenedor no confirmó su estado."
                        )
            finally:
                if created_volume:
                    docker("volume", "rm", volume)
                if created_image:
                    docker("image", "rm", image)
    print(
        "Docker: usuario sin privilegios, datos excluidos, persistencia y reintentos correctos."
    )


if __name__ == "__main__":
    main()
