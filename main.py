import json
import base64
import os
import sys
from typing import Optional, Callable, Generator, Dict, Any

import wasmtime
import numpy as np

WASM_DIR = os.path.dirname(os.path.abspath(__file__))
WASM_PATH = os.path.join(WASM_DIR, "@peekuptime.wasm")


class DeepSeekHash:
    def __init__(self):
        self.instance = None
        self.memory = None
        self.store = None

    def init(self, wasm_path: str):
        engine = wasmtime.Engine()
        with open(wasm_path, 'rb') as f:
            wasm_bytes = f.read()
        module = wasmtime.Module(engine, wasm_bytes)
        self.store = wasmtime.Store(engine)
        linker = wasmtime.Linker(engine)
        linker.define_wasi()
        self.instance = linker.instantiate(self.store, module)
        self.memory = self.instance.exports(self.store)["memory"]
        return self

    def _write_to_memory(self, text: str) -> tuple:
        encoded = text.encode('utf-8')
        length = len(encoded)
        ptr = self.instance.exports(self.store)["__wbindgen_export_0"](self.store, length, 1)
        memory_view = self.memory.data_ptr(self.store)
        for i, byte in enumerate(encoded):
            memory_view[ptr + i] = byte
        return ptr, length

    def calculate_hash(self, algorithm: str, challenge: str, salt: str,
                       difficulty: int, expire_at: int) -> Optional[int]:
        prefix = f"{salt}_{expire_at}_"
        retptr = self.instance.exports(self.store)["__wbindgen_add_to_stack_pointer"](self.store, -16)
        try:
            challenge_ptr, challenge_len = self._write_to_memory(challenge)
            prefix_ptr, prefix_len = self._write_to_memory(prefix)
            self.instance.exports(self.store)["wasm_solve"](
                self.store, retptr, challenge_ptr, challenge_len,
                prefix_ptr, prefix_len, float(difficulty)
            )
            memory_view = self.memory.data_ptr(self.store)
            status = int.from_bytes(bytes(memory_view[retptr:retptr + 4]), byteorder='little', signed=True)
            if status == 0:
                return None
            value_bytes = bytes(memory_view[retptr + 8:retptr + 16])
            value = np.frombuffer(value_bytes, dtype=np.float64)[0]
            return int(value)
        finally:
            self.instance.exports(self.store)["__wbindgen_add_to_stack_pointer"](self.store, 16)


class DeepSeekPOW:
    def __init__(self):
        self.hasher = DeepSeekHash().init(WASM_PATH)

    def solve_challenge(self, config: Dict[str, Any]) -> str:
        answer = self.hasher.calculate_hash(
            config['algorithm'], config['challenge'], config['salt'],
            config['difficulty'], config['expire_at']
        )
        result = {
            'algorithm': config['algorithm'],
            'challenge': config['challenge'],
            'salt': config['salt'],
            'answer': answer,
            'signature': config['signature'],
            'target_path': config['target_path']
        }
        return base64.b64encode(json.dumps(result).encode()).decode()


import requests


