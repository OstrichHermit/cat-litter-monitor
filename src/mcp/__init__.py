"""
MCP服务器模块

该模块提供猫厕所监控系统的MCP服务器接口。
"""

from src.mcp.server import LitterMonitorMCPServer, get_server

__all__ = ['LitterMonitorMCPServer', 'get_server']
