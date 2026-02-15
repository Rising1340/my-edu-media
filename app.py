import os, sqlite3, io, re, pyotp, qrcode, base64
from flask import Flask, render_template_string, request, redirect, session, abort, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "ULTIMATE_FINAL_SECRET_2026"
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- データベース初期化 ---
def init_db():
    conn = sqlite3.connect("blog.db")
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, totp_secret TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, content TEXT, views INTEGER DEFAULT 0, category TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER, name TEXT, body TEXT, ip_address TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    c.execute("CREATE TABLE IF NOT EXISTS ban_list (id INTEGER PRIMARY KEY AUTOINCREMENT, ip_address TEXT UNIQUE)")
    conn.commit(); conn.close()

init_db()

# --- アクセス制限（BAN）チェック ---
@app.before_request
def check_ban():
    user_ip = request.remote_addr
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    c.execute("SELECT 1 FROM ban_list WHERE ip_address = ?", (user_ip,))
    if c.fetchone():
        conn.close()
        return "<h1>403 禁止</h1>アクセスが制限されています。", 403
    conn.close()

# --- 分野別カラー ---
CAT_COLORS = {"数学": "#0076a8", "英語": "#e67e22", "理科": "#27ae60", "化学": "#5cb85c", "物理": "#d9534f", "その他": "#777777"}

# --- 広告枠 ---
AD_HTML = """
<div style="margin:2rem 0; padding:1rem; background:#fffdeb; border:1px solid #fef3c7; border-radius:8px; text-align:center;">
    <p style="font-size:12px; color:#92400e; margin:0 0-5px 0;">スポンサーリンク</p>
    <div style="height:90px; display:flex; align-items:center; justify-content:center; color:#f59e0b; font-weight:bold; border:1px dashed #f59e0b;">広告エリア</div>
</div>
"""

# --- 目次生成 ---
def generate_toc(content):
    if "[目次]" not in content: return content
    headings = re.findall(r'■\s*(.+)', content)
    if not headings: return content.replace("[目次]", "")
    toc_html = '<div style="background:#f8fafc; padding:1rem; border:1px solid #e2e8f0; border-radius:8px; margin-bottom:2rem;"><p style="font-weight:bold; margin:0;">目次</p><ul>'
    for h in headings: toc_html += f'<li>{h}</li>'
    return content.replace("[目次]", toc_html + "</ul></div>")

