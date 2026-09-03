from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, send, emit, join_room, leave_room
import sqlite3
import hashlib
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-it'
socketio = SocketIO(app, cors_allowed_origins="*")

# ---------- DATABASE ----------
def init_db():
    conn = sqlite3.connect('chat.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user',
        joined TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        creator TEXT,
        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        room TEXT,
        username TEXT,
        content TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES ('admin', 'admin123', 'admin')")
    c.execute("INSERT OR IGNORE INTO rooms (name, creator) VALUES ('General', 'system')")
    c.execute("INSERT OR IGNORE INTO rooms (name, creator) VALUES ('Tech', 'system')")
    c.execute("INSERT OR IGNORE INTO rooms (name, creator) VALUES ('Gaming', 'system')")
    conn.commit()
    conn.close()

init_db()

def get_db():
    return sqlite3.connect('chat.db')

def hash_pass(pwd):
    return hashlib.md5(pwd.encode()).hexdigest()

# ---------- ROUTES ----------
@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_pass(request.form['password'])
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user'] = username
            session['role'] = user[3]
            return redirect(url_for('chat'))
        else:
            return render_template_string(LOGIN_PAGE, error='Invalid credentials')
    return render_template_string(LOGIN_PAGE, error=None)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_pass(request.form['password'])
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except:
            conn.close()
            return render_template_string(REGISTER_PAGE, error='Username already exists')
    return render_template_string(REGISTER_PAGE, error=None)

@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    rooms = conn.execute("SELECT name FROM rooms").fetchall()
    conn.close()
    return render_template_string(CHAT_PAGE, username=session['user'], role=session.get('role', 'user'), rooms=rooms)

@app.route('/create_room', methods=['POST'])
def create_room():
    if 'user' not in session:
        return redirect(url_for('login'))
    room_name = request.form['room_name']
    conn = get_db()
    try:
        conn.execute("INSERT INTO rooms (name, creator) VALUES (?, ?)", (room_name, session['user']))
        conn.commit()
    except:
        pass
    conn.close()
    return redirect(url_for('chat'))

@app.route('/admin')
def admin_panel():
    if 'user' not in session or session.get('role') != 'admin':
        return "Access Denied", 403
    conn = get_db()
    users = conn.execute("SELECT id, username, role FROM users").fetchall()
    rooms = conn.execute("SELECT * FROM rooms").fetchall()
    conn.close()
    return render_template_string(ADMIN_PAGE, users=users, rooms=rooms)

@app.route('/admin/promote/<int:user_id>')
def promote_user(user_id):
    if 'user' not in session or session.get('role') != 'admin':
        return "Access Denied", 403
    conn = get_db()
    conn.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_room/<room_name>')
def delete_room(room_name):
    if 'user' not in session or session.get('role') != 'admin':
        return "Access Denied", 403
    conn = get_db()
    conn.execute("DELETE FROM rooms WHERE name = ?", (room_name,))
    conn.execute("DELETE FROM messages WHERE room = ?", (room_name,))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- SOCKET.IO EVENTS ----------
@socketio.on('join')
def handle_join(data):
    username = data['username']
    room = data['room']
    join_room(room)
    emit('message', {'username': 'System', 'content': f'{username} joined the room', 'time': datetime.now().strftime('%H:%M')}, room=room)

@socketio.on('leave')
def handle_leave(data):
    username = data['username']
    room = data['room']
    leave_room(room)
    emit('message', {'username': 'System', 'content': f'{username} left the room', 'time': datetime.now().strftime('%H:%M')}, room=room)

@socketio.on('message')
def handle_message(data):
    room = data['room']
    username = data['username']
    content = data['content']
    conn = get_db()
    conn.execute("INSERT INTO messages (room, username, content) VALUES (?, ?, ?)", (room, username, content))
    conn.commit()
    conn.close()
    emit('message', {'username': username, 'content': content, 'time': datetime.now().strftime('%H:%M')}, room=room)

@socketio.on('get_history')
def handle_history(data):
    room = data['room']
    conn = get_db()
    messages = conn.execute("SELECT username, content, timestamp FROM messages WHERE room = ? ORDER BY timestamp ASC LIMIT 50", (room,)).fetchall()
    conn.close()
    history = [{'username': m[0], 'content': m[1], 'time': m[2][11:16]} for m in messages]
    emit('history', history, room=request.sid)

# ---------- HTML TEMPLATES ----------
LOGIN_PAGE = '''
<!DOCTYPE html>
<html>
<head><title>Login</title>
<style>
body{font-family:sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
.container{background:#161b22;padding:2rem;border-radius:12px;width:350px}
h2{text-align:center}
input{width:100%;padding:10px;margin:8px 0;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}
button{width:100%;padding:10px;background:#238636;border:none;border-radius:6px;color:white;font-weight:bold}
button:hover{background:#2ea043}
.error{color:#f85149;text-align:center}
a{color:#58a6ff;text-decoration:none}
</style>
</head>
<body>
<div class=container>
<h2>Login</h2>
<form method=post>
<input name=username placeholder=Username required>
<input name=password type=password placeholder=Password required>
<button type=submit>Login</button>
{% if error %}<p class=error>{{ error }}</p>{% endif %}
</form>
<p style=text-align:center><a href='/register'>Create account</a></p>
</div>
</body>
</html>
'''

REGISTER_PAGE = '''
<!DOCTYPE html>
<html>
<head><title>Register</title>
<style>body{font-family:sans-serif;background:#0d1117;color:#e6edf3;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}
.container{background:#161b22;padding:2rem;border-radius:12px;width:350px}
h2{text-align:center}
input{width:100%;padding:10px;margin:8px 0;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}
button{width:100%;padding:10px;background:#238636;border:none;border-radius:6px;color:white;font-weight:bold}
button:hover{background:#2ea043}
.error{color:#f85149;text-align:center}
a{color:#58a6ff;text-decoration:none}
</style>
</head>
<body>
<div class=container>
<h2>Register</h2>
<form method=post>
<input name=username placeholder=Username required>
<input name=password type=password placeholder=Password required>
<button type=submit>Register</button>
{% if error %}<p class=error>{{ error }}</p>{% endif %}
</form>
<p style=text-align:center><a href='/login'>Back to login</a></p>
</div>
</body>
</html>
'''

CHAT_PAGE = '''
<!DOCTYPE html>
<html>
<head><title>Chat</title>
<script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:sans-serif;background:#0d1117;color:#e6edf3;height:100vh;display:flex}
.sidebar{width:200px;background:#161b22;padding:20px;border-right:1px solid #30363d}
.sidebar h3{color:#58a6ff}
.sidebar a{display:block;color:#58a6ff;text-decoration:none;margin:10px 0}
.sidebar .room{display:block;padding:8px;border-radius:6px;cursor:pointer;margin:4px 0}
.sidebar .room:hover{background:#30363d}
.sidebar .room.active{background:#238636}
.chat{flex:1;display:flex;flex-direction:column}
.header{background:#161b22;padding:15px 20px;border-bottom:1px solid #30363d;display:flex;justify-content:space-between}
#messages{flex:1;padding:20px;overflow-y:auto}
.msg{margin:8px 0}
.msg .user{color:#58a6ff;font-weight:bold}
.msg .time{color:#8b949e;font-size:12px;margin-left:10px}
.msg .content{word-wrap:break-word}
.input-area{display:flex;padding:15px;background:#161b22;border-top:1px solid #30363d}
.input-area input{flex:1;padding:12px;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}
.input-area button{padding:12px 24px;margin-left:10px;background:#238636;border:none;border-radius:6px;color:white;font-weight:bold;cursor:pointer}
.input-area button:hover{background:#2ea043}
</style>
</head>
<body>
<div class=sidebar>
<h3>Rooms</h3>
<div id=roomList>
{% for room in rooms %}
<div class=room onclick="joinRoom('{{ room[0] }}')">{{ room[0] }}</div>
{% endfor %}
</div>
<form action='/create_room' method=post style=margin-top:20px>
<input name=room_name placeholder="New room" style="width:100%;padding:8px;border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3">
<button type=submit style="width:100%;margin-top:8px;padding:8px;background:#238636;border:none;border-radius:6px;color:white">Create</button>
</form>
<a href='/admin'>Admin Panel</a>
<a href='/logout'>Logout</a>
</div>
<div class=chat>
<div class=header><span>Welcome, {{ username }} ({{ role }})</span><span id=currentRoom>General</span></div>
<div id=messages></div>
<div class=input-area>
<input id=msgInput placeholder="Type message..." onkeydown="if(event.key==='Enter') sendMessage()">
<button onclick="sendMessage()">Send</button>
</div>
</div>
<script>
let currentRoom = 'General';
const socket = io();
const username = '{{ username }}';
function joinRoom(room) {
    if (currentRoom) socket.emit('leave', {username, room: currentRoom});
    currentRoom = room;
    document.getElementById('currentRoom').textContent = room;
    document.getElementById('messages').innerHTML = '';
    socket.emit('join', {username, room});
    socket.emit('get_history', {room});
}
function sendMessage() {
    const input = document.getElementById('msgInput');
    if (input.value.trim()) {
        socket.emit('message', {room: currentRoom, username, content: input.value});
        input.value = '';
    }
}
socket.on('message', (data) => {
    const div = document.createElement('div');
    div.className = 'msg';
    div.innerHTML = `<span class="user">${data.username}</span><span class="time">${data.time}</span><div class="content">${data.content}</div>`;
    document.getElementById('messages').appendChild(div);
    document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
});
socket.on('history', (history) => {
    history.forEach(msg => {
        const div = document.createElement('div');
        div.className = 'msg';
        div.innerHTML = `<span class="user">${msg.username}</span><span class="time">${msg.time}</span><div class="content">${msg.content}</div>`;
        document.getElementById('messages').appendChild(div);
    });
    document.getElementById('messages').scrollTop = document.getElementById('messages').scrollHeight;
});
window.onload = () => joinRoom('General');
</script>
</div>
</body>
</html>
'''

ADMIN_PAGE = '''
<!DOCTYPE html>
<html>
<head><title>Admin Panel</title>
<style>
body{font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:20px}
h2{color:#58a6ff}
table{width:100%;border-collapse:collapse;margin-top:20px}
th,td{border:1px solid #30363d;padding:10px;text-align:left}
th{background:#161b22}
a{color:#58a6ff;text-decoration:none}
.btn{padding:4px 12px;background:#238636;border-radius:6px;color:white}
.btn:hover{background:#2ea043}
.btn-danger{background:#da3633}
.btn-danger:hover{background:#f85149}
</style>
</head>
<body>
<h2>Admin Panel</h2>
<a href='/chat'>Back to Chat</a>
<h3>Users</h3>
<table>
<tr><th>ID</th><th>Username</th><th>Role</th><th>Action</th></tr>
{% for u in users %}
<tr><td>{{ u[0] }}</td><td>{{ u[1] }}</td><td>{{ u[2] }}</td>
<td>{% if u[2] != 'admin' %}<a href='/admin/promote/{{ u[0] }}' class=btn>Promote to Admin</a>{% else %}Already Admin{% endif %}</td></tr>
{% endfor %}
</table>
<h3>Rooms</h3>
<table>
<tr><th>Name</th><th>Creator</th><th>Action</th></tr>
{% for r in rooms %}
<tr><td>{{ r[1] }}</td><td>{{ r[2] }}</td><td><a href='/admin/delete_room/{{ r[1] }}' class='btn btn-danger'>Delete</a></td></tr>
{% endfor %}
</table>
</body>
</html>
'''

# ---------- MAIN ----------
if __name__ == "__main__":
    print("Chat App Running...")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
