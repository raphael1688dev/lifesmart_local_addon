"""Provides an implementation of the LifeSmart API.

This class `LifeSmartAPI` is used to interact with the LifeSmart API. It handles the creation of API requests, including generating the necessary signature, and provides a high-level interface for making API calls.

The `LifeSmartAPI` class has the following methods:

- `_create_signature(self, obj: str, args: Dict[str, Any], ts: int) -> str`: Creates the signature for an API request.
- `create_message(self, obj: str, args: Dict[str, Any], pkg_type: int) -> bytes`: Creates the message payload for an API request.
- `send_command(self, obj: str, args: Dict[str, Any], pkg_type: int) -> Dict[str, Any]`: Sends an API command and returns the response.
- `discover_devices(self)`: Discovers devices connected to the LifeSmart API.
- `get_state_updates(self)`: Receives state updates from the LifeSmart API.
- `get_remote_list(self) -> Dict[str, Any]`: Retrieves the list of IR remote controls.
- `get_remote_keys(self, remote_id: str) -> Dict[str, Any]`: Retrieves the keys for a specific IR remote control.
- `send_remote_key(self, remote_id: str, key: str) -> Dict[str, Any]`: Sends a command to an IR remote control.
"""
"""Provides an implementation of the LifeSmart API.

This module contains the `LifeSmartAPI` class, which is used to interact with the LifeSmart API. It handles the creation of API requests, including generating the necessary signature, and provides a high-level interface for making API calls.
"""
"""LifeSmart API implementation."""
import socket
import json
import time
import hashlib
import struct
import logging
from asyncio import Lock
from queue import Queue
from cachetools import TTLCache
from cachetools.func import ttl_cache
from cachetools.keys import hashkey
from typing import Any, Dict
from .const import API_PORT, REMARK, CMD_SET

_LOGGER = logging.getLogger(__name__)

