#!/usr/bin/env python3
"""
NVDI Mail Server 2
WebSocket HTTPS сервер для Render
"""

import asyncio
import json
import os
import hashlib
import base64
from datetime import datetime
import websockets

SERVER_NAME = "NVDI Server 2"
DATA_FILE = "server2_data.json"

users = {}
mailboxes = {}
sessions = {}

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
        salt, h = data[:16], data[16:]
        return hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000) == h
    except:
        return False

def generate_token():
    return base64.b64encode(os.urandom(32)).decode()

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
        
        users[username] = {
            'password_hash': hash_password(password),
            'created_at': datetime.now().isoformat()
        }
        mailboxes[username] = []
        save_data()
        
        print(f"[{SERVER_NAME}] + Регистрация: {username}")
        return {'success': True, 'message': f'Регистрация на {SERVER_NAME} успешна!', 'server': SERVER_NAME}
    
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
            'from': sender,
            'to': to,
            'subject': subject,
            'body': body,
            'date': datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            'read': False
        }
        
        mailboxes[to].append(mail)
        save_data()
        
        print(f"[{SERVER_NAME}] Письмо: {sender} -> {to}")
        return {'success': True, 'message': f'Письмо отправлено через {SERVER_NAME}'}
    
    elif action == 'inbox':
        token = data.get('token', '')
        
        if token not in sessions:
            return {'success': False, 'error': 'Не авторизован'}
        
        username = sessions[token]
        inbox = mailboxes.get(username, [])
        
        return {'success': True, 'username': username, 'inbox': inbox, 'count': len(inbox), 'server': SERVER_NAME}
    
    elif action == 'delete':
        token = data.get('token', '')
        mail_id = data.get('mail_id', -1)
        
        if token not in sessions:
            return {'success': False, 'error': 'Не авторизован'}
        
        username = sessions[token]
        mailboxes[username] = [m for m in mailboxes.get(username, []) if m['id'] != mail_id]
        save_data()
        
        return {'success': True, 'message': 'Письмо удалено'}
    
    elif action == 'status':
        return {
            'success': True,
            'server': SERVER_NAME,
            'users': len(users),
            'mails': sum(len(v) for v in mailboxes.values())
        }
    
    return {'success': False, 'error': 'Неизвестное действие'}


async def handler(websocket):
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


async def main():
    load_data()
    port = int(os.environ.get('PORT', 5002))
    
    print(f"{'='*50}")
    print(f"  {SERVER_NAME}")
    print(f"  Порт: {port}")
    print(f"{'='*50}")
    
    async with websockets.serve(handler, '0.0.0.0', port):
        await asyncio.Future()


if __name__ == '__main__':
    asyncio.run(main())