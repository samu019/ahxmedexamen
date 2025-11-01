import os
import hashlib
import sqlite3
import csv
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, g, render_template_string, Response
import bleach
import markdown

# Создание приложения Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = 'development-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}
app.config['BOOKS_PER_PAGE'] = 10
app.config['REVIEWS_PER_PAGE'] = 10

# Создание папки для загрузок если не существует
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

DATABASE = 'electronic_library.db'

def get_db():
    """Получение соединения с базой данных SQLite"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys = ON')
    return g.db

def close_db(error):
    """Закрытие соединения с базой данных"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.teardown_appcontext
def close_db_connection(error):
    close_db(error)

def init_db():
    """Инициализация базы данных"""
    print("Инициализация базы данных...")
    db = get_db()
    
    # Создание таблиц
    db.executescript('''
        -- Удаляем существующие таблицы для чистого старта
        DROP TABLE IF EXISTS collection_books;
        DROP TABLE IF EXISTS collections;
        DROP TABLE IF EXISTS visit_history;
        DROP TABLE IF EXISTS reviews;
        DROP TABLE IF EXISTS book_genres;
        DROP TABLE IF EXISTS book_covers;
        DROP TABLE IF EXISTS books;
        DROP TABLE IF EXISTS genres;
        DROP TABLE IF EXISTS users;
        DROP TABLE IF EXISTS roles;
        DROP TABLE IF EXISTS review_statuses;

        -- Таблица ролей
        CREATE TABLE roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL
        );

        -- Таблица пользователей
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            middle_name TEXT,
            role_id INTEGER NOT NULL,
            FOREIGN KEY (role_id) REFERENCES roles(id)
        );

        -- Таблица жанров
        CREATE TABLE genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        -- Таблица книг
        CREATE TABLE books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            short_description TEXT NOT NULL,
            publication_year INTEGER NOT NULL,
            publisher TEXT NOT NULL,
            author TEXT NOT NULL,
            page_count INTEGER NOT NULL
        );

        -- Связующая таблица книги-жанры
        CREATE TABLE book_genres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            genre_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (genre_id) REFERENCES genres(id),
            UNIQUE(book_id, genre_id)
        );

        -- Таблица обложек
        CREATE TABLE book_covers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            md5_hash TEXT NOT NULL UNIQUE,
            book_id INTEGER NOT NULL,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        );

        -- Таблица статусов рецензий
        CREATE TABLE review_statuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        -- Таблица рецензий
        CREATE TABLE reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            rating INTEGER NOT NULL CHECK (rating >= 0 AND rating <= 5),
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status_id INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (status_id) REFERENCES review_statuses(id),
            UNIQUE(user_id, book_id)
        );

        -- Таблица истории посещений
        CREATE TABLE visit_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            book_id INTEGER NOT NULL,
            visit_date DATE NOT NULL,
            visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            visit_count INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE(user_id, book_id, visit_date)
        );

        -- Таблица подборок (для варианта 2)
        CREATE TABLE collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        -- Связующая таблица подборки-книги
        CREATE TABLE collection_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER NOT NULL,
            book_id INTEGER NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE(collection_id, book_id)
        );
    ''')
    
    # Вставка начальных данных
    db.execute("INSERT INTO roles (name, description) VALUES (?, ?)", 
               ('administrator', 'Суперпользователь, имеет полный доступ к системе'))
    db.execute("INSERT INTO roles (name, description) VALUES (?, ?)", 
               ('moderator', 'Может редактировать данные книг и производить модерацию рецензий'))
    db.execute("INSERT INTO roles (name, description) VALUES (?, ?)", 
               ('user', 'Может оставлять рецензии'))
    
    db.execute("INSERT INTO review_statuses (name) VALUES (?)", ('pending',))
    db.execute("INSERT INTO review_statuses (name) VALUES (?)", ('approved',))
    db.execute("INSERT INTO review_statuses (name) VALUES (?)", ('rejected',))
    
    genres = ['Фантастика', 'Детектив', 'Роман', 'Классическая литература', 
              'Поэзия', 'Драма', 'Приключения', 'Биография', 'История', 
              'Научная литература', 'Психология', 'Философия']
    for genre in genres:
        db.execute("INSERT INTO genres (name) VALUES (?)", (genre,))
    
    password_hash = generate_password_hash('password')
    
    db.execute("""INSERT INTO users 
                  (login, password_hash, last_name, first_name, middle_name, role_id) 
                  VALUES (?, ?, ?, ?, ?, ?)""", 
               ('admin', password_hash, 'Администратор', 'Системный', 'Главный', 1))
    
    db.execute("""INSERT INTO users 
                  (login, password_hash, last_name, first_name, middle_name, role_id) 
                  VALUES (?, ?, ?, ?, ?, ?)""", 
               ('moderator', password_hash, 'Модератор', 'Главный', 'Контентный', 2))
    
    db.execute("""INSERT INTO users 
                  (login, password_hash, last_name, first_name, middle_name, role_id) 
                  VALUES (?, ?, ?, ?, ?, ?)""", 
               ('user1', password_hash, 'Иванов', 'Иван', 'Иванович', 3))
    
    db.execute("""INSERT INTO users 
                  (login, password_hash, last_name, first_name, middle_name, role_id) 
                  VALUES (?, ?, ?, ?, ?, ?)""", 
               ('user2', password_hash, 'Петрова', 'Анна', 'Сергеевна', 3))
    
    db.execute("""INSERT INTO users 
                  (login, password_hash, last_name, first_name, middle_name, role_id) 
                  VALUES (?, ?, ?, ?, ?, ?)""", 
               ('user3', password_hash, 'Сидоров', 'Михаил', 'Александрович', 3))
    
    db.execute("""INSERT INTO users 
                  (login, password_hash, last_name, first_name, middle_name, role_id) 
                  VALUES (?, ?, ?, ?, ?, ?)""", 
               ('user4', password_hash, 'Козлова', 'Елена', 'Викторовна', 3))
    
    # Тестовые книги
    books = [
        ('Война и мир', '''Роман-эпопея **Льва Толстого**, описывающий русское общество в эпоху войн против Наполеона в 1805—1812 годах.

Это масштабное произведение о жизни русского дворянства и народа в период Отечественной войны 1812 года.

### Основные темы:
- Война и мир как противоположности
- Судьба отдельного человека и народа
- Поиск смысла жизни''', 1869, 'Русский вестник', 'Лев Толстой', 1274),
        
        ('Преступление и наказание', '''Социально-психологический роман **Фёдора Достоевского** о молодом человеке Родионе Раскольникове.

Глубокое исследование человеческой психики и морали, вопросов добра и зла.

### Центральные вопросы:
- Имеет ли человек право на преступление?
- Что такое совесть и раскаяние?
- Возможно ли искупление?''', 1866, 'Русский вестник', 'Фёдор Достоевский', 672),
        
        ('Мастер и Маргарита', '''Роман **Михаила Булгакова**, сочетающий в себе фантастику, сатиру, мистику и любовную лирику.

История о добре и зле, любви и предательстве, творчестве и власти.

### Сюжетные линии:
- Приход Воланда в Москву
- История Понтия Пилата и Иешуа
- Любовь Мастера и Маргариты''', 1967, 'Москва', 'Михаил Булгаков', 384),
        
        ('1984', '''Антиутопия **Джорджа Оруэлла** о тоталитарном обществе будущего.

Пророческий роман о мире, где правит Большой Брат и мыслепреступление карается смертью.

### Ключевые концепции:
- "Двоемыслие" и "новояз"
- Тотальная слежка
- Переписывание истории''', 1949, 'Secker & Warburg', 'Джордж Оруэлл', 328),
        
        ('Анна Каренина', '''Роман **Льва Толстого** о любви, семье и обществе в России XIX века.

Трагическая история Анны Карениной и её запретной любви.

### Основные темы:
- Любовь и страсть
- Семья и общество
- Поиск смысла жизни''', 1877, 'Русский вестник', 'Лев Толстой', 864),
        
        ('Три товарища', '''Роман **Эриха Марии Ремарка** о дружбе, любви и молодости в послевоенной Германии.

История о трёх фронтовых друзьях и их попытках найти своё место в мирной жизни.

### Основные темы:
- Дружба и верность
- Любовь и потеря
- Жизнь после войны''', 1936, 'Querido Verlag', 'Эрих Мария Ремарк', 496)
    ]
    
    for book_data in books:
        cursor = db.execute("""INSERT INTO books 
                              (title, short_description, publication_year, publisher, author, page_count) 
                              VALUES (?, ?, ?, ?, ?, ?)""", book_data)
        book_id = cursor.lastrowid
        
        # Добавляем жанры для книг
        if 'Война и мир' in book_data[0] or 'Анна Каренина' in book_data[0]:
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 3))  # Роман
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 4))  # Классическая литература
        elif 'Преступление' in book_data[0]:
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 3))  # Роман
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 4))  # Классическая литература
        elif 'Мастер' in book_data[0]:
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 1))  # Фантастика
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 3))  # Роман
        elif '1984' in book_data[0]:
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 1))  # Фантастика
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 3))  # Роман
        elif 'Три товарища' in book_data[0]:
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 3))  # Роман
            db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, 6))  # Драма
    
    db.commit()
    print("✅ База данных успешно инициализирована!")

