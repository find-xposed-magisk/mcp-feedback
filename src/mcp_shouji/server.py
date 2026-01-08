#!/usr/bin/env python3
"""
MCP Shouji 伺服器主要模組

此模組提供 MCP (Model Context Protocol) 的增強回饋收集功能，
支援智能環境檢測，自動使用 Web UI 介面。

主要功能：
- MCP 工具實現
- 介面選擇（Web UI）
- 環境檢測 (SSH Remote, WSL, Local)
- 國際化支援
- 圖片處理與上傳
- 命令執行與結果展示
- 專案目錄管理

主要 MCP 工具：
- shouji: 收集用户输入
- get_system_info: 获取系统环境信息

作者: f
增强: f (Web UI, 图片支持, 环境检测)
重構: 模塊化設計
"""

import json
import os
import sys
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ImageContent, TextContent
from pydantic import Field

# 導入統一的調試功能
from .debug import server_debug_log as debug_log

# 導入錯誤處理框架
from .utils.error_handler import ErrorHandler, ErrorType

# 導入工具模組
from .utils.env_utils import (
    init_encoding,
    is_remote_environment,
    is_wsl_environment,
    get_system_info_dict,
)
from .utils.feedback_utils import (
    save_feedback_to_file,
    create_feedback_text,
    process_images,
)


# 初始化編碼（在導入時就執行）
_encoding_initialized = init_encoding()

# ===== 常數定義 =====
SERVER_NAME = "MCP Shouji"


# 初始化 MCP 服務器
from . import __version__


# 確保 log_level 設定為正確的大寫格式
fastmcp_settings = {}

# 檢查環境變數並設定正確的 log_level
env_log_level = os.getenv("FASTMCP_LOG_LEVEL", "").upper()
if env_log_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
    fastmcp_settings["log_level"] = env_log_level
else:
    # 預設使用 INFO 等級
    fastmcp_settings["log_level"] = "INFO"

mcp: Any = FastMCP(SERVER_NAME)


# ===== MCP 工具定義 =====
def _get_default_timeout() -> int:
    """
    獲取預設超時時間
    Get default timeout value
    
    優先順序: MCP_DEFAULT_TIMEOUT 環境變數 > 預設值 86400
    Priority: MCP_DEFAULT_TIMEOUT env var > default 86400
    """
    env_timeout = os.getenv("MCP_DEFAULT_TIMEOUT")
    if env_timeout:
        try:
            timeout_value = int(env_timeout)
            if timeout_value > 0:
                return timeout_value
            debug_log(f"MCP_DEFAULT_TIMEOUT 值無效 ({timeout_value})，必須大於 0，使用預設值 86400")
        except ValueError:
            debug_log(f"MCP_DEFAULT_TIMEOUT 格式錯誤 ({env_timeout})，必須為數字，使用預設值 86400")
    return 86400


@mcp.tool()
async def shouji(
    project_directory: Annotated[str, Field(description="项目目录路径")] = ".",
    summary: Annotated[
        str, Field(description="工作摘要说明")
    ] = "任务已完成，请查看。",
    timeout: Annotated[int, Field(description="等待超时时间（秒），可通过 MCP_DEFAULT_TIMEOUT 环境变量设定")] = None,
) -> list:
    """通过 Web 界面收集用户输入。
    
    提供一个交互式界面，用于获取用户的文字输入和图片附件。
    当需要用户确认或额外指导时可调用此工具。
    
    Args:
        project_directory: 项目目录路径，用于上下文定位
        summary: 当前工作的摘要说明，供用户参考
        timeout: 等待用户输入的超时时间（秒）
    
    Returns:
        list: 用户输入内容，包含文字和可选的图片
    """
    # 處理 timeout 預設值 (支援環境變數 MCP_DEFAULT_TIMEOUT)
    if timeout is None:
        timeout = _get_default_timeout()
    
    # 環境偵測
    is_remote = is_remote_environment()
    is_wsl = is_wsl_environment()

    debug_log(f"環境偵測結果 - 遠端: {is_remote}, WSL: {is_wsl}")
    debug_log(f"使用介面: Web UI, 超時時間: {timeout} 秒")

    try:
        # 確保專案目錄存在
        if not os.path.exists(project_directory):
            project_directory = os.getcwd()
        project_directory = os.path.abspath(project_directory)

        # 使用 Web 模式
        debug_log("回饋模式: web")

        result = await launch_web_feedback_ui(project_directory, summary, timeout)

        # 處理取消情況
        if not result:
            return [TextContent(type="text", text="用戶取消了回饋。")]

        # 儲存詳細結果
        save_feedback_to_file(result)

        # 建立回饋項目列表
        feedback_items = []

        # 添加文字回饋
        if (
            result.get("interactive_feedback")
            or result.get("command_logs")
            or result.get("images")
        ):
            feedback_text = create_feedback_text(result)
            feedback_items.append(TextContent(type="text", text=feedback_text))
            debug_log("文字回饋已添加")

        # 添加圖片回饋
        if result.get("images"):
            image_contents = process_images(result["images"])
            # 直接擴展列表
            feedback_items.extend(image_contents)
            debug_log(f"已添加 {len(image_contents)} 張圖片")

        # 確保至少有一個回饋項目
        if not feedback_items:
            feedback_items.append(
                TextContent(type="text", text="用戶未提供任何回饋內容。")
            )

        debug_log(f"回饋收集完成，共 {len(feedback_items)} 個項目")
        return feedback_items

    except Exception as e:
        # 使用統一錯誤處理，但不影響 JSON RPC 響應
        error_id = ErrorHandler.log_error_with_context(
            e,
            context={"operation": "回饋收集", "project_dir": project_directory},
            error_type=ErrorType.SYSTEM,
        )

        # 生成用戶友好的錯誤信息
        user_error_msg = ErrorHandler.format_user_error(e, include_technical=False)
        debug_log(f"回饋收集錯誤 [錯誤ID: {error_id}]: {e!s}")

        return [TextContent(type="text", text=user_error_msg)]