class LifeSmartAPI:
    def __init__(self, host: str, model: str, token: str , timeout: int = 10):
        self.host = host
        self.model = model
        self.token = token
        self.sequence = 1
        self._socket = None
        self.timeout = timeout
        self._connection_pool = Queue(maxsize=5)
        self._pool_lock = Lock()
        self._init_connection_pool()
          # Add caches
        self._device_cache = TTLCache(maxsize=50, ttl=300)  # 5 min cache for devices
        self._state_cache = TTLCache(maxsize=100, ttl=2)    # 2 sec cache for states


    def _init_connection_pool(self):
        """Initialize the connection pool with sockets."""
        for _ in range(5):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(self.timeout)
            self._connection_pool.put(sock)

    async def _get_connection(self):
        """Get a connection from the pool."""
        async with self._pool_lock:
            try:
                return self._connection_pool.get_nowait()
            except:
                # If pool is empty, create new connection
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.settimeout(self.timeout)
                return sock

    async def _return_connection(self, sock):
        """Return a connection to the pool."""
        async with self._pool_lock:
            try:
                self._connection_pool.put_nowait(sock)
            except:
                # If pool is full, close the connection
                sock.close()

    def _create_signature(self, obj: str, args: Dict[str, Any], ts: int) -> str:
        sorted_args = sorted(args.items())
        args_string = ','.join(f'{k}:{v}' for k, v in sorted_args)
        base_string = f"obj:{obj},{args_string},ts:{ts},model:{self.model},token:{self.token}"
        return hashlib.md5(base_string.encode()).hexdigest()

    def create_message(self, obj: str, args: Dict[str, Any], pkg_type: int) -> bytes:
        ts = int(time.time())
        sign = self._create_signature(obj, args, ts)

        body = {
            "sys": {
                "ver": 1,
                "sign": sign,
                "model": self.model,
                "ts": ts
            },
            "id": self.sequence,
            "obj": obj,
            "args": args
        }
        self.sequence += 1

        body_json = json.dumps(body).encode('utf-8')
        header = struct.pack('>2sHHI', 
                           REMARK.encode(),
                           0,
                           pkg_type,
                           len(body_json))

        return header + body_json

    async def get_devices(self) -> Dict[str, Any]:
        """Get all devices from the LifeSmart system."""
        # Use discover_devices directly instead of caching the coroutine
        devices = await self.discover_devices()
        if isinstance(devices, dict) and "msg" in devices:
            return {device["me"]: device for device in devices["msg"]}
        return {}


    async def set_device_state(self, device_id: str, state: Dict[str, Any] , time_out: float = 0.2) -> Dict[str, Any]:
        """Set device state."""
        _LOGGER.debug("Step 5: API preparing device command")
        cache_key = hashkey(device_id, state['idx'], state['type'], state['val'])
    
        if cache_key in self._state_cache:
            return self._state_cache[cache_key]
        args = {
            "me": device_id,
            "idx": state["idx"],
            "type": state["type"],
            "val": state["val"]
        }
        _LOGGER.debug("Step 5 Command args: %s", args)
        message = self.create_message("ep", args, CMD_SET)
        _LOGGER.debug("Step 6: Sending UDP message to device")

        sock = await self._get_connection()
        try:
            sock.sendto(message, (self.host, API_PORT))
            data, _ = sock.recvfrom(65535)
            response = json.loads(data[10:].decode('utf-8'))
            _LOGGER.debug("Step 7: Received device response: %s", response)
            return response
        finally:
            await self._return_connection(sock)

    async def send_command(self, obj: str, args: Dict[str, Any], pkg_type: int , time_out: float = 10.0) -> Dict[str, Any]:
        message = self.create_message(obj, args, pkg_type)
        _LOGGER.debug("Sending command: obj=%s, args=%s, pkg_type=%s", obj, args, pkg_type)

        sock = await self._get_connection()
        try:
            sock.sendto(message, (self.host, API_PORT))
            data, _ = sock.recvfrom(65535)
            response = json.loads(data[10:].decode('utf-8'))
            return response
        finally:
            await self._return_connection(sock)

    async def discover_devices(self):
        args = {"me": ""}
        return await self.send_command("eps", args, 1)

    async def discover_devices_by_id(self, device_id: str, time_out: float = 0.2):
        args = {
            "me": device_id,
        }
        return await self.send_command("ep", args, 1, time_out)

    @ttl_cache(maxsize=100, ttl=2)
    async def get_state_updates(self):
        sock = await self._get_connection()
        try:
            data, _ = sock.recvfrom(65535)
            if len(data) > 10:
                message = json.loads(data[10:].decode('utf-8'))
                _LOGGER.debug("Received UDP message: %s", message)
                
                if 'msg' in message:
                    msg = message['msg']
                    if isinstance(msg, dict):
                        return {
                            'me': msg.get('me'),
                            'idx': msg.get('idx'),
                            'val': msg.get('data', {}).get('v', msg.get('val')),
                            'type': msg.get('type')
                        }
        except Exception as e:
            _LOGGER.error("Error receiving state update: %s", str(e))
        finally:
            await self._return_connection(sock)
        return None

    @ttl_cache(maxsize=50, ttl=300)
    async def get_remote_list(self) -> Dict[str, Any]:
        """Retrieve IR remote list for devices."""
        args = {
            "cmd": "getlist"
        }
        response = await self.send_command("spotremote", args, 3)
        
        if response and response.get("code") == 0 and "msg" in response:
            remote_list = response["msg"]
            all_keys = []
            
            for remote in remote_list:
                if "id" in remote:
                    keys = await self.get_remote_keys(remote["id"])
                    if keys and keys.get("code") == 0 and "msg" in keys:
                        all_keys.append({"remote": remote, "keys": keys["msg"]})
            return all_keys
        return response

    @ttl_cache(maxsize=50, ttl=300)
    async def get_remote_keys(self, remote_id: str) -> Dict[str, Any]:
        """Retrieve IR remote keys for a specific device."""
        args = {
            "id": remote_id,
            "cmd": "getkeys"
        }
        return await self.send_command("spotremote", args, 3)

    async def send_remote_key(self, remote_id: str, key: str) -> Dict[str, Any]:
        """Send IR remote key command."""
        args = {
            "id": remote_id,
            "cmd": "sendkey",
            "key": key
        }
        return await self.send_command("spotremote", args, 3)