def ensure_db_initialized():
    """Убеждаемся, что база данных инициализирована"""
    try:
        db = get_db()
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='books'")
        if not cursor.fetchone():
            init_db()
    except Exception as e:
        print(f"Ошибка при проверке БД: {e}")
        init_db()

def allowed_file(filename):
    """Проверка допустимых расширений файлов"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_file_md5(file_content):
    """Вычисление MD5 хэша файла"""
    return hashlib.md5(file_content).hexdigest()

def get_current_user():
    """Получение текущего пользователя"""
    if 'user_id' not in session:
        return None
    
    db = get_db()
    user = db.execute("""
        SELECT u.*, r.name as role_name 
        FROM users u 
        JOIN roles r ON u.role_id = r.id 
        WHERE u.id = ?
    """, (session['user_id'],)).fetchone()
    return user

def login_required(f):
    """Декоратор для проверки аутентификации"""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Для выполнения данного действия необходимо пройти процедуру аутентификации')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def admin_required(f):
    """Декоратор для проверки прав администратора"""
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or user['role_name'] != 'administrator':
            flash('У вас недостаточно прав для выполнения данного действия')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def moderator_required(f):
    """Декоратор для проверки прав модератора или администратора"""
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or user['role_name'] not in ['administrator', 'moderator']:
            flash('У вас недостаточно прав для выполнения данного действия')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def user_required(f):
    """Декоратор для проверки роли пользователя"""
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user or user['role_name'] != 'user':
            flash('У вас недостаточно прав для выполнения данного действия')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

def record_visit(book_id, user_id=None):
    """Записать посещение книги"""
    db = get_db()
    today = datetime.now().date()
    
    try:
        if user_id:
            # Для аутентифицированных пользователей
            current_visits = db.execute("""
                SELECT visit_count FROM visit_history 
                WHERE user_id = ? AND book_id = ? AND visit_date = ?
            """, (user_id, book_id, today)).fetchone()
            
            if current_visits and current_visits['visit_count'] < 10:
                db.execute("""
                    UPDATE visit_history 
                    SET visit_count = visit_count + 1, visit_time = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND book_id = ? AND visit_date = ?
                """, (user_id, book_id, today))
            elif not current_visits:
                db.execute("""
                    INSERT INTO visit_history (user_id, book_id, visit_date, visit_count)
                    VALUES (?, ?, ?, 1)
                """, (user_id, book_id, today))
        else:
            # Для неаутентифицированных пользователей
            db.execute("""
                INSERT OR IGNORE INTO visit_history (user_id, book_id, visit_date, visit_count)
                VALUES (NULL, ?, ?, 1)
            """, (book_id, today))
        
        db.commit()
    except Exception as e:
        print(f"Ошибка записи посещения: {e}")

@app.route('/')
def index():
    """Главная страница с списком книг"""
    ensure_db_initialized()
    
    page = request.args.get('page', 1, type=int)
    per_page = app.config['BOOKS_PER_PAGE']
    offset = (page - 1) * per_page
    
    # Получение параметров поиска (Вариант 3)
    search_title = request.args.get('title', '').strip()
    search_author = request.args.get('author', '').strip()
    search_genres = request.args.getlist('genres')
    search_years = request.args.getlist('years')
    page_from = request.args.get('page_from', type=int)
    page_to = request.args.get('page_to', type=int)
    
    db = get_db()
    
    # Построение SQL запроса с фильтрами
    where_conditions = []
    params = []
    
    if search_title:
        where_conditions.append("b.title LIKE ?")
        params.append(f"%{search_title}%")
    
    if search_author:
        where_conditions.append("b.author LIKE ?")
        params.append(f"%{search_author}%")
    
    if search_genres:
        genre_placeholders = ','.join('?' * len(search_genres))
        where_conditions.append(f"b.id IN (SELECT bg.book_id FROM book_genres bg WHERE bg.genre_id IN ({genre_placeholders}))")
        params.extend(search_genres)
    
    if search_years:
        year_placeholders = ','.join('?' * len(search_years))
        where_conditions.append(f"b.publication_year IN ({year_placeholders})")
        params.extend(search_years)
    
    if page_from:
        where_conditions.append("b.page_count >= ?")
        params.append(page_from)
    
    if page_to:
        where_conditions.append("b.page_count <= ?")
        params.append(page_to)
    
    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)
    
    # Получение общего количества книг
    count_query = f"SELECT COUNT(DISTINCT b.id) as total FROM books b {where_clause}"
    total_books = db.execute(count_query, params).fetchone()['total']
    
    # Получение книг с пагинацией
    books_query = f"""
        SELECT b.*, 
               GROUP_CONCAT(DISTINCT g.name) as genres,
               COALESCE(AVG(CAST(r.rating AS FLOAT)), 0) as avg_rating,
               COUNT(DISTINCT r.id) as review_count,
               bc.filename as cover_filename
        FROM books b
        LEFT JOIN book_genres bg ON b.id = bg.book_id
        LEFT JOIN genres g ON bg.genre_id = g.id
        LEFT JOIN reviews r ON b.id = r.book_id AND r.status_id = 2
        LEFT JOIN book_covers bc ON b.id = bc.book_id
        {where_clause}
        GROUP BY b.id
        ORDER BY b.publication_year DESC
        LIMIT ? OFFSET ?
    """
    books = db.execute(books_query, params + [per_page, offset]).fetchall()
    
    # Получение данных для формы поиска
    all_genres = db.execute("SELECT * FROM genres ORDER BY name").fetchall()
    all_years = db.execute("SELECT DISTINCT publication_year FROM books ORDER BY publication_year DESC").fetchall()
    
    # Получение популярных книг (Вариант 4)
    three_months_ago = datetime.now() - timedelta(days=90)
    popular_books = db.execute("""
        SELECT b.*, COUNT(vh.id) as visit_count,
               bc.filename as cover_filename
        FROM books b
        LEFT JOIN visit_history vh ON b.id = vh.book_id AND vh.visit_date >= ?
        LEFT JOIN book_covers bc ON b.id = bc.book_id
        GROUP BY b.id
        ORDER BY visit_count DESC
        LIMIT 5
    """, (three_months_ago.date(),)).fetchall()
    
    # Получение недавно просмотренных книг
    recent_books = []
    if 'user_id' in session:
        recent_books = db.execute("""
            SELECT DISTINCT b.*, vh.visit_time,
                   bc.filename as cover_filename
            FROM books b
            JOIN visit_history vh ON b.id = vh.book_id
            LEFT JOIN book_covers bc ON b.id = bc.book_id
            WHERE vh.user_id = ?
            ORDER BY vh.visit_time DESC
            LIMIT 5
        """, (session['user_id'],)).fetchall()
    
    # Вычисление пагинации
    total_pages = (total_books + per_page - 1) // per_page if total_books > 0 else 1
    has_prev = page > 1
    has_next = page < total_pages
    
    current_user = get_current_user()
    
    # Сохранение параметров поиска для пагинации
    search_params = {
        'title': search_title,
        'author': search_author,
        'genres': search_genres,
        'years': search_years,
        'page_from': page_from,
        'page_to': page_to
    }
    
    return render_template('index.html', 
                         books=books,
                         current_user=current_user,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         popular_books=popular_books,
                         recent_books=recent_books,
                         all_genres=all_genres,
                         all_years=all_years,
                         search_params=search_params)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Страница входа"""
    if request.method == 'POST':
        login_username = request.form['login']
        password = request.form['password']
        remember = 'remember' in request.form
        
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE login = ?", (login_username,)).fetchone()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            if remember:
                session.permanent = True
                app.permanent_session_lifetime = timedelta(days=7)
            
            flash('Успешный вход в систему')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Невозможно аутентифицироваться с указанными логином и паролем')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Выход из системы"""
    session.pop('user_id', None)
    flash('Вы успешно вышли из системы')
    return redirect(url_for('index'))