async def launch_web_feedback_ui(project_dir: str, summary: str, timeout: int) -> dict:
    """
    啟動 Web UI 收集回饋，支援自訂超時時間

    Args:
        project_dir: 專案目錄路徑
        summary: 工作摘要
        timeout: 超時時間（秒）

    Returns:
        dict: 收集到的回饋資料
    """
    debug_log(f"啟動 Web UI 介面，超時時間: {timeout} 秒")

    try:
        # 使用新的 web 模組
        from .web import launch_web_feedback_ui as web_launch

        # 傳遞 timeout 參數給 Web UI
        return await web_launch(project_dir, summary, timeout)
    except ImportError as e:
        # 使用統一錯誤處理
        error_id = ErrorHandler.log_error_with_context(
            e,
            context={"operation": "Web UI 模組導入", "module": "web"},
            error_type=ErrorType.DEPENDENCY,
        )
        user_error_msg = ErrorHandler.format_user_error(
            e, ErrorType.DEPENDENCY, include_technical=False
        )
        debug_log(f"Web UI 模組導入失敗 [錯誤ID: {error_id}]: {e}")

        return {
            "command_logs": "",
            "interactive_feedback": user_error_msg,
            "images": [],
        }


@mcp.tool()
def get_system_info() -> str:
    """
    獲取系統環境資訊

    Returns:
        str: JSON 格式的系統資訊
    """
    system_info = get_system_info_dict()
    return json.dumps(system_info, ensure_ascii=False, indent=2)


# ===== 主程式入口 =====
def main():
    """主要入口點，用於套件執行
    收集用戶的互動回饋，支援文字和圖片
    此工具使用 Web UI 介面收集用戶回饋，支援智能環境檢測。

    用戶可以：
    1. 執行命令來驗證結果
    2. 提供文字回饋
    3. 上傳圖片作為回饋
    4. 查看工作摘要

    調試模式：
    - 設置環境變數 MCP_DEBUG=true 可啟用詳細調試輸出
    - 生產環境建議關閉調試模式以避免輸出干擾
    """
    # 檢查是否啟用調試模式
    debug_enabled = os.getenv("MCP_DEBUG", "").lower() in ("true", "1", "yes", "on")

    # 檢查是否啟用桌面模式
    desktop_mode = os.getenv("MCP_DESKTOP_MODE", "").lower() in (
        "true",
        "1",
        "yes",
        "on",
    )

    if debug_enabled:
        debug_log("🚀 啟動互動式回饋收集 MCP 服務器")
        debug_log(f"   服務器名稱: {SERVER_NAME}")
        debug_log(f"   版本: {__version__}")
        debug_log(f"   平台: {sys.platform}")
        debug_log(f"   編碼初始化: {'成功' if _encoding_initialized else '失敗'}")
        debug_log(f"   遠端環境: {is_remote_environment()}")
        debug_log(f"   WSL 環境: {is_wsl_environment()}")
        debug_log(f"   桌面模式: {'啟用' if desktop_mode else '禁用'}")
        debug_log("   介面類型: Web UI")
        debug_log("   等待來自自動化助手的調用...")
        debug_log("準備啟動 MCP 伺服器...")
        debug_log("調用 mcp.run()...")

    try:
        # 使用正確的 FastMCP API
        mcp.run()
    except KeyboardInterrupt:
        if debug_enabled:
            debug_log("收到中斷信號，正常退出")
        sys.exit(0)
    except Exception as e:
        if debug_enabled:
            debug_log(f"MCP 服務器啟動失敗: {e}")
            import traceback

            debug_log(f"詳細錯誤: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
