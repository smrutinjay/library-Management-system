import os
import uuid
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message
from threading import Thread
# import pandas as pd # Moved to lazy import

# Configuration
app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-prod'

# Vercel filesystem is read-only except /tmp
if os.environ.get('VERCEL'):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/library.db'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///library.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
# Email Config (Console Backend for testing - Prints to terminal)
app.config['MAIL_SERVER'] = 'smtp.gmail.com' # Placeholder
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com' # Replace in Prod
app.config['MAIL_PASSWORD'] = 'your-password' # Replace in Prod
app.config['MAIL_DEFAULT_SENDER'] = 'library@example.com'
app.config['MAIL_BACKEND'] = 'flask_mail.backends.console.Mail' # Log to console for now

mail = Mail(app)
db = SQLAlchemy(app)

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Error sending email: {e}")

def send_email(subject, recipient, body):
    msg = Message(subject, recipients=[recipient])
    msg.body = body
    # Threading to avoid blocking response
    Thread(target=send_async_email, args=(app, msg)).start()
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student') # 'admin' or 'student'
    full_name = db.Column(db.String(100))
    dob = db.Column(db.Date)
    registration_number = db.Column(db.String(20), unique=True)
    section = db.Column(db.String(10))
    semester = db.Column(db.Integer)
    photo_filename = db.Column(db.String(100))
    is_blocked = db.Column(db.Boolean, default=False)
    mobile_number = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    isbn = db.Column(db.String(20), unique=True, nullable=False)
    category = db.Column(db.String(50))
    quantity = db.Column(db.Integer, default=1)
    available = db.Column(db.Integer, default=1)
    misplaced = db.Column(db.Integer, default=0)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    issue_date = db.Column(db.DateTime, default=datetime.utcnow)
    return_date = db.Column(db.DateTime) # Actual return date
    due_date = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default='issued') # 'issued', 'returned'
    fine_paid = db.Column(db.Boolean, default=False)
    payment_id = db.Column(db.String(50))

    user = db.relationship('User', backref=db.backref('transactions', lazy=True))
    book = db.relationship('Book', backref=db.backref('transactions', lazy=True))

    @property
    def penalty(self):
        end_date = self.return_date if self.return_date else datetime.utcnow()
        if end_date > self.due_date:
            delta = end_date - self.due_date
            return delta.days * 10
        return 0

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            if user.is_blocked:
                flash('Your account has been blocked. Please contact admin.', 'error')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth.html', mode='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        reg_no = request.form.get('reg_no')
        dob_str = request.form.get('dob')
        section = request.form.get('section') # Check regex client-side or here
        semester = request.form.get('semester')
        mobile_number = request.form.get('mobile_number')
        role = request.form.get('role', 'student') 
        
        # Photo Upload
        photo = request.files.get('photo')
        photo_filename = None
        if photo:
            if not photo.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                flash('Invalid photo format. Please use PNG, JPG, or JPEG.', 'error')
                return redirect(request.url)
                
            filename = secure_filename(photo.filename)
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            photo_filename = filename

        # Date conversion
        dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None

        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
        elif reg_no and User.query.filter_by(registration_number=reg_no).first():
            flash('Registration Number already exists', 'error')
        else:
            new_user = User(
                username=username, 
                email=email,
                role=role, 
                full_name=full_name,
                registration_number=reg_no,
                dob=dob,
                section=section,
                semester=semester,
                photo_filename=photo_filename,
                mobile_number=mobile_number
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            
            # Send Welcome Email
            send_email('Welcome to Library System', email, 
                      f"Hi {full_name},\n\nYour account has been created successfully.\nUsername: {username}\n\nHappy Reading!")
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
    return render_template('auth.html', mode='register')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- Admin Routes ---

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        return redirect(url_for('student_dashboard'))
        
    total_books = Book.query.count()
    active_loans = Transaction.query.filter_by(status='issued').count()
    # Simple overdue check: issued items where due_date < now
    overdue_transactions = Transaction.query.filter(Transaction.status=='issued', Transaction.due_date < datetime.utcnow()).all()
    overdue_count = len(overdue_transactions)
    
    total_penalty = sum(t.penalty for t in overdue_transactions)
    
    recent_transactions = Transaction.query.order_by(Transaction.issue_date.desc()).limit(5).all()
    
    return render_template('admin_dashboard.html', 
                           total_books=total_books, 
                           active_loans=active_loans, 
                           overdue=overdue_count,
                           total_penalty=total_penalty,
                           recent_transactions=recent_transactions)

@app.route('/admin/users')
@login_required
def admin_users():
    if current_user.role != 'admin':
        abort(403)
        
    status_filter = request.args.get('status', 'all')
    
    if status_filter == 'blocked':
        users = User.query.filter_by(is_blocked=True).all()
    elif status_filter == 'active':
        users = User.query.filter_by(is_blocked=False).all()
    else:
        users = User.query.all()
        
    return render_template('users.html', users=users, current_filter=status_filter)

@app.route('/admin/user/toggle_block/<int:user_id>', methods=['POST'])
@login_required
def toggle_block_user(user_id):
    if current_user.role != 'admin':
        abort(403)
        
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot block yourself.', 'error')
    else:
        user.is_blocked = not user.is_blocked
        db.session.commit()
        status = 'blocked' if user.is_blocked else 'active'
        flash(f'User {user.username} is now {status}.', 'success')
        
    return redirect(url_for('admin_users'))

@app.route('/admin/student_search', methods=['GET', 'POST'])
@login_required
def student_search():
    if current_user.role != 'admin':
        abort(403)
    
    found_user = None
    if request.method == 'POST':
        query = request.form.get('query')
        # Search by Username, Full Name (exact), or Reg No
        found_user = User.query.filter(
            (User.username == query) | 
            (User.registration_number == query) |
            (User.full_name == query)
        ).first()
        if not found_user:
            flash('No student found with those details.', 'error')
            
    return render_template('student_search.html', user=found_user)

@app.route('/admin/transactions')
@login_required
def admin_transactions():
    if current_user.role != 'admin':
        abort(403)
        
    filter_type = request.args.get('filter')
    transactions = []
    
    if filter_type == 'overdue':
        transactions = Transaction.query.filter(
            Transaction.status == 'issued',
            Transaction.due_date < datetime.utcnow()
        ).all()
        title = "Overdue Transactions"
    else:
        transactions = Transaction.query.all()
        title = "All Transactions"
        
    return render_template('transactions.html', transactions=transactions, title=title)

@app.route('/admin/payments')
@login_required
def admin_payments():
    if current_user.role != 'admin':
        abort(403)
    
    # Show transactions where fine is paid
    paid_transactions = Transaction.query.filter_by(fine_paid=True).order_by(Transaction.return_date.desc()).all()
    
    return render_template('admin_payments.html', payments=paid_transactions)

@app.route('/admin/books', methods=['GET', 'POST'])
@login_required
def manage_books():
    if current_user.role != 'admin':
        abort(403)
        
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'add':
            title = request.form.get('title')
            author = request.form.get('author')
            isbn = request.form.get('isbn')
            category = request.form.get('category')
            quantity = int(request.form.get('quantity'))
            
            # Check if book exists
            existing_book = Book.query.filter_by(isbn=isbn).first()
            if existing_book:
                flash(f'Book with ISBN {isbn} already exists.', 'error')
            else:
                new_book = Book(title=title, author=author, isbn=isbn, category=category, quantity=quantity, available=quantity)
                db.session.add(new_book)
                db.session.commit()
                flash('Book added successfully!', 'success')
                
        elif action == 'delete':
            book_id = request.form.get('book_id')
            book = Book.query.get(book_id)
            if book:
                db.session.delete(book)
                db.session.commit()
                flash('Book deleted successfully!', 'success')
            else:
                flash('Book not found.', 'error')
                
        return redirect(url_for('manage_books'))
        
    books = Book.query.all()
    return render_template('books.html', books=books)

@app.route('/admin/issue', methods=['POST'])
@login_required
def issue_book():
    if current_user.role != 'admin':
        abort(403)
        
    book_id = request.form.get('book_id')
    student_username = request.form.get('student_username')
    days = int(request.form.get('days', 14))
    
    book = Book.query.get(book_id)
    student = User.query.filter_by(username=student_username, role='student').first()
    
    if not book or not student:
        flash('Invalid book or student.', 'error')
        return redirect(url_for('manage_books'))
        
    if book.available < 1:
        flash('Book is not available.', 'error')
        return redirect(url_for('manage_books'))
        
    # Create transaction
    due_date = datetime.utcnow() + timedelta(days=days)
    transaction = Transaction(user_id=student.id, book_id=book.id, due_date=due_date)
    book.available -= 1
    
    db.session.add(transaction)
    db.session.commit()
    
    # Send Issue Email
    send_email('Book Issued', student.email, 
              f"Hi {student.full_name},\n\nYou have borrowed: {book.title}\nDue Date: {due_date.strftime('%Y-%m-%d')}\n\nPlease return on time to avoid fines.")
              
    flash(f'Book issued to {student.username}.', 'success')
    return redirect(url_for('manage_books'))

@app.route('/admin/return/<int:transaction_id>', methods=['POST'])
@login_required
def return_book_transaction(transaction_id):
    if current_user.role != 'admin':
        abort(403)
        
    transaction = Transaction.query.get_or_404(transaction_id)
    if transaction.status == 'returned':
        flash('Book already returned.', 'info')
        return redirect(url_for('admin_dashboard')) # Or wherever this is called from
        
    transaction.status = 'returned'
    transaction.return_date = datetime.utcnow()
    
    # Calculate penalty immediately specifically if needed for email, 
    # though property does it.
    
    book = Book.query.get(transaction.book_id)
    book.available += 1
    
    db.session.commit()
    
    # Send Return Email
    penalty_msg = f"\nPenalty: ₹{transaction.penalty}" if transaction.penalty > 0 else ""
    send_email('Book Returned', transaction.user.email,
              f"Hi {transaction.user.full_name},\n\nYou have returned: {book.title}\nReturned On: {transaction.return_date.strftime('%Y-%m-%d')}{penalty_msg}\n\nThank you!")
              
    flash('Book returned successfully.', 'success')
    
    # Redirect back to where we came from preferably, for now dashboard or books
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/import_books', methods=['GET', 'POST'])
@login_required
def import_books():
    if current_user.role != 'admin':
        abort(403)
        
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
            
        file = request.files['file']
        
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)
            
        if file and file.filename.endswith('.xlsx'):
            try:
                # Read Excel
                import pandas as pd
                df = pd.read_excel(file)
                
                # Check columns
                required_cols = ['Title', 'Author', 'ISBN', 'Category', 'Total Copies']
                if not all(col in df.columns for col in required_cols):
                    flash(f'Missing columns. Required: {", ".join(required_cols)}', 'error')
                    return redirect(request.url)
                
                count_new = 0
                count_updated = 0
                
                for _, row in df.iterrows():
                    title = str(row['Title']).strip()
                    author = str(row['Author']).strip()
                    isbn = str(row['ISBN']).strip()
                    category = str(row['Category']).strip()
                    try:
                        copies = int(row['Total Copies'])
                    except ValueError:
                        continue # Skip bad rows
                        
                    if not title or copies < 1:
                        continue

                    # Check by ISBN (more reliable) or Title
                    existing_book = Book.query.filter((Book.isbn == isbn) | (Book.title == title)).first()
                    
                    if existing_book:
                        existing_book.quantity += copies
                        existing_book.available += copies
                        count_updated += 1
                    else:
                        new_book = Book(title=title, author=author, isbn=isbn, category=category, quantity=copies, available=copies)
                        db.session.add(new_book)
                        count_new += 1
                
                db.session.commit()
                flash(f'Import successful! Added {count_new} new books, Updated {count_updated} existing books.', 'success')
                return redirect(url_for('manage_books'))
                
            except Exception as e:
                flash(f'Error processing file: {str(e)}', 'error')
                return redirect(request.url)
        else:
            flash('Invalid file type. Please upload an Excel (.xlsx) file.', 'error')
            
    return render_template('import_books.html')