@app.route('/book/<int:book_id>')
def view_book(book_id):
    """Просмотр информации о книге"""
    ensure_db_initialized()
    db = get_db()
    
    # Получение информации о книге
    book = db.execute("""
        SELECT b.*, 
               GROUP_CONCAT(g.name) as genres,
               bc.filename as cover_filename
        FROM books b
        LEFT JOIN book_genres bg ON b.id = bg.book_id
        LEFT JOIN genres g ON bg.genre_id = g.id
        LEFT JOIN book_covers bc ON b.id = bc.book_id
        WHERE b.id = ?
        GROUP BY b.id
    """, (book_id,)).fetchone()
    
    if not book:
        flash('Книга не найдена')
        return redirect(url_for('index'))
    
    # Получение рецензий
    reviews = db.execute("""
        SELECT r.*, u.first_name, u.last_name, u.middle_name
        FROM reviews r
        JOIN users u ON r.user_id = u.id
        WHERE r.book_id = ? AND r.status_id = 2
        ORDER BY r.created_at DESC
    """, (book_id,)).fetchall()
    
    # Проверка, оставлял ли пользователь рецензию
    user_review = None
    current_user = get_current_user()
    if current_user:
        user_review = db.execute("""
            SELECT r.*, rs.name as status_name FROM reviews r
            JOIN review_statuses rs ON r.status_id = rs.id
            WHERE r.book_id = ? AND r.user_id = ?
        """, (book_id, current_user['id'])).fetchone()
        
        # Запись посещения
        record_visit(book_id, current_user['id'])
    else:
        # Запись посещения для неаутентифицированного пользователя
        record_visit(book_id)
    
    # Преобразование Markdown в HTML
    book_dict = dict(book)
    book_dict['short_description'] = markdown.markdown(book_dict['short_description'])
    
    reviews_list = []
    for review in reviews:
        review_dict = dict(review)
        review_dict['text'] = markdown.markdown(review_dict['text'])
        reviews_list.append(review_dict)
    
    return render_template('book/view.html',
                         book=book_dict,
                         reviews=reviews_list,
                         user_review=user_review,
                         current_user=current_user)

