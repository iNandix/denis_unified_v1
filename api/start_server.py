#!/usr/bin/env python3
"""Script de inicio para API Registry"""

import sys
import os
from pathlib import Path

# Configurar PYTHONPATH correctamente
api_dir = Path(__file__).parent.absolute()
project_root = api_dir.parent

# Añadir al path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Cambiar al directorio del proyecto
os.chdir(str(project_root))

# Ahora importar y ejecutar
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Importar usando ruta absoluta
import importlib.util

spec = importlib.util.spec_from_file_location(
    "api_registry", str(api_dir / "api_registry.py")
)
api_module = importlib.util.module_from_spec(spec)

# Ejecutar el módulo
spec.loader.exec_module(api_module)

# Iniciar servidor
api_module.start_registry_server()
