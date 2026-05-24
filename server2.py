#!/usr/bin/env python3
"""
NVDI Mail Server 1
WebSocket + HTTP health check для Render
"""

import asyncio
import json
import os
import hashlib
import base64
from datetime import datetime
import websockets
from websockets.asyncio.server import serve

SERVER_NAME = "NVDI Server 2"
DATA_FILE = "server2_data.json"
users, mailboxes, sessions = {}, {}, {}


# ===========================================================================
# ДАННЫЕ
# ===========================================================================
def load_data():
    global users, mailboxes
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            users = data.get('users', {})
            mailboxes = data.get('mailboxes', {})
    except:
        pass

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': users, 'mailboxes': mailboxes}, f, ensure_ascii=False, indent=2)

def hash_password(password):
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return base64.b64encode(salt + h).decode()

def verify_password(password, stored):
    try:
        data = base64.b64decode(stored)
        return hashlib.pbkdf2_hmac('sha256', password.encode(), data[:16], 100000) == data[16:]
    except:
        return False

def generate_token():
    return base64.b64encode(os.urandom(32)).decode()


# ===========================================================================
# ДЕЙСТВИЯ
# ===========================================================================
def handle_action(data):
    action = data.get('action')

    if action == 'register':
        username = data.get('username', '').strip()
        password = data.get('password', '')
        if not username or not password:
            return {'success': False, 'error': 'Логин и пароль обязательны'}
        if len(username) < 3:
            return {'success': False, 'error': 'Логин минимум 3 символа'}
        if len(password) < 4:
            return {'success': False, 'error': 'Пароль минимум 4 символа'}
        if username in users:
            return {'success': False, 'error': 'Пользователь уже существует'}
        users[username] = {'password_hash': hash_password(password), 'created_at': datetime.now().isoformat()}
        mailboxes[username] = []
        save_data()
        print(f"[{SERVER_NAME}] + {username}")
        return {'success': True, 'message': 'Аккаунт создан!', 'server': SERVER_NAME}

    elif action == 'login':
        username = data.get('username', '').strip()
        password = data.get('password', '')
        if username not in users:
            return {'success': False, 'error': 'Пользователь не найден'}
        if not verify_password(password, users[username]['password_hash']):
            return {'success': False, 'error': 'Неверный пароль'}
        token = generate_token()
        sessions[token] = username
        print(f"[{SERVER_NAME}] + Вход: {username}")
        return {'success': True, 'token': token, 'username': username, 'server': SERVER_NAME}

    elif action == 'send':
        token = data.get('token', '')
        to = data.get('to', '').strip()
        subject = data.get('subject', '')
        body = data.get('body', '')
        if token not in sessions:
            return {'success': False, 'error': 'Не авторизован'}
        if to not in users:
            return {'success': False, 'error': f'Пользователь {to} не найден'}
        sender = sessions[token]
        mail = {
            'id': len(mailboxes.get(to, [])) + 1,
            'from': sender, 'to': to, 'subject': subject, 'body': body,
            'date': datetime.now().strftime('%d.%m.%Y %H:%M:%S'), 'read': False
        }
        mailboxes[to].append(mail)
        save_data()
        print(f"[{SERVER_NAME}] {sender} -> {to}")
        return {'success': True, 'message': 'Отправлено!'}

    elif action == 'inbox':
        token = data.get('token', '')
        if token not in sessions:
            return {'success': False, 'error': 'Не авторизован'}
        username = sessions[token]
        return {
            'success': True, 'username': username,
            'inbox': mailboxes.get(username, []),
            'count': len(mailboxes.get(username, [])),
            'server': SERVER_NAME
        }

    elif action == 'delete':
        token = data.get('token', '')
        mail_id = data.get('mail_id', -1)
        if token not in sessions:
            return {'success': False, 'error': 'Не авторизован'}
        username = sessions[token]
        mailboxes[username] = [m for m in mailboxes.get(username, []) if m['id'] != mail_id]
        save_data()
        return {'success': True, 'message': 'Удалено'}

    elif action == 'status':
        return {
            'success': True, 'server': SERVER_NAME,
            'users': len(users),
            'mails': sum(len(v) for v in mailboxes.values())
        }

    return {'success': False, 'error': 'Неизвестное действие'}


# ===========================================================================
# HTTP HEALTH CHECK + WebSocket
# ===========================================================================
async def health_check(host, port):
    """Отвечает на HTTP health check от Render."""
    async def handler(reader, writer):
        try:
            request = await asyncio.wait_for(reader.read(1024), timeout=5)
            if request:
                response = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: text/plain\r\n"
                    b"Content-Length: 2\r\n"
                    b"Connection: close\r\n"
                    b"\r\n"
                    b"OK"
                )
                writer.write(response)
                await writer.drain()
        except:
            pass
        finally:
            writer.close()
    
    server = await asyncio.start_server(handler, host, port)
    return server


async def ws_handler(websocket):
    """Обработчик WebSocket."""
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                response = handle_action(data)
                await websocket.send(json.dumps(response, ensure_ascii=False))
            except json.JSONDecodeError:
                await websocket.send(json.dumps({'success': False, 'error': 'Неверный JSON'}))
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"[{SERVER_NAME}] Ошибка: {e}")


async def main():
    load_data()
    
    port = int(os.environ.get('PORT', 5001))
    
    print(f"{'='*50}")
    print(f"  {SERVER_NAME}")
    print(f"  Порт: {port}")
    print(f"  Пользователей: {len(users)}")
    print(f"{'='*50}")
    
    # WebSocket сервер
    ws_server = await serve(ws_handler, '0.0.0.0', port)
    print(f"  WebSocket: ws://0.0.0.0:{port}")
    print(f"  Health check: HTTP 200 OK")
    
    await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())
