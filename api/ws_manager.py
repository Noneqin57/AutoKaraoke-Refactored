# -*- coding: utf-8 -*-
"""WebSocket 连接管理器"""
import json
import asyncio
from typing import List, Any, Dict
from fastapi import WebSocket


class WebSocketManager:
    """管理 WebSocket 连接的生命周期和消息广播"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """接受并注册新的 WebSocket 连接"""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """断开并移除 WebSocket 连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def send_json(self, websocket: WebSocket, data: Dict[str, Any]):
        """向单个客户端发送 JSON 消息"""
        try:
            await websocket.send_json(data)
        except Exception:
            self.disconnect(websocket)

    async def broadcast(self, data: Dict[str, Any]):
        """向所有活跃连接广播 JSON 消息"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(data)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

    @property
    def has_connections(self) -> bool:
        return len(self.active_connections) > 0


# 全局实例
task_ws_manager = WebSocketManager()
model_ws_manager = WebSocketManager()
batch_ws_manager = WebSocketManager()
