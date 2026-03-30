"""
install.py — Setup: dependências, startup automático, config inicial.
Executar: python install.py
"""

import os
import sys
import logging
import subprocess
import json
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

APP_NAME = "ActivityMonitor"
SCRIPT_NAME = "main.py"


def get_install_dir() -> Path:
    """Diretório onde está este script."""
    return Path(__file__).resolve().parent


def get_python_exe() -> str:
    """Retorna path do Python atual."""
    return sys.executable


def check_dependencies() -> bool:
    """Verifica e instala dependências."""
    logger.info("Verificando dependências...")
    
    requirements_file = get_install_dir() / "requirements.txt"
    if not requirements_file.exists():
        logger.warning("requirements.txt não encontrado.")
        return True
    
    try:
        result = subprocess.run(
            [get_python_exe(), "-m", "pip", "install", "-r", str(requirements_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("Dependências instaladas com sucesso.")
            return True
        else:
            logger.error("Falha ao instalar dependências: %s", result.stderr)
            return False
    except Exception as e:
        logger.error("Erro ao instalar dependências: %s", e)
        return False


def register_startup() -> bool:
    """Registra aplicação para iniciar com o Windows via HKCU\\Run."""
    logger.info("Registrando startup automático...")
    
    try:
        import winreg
        
        script_path = str(get_install_dir() / SCRIPT_NAME)
        python_path = get_python_exe()
        
        command = f'"{python_path}" "{script_path}"'
        
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        
        winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        
        logger.info("Startup registrado com sucesso (HKCU\\Run).")
        return True
        
    except PermissionError:
        logger.error("Permissão negada. Execute como Administrador.")
        return False
    except Exception as e:
        logger.error("Erro ao registrar startup: %s", e)
        return False


def unregister_startup() -> bool:
    """Remove registro de startup."""
    logger.info("Removendo registro de startup...")
    
    try:
        import winreg
        
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        
        try:
            winreg.DeleteValue(key, APP_NAME)
            winreg.CloseKey(key)
            logger.info("Startup removido com sucesso.")
            return True
        except FileNotFoundError:
            logger.info("Aplicativo não estava registrado no startup.")
            winreg.CloseKey(key)
            return True
            
    except Exception as e:
        logger.error("Erro ao remover startup: %s", e)
        return False


def create_default_config() -> None:
    """Cria config inicial se não existir."""
    config_dir = get_install_dir() / "config"
    config_dir.mkdir(exist_ok=True)
    
    settings_file = config_dir / "settings.json"
    if not settings_file.exists():
        settings = {
            "ollama_model": "glm4",
            "ollama_url": "http://localhost:11434/api/chat",
            "report_hour": 23,
            "idle_threshold_seconds": 60,
            "poll_interval_seconds": 10,
            "score_update_interval_minutes": 60,
            "startup_with_windows": True,
            "app_name": "ActivityMonitor",
            "reports_dir": None,
            "db_dir": None,
        }
        with open(settings_file, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
        logger.info("Configuração inicial criada: settings.json")
    
    categories_file = config_dir / "categories.json"
    if not categories_file.exists():
        categories = {
            "rules": [
                {"pattern": "code.exe", "category": "Desenvolvimento", "is_productive": True, "match_type": "exact"},
                {"pattern": "chrome.exe", "category": "Browser", "is_productive": False, "match_type": "exact"},
                {"pattern": "msedge.exe", "category": "Browser", "is_productive": False, "match_type": "exact"},
                {"pattern": "explorer.exe", "category": "Sistema", "is_productive": False, "match_type": "exact"},
            ],
            "url_rules": [
                {"pattern": "github.com", "category": "Desenvolvimento", "is_productive": True},
            ],
            "default_category": "Outros",
            "default_productive": False,
        }
        with open(categories_file, "w", encoding="utf-8") as f:
            json.dump(categories, f, indent=2)
        logger.info("Categorias padrão criadas: categories.json")
    
    blocklist_file = config_dir / "blocklist.json"
    if not blocklist_file.exists():
        blocklist = {
            "processes": [],
            "window_title_keywords": ["senha", "password"],
            "url_domains": [],
        }
        with open(blocklist_file, "w", encoding="utf-8") as f:
            json.dump(blocklist, f, indent=2)
        logger.info("Blocklist padrão criada: blocklist.json")


def create_shortcut() -> bool:
    """Cria atalho na área de trabalho."""
    logger.info("Criando atalho na área de trabalho...")
    
    try:
        from win32com.client import Dispatch
        
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_path = os.path.join(desktop, f"{APP_NAME}.lnk")
        
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(shortcut_path)
        
        script_path = str(get_install_dir() / SCRIPT_NAME)
        python_path = get_python_exe()
        
        shortcut.TargetPath = python_path
        shortcut.Arguments = f'"{script_path}"'
        shortcut.WorkingDirectory = str(get_install_dir())
        shortcut.Description = "Windows Activity Monitor - Monitoramento de Produtividade"
        shortcut.Save()
        
        logger.info(f"Atalho criado: {shortcut_path}")
        return True
        
    except ImportError:
        logger.warning("pywin32 não disponível. Atalho não criado.")
        return False
    except Exception as e:
        logger.error("Erro ao criar atalho: %s", e)
        return False


def run_install(uninstall: bool = False) -> None:
    """Executa instalação ou desinstalação."""
    if uninstall:
        logger.info("=== Desinstalando Activity Monitor ===")
        unregister_startup()
        logger.info("Desinstalação concluída.")
        return
    
    logger.info("=== Instalando Activity Monitor ===")
    
    logger.info("Criando configurações padrão...")
    create_default_config()
    
    logger.info("Instalando dependências Python...")
    if not check_dependencies():
        logger.error("Falha ao instalar dependências.")
        return
    
    logger.info("Registrando inicialização automática...")
    register_startup()
    
    logger.info("Criando atalho na área de trabalho...")
    create_shortcut()
    
    logger.info("")
    logger.info("=" * 50)
    logger.info("Instalação concluída!")
    logger.info("=" * 50)
    logger.info("")
    logger.info("O Activity Monitor:")
    logger.info("  - Inicia automaticamente com o Windows")
    logger.info("  - Gera relatórios às 23h")
    logger.info("  - Roda em background via System Tray")
    logger.info("")
    logger.info("Para iniciar agora: python main.py")
    logger.info("Para desinstalar: python install.py --uninstall")


def main() -> None:
    if "--uninstall" in sys.argv:
        run_install(uninstall=True)
    else:
        run_install()


if __name__ == "__main__":
    main()