@app.route('/admin/book/misplaced/<int:book_id>', methods=['POST'])
@login_required
def report_misplaced(book_id):
    if current_user.role != 'admin':
        abort(403)
        
    book = Book.query.get_or_404(book_id)
    action = request.form.get('action', 'report')
    count = int(request.form.get('count', 1))
    
    if action == 'report':
        if book.available >= count:
            book.available -= count
            book.misplaced += count
            db.session.commit()
            flash(f'Reported {count} copies of "{book.title}" as misplaced.', 'warning')
        else:
            flash('Cannot report misplaced: Not enough available copies.', 'error')
            
    elif action == 'found':
        if book.misplaced >= count:
            book.misplaced -= count
            book.available += count
            db.session.commit()
            flash(f'Restored {count} copies of "{book.title}" to inventory.', 'success')
        else:
            flash('Cannot restore: Count exceeds misplaced copies.', 'error')
        
    return redirect(url_for('manage_books'))

@app.route('/admin/bulk_delete_books', methods=['GET', 'POST'])
@login_required
def bulk_delete_books():
    if current_user.role != 'admin':
        abort(403)
        
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
            
        file = request.files['file']
        
        if file.filename == '' or not file.filename.endswith('.xlsx'):
            flash('Invalid file. Please upload an Excel (.xlsx) file.', 'error')
            return redirect(request.url)
            
        try:
            df = pd.read_excel(file)
            
            if 'Title' not in df.columns:
                flash('Missing "Title" column in Excel.', 'error')
                return redirect(request.url)
            
            deleted_count = 0
            not_found_count = 0
            
            for title in df['Title']:
                title = str(title).strip()
                if not title: continue
                
                book = Book.query.filter_by(title=title).first()
                if book:
                    # Optional: Check if active loans exist? For now, we force delete as requested.
                    # Note: This might cascade delete transactions depending on DB setup, 
                    # but current setup might leave orphaned transactions or error. 
                    # We will assume admin knows what they are doing for "Bulk Delete".
                    db.session.delete(book)
                    deleted_count += 1
                else:
                    not_found_count += 1
            
            db.session.commit()
            flash(f'Bulk Delete Complete: Deleted {deleted_count} books. {not_found_count} not found.', 'info')
            return redirect(url_for('manage_books'))
            
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('bulk_delete.html')

