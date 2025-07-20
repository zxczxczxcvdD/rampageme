import os
import psycopg2

# Попробовать взять DATABASE_URL из переменных окружения (Railway), иначе использовать PUBLIC_URL для локального запуска
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    DATABASE_URL = 'postgresql://postgres:ZXAnJxWozHsJWgxHFuJzKXVEZfuZIEGy@crossover.proxy.rlwy.net:15802/railway'

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# --- Создание таблиц ---
cur.execute('''
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    passed_captcha BOOLEAN DEFAULT FALSE,
    registered_at TIMESTAMP DEFAULT NOW()
)
''')
cur.execute('''
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id BIGINT PRIMARY KEY,
    active BOOLEAN,
    expires_at BIGINT,
    created_by BIGINT,
    created_at BIGINT
)
''')
cur.execute('''
CREATE TABLE IF NOT EXISTS referrals (
    referrer_id BIGINT,
    referred_id BIGINT PRIMARY KEY,
    referred_at TIMESTAMP DEFAULT NOW()
)
''')
cur.execute('''
CREATE TABLE IF NOT EXISTS free_requests (
    user_id BIGINT PRIMARY KEY,
    count INT DEFAULT 0
)
''')
cur.execute('''
CREATE TABLE IF NOT EXISTS channels (
    id BIGINT PRIMARY KEY,
    link TEXT,
    name TEXT
)
''')
conn.commit()

# --- USERS ---
def add_user(user_id, username):
    cur.execute('INSERT INTO users (id, username) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING', (user_id, username))
    conn.commit()

def set_captcha_passed(user_id):
    cur.execute('UPDATE users SET passed_captcha = TRUE WHERE id = %s', (user_id,))
    conn.commit()

def has_passed_captcha(user_id):
    with conn.cursor() as cur:
        cur.execute('SELECT passed_captcha FROM users WHERE id = %s', (user_id,))
        row = cur.fetchone()
        return row and row[0]

def get_all_users():
    with conn.cursor() as cur:
        cur.execute('SELECT id, username FROM users')
        return cur.fetchall()

# --- SUBSCRIPTIONS ---
def add_subscription(user_id, expires_at, created_by):
    cur.execute('''
        INSERT INTO subscriptions (user_id, active, expires_at, created_by, created_at)
        VALUES (%s, TRUE, %s, %s, EXTRACT(EPOCH FROM NOW()))
        ON CONFLICT (user_id) DO UPDATE SET active = TRUE, expires_at = %s
    ''', (user_id, expires_at, created_by, expires_at))
    conn.commit()

def get_subscription(user_id):
    with conn.cursor() as cur:
        cur.execute('SELECT active, expires_at FROM subscriptions WHERE user_id = %s', (user_id,))
        return cur.fetchone()

def remove_subscription(user_id):
    cur.execute('DELETE FROM subscriptions WHERE user_id = %s', (user_id,))
    conn.commit()

def get_all_subscriptions():
    with conn.cursor() as cur:
        cur.execute('SELECT user_id, active, expires_at FROM subscriptions')
        return cur.fetchall()

# --- REFERRALS ---
def add_referral(referrer_id, referred_id):
    cur.execute('INSERT INTO referrals (referrer_id, referred_id) VALUES (%s, %s) ON CONFLICT DO NOTHING', (referrer_id, referred_id))
    conn.commit()

def get_referrals(referrer_id):
    with conn.cursor() as cur:
        cur.execute('SELECT referred_id FROM referrals WHERE referrer_id = %s', (referrer_id,))
        return [row[0] for row in cur.fetchall()]

# --- FREE REQUESTS ---
def get_free_requests(user_id):
    with conn.cursor() as cur:
        cur.execute('SELECT count FROM free_requests WHERE user_id = %s', (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0

def add_free_request(user_id, count=1):
    cur.execute('INSERT INTO free_requests (user_id, count) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET count = free_requests.count + %s', (user_id, count, count))
    conn.commit()

def use_free_request(user_id):
    with conn.cursor() as cur:
        cur.execute('SELECT count FROM free_requests WHERE user_id = %s', (user_id,))
        row = cur.fetchone()
        if row is None:
            # Если записи нет, создаём с 0 и не даём уйти в минус
            cur.execute('INSERT INTO free_requests (user_id, count) VALUES (%s, 0) ON CONFLICT (user_id) DO NOTHING', (user_id,))
            conn.commit()
            return False
        if row[0] > 0:
            cur.execute('UPDATE free_requests SET count = count - 1 WHERE user_id = %s', (user_id,))
            conn.commit()
            return True
        return False 

# --- КАНАЛЫ ---
def add_channel(channel_id, link, name):
    cur.execute('INSERT INTO channels (id, link, name) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING', (channel_id, link, name))
    conn.commit()

def remove_channel(channel_id):
    cur.execute('DELETE FROM channels WHERE id = %s', (channel_id,))
    conn.commit()

def get_channels():
    with conn.cursor() as cur2:
        cur2.execute('SELECT id, link, name FROM channels')
        return cur2.fetchall() 

def reset_all_captcha():
    cur.execute('UPDATE users SET passed_captcha = FALSE')
    conn.commit() 
