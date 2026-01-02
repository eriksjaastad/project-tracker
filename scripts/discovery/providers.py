"""Metadata providers for project discovery."""

import shutil
import subprocess
import json
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from pathlib import Path

# Configure logging using project-specific logger
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from logger import get_logger
from config import AUDIT_BIN_PATH

logger = get_logger(__name__)

class MetadataProvider(ABC):
    """Abstract base class for project metadata providers."""
    
    @abstractmethod
    def get_health(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Returns {"score": 0-100, "grade": "A-F"} or None if unavailable."""
        pass
    
    @abstractmethod
    def get_tasks(self, project_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns list of task dicts from parsing."""
        pass
    
    @abstractmethod
    def check_file(self, file_path: str) -> Dict[str, Any]:
        """Returns {"valid": bool, "issues": [...]}."""
        pass
    
    @abstractmethod
    def fix_file(self, file_path: str) -> bool:
        """Returns True if fixed successfully."""
        pass

class AuditProvider(MetadataProvider):
    """Concrete provider that calls the Go `audit` binary."""
    
    def __init__(self, bin_path: str):
        self.bin_path = bin_path
        
    def get_health(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Calls `audit health [project] --json`."""
        try:
            result = subprocess.run(
                [self.bin_path, "health", project_path, "--json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                logger.warning(f"audit health failed for {project_path}: {result.stderr}")
                return None
            data = json.loads(result.stdout)
            
            # 🛡️ Validate binary output
            score = data.get("score")
            grade = data.get("grade")
            if not isinstance(score, int) or not (0 <= score <= 100):
                logger.error(f"Invalid score from audit binary for {project_path}: {score}")
                return None
            if grade not in {"A", "B", "C", "D", "F"}:
                logger.error(f"Invalid grade from audit binary for {project_path}: {grade}")
                return None
                
            return {"score": score, "grade": grade}
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
            logger.error(f"audit health error for {project_path}: {e}")
            return None
    
    def get_tasks(self, project_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Calls `audit tasks` and parses NDJSON output."""
        try:
            cmd = [self.bin_path, "tasks"]
            if project_path:
                cmd.extend(["--root", project_path])
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.warning(f"audit tasks failed: {result.stderr}")
                return []
            
            tasks = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    tasks.append(json.loads(line))
            return tasks
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            logger.error(f"audit tasks error: {e}")
            return []
    
    def check_file(self, file_path: str) -> Dict[str, Any]:
        """Calls `audit check [file]` and parses NDJSON."""
        try:
            result = subprocess.run(
                [self.bin_path, "check", file_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            # Parse first line of NDJSON output
            if result.stdout.strip():
                data = json.loads(result.stdout.strip().split('\n')[0])
                return {"valid": data.get("valid", False), "issues": data.get("issues", [])}
            return {"valid": False, "issues": ["No output from audit check"]}
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as e:
            logger.error(f"audit check error for {file_path}: {e}")
            return {"valid": False, "issues": [str(e)]}
    
    def fix_file(self, file_path: str) -> bool:
        """Calls `audit fix [file]` (Interface only)."""
        raise NotImplementedError("AuditProvider.fix_file not yet implemented")

class LegacyProvider(MetadataProvider):
    """Concrete provider that uses existing Python logic."""
    
    def get_health(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Legacy Python logic doesn't compute health scores."""
        return None
    
    def get_tasks(self, project_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Uses existing todo_parser.py logic (Interface only)."""
        raise NotImplementedError("LegacyProvider.get_tasks not yet implemented")
    
    def check_file(self, file_path: str) -> Dict[str, Any]:
        """Uses existing validation logic (Interface only)."""
        raise NotImplementedError("LegacyProvider.check_file not yet implemented")
    
    def fix_file(self, file_path: str) -> bool:
        """Legacy logic doesn't support auto-fixing."""
        return False

def get_provider() -> MetadataProvider:
    """
    Returns AuditProvider if audit binary exists, else LegacyProvider.
    Checks config.AUDIT_BIN_PATH first, then falls back to PATH lookup.
    """
    # 1. Check config path
    if AUDIT_BIN_PATH and Path(AUDIT_BIN_PATH).is_absolute():
        if Path(AUDIT_BIN_PATH).exists():
            logger.info(f"Using AuditProvider with binary at: {AUDIT_BIN_PATH}")
            return AuditProvider(str(AUDIT_BIN_PATH))
    
    # 2. Check shutil.which
    bin_name = AUDIT_BIN_PATH if AUDIT_BIN_PATH else "audit"
    which_path = shutil.which(bin_name)
    
    if which_path:
        logger.info(f"Using AuditProvider with binary found in PATH: {which_path}")
        return AuditProvider(which_path)
    
    # 3. Fallback to Legacy
    logger.info("audit binary not found. Falling back to LegacyProvider.")
    return LegacyProvider()