@app.route('/book/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_book():
    """Добавление новой книги"""
    if request.method == 'POST':
        try:
            db = get_db()
            
            title = request.form['title'].strip()
            short_description = bleach.clean(request.form['short_description'], 
                                           tags=['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'a'],
                                           attributes={'a': ['href']})
            publication_year = int(request.form['publication_year'])
            publisher = request.form['publisher'].strip()
            author = request.form['author'].strip()
            page_count = int(request.form['page_count'])
            genre_ids = request.form.getlist('genres')
            
            if not all([title, short_description, publisher, author]):
                flash('Все поля обязательны для заполнения')
                return render_template('book/add.html', genres=get_all_genres())
            
            cursor = db.execute("""
                INSERT INTO books (title, short_description, publication_year, publisher, author, page_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, short_description, publication_year, publisher, author, page_count))
            
            book_id = cursor.lastrowid
            
            for genre_id in genre_ids:
                db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, genre_id))
            
            # Обработка обложки
            cover_file = request.files.get('cover')
            if cover_file and cover_file.filename and allowed_file(cover_file.filename):
                file_content = cover_file.read()
                file_md5 = get_file_md5(file_content)
                
                existing_cover = db.execute("SELECT id FROM book_covers WHERE md5_hash = ?", (file_md5,)).fetchone()
                
                if existing_cover:
                    db.execute("UPDATE book_covers SET book_id = ? WHERE id = ?", (book_id, existing_cover['id']))
                else:
                    filename = secure_filename(f"{book_id}_{cover_file.filename}")
                    mime_type = cover_file.content_type
                    
                    db.execute("""
                        INSERT INTO book_covers (filename, mime_type, md5_hash, book_id)
                        VALUES (?, ?, ?, ?)
                    """, (filename, mime_type, file_md5, book_id))
                    
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    with open(file_path, 'wb') as f:
                        f.write(file_content)
            
            db.commit()
            flash('Книга успешно добавлена')
            return redirect(url_for('view_book', book_id=book_id))
            
        except Exception as e:
            db.rollback()
            flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.')
            print(f"Ошибка добавления книги: {e}")
            return render_template('book/add.html', genres=get_all_genres())
    
    return render_template('book/add.html', genres=get_all_genres())

# ===== ВАРИАНТ 1: МОДЕРАЦИЯ РЕЦЕНЗИЙ =====

@app.route('/my-reviews')
@login_required
@user_required
def my_reviews():
    """Мои рецензии (для пользователей)"""
    db = get_db()
    reviews = db.execute("""
        SELECT r.*, b.title as book_title, rs.name as status_name,
               CASE rs.name 
                   WHEN 'pending' THEN 'На рассмотрении'
                   WHEN 'approved' THEN 'Одобрена' 
                   WHEN 'rejected' THEN 'Отклонена'
               END as status_display
        FROM reviews r
        JOIN books b ON r.book_id = b.id
        JOIN review_statuses rs ON r.status_id = rs.id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
    """, (session['user_id'],)).fetchall()
    
    return render_template('user/my_reviews.html', reviews=reviews)

@app.route('/moderate-reviews')
@login_required
@moderator_required
def moderate_reviews():
    """Модерация рецензий (для модераторов)"""
    page = request.args.get('page', 1, type=int)
    per_page = app.config['REVIEWS_PER_PAGE']
    offset = (page - 1) * per_page
    
    db = get_db()
    
    # Получение общего количества рецензий на модерации
    total_reviews = db.execute("""
        SELECT COUNT(*) as total FROM reviews 
        WHERE status_id = 1
    """).fetchone()['total']
    
    # Получение рецензий на модерации
    reviews = db.execute("""
        SELECT r.*, b.title as book_title, u.first_name, u.last_name, u.middle_name
        FROM reviews r
        JOIN books b ON r.book_id = b.id
        JOIN users u ON r.user_id = u.id
        WHERE r.status_id = 1
        ORDER BY r.created_at ASC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    
    # Вычисление пагинации
    total_pages = (total_reviews + per_page - 1) // per_page if total_reviews > 0 else 1
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template('moderator/reviews.html',
                         reviews=reviews,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         total_reviews=total_reviews)

@app.route('/review/<int:review_id>/moderate', methods=['GET', 'POST'])
@login_required
@moderator_required
def moderate_review(review_id):
    """Модерация конкретной рецензии"""
    db = get_db()
    
    # Получение рецензии
    review = db.execute("""
        SELECT r.*, b.title as book_title, u.first_name, u.last_name, u.middle_name
        FROM reviews r
        JOIN books b ON r.book_id = b.id
        JOIN users u ON r.user_id = u.id
        WHERE r.id = ? AND r.status_id = 1
    """, (review_id,)).fetchone()
    
    if not review:
        flash('Рецензия не найдена или уже обработана')
        return redirect(url_for('moderate_reviews'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        new_status = 2 if action == 'approve' else 3  # 2 - одобрена, 3 - отклонена
        
        db.execute("""
            UPDATE reviews SET status_id = ? WHERE id = ?
        """, (new_status, review_id))
        
        db.commit()
        
        status_text = 'одобрена' if action == 'approve' else 'отклонена'
        flash(f'Рецензия {status_text}')
        return redirect(url_for('moderate_reviews'))
    
    # Преобразование Markdown в HTML для отображения
    review_dict = dict(review)
    review_dict['text'] = markdown.markdown(review_dict['text'])
    
    return render_template('moderator/review_detail.html', review=review_dict)

# ===== ВАРИАНТ 2: ПОДБОРКИ КНИГ =====

@app.route('/my-collections')
@login_required
@user_required
def my_collections():
    """Мои подборки (для пользователей)"""
    db = get_db()
    collections = db.execute("""
        SELECT c.*, COUNT(cb.id) as book_count
        FROM collections c
        LEFT JOIN collection_books cb ON c.id = cb.collection_id
        WHERE c.user_id = ?
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """, (session['user_id'],)).fetchall()
    
    return render_template('user/my_collections.html', collections=collections)

@app.route('/collection/<int:collection_id>')
@login_required
@user_required
def view_collection(collection_id):
    """Просмотр подборки"""
    db = get_db()
    
    # Проверяем, что подборка принадлежит текущему пользователю
    collection = db.execute("""
        SELECT * FROM collections WHERE id = ? AND user_id = ?
    """, (collection_id, session['user_id'])).fetchone()
    
    if not collection:
        flash('Подборка не найдена')
        return redirect(url_for('my_collections'))
    
    # Получаем книги в подборке
    books = db.execute("""
        SELECT b.*, cb.added_at,
               GROUP_CONCAT(g.name) as genres,
               COALESCE(AVG(CAST(r.rating AS FLOAT)), 0) as avg_rating,
               COUNT(DISTINCT r.id) as review_count,
               bc.filename as cover_filename
        FROM collection_books cb
        JOIN books b ON cb.book_id = b.id
        LEFT JOIN book_genres bg ON b.id = bg.book_id
        LEFT JOIN genres g ON bg.genre_id = g.id
        LEFT JOIN reviews r ON b.id = r.book_id AND r.status_id = 2
        LEFT JOIN book_covers bc ON b.id = bc.book_id
        WHERE cb.collection_id = ?
        GROUP BY b.id
        ORDER BY cb.added_at DESC
    """, (collection_id,)).fetchall()
    
    return render_template('user/view_collection.html', collection=collection, books=books)

@app.route('/add-collection', methods=['POST'])
@login_required
@user_required
def add_collection():
    """Добавление новой подборки"""
    name = request.form.get('name', '').strip()
    
    if not name:
        flash('Введите название подборки')
        return redirect(url_for('my_collections'))
    
    db = get_db()
    
    try:
        db.execute("""
            INSERT INTO collections (name, user_id) VALUES (?, ?)
        """, (name, session['user_id']))
        db.commit()
        flash('Подборка успешно создана')
    except Exception as e:
        flash('Ошибка при создании подборки')
        print(f"Ошибка создания подборки: {e}")
    
    return redirect(url_for('my_collections'))

@app.route('/api/user-collections')
@login_required
@user_required
def api_user_collections():
    """API для получения подборок пользователя"""
    db = get_db()
    collections = db.execute("""
        SELECT id, name FROM collections WHERE user_id = ? ORDER BY name
    """, (session['user_id'],)).fetchall()
    
    return jsonify([{'id': c['id'], 'name': c['name']} for c in collections])

@app.route('/add-to-collection', methods=['POST'])
@login_required
@user_required
def add_to_collection():
    """Добавление книги в подборку"""
    book_id = request.form.get('book_id', type=int)
    collection_id = request.form.get('collection_id', type=int)
    
    if not book_id or not collection_id:
        return jsonify({'success': False, 'message': 'Неверные параметры'})
    
    db = get_db()
    
    # Проверяем, что подборка принадлежит пользователю
    collection = db.execute("""
        SELECT id FROM collections WHERE id = ? AND user_id = ?
    """, (collection_id, session['user_id'])).fetchone()
    
    if not collection:
        return jsonify({'success': False, 'message': 'Подборка не найдена'})
    
    try:
        # Проверяем, есть ли уже книга в подборке
        existing = db.execute("""
            SELECT id FROM collection_books 
            WHERE collection_id = ? AND book_id = ?
        """, (collection_id, book_id)).fetchone()
        
        if existing:
            return jsonify({'success': False, 'message': 'Книга уже есть в этой подборке'})
        
        # Добавляем книгу в подборку
        db.execute("""
            INSERT INTO collection_books (collection_id, book_id)
            VALUES (?, ?)
        """, (collection_id, book_id))
        db.commit()
        
        return jsonify({'success': True, 'message': 'Книга добавлена в подборку'})
        
    except Exception as e:
        print(f"Ошибка добавления в подборку: {e}")
        return jsonify({'success': False, 'message': 'Ошибка при добавлении'})

@app.route('/remove-from-collection/<int:collection_id>/<int:book_id>', methods=['POST'])
@login_required
@user_required
def remove_from_collection(collection_id, book_id):
    """Удаление книги из подборки"""
    db = get_db()
    
    # Проверяем права доступа
    collection = db.execute("""
        SELECT id FROM collections WHERE id = ? AND user_id = ?
    """, (collection_id, session['user_id'])).fetchone()
    
    if not collection:
        flash('Подборка не найдена')
        return redirect(url_for('my_collections'))
    
    try:
        db.execute("""
            DELETE FROM collection_books 
            WHERE collection_id = ? AND book_id = ?
        """, (collection_id, book_id))
        db.commit()
        flash('Книга удалена из подборки')
    except Exception as e:
        flash('Ошибка при удалении книги из подборки')
        print(f"Ошибка удаления из подборки: {e}")
    
    return redirect(url_for('view_collection', collection_id=collection_id))

@app.route('/delete-collection/<int:collection_id>', methods=['POST'])
@login_required
@user_required
def delete_collection(collection_id):
    """Удаление подборки"""
    db = get_db()
    
    # Проверяем права доступа
    collection = db.execute("""
        SELECT id FROM collections WHERE id = ? AND user_id = ?
    """, (collection_id, session['user_id'])).fetchone()
    
    if not collection:
        flash('Подборка не найдена')
        return redirect(url_for('my_collections'))
    
    try:
        db.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        db.commit()
        flash('Подборка удалена')
    except Exception as e:
        flash('Ошибка при удалении подборки')
        print(f"Ошибка удаления подборки: {e}")
    
    return redirect(url_for('my_collections'))

# ===== ВАРИАНТ 4: СТАТИСТИКА =====

@app.route('/statistics')
@login_required
@admin_required
def statistics():
    """Статистика для администраторов"""
    return render_template('admin/statistics.html')

@app.route('/statistics/user-actions')
@login_required
@admin_required
def user_actions_log():
    """Журнал действий пользователей"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    db = get_db()
    
    # Получение общего количества записей
    total_records = db.execute("""
        SELECT COUNT(*) as total FROM visit_history
    """).fetchone()['total']
    
    # Получение записей с пагинацией
    visits = db.execute("""
        SELECT vh.*, b.title as book_title,
               CASE 
                   WHEN u.id IS NOT NULL 
                   THEN u.last_name || ' ' || u.first_name || 
                        CASE WHEN u.middle_name IS NOT NULL THEN ' ' || u.middle_name ELSE '' END
                   ELSE 'Неаутентифицированный пользователь'
               END as user_name
        FROM visit_history vh
        JOIN books b ON vh.book_id = b.id
        LEFT JOIN users u ON vh.user_id = u.id
        ORDER BY vh.visit_time DESC
        LIMIT ? OFFSET ?
    """, (per_page, offset)).fetchall()
    
    # Вычисление пагинации
    total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template('admin/user_actions.html',
                         visits=visits,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         total_records=total_records)

@app.route('/statistics/book-views')
@login_required
@admin_required
def book_views_stats():
    """Статистика просмотров книг"""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page
    
    # Получение параметров фильтрации
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    db = get_db()
    
    # Построение условий фильтрации
    where_conditions = ["vh.user_id IS NOT NULL"]
    params = []
    
    if date_from:
        where_conditions.append("vh.visit_date >= ?")
        params.append(date_from)
    
    if date_to:
        where_conditions.append("vh.visit_date <= ?")
        params.append(date_to)
    
    where_clause = " AND ".join(where_conditions)
    
    # Получение общего количества книг
    count_query = f"""
        SELECT COUNT(DISTINCT b.id) as total 
        FROM books b
        JOIN visit_history vh ON b.id = vh.book_id
        WHERE {where_clause}
    """
    total_books = db.execute(count_query, params).fetchone()['total']
    
    # Получение статистики с пагинацией
    stats_query = f"""
        SELECT b.title, SUM(vh.visit_count) as total_views
        FROM books b
        JOIN visit_history vh ON b.id = vh.book_id
        WHERE {where_clause}
        GROUP BY b.id, b.title
        ORDER BY total_views DESC
        LIMIT ? OFFSET ?
    """
    book_stats = db.execute(stats_query, params + [per_page, offset]).fetchall()
    
    # Вычисление пагинации
    total_pages = (total_books + per_page - 1) // per_page if total_books > 0 else 1
    has_prev = page > 1
    has_next = page < total_pages
    
    return render_template('admin/book_views.html',
                         book_stats=book_stats,
                         page=page,
                         total_pages=total_pages,
                         has_prev=has_prev,
                         has_next=has_next,
                         total_books=total_books,
                         date_from=date_from,
                         date_to=date_to)

@app.route('/export-user-actions-csv')
@login_required
@admin_required
def export_user_actions_csv():
    """Экспорт журнала действий в CSV"""
    db = get_db()
    
    visits = db.execute("""
        SELECT vh.visit_date, vh.visit_time, vh.visit_count,
               b.title as book_title,
               CASE 
                   WHEN u.id IS NOT NULL 
                   THEN u.last_name || ' ' || u.first_name || 
                        CASE WHEN u.middle_name IS NOT NULL THEN ' ' || u.middle_name ELSE '' END
                   ELSE 'Неаутентифицированный пользователь'
               END as user_name
        FROM visit_history vh
        JOIN books b ON vh.book_id = b.id
        LEFT JOIN users u ON vh.user_id = u.id
        ORDER BY vh.visit_time DESC
    """).fetchall()
    
    # Создание CSV
    output = []
    output.append('№,ФИО пользователя,Название книги,Дата просмотра,Время просмотра')
    
    for i, visit in enumerate(visits, 1):
        row = [
            str(i),
            visit['user_name'],
            visit['book_title'],
            visit['visit_date'],
            visit['visit_time']
        ]
        output.append(','.join([f'"{field}"' for field in row]))
    
    csv_content = '\n'.join(output)
    
    # Генерация имени файла
    filename = f"user_actions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    response = Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    
    return response

@app.route('/export-book-views-csv')
@login_required
@admin_required
def export_book_views_csv():
    """Экспорт статистики просмотров в CSV"""
    # Получение параметров фильтрации
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    
    db = get_db()
    
    # Построение условий фильтрации
    where_conditions = ["vh.user_id IS NOT NULL"]
    params = []
    
    if date_from:
        where_conditions.append("vh.visit_date >= ?")
        params.append(date_from)
    
    if date_to:
        where_conditions.append("vh.visit_date <= ?")
        params.append(date_to)
    
    where_clause = " AND ".join(where_conditions)
    
    stats_query = f"""
        SELECT b.title, SUM(vh.visit_count) as total_views
        FROM books b
        JOIN visit_history vh ON b.id = vh.book_id
        WHERE {where_clause}
        GROUP BY b.id, b.title
        ORDER BY total_views DESC
    """
    book_stats = db.execute(stats_query, params).fetchall()
    
    # Создание CSV
    output = []
    output.append('№,Название книги,Количество просмотров')
    
    for i, stat in enumerate(book_stats, 1):
        row = [
            str(i),
            stat['title'],
            str(stat['total_views'])
        ]
        output.append(','.join([f'"{field}"' for field in row]))
    
    csv_content = '\n'.join(output)
    
    # Генерация имени файла
    period_suffix = ""
    if date_from or date_to:
        period_suffix = f"_{date_from or 'начало'}_{date_to or 'конец'}"
    
    filename = f"book_views_stats{period_suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    response = Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )
    
    return response

# ===== ОСТАЛЬНЫЕ МАРШРУТЫ =====

@app.route('/book/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_book(book_id):
    """Редактирование книги"""
    db = get_db()
    
    book = db.execute("""
        SELECT b.*, GROUP_CONCAT(bg.genre_id) as genre_ids
        FROM books b
        LEFT JOIN book_genres bg ON b.id = bg.book_id
        WHERE b.id = ?
        GROUP BY b.id
    """, (book_id,)).fetchone()
    
    if not book:
        flash('Книга не найдена')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            title = request.form['title'].strip()
            short_description = bleach.clean(request.form['short_description'],
                                           tags=['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'a'],
                                           attributes={'a': ['href']})
            publication_year = int(request.form['publication_year'])
            publisher = request.form['publisher'].strip()
            author = request.form['author'].strip()
            page_count = int(request.form['page_count'])
            genre_ids = request.form.getlist('genres')
            
            if not all([title, short_description, publisher, author]):
                flash('Все поля обязательны для заполнения')
                return redirect(url_for('edit_book', book_id=book_id))
            
            db.execute("""
                UPDATE books 
                SET title = ?, short_description = ?, publication_year = ?, 
                    publisher = ?, author = ?, page_count = ?
                WHERE id = ?
            """, (title, short_description, publication_year, publisher, author, page_count, book_id))
            
            db.execute("DELETE FROM book_genres WHERE book_id = ?", (book_id,))
            
            for genre_id in genre_ids:
                db.execute("INSERT INTO book_genres (book_id, genre_id) VALUES (?, ?)", (book_id, genre_id))
            
            db.commit()
            flash('Книга успешно обновлена')
            return redirect(url_for('view_book', book_id=book_id))
            
        except Exception as e:
            flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.')
            print(f"Ошибка редактирования книги: {e}")
    
    genres = db.execute("SELECT * FROM genres ORDER BY name").fetchall()
    selected_genres = book['genre_ids'].split(',') if book['genre_ids'] else []
    
    return render_template('book/edit.html', book=book, genres=genres, selected_genres=selected_genres)

@app.route('/book/<int:book_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_book(book_id):
    """Удаление книги"""
    try:
        db = get_db()
        
        # Получение информации об обложке для удаления файла
        cover = db.execute("SELECT filename FROM book_covers WHERE book_id = ?", (book_id,)).fetchone()
        
        # Получение названия книги для сообщения
        book = db.execute("SELECT title FROM books WHERE id = ?", (book_id,)).fetchone()
        book_title = book['title'] if book else 'Неизвестная книга'
        
        # Удаление книги (связанные записи удалятся автоматически благодаря ON DELETE CASCADE)
        result = db.execute("DELETE FROM books WHERE id = ?", (book_id,))
        
        if result.rowcount > 0:
            # Удаление файла обложки
            if cover and cover['filename']:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], cover['filename'])
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        print(f"Файл обложки {cover['filename']} удален")
                    except Exception as e:
                        print(f"Ошибка удаления файла обложки: {e}")
            
            db.commit()
            flash(f'Книга "{book_title}" успешно удалена')
        else:
            flash('Книга не найдена или уже была удалена')
        
    except Exception as e:
        db.rollback()
        print(f"Ошибка при удалении книги: {e}")
        flash('Ошибка при удалении книги')
    
    return redirect(url_for('index'))

@app.route('/book/<int:book_id>/review/add', methods=['GET', 'POST'])
@login_required
def add_review(book_id):
    """Добавление рецензии"""
    db = get_db()
    
    book = db.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
    if not book:
        flash('Книга не найдена')
        return redirect(url_for('index'))
    
    existing_review = db.execute("""
        SELECT id FROM reviews WHERE book_id = ? AND user_id = ?
    """, (book_id, session['user_id'])).fetchone()
    
    if existing_review:
        flash('Вы уже оставили рецензию на эту книгу. Удалите старую рецензию, чтобы написать новую.')
        return redirect(url_for('view_book', book_id=book_id))
    
    if request.method == 'POST':
        try:
            rating = int(request.form['rating'])
            text = bleach.clean(request.form['text'],
                              tags=['p', 'br', 'strong', 'em', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'a'],
                              attributes={'a': ['href']})
            
            if not (0 <= rating <= 5) or not text.strip():
                flash('Пожалуйста, укажите оценку и текст рецензии')
                return render_template('review/add.html', book=book)
            
            db.execute("""
                INSERT INTO reviews (book_id, user_id, rating, text, status_id)
                VALUES (?, ?, ?, ?, 1)
            """, (book_id, session['user_id'], rating, text))
            
            db.commit()
            flash('Рецензия отправлена на модерацию')
            return redirect(url_for('view_book', book_id=book_id))
            
        except Exception as e:
            flash('Ошибка при сохранении рецензии')
            print(f"Ошибка при сохранении рецензии: {e}")
    
    return render_template('review/add.html', book=book)

def get_all_genres():
    """Получение всех жанров"""
    db = get_db()
    return db.execute("SELECT * FROM genres ORDER BY name").fetchall()

# Контекстный процессор для передачи данных во все шаблоны
@app.context_processor
def inject_user():
    return dict(current_user=get_current_user())

@app.template_filter('avg')
def average(lst):
    return sum(lst) / len(lst) if lst else 0

# Обработчики ошибок
@app.errorhandler(404)
def not_found_error(error):
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>404 - Страница не найдена</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5 text-center">
            <h1 class="display-1">404</h1>
            <p class="lead">Страница не найдена</p>
            <a href="{{ url_for('index') }}" class="btn btn-primary">На главную</a>
        </div>
    </body>
    </html>
    """), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>500 - Внутренняя ошибка сервера</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container mt-5 text-center">
            <h1 class="display-1">500</h1>
            <p class="lead">Внутренняя ошибка сервера</p>
            <a href="{{ url_for('index') }}" class="btn btn-primary">На главную</a>
        </div>
    </body>
    </html>
    """), 500
    
@app.route('/review/<int:review_id>/delete', methods=['POST'])
@login_required
def delete_review(review_id):
    """Удаление рецензии"""
    db = get_db()
    current_user = get_current_user()
    
    # Получаем рецензию
    review = db.execute("""
        SELECT r.*, b.title as book_title 
        FROM reviews r
        JOIN books b ON r.book_id = b.id
        WHERE r.id = ?
    """, (review_id,)).fetchone()
    
    if not review:
        flash('Рецензия не найдена')
        return redirect(url_for('my_reviews'))
    
    # Проверяем права доступа
    can_delete = False
    if current_user['role_name'] == 'administrator':
        can_delete = True  # Админ может удалить любую рецензию
    elif current_user['role_name'] == 'user' and review['user_id'] == current_user['id']:
        can_delete = True  # Пользователь может удалить свою рецензию
    
    if not can_delete:
        flash('У вас нет прав для удаления этой рецензии')
        return redirect(url_for('my_reviews'))
    
    try:
        db.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        db.commit()
        flash(f'Рецензия на книгу "{review["book_title"]}" удалена')
    except Exception as e:
        flash('Ошибка при удалении рецензии')
        print(f"Ошибка удаления рецензии: {e}")
    
    # Перенаправляем в зависимости от роли
    if current_user['role_name'] == 'administrator':
        return redirect(url_for('index'))
    else:
        return redirect(url_for('my_reviews'))

if __name__ == '__main__':
    # Принудительная инициализация базы данных при запуске
    with app.app_context():
        init_db()
    
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