# --- Student Routes ---

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
        
    my_loans = Transaction.query.filter_by(user_id=current_user.id, status='issued').all()
    # Calculate penalty only for issued books here. Payable penalties are handled in Payments page
    # But dashboard alert should probably show total liability (Active + Unpaid Returned)
    all_loans = Transaction.query.filter_by(user_id=current_user.id).all()
    my_penalty = sum(t.penalty for t in all_loans if t.penalty > 0 and not t.fine_paid)
    
    # Analytics
    total_books_read = len([t for t in all_loans if t.status == 'returned'])
    total_penalties_incurred = sum(t.penalty for t in all_loans)
    
    # Favorite Genre Logic
    from collections import Counter
    genres = []
    for t in all_loans:
        book = Book.query.get(t.book_id)
        if book and book.category:
            genres.append(book.category)
    
    favorite_genre = "N/A"
    if genres:
        favorite_genre = Counter(genres).most_common(1)[0][0]
    
    books = Book.query.all()
    
    return render_template('student_dashboard.html', 
                           books=books, 
                           my_loans=my_loans, 
                           my_penalty=my_penalty,
                           analytics={
                               'read': total_books_read,
                               'penalties': total_penalties_incurred,
                               'genre': favorite_genre
                           })

@app.route('/student/history')
@login_required
def student_history():
    if current_user.role != 'student':
        abort(403)
    
    history = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.issue_date.desc()).all()
    return render_template('student_history.html', history=history)