# --- 共通レイアウト ---
HTML_LAYOUT = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="google-site-verification" content="AvN-w3nxJ1uAhAyT4wvlIaqTYdCJCQTpwxtV6-pKcNA" />
    <title>放課後の学び場</title>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js" async></script>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <script>mermaid.initialize({startOnLoad:true});</script>
    <style>
        :root { --main: #004d71; --bg: #f4f7f9; }
        body { font-family: sans-serif; background: var(--bg); color: #333; margin: 0; line-height: 1.7; }
        nav { background: var(--main); color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }
        .main-container { max-width: 900px; margin: 2rem auto; padding: 0 1rem; }
        .owner-card { background: white; border-left: 5px solid var(--main); padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .article-wrap { background: white; border: 1px solid #e1e1e1; border-radius: 8px; padding: 2.5rem; margin-bottom: 2rem; }
        .btn { background: #0076a8; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; text-decoration: none; font-weight:bold; }
        input, textarea, select { width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 4px; margin-bottom: 1rem; box-sizing: border-box; }
        .card { background: white; border: 1px solid #e1e1e1; border-radius: 8px; padding: 1.5rem; cursor: pointer; transition: 0.2s; min-height: 140px; display: flex; flex-direction: column; }
        .card:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.1); }
        .mermaid { background: white; padding: 10px; border: 1px solid #eee; border-radius: 8px; margin: 1rem 0; }
    </style>
</head>
<body>
    <nav>
        <a href="/" style="color:white; text-decoration:none; font-weight:bold; font-size:1.5rem;">放課後の学び場</a>
        <div>{% if session.get('user_id') %}<a href="/logout" style="color:white; font-size:12px;">ログアウト</a>{% else %}<a href="/login" style="color:white; font-size:12px; opacity:0.5;">管理者</a>{% endif %}</div>
    </nav>
    <div class="main-container">{{ content | safe }}</div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    if request.method == "POST" and session.get('user_id'):
        c.execute("INSERT INTO posts (title, content, category) VALUES (?, ?, ?)", (request.form.get("title"), request.form.get("content"), request.form.get("category")))
        conn.commit()

    query = request.args.get('q', '')
    if query:
        c.execute("SELECT id, title, category, views FROM posts WHERE title LIKE ? OR content LIKE ? ORDER BY id DESC", (f'%{query}%', f'%{query}%'))
    else:
        c.execute("SELECT id, title, category, views FROM posts ORDER BY id DESC")
    posts = c.fetchall(); conn.close()
    
    owner_msg = """
    <div class="owner-card">
        <h4 style="margin:0 0 10px 0; color:var(--main);">運営主より</h4>
        <p style="margin:0; font-size:0.95rem;">
            このサイトは理系の大学生が運営しています。小学校から大学までの範囲で数学・英語・理科について皆さまのお役に立てるような記事を投稿したいと思っています。なにか質問などがありましたらコメントをしていただけたら幸いです。
        </p>
    </div>
    """

    form_html = ""
    if session.get('user_id'):
        form_html = f'<div style="background:white; padding:1.5rem; border:1px solid #ddd; border-radius:8px; margin-bottom:2rem;"><h3>📥 教材新規作成</h3><form method="post"><select name="category"><option>数学</option><option>英語</option><option>理科</option><option>化学</option><option>物理</option></select><input name="title" placeholder="タイトル" required><textarea name="content" placeholder="[目次] や ■見出し、[図解]...[/図解] が使えます" style="height:120px;" required></textarea><button type="submit" class="btn">公開</button></form></div>'

    search_bar = f'<form action="/" method="get" style="margin-bottom:2rem; display:flex; gap:10px;"><input type="text" name="q" placeholder="キーワード検索..." value="{query}" style="margin:0;"><button type="submit" class="btn">検索</button></form>'
    
    grid_html = '<div style="display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:1.5rem;">'
    for pid, title, cat, views in posts:
        color = CAT_COLORS.get(cat, "#777")
        grid_html += f'<div onclick="location.href=\'/post/{pid}\'" class="card" style="border-top: 5px solid {color};"><small style="color:{color}; font-weight:bold;">{cat}</small><h3 style="margin:5px 0 15px 0;">{title}</h3><small style="color:#999; margin-top:auto;">👁 {views} views</small></div>'
    
    return render_template_string(HTML_LAYOUT, content=owner_msg + form_html + search_bar + grid_html + "</div>")

@app.route("/post/<int:pid>", methods=["GET", "POST"])
def post_detail(pid):
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    if request.method == "POST":
        c.execute("INSERT INTO comments (post_id, name, body, ip_address) VALUES (?, ?, ?, ?)", (pid, request.form.get("name"), request.form.get("body"), request.remote_addr))
        conn.commit()
    
    c.execute("UPDATE posts SET views = views + 1 WHERE id = ?",(pid,))
    c.execute("SELECT title, content, category FROM posts WHERE id = ?",(pid,))
    p = c.fetchone()
    c.execute("SELECT id, name, body, ip_address FROM comments WHERE post_id = ? ORDER BY id DESC",(pid,))
    comments = c.fetchall(); conn.close()
    
    if not p: return redirect("/")
    processed_content = generate_toc(p[1]).replace("[図解]", '<div class="mermaid">').replace("[/図解]", '</div>')
    
    admin_tools = ""
    if session.get('user_id'):
        admin_tools = f'<div style="margin-top:2rem; background:#f1f5f9; padding:1.2rem; border-radius:8px;"><p style="margin:0; font-weight:bold;">管理者メニュー</p><a href="/edit/{pid}" class="btn" style="background:#666; font-size:12px;">編集</a> <a href="/delete/{pid}" style="color:#d9534f; margin-left:10px; font-size:12px;" onclick="return confirm(\'消去しますか？\')">削除</a></div>'

    comment_html = '<div style="margin-top:2rem; background:#fff; padding:2rem; border:1px solid #ddd; border-radius:8px;"><h4>💬 コメント</h4>'
    for cid, c_name, c_body, c_ip in comments:
        admin_btns = ""
        if session.get('user_id'):
            admin_btns = f'<div style="margin-top:5px;"><a href="/del_comm/{cid}" style="color:#d9534f; font-size:11px;">削除</a> | <a href="/ban/{cid}" style="color:#000; font-size:11px;">IPをBANする ({c_ip})</a></div>'
        comment_html += f'<div style="border-bottom:1px solid #eee; padding:15px 0;"><strong>{c_name}</strong><p style="margin:5px 0;">{c_body}</p>{admin_btns}</div>'
    
    comment_html += f'<form method="post" style="margin-top:2rem;"><input name="name" placeholder="名前" required><textarea name="body" placeholder="質問などはこちらへ" required></textarea><button class="btn">送信</button></form></div>'

    return render_template_string(HTML_LAYOUT, content=f'<div class="article-wrap"><small style="color:{CAT_COLORS.get(p[2])}; font-weight:bold;">{p[2]}</small><h1>{p[0]}</h1>{AD_HTML}<div style="white-space: pre-wrap;">{processed_content}</div>{AD_HTML}{admin_tools}</div>{comment_html}')

# --- 管理機能ルート (2FA) ---
@app.route("/register", methods=["GET", "POST"])
def register():
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    c.execute("SELECT count(*) FROM users"); count = c.fetchone()[0]; conn.close()
    if count >= 1: return "登録済みです"
    if request.method == "POST":
        u, p, secret = request.form["u"], request.form["p"], pyotp.random_base32()
        conn = sqlite3.connect("blog.db"); c = conn.cursor()
        c.execute("INSERT INTO users (username, password, totp_secret) VALUES (?, ?, ?)", (u, generate_password_hash(p), secret))
        conn.commit(); conn.close()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(name=u, issuer_name="EduMedia")
        qr = qrcode.make(uri); buf = io.BytesIO(); qr.save(buf, format="PNG")
        img = base64.b64encode(buf.getvalue()).decode()
        return f"<div style='text-align:center;'><h2>2FA設定</h2><img src='data:image/png;base64,{img}'><br><a href='/login'>ログインへ</a></div>"
    return "<form method='post'>ユーザー名：<input name='u'>パスワード：<input type='password' name='p'><input type='submit' value='登録'></form>"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u, p, t = request.form["u"], request.form["p"], request.form["t"]
        conn = sqlite3.connect("blog.db"); c = conn.cursor()
        c.execute("SELECT id, password, totp_secret FROM users WHERE username = ?", (u,))
        user = c.fetchone(); conn.close()
        
        # --- 2FAのチェックを環境変数で切り替えるように変更 ---
        is_2fa_enabled = os.environ.get('ENABLE_2FA', 'True') == 'True'
        
        if user and check_password_hash(user[1], p):
            if not is_2fa_enabled or pyotp.TOTP(user[2]).verify(t):
                session['user_id'] = user[0]
                return redirect("/")
    
    # 2FAが無効な場合は、入力欄を表示しないように工夫（任意）
    return render_template_string(HTML_LAYOUT, content="<div class='article-wrap'><h2>管理者ログイン</h2><form method='post'><input name='u' placeholder='ユーザー名'><input type='password' name='p' placeholder='パスワード'><input name='t' placeholder='2FAコード（無効時は適当でOK）'><input type='submit' class='btn' value='ログイン'></form></div>")

@app.route("/logout")
def logout(): session.clear(); return redirect("/")

@app.route("/edit/<int:pid>", methods=["GET", "POST"])
def edit(pid):
    if not session.get('user_id'): abort(403)
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    if request.method == "POST":
        c.execute("UPDATE posts SET title=?, content=?, category=? WHERE id=?", (request.form["t"], request.form["c"], request.form["cat"], pid))
        conn.commit(); conn.close(); return redirect(f"/post/{pid}")
    c.execute("SELECT title, content, category FROM posts WHERE id=?", (pid,))
    p = c.fetchone(); conn.close()
    return render_template_string(HTML_LAYOUT, content=f'<div class="article-wrap"><h2>編集</h2><form method="post"><select name="cat"><option {"selected" if p[2]=="数学" else ""}>数学</option><option {"selected" if p[2]=="英語" else ""}>英語</option><option {"selected" if p[2]=="理科" else ""}>理科</option></select><input name="t" value="{p[0]}"><textarea name="c" style="height:300px;">{p[1]}</textarea><button class="btn">更新</button></form></div>')

@app.route("/delete/<int:pid>")
def delete(pid):
    if not session.get('user_id'): abort(403)
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    c.execute("DELETE FROM posts WHERE id=?"); c.execute("DELETE FROM comments WHERE post_id=?", (pid, pid))
    conn.commit(); conn.close(); return redirect("/")

@app.route("/del_comm/<int:cid>")
def del_comm(cid):
    if not session.get('user_id'): abort(403)
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    c.execute("DELETE FROM comments WHERE id = ?", (cid,))
    conn.commit(); conn.close(); return redirect(request.referrer)

@app.route("/ban/<int:cid>")
def ban_user(cid):
    if not session.get('user_id'): abort(403)
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    c.execute("SELECT ip_address FROM comments WHERE id = ?", (cid,))
    ip = c.fetchone()[0]
    c.execute("INSERT OR IGNORE INTO ban_list (ip_address) VALUES (?)", (ip,))
    c.execute("DELETE FROM comments WHERE ip_address = ?", (ip,))
    conn.commit(); conn.close(); return redirect("/")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))

    app.run(host="0.0.0.0", port=port)
@app.route("/sitemap.xml")
def sitemap():
    conn = sqlite3.connect("blog.db"); c = conn.cursor()
    c.execute("SELECT id FROM posts")
    posts = c.fetchall(); conn.close()
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    xml += '<url><loc>https://my-edu-media.onrender.com/</loc><priority>1.0</priority></url>'
    for p in posts:
        xml += f'<url><loc>https://my-edu-media.onrender.com/post/{p[0]}</loc><priority>0.8</priority></url>'
    xml += '</urlset>'
    return xml, {'Content-Type': 'application/xml'}

