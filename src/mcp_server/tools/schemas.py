"""
Tools 資料模型定義

包含 ExecutionResult 等 Tools 專用的資料結構
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionResult:
    """統一的執行結果格式"""

    success: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    execution_time: str = "0.000s"
    metadata: dict[str, Any] = field(default_factory=dict)
    error_type: str = ""
    error_message: str = ""

    def to_text_output(self) -> str:
        """轉換為人類可讀的文字格式"""
        lines: list[str] = []
        for key, value in self.metadata.items():
            if value and key not in ["version_info"]:
                lines.append(f"📁 {key.replace('_', ' ').title()}: {value}")
        lines.append(f"⏱️ Execution Time: {self.execution_time}")
        lines.append(f"🔢 Return Code: {self.returncode}")
        if not self.success:
            lines.append(f"❌ Error: [{self.error_type}] {self.error_message}")
        if self.stdout:
            lines.append(f"📤 Standard Output:\n{self.stdout}")
        if self.stderr:
            lines.append(f"⚠️ Standard Error:\n{self.stderr}")
        return "\n".join(lines)
