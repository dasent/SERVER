from flask import Flask, request, jsonify, render_template, redirect, url_for
import sqlite3
import random
import string
import os
import base64
from datetime import datetime, timedelta
from urllib.parse import quote  # Reemplazo de werkzeug.urls.url_quote
import google.auth
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, render_template, redirect, url_for
from urllib.parse import quote as url_quote  # Cambiar esta línea

app = Flask(__name__)

# Resto de tu código...


app = Flask(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# Inicializar la base de datos
def initialize_database():
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS licenses (
                        id INTEGER PRIMARY KEY,
                        token TEXT,
                        duration INTEGER,
                        active INTEGER,
                        created_at TIMESTAMP
                    )''')
    conn.commit()
    conn.close()

initialize_database()

# Función para generar token de licencia
def generate_license_token(duration):
    token = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()
    created_at = datetime.now()
    cursor.execute("INSERT INTO licenses (token, duration, active, created_at) VALUES (?, ?, 1, ?)", (token, duration, created_at))
    conn.commit()
    conn.close()
    return token

# Ruta de inicio de sesión para el administrador
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin':  # Autenticación de ejemplo
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('login.html', message='Credenciales incorrectas')
    return render_template('login.html')

# Panel de control del administrador
@app.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')

# Ruta para generar tokens de licencia
@app.route('/generate_license', methods=['POST'])
def generate_license():
    duration = int(request.form['duration'])
    token = generate_license_token(duration)
    return render_template('admin_dashboard.html', message=f'Token generado: {token}')

# Enviar token de licencia por correo electrónico con OAuth2
def send_license_email(email, token):
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token_file:
            token_file.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)
    
    message = MIMEMultipart()
    message['From'] = 'your_email@gmail.com'
    message['To'] = email
    message['Subject'] = 'Token de Licencia'

    body = f'Se ha generado un nuevo token de licencia para usted: {token}'
    message.attach(MIMEText(body, 'plain'))

    raw = base64.urlsafe_b64encode(message.as_string().encode()).decode()
    message = {'raw': raw}

    try:
        service.users().messages().send(userId='me', body=message).execute()
        print('Correo electrónico enviado correctamente')
    except Exception as e:
        print(f'Ocurrió un error: {e}')

# Distribuir token de licencia
@app.route('/distribute_license', methods=['POST'])
def distribute_license():
    email = request.form['email']
    token = request.form['token']
    send_license_email(email, token)
    return render_template('admin_dashboard.html', message=f'Token enviado a {email}')

# Validar token de licencia
@app.route('/validate_license', methods=['POST'])
def validate_license():
    data = request.get_json()
    token = data.get('token')
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()
    cursor.execute("SELECT token, duration, created_at, active FROM licenses WHERE token = ?", (token,))
    row = cursor.fetchone()
    conn.close()

    if row:
        token, duration, created_at, active = row
        if active == 1:
            expiration_date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f') + timedelta(days=duration*30)
            if datetime.now() < expiration_date:
                remaining_days = (expiration_date - datetime.now()).days
                return jsonify({'valid': True, 'remaining_days': remaining_days, 'duration': duration})
    return jsonify({'valid': False, 'remaining_days': 0, 'duration': 0})

# Ver y gestionar licencias
@app.route('/manage_licenses', methods=['GET', 'POST'])
def manage_licenses():
    if request.method == 'POST':
        action = request.form.get('action')
        token = request.form.get('token')
        
        with sqlite3.connect('licenses.db') as conn:
            if action == 'suspend':
                conn.execute('UPDATE licenses SET active = 0 WHERE token = ?', (token,))
            elif action == 'activate':
                conn.execute('UPDATE licenses SET active = 1 WHERE token = ?', (token,))
            elif action == 'delete':
                conn.execute('DELETE FROM licenses WHERE token = ?', (token,))
            conn.commit()
    
    with sqlite3.connect('licenses.db') as conn:
        cursor = conn.execute('SELECT id, token, created_at, duration, active FROM licenses')
        licenses = cursor.fetchall()
    
    return render_template('manage_licenses.html', licenses=licenses)

# Mostrar todas las licencias activas
@app.route('/active_licenses')
def active_licenses():
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, token, duration, created_at, active FROM licenses")
    rows = cursor.fetchall()
    conn.close()
    licenses = []
    for row in rows:
        id, token, duration, created_at, active = row
        expiration_date = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S.%f') + timedelta(days=duration*30)
        remaining_days = (expiration_date - datetime.now()).days if active == 1 else 0
        licenses.append({
            'id': id,
            'token': token,
            'duration': duration,
            'created_at': created_at,
            'active': active,
            'remaining_days': remaining_days,
            'expired': remaining_days <= 0
        })
    return render_template('active_licenses.html', licenses=licenses)

# Suspender, activar, eliminar o cambiar la duración de las licencias
@app.route('/modify_license', methods=['POST'])
def modify_license():
    license_id = int(request.form['license_id'])
    action = request.form['action']
    new_duration = request.form.get('new_duration')
    conn = sqlite3.connect('licenses.db')
    cursor = conn.cursor()
    if action == 'suspend':
        cursor.execute("UPDATE licenses SET active = 0 WHERE id = ?", (license_id,))
    elif action == 'activate':
        cursor.execute("UPDATE licenses SET active = 1 WHERE id = ?", (license_id,))
    elif action == 'delete':
        cursor.execute("DELETE FROM licenses WHERE id = ?", (license_id,))
    elif action == 'change_duration' and new_duration:
        cursor.execute("UPDATE licenses SET duration = ? WHERE id = ?", (new_duration, license_id))
    conn.commit()
    conn.close()
    return redirect(url_for('active_licenses'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
