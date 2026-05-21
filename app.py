import os
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Client, Note

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Use DATABASE_URL from env (Render/Neon PostgreSQL), fallback to local SQLite
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///crm.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Pro přístup se musíte přihlásit.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


# --- Auth ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=request.form.get('remember'))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        flash('Nesprávné jméno nebo heslo.', 'danger')
    return render_template('auth/login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        if not username or not email or not password:
            flash('Vyplňte všechna povinná pole.', 'danger')
        elif password != password2:
            flash('Hesla se neshodují.', 'danger')
        elif len(password) < 6:
            flash('Heslo musí mít alespoň 6 znaků.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Toto uživatelské jméno je již obsazeno.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Tento e-mail je již registrován.', 'danger')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Účet byl vytvořen. Vítejte!', 'success')
            return redirect(url_for('dashboard'))
    return render_template('auth/register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- Dashboard ---

@app.route('/')
@login_required
def dashboard():
    total = Client.query.filter_by(user_id=current_user.id).count()
    new_count = Client.query.filter_by(user_id=current_user.id, status='new').count()
    contacted = Client.query.filter_by(user_id=current_user.id, status='contacted').count()
    responded = Client.query.filter_by(user_id=current_user.id, status='responded').count()
    closed = Client.query.filter_by(user_id=current_user.id, status='closed').count()
    recent = Client.query.filter_by(user_id=current_user.id).order_by(Client.created_at.desc()).limit(8).all()
    return render_template('dashboard.html',
                           total=total, new_count=new_count,
                           contacted=contacted, responded=responded, closed=closed,
                           recent=recent)


# --- Clients ---

@app.route('/clients')
@login_required
def clients_list():
    q = request.args.get('q', '').strip()
    status_filter = request.args.get('status', '')
    query = Client.query.filter_by(user_id=current_user.id)

    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Client.name.ilike(like),
                Client.company.ilike(like),
                Client.website_url.ilike(like),
                Client.email.ilike(like),
            )
        )
    if status_filter:
        query = query.filter_by(status=status_filter)

    clients = query.order_by(Client.created_at.desc()).all()
    return render_template('clients/list.html', clients=clients, q=q, status_filter=status_filter)


@app.route('/clients/add', methods=['GET', 'POST'])
@login_required
def client_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Jméno / název je povinné.', 'danger')
        else:
            client = Client(
                user_id=current_user.id,
                name=name,
                company=request.form.get('company', '').strip(),
                website_url=request.form.get('website_url', '').strip(),
                email=request.form.get('email', '').strip(),
                phone=request.form.get('phone', '').strip(),
                status=request.form.get('status', 'new'),
            )
            db.session.add(client)
            db.session.commit()
            flash('Klient byl přidán.', 'success')
            return redirect(url_for('client_detail', client_id=client.id))
    return render_template('clients/add.html')


@app.route('/clients/<int:client_id>')
@login_required
def client_detail(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    return render_template('clients/detail.html', client=client)


@app.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@login_required
def client_edit(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('Jméno / název je povinné.', 'danger')
        else:
            client.name = name
            client.company = request.form.get('company', '').strip()
            client.website_url = request.form.get('website_url', '').strip()
            client.email = request.form.get('email', '').strip()
            client.phone = request.form.get('phone', '').strip()
            client.status = request.form.get('status', client.status)
            client.updated_at = datetime.utcnow()
            db.session.commit()
            flash('Klient byl upraven.', 'success')
            return redirect(url_for('client_detail', client_id=client.id))
    return render_template('clients/edit.html', client=client)


@app.route('/clients/<int:client_id>/delete', methods=['POST'])
@login_required
def client_delete(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    db.session.delete(client)
    db.session.commit()
    flash('Klient byl smazán.', 'success')
    return redirect(url_for('clients_list'))


@app.route('/clients/<int:client_id>/notes', methods=['POST'])
@login_required
def note_add(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    content = request.form.get('content', '').strip()
    if content:
        note = Note(client_id=client.id, user_id=current_user.id, content=content)
        db.session.add(note)
        db.session.commit()
        flash('Poznámka přidána.', 'success')
    return redirect(url_for('client_detail', client_id=client.id))


@app.route('/clients/<int:client_id>/status', methods=['POST'])
@login_required
def client_status(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    new_status = request.form.get('status')
    if new_status in ('new', 'contacted', 'responded', 'closed'):
        client.status = new_status
        client.updated_at = datetime.utcnow()
        db.session.commit()
    return redirect(request.referrer or url_for('client_detail', client_id=client.id))


@app.route('/health')
def health():
    import os
    db_url = app.config['SQLALCHEMY_DATABASE_URI']
    db_type = 'postgresql' if 'postgresql' in db_url else 'sqlite'
    return {'db': db_type, 'url_prefix': db_url[:30]}


if __name__ == '__main__':
    app.run(debug=True)
