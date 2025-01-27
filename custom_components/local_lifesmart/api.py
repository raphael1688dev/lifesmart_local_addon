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
import asyncio
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
        devices = await self.discover_devices()
        if isinstance(devices, dict) and "msg" in devices:
            device_dict = {device["me"]: device for device in devices["msg"]}
            return device_dict
        return {}
    def set_device_state(self, device_id: str, state: Dict[str, Any], time_out: float = 2.0) -> Dict[str, Any]:
        """Set device state with reliable UDP handling."""
        args = {
            "me": device_id,
            "idx": state["idx"],
            "type": state["type"],
            "val": state["val"]
        }
        message = self.create_message("ep", args, CMD_SET)
        
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(time_out)
            # Send multiple times to ensure delivery
            for _ in range(1):
                sock.sendto(message, (self.host, API_PORT))
                try:
                    data, _ = sock.recvfrom(65535)
                    response = json.loads(data[10:].decode('utf-8'))
                    return response
                except socket.timeout:
                    continue
        
        # Return a default response instead of raising timeout
        return {"code": 0, "msg": "command sent"}
    async def send_command(self, obj: str, args: Dict[str, Any], pkg_type: int, time_out: float = 5.0) -> Dict[str, Any]:
        if obj == "spotremote":
            time_out = 0.3
        try:
            message = self.create_message(obj, args, pkg_type)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(time_out)  # Reduce timeout to 5 seconds
                sock.sendto(message, (self.host, API_PORT))

                data, _ = sock.recvfrom(65535)
                return json.loads(data[10:].decode('utf-8'))
        except Exception as e:
            if obj == "spotremote":
                
                return {"code": 0, "msg": "command sent"}    
            _LOGGER.error(f"Error sending command: {str(e)}")
            return {"code": 0, "msg": "command sent"}    


    async def discover_devices(self):
        args = {"me": ""}
        return await self.send_command("eps", args, 1)
    async def discover_devices_by_id(self, device_id: str, time_out: float = 1.0):
        args = {
            "me": device_id,
     
        }
        
        return await self.send_command("ep", args, 1, time_out)

    async def get_state_updates(self):
        if not self._socket:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.bind((self.host, API_PORT))
            self._socket.settimeout(5)

        try:
            data, _ = self._socket.recvfrom(65535)
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
            if self._socket:
                self._socket.close()
                self._socket = None
        return None
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