class DeepSeekAndroidClient:
    BASE_URL = "https://chat.deepseek.com"

    def __init__(
        self,
        bearer_token: str,
        rangers_id: str = "7692587925250278662",
        client_version: str = "2.1.6",
        client_platform: str = "android",
        client_locale: str = "tr",
        bundle_id: str = "com.deepseek.chat",
        timezone_offset: int = 10800
    ):
        self.bearer_token = bearer_token
        self.rangers_id = rangers_id
        self.client_version = client_version
        self.client_platform = client_platform
        self.client_locale = client_locale
        self.bundle_id = bundle_id
        self.timezone_offset = timezone_offset
        self.pow_solver = DeepSeekPOW()
        self.session = requests.Session()
        self.current_chat_session_id: Optional[str] = None
        self.ds_session_id: Optional[str] = None

    def _get_headers(self, extra: dict = None) -> dict:
        headers = {
            "x-client-platform": self.client_platform,
            "x-client-version": self.client_version,
            "x-client-locale": self.client_locale,
            "x-client-bundle-id": self.bundle_id,
            "x-rangers-id": self.rangers_id,
            "x-client-timezone-offset": str(self.timezone_offset),
            "user-agent": f"DeepSeek/{self.client_version} Android/36",
            "authorization": f"Bearer {self.bearer_token}",
            "accept": "application/json",
            "accept-charset": "UTF-8",
            "accept-encoding": "gzip",
        }
        if extra:
            headers.update(extra)
        return headers

    def create_chat_session(self, model_type: str = "default") -> dict:
        url = f"{self.BASE_URL}/api/v0/chat_session/create"
        resp = self.session.post(
            url,
            headers=self._get_headers({"content-type": "application/json"}),
            json={},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        session = data["data"]["biz_data"]["chat_session"]
        self.current_chat_session_id = session["id"]
        for cookie in resp.cookies:
            if hasattr(cookie, 'name') and cookie.name == "ds_session_id":
                self.ds_session_id = cookie.value
                break
        return {
            "session_id": session["id"],
            "seq_id": session["seq_id"],
            "model_type": session["model_type"],
            "ttl_seconds": data["data"]["biz_data"]["ttl_seconds"],
            "ds_session_id": self.ds_session_id
        }

    def create_pow_challenge(self, target_path: str = "/api/v0/chat/completion") -> dict:
        url = f"{self.BASE_URL}/api/v0/chat/create_pow_challenge"
        resp = self.session.post(
            url,
            headers=self._get_headers({"content-type": "application/json"}),
            json={"target_path": target_path},
            timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        return data["data"]["biz_data"]["challenge"]

    def send_message(
        self,
        prompt: str,
        chat_session_id: Optional[str] = None,
        parent_message_id: Optional[int] = None,
        model_type: str = "expert",
        thinking_enabled: bool = False,
        search_enabled: bool = False,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> dict:
        session_id = chat_session_id or self.current_chat_session_id
        if not session_id:
            raise ValueError("chat_session_id gerekli!")

        challenge_data = self.create_pow_challenge()
        pow_response = self.pow_solver.solve_challenge(challenge_data)

        url = f"{self.BASE_URL}/api/v0/chat/completion"
        payload = {
            "chat_session_id": session_id,
            "parent_message_id": parent_message_id,
            "prompt": prompt,
            "ref_file_ids": [],
            "thinking_enabled": thinking_enabled,
            "search_enabled": search_enabled,
            "audio_id": None,
            "preempt": False,
            "model_type": model_type,
            "action": None
        }
        headers = self._get_headers({
            "content-type": "application/json",
            "x-ds-pow-response": pow_response
        })
        resp = self.session.post(url, headers=headers, json=payload, stream=True, timeout=120)
        resp.raise_for_status()

        full_text = ""
        title = None
        message_ids = {}

        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("event: "):
                continue
            if line.startswith("data: "):
                data_str = line[6:]
                try:
                    data = json.loads(data_str)
                    if "request_message_id" in data:
                        message_ids = {
                            "request_message_id": data.get("request_message_id"),
                            "response_message_id": data.get("response_message_id"),
                            "model_type": data.get("model_type")
                        }
                    elif "content" in data and "v" not in data:
                        title = data.get("content")
                    elif "v" in data:
                        v = data["v"]
                        if isinstance(v, str) and v:
                            full_text += v
                            if on_chunk:
                                on_chunk(v)
                        elif isinstance(v, dict) and "response" in v:
                            fragments = v["response"].get("fragments", [])
                            for frag in fragments:
                                if frag.get("type") == "RESPONSE":
                                    content = frag.get("content", "")
                                    if content:
                                        full_text += content
                                        if on_chunk:
                                            on_chunk(content)
                except json.JSONDecodeError:
                    pass

        return {
            "text": full_text,
            "title": title,
            "message_ids": message_ids,
            "chat_session_id": session_id
        }

    def send_message_stream(
        self,
        prompt: str,
        chat_session_id: Optional[str] = None,
        model_type: str = "expert",
        thinking_enabled: bool = False,
        search_enabled: bool = False
    ) -> Generator[str, None, None]:
        session_id = chat_session_id or self.current_chat_session_id
        if not session_id:
            raise ValueError("chat_session_id gerekli!")

        challenge_data = self.create_pow_challenge()
        pow_response = self.pow_solver.solve_challenge(challenge_data)

        url = f"{self.BASE_URL}/api/v0/chat/completion"
        payload = {
            "chat_session_id": session_id,
            "parent_message_id": None,
            "prompt": prompt,
            "ref_file_ids": [],
            "thinking_enabled": thinking_enabled,
            "search_enabled": search_enabled,
            "audio_id": None,
            "preempt": False,
            "model_type": model_type,
            "action": None
        }
        headers = self._get_headers({
            "content-type": "application/json",
            "x-ds-pow-response": pow_response
        })
        resp = self.session.post(url, headers=headers, json=payload, stream=True, timeout=120)
        resp.raise_for_status()

        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            try:
                data = json.loads(data_str)
                v = data.get("v", "")
                if isinstance(v, str) and v:
                    yield v
                elif isinstance(v, dict) and "response" in v:
                    fragments = v["response"].get("fragments", [])
                    for frag in fragments:
                        if frag.get("type") == "RESPONSE":
                            content = frag.get("content", "")
                            if content:
                                yield content
            except json.JSONDecodeError:
                pass

    def chat(
        self,
        prompt: str,
        model_type: str = "expert",
        thinking_enabled: bool = False,
        search_enabled: bool = False,
        on_chunk: Optional[Callable[[str], None]] = None
    ) -> dict:
        if not self.current_chat_session_id:
            session = self.create_chat_session(model_type=model_type)
        return self.send_message(
            prompt=prompt, model_type=model_type,
            thinking_enabled=thinking_enabled, search_enabled=search_enabled,
            on_chunk=on_chunk
        )


def main():
    BEARER_TOKEN = "YOUR_TOKEN"

    client = DeepSeekAndroidClient(bearer_token=BEARER_TOKEN)

    print("=" * 60)
    print("  DEEPSEEK SOHBET BOTU")
    print("=" * 60)
    print("  Komutlar: /exit (cikis), /new (yeni oturum), /think (dusunme modu)")
    print("=" * 60 + "\n")

    thinking_enabled = False

    try:
        print("Oturum olusturuluyor...")
        session = client.create_chat_session()
        print(f"Oturum baslatildi! ID: {session['session_id'][:12]}...\n")
    except Exception as e:
        print(f"Oturum baslatma hatasi: {e}")
        return

    while True:
        try:
            user_input = input("Sen: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGorusuruz!")
            break

        if not user_input:
            continue

        if user_input.lower() == "/exit":
            print("Gorusuruz!")
            break

        if user_input.lower() == "/new":
            try:
                session = client.create_chat_session()
                print(f"Yeni oturum baslatildi! ID: {session['session_id'][:12]}...\n")
            except Exception as e:
                print(f"Hata: {e}")
            continue

        if user_input.lower() == "/think":
            thinking_enabled = not thinking_enabled
            print(f"Dusunme modu: {'ACIK' if thinking_enabled else 'KAPALI'}\n")
            continue

        try:
            print("DeepSeek: ", end="", flush=True)
            for chunk in client.send_message_stream(
                prompt=user_input,
                thinking_enabled=thinking_enabled
            ):
                print(chunk, end="", flush=True)
            print("\n")
        except Exception as e:
            print(f"\nHata: {e}\n")


if __name__ == "__main__":
    main()