@app.route('/student/payments', methods=['GET', 'POST'])
@login_required
def student_payments():
    if current_user.role != 'student':
        abort(403)
        
    if request.method == 'POST':
        transaction_id = request.form.get('transaction_id')
        transaction = Transaction.query.get(transaction_id)
        
        if transaction and transaction.user_id == current_user.id and not transaction.fine_paid:
            transaction.fine_paid = True
            transaction.payment_id = f"TXN-{str(uuid.uuid4())[:8].upper()}"
            db.session.commit()
            flash(f'Payment successful! Transaction ID: {transaction.payment_id}', 'success')
        
        return redirect(url_for('student_payments'))
    
    # Payable: Returned but fine not paid AND fine > 0
    # Note: We need to filter in Python because penalty is a property
    all_transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    
    payable_fines = [t for t in all_transactions if t.status == 'returned' and t.penalty > 0 and not t.fine_paid]
    estimated_fines = [t for t in all_transactions if t.status == 'issued' and t.penalty > 0]
    
    return render_template('student_payments.html', payable=payable_fines, estimated=estimated_fines)


# --- Initialize DB ---
# --- Initialize DB Lazily ---
def init_db():
    try:
        db.create_all()
        # Create default admin if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@library.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
        # print("Database initialized successfully.") 
    except Exception as e:
        print(f"Error initializing database: {e}")

@app.before_request
def initialize_database():
    if not getattr(app, 'db_initialized', False):
        init_db()
        app.db_initialized = True

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)